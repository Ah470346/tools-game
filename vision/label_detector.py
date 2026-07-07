"""
vision/label_detector.py

Detects item labels on the ground and verifies if they are highlighted (hovered).
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class LabelBox:
    x: int
    y: int
    w: int
    h: int
    
    @property
    def center_x(self) -> int:
        return self.x + self.w // 2
        
    @property
    def center_y(self) -> int:
        return self.y + self.h // 2
        
    @property
    def bottom_y(self) -> int:
        return self.y + self.h

def split_stacked_label(gray: np.ndarray, box: LabelBox, config: dict) -> List["LabelBox"]:
    """
    Splits a tall blob (multiple item labels stacked/overlapping vertically)
    into individual single-row LabelBoxes.

    Overlapping semi-transparent label backgrounds merge into one blob with
    no dark gap between them, but the bright text lines inside stay visually
    separated, so splitting is done on the row-wise profile of bright
    (text) pixels rather than on the dark background mask.
    """
    single_row_max_h = config.get("single_row_max_height_px", 22)

    if box.h <= single_row_max_h:
        return [box]

    min_bright = config.get("min_brightness_bright", 150)
    roi = gray[box.y:box.y + box.h, box.x:box.x + box.w]
    if roi.size == 0:
        return [box]

    bright_mask = roi > min_bright
    row_counts = bright_mask.sum(axis=1)

    # Rows with (almost) no bright text pixels are gaps between stacked labels.
    is_gap = row_counts <= max(1, int(0.05 * box.w))

    rows: List[Tuple[int, int]] = []  # (start, end) offsets within the box
    row_start = None
    for i, gap in enumerate(is_gap):
        if not gap and row_start is None:
            row_start = i
        elif gap and row_start is not None:
            rows.append((row_start, i))
            row_start = None
    if row_start is not None:
        rows.append((row_start, box.h))

    expected_row_h = config.get("expected_row_height_px", 16)
    min_h = config.get("min_label_height", 8)

    # Merge/expand thin slivers so each row is at least a plausible label height.
    merged_rows: List[Tuple[int, int]] = []
    for start, end in rows:
        if end - start < min_h:
            continue
        merged_rows.append((start, end))

    if len(merged_rows) < 2:
        # No clean valleys found (labels' backgrounds fully overlap) -> fall
        # back to a uniform split by the expected single-row height.
        num_rows = max(1, round(box.h / expected_row_h))
        if num_rows < 2:
            return [box]
        row_h = box.h / num_rows
        merged_rows = [(int(i * row_h), int((i + 1) * row_h)) for i in range(num_rows)]

    max_stack_rows = config.get("max_stack_rows", 5)
    merged_rows = merged_rows[:max_stack_rows]

    split_boxes = []
    for start, end in merged_rows:
        split_boxes.append(LabelBox(box.x, box.y + start, box.w, max(min_h, end - start)))
    return split_boxes


def detect_labels(frame: np.ndarray, config: dict) -> List[LabelBox]:
    """
    Detects semi-transparent dark item labels on the screen.
    """
    if frame is None or frame.size == 0:
        return []

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Extract config values with defaults (relaxed to catch more labels)
    min_dark = config.get("min_brightness_dark", 20)
    max_dark = config.get("max_brightness_dark", 120)
    min_w = config.get("min_label_width", 20)
    min_h = config.get("min_label_height", 8)
    max_h = config.get("max_label_height", 45)
    row_split_enabled = config.get("row_split_enabled", True)
    single_row_max_h = config.get("single_row_max_height_px", 22)
    max_stack_rows = config.get("max_stack_rows", 5)
    dedupe_iou = config.get("dedupe_iou", 0.85)

    # When row splitting is enabled, allow tall blobs (stacked/overlapping
    # labels) through the size filter so they can be split below, instead of
    # discarding them outright.
    max_h_filter = (single_row_max_h * max_stack_rows) if row_split_enabled else max_h

    # Mask for dark regions (the semi-transparent black background of labels)
    mask = cv2.inRange(gray, min_dark, max_dark)

    # Morphological operations to connect text parts and smooth the box
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    height_limit, width_limit = frame.shape[:2]

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        # Filter by size and aspect ratio
        if min_w <= w <= 400 and min_h <= h <= max_h_filter:
            aspect_ratio = float(w) / float(h)
            if 1.5 <= aspect_ratio <= 20.0:
                # Restrict to gameplay area (avoiding extreme edges for UI)
                if (0.05 * height_limit <= y <= 0.95 * height_limit) and (0.05 * width_limit <= x <= 0.95 * width_limit):
                    boxes.append(LabelBox(x, y, w, h))

    if row_split_enabled:
        split_result: List[LabelBox] = []
        for box in boxes:
            split_result.extend(split_stacked_label(gray, box, config))
        boxes = split_result

    # Dedupe only near-identical boxes (same label detected twice), instead
    # of dropping legitimately overlapping labels from stacked items.
    boxes.sort(key=lambda b: b.w * b.h, reverse=True)
    cleaned_boxes: List[LabelBox] = []

    for box in boxes:
        is_dup = False
        box_xyxy = [box.x, box.y, box.x + box.w, box.y + box.h]
        for c_box in cleaned_boxes:
            c_xyxy = [c_box.x, c_box.y, c_box.x + c_box.w, c_box.y + c_box.h]
            if _iou_xyxy(box_xyxy, c_xyxy) > dedupe_iou:
                is_dup = True
                break
        if not is_dup:
            cleaned_boxes.append(box)

    return cleaned_boxes


def _iou_xyxy(box_a: List[float], box_b: List[float]) -> float:
    """IoU of two [x1, y1, x2, y2] boxes in pixel coordinates."""
    ix1 = max(box_a[0], box_b[0])
    iy1 = max(box_a[1], box_b[1])
    ix2 = min(box_a[2], box_b[2])
    iy2 = min(box_a[3], box_b[3])

    inter_w = max(0.0, ix2 - ix1)
    inter_h = max(0.0, iy2 - iy1)
    inter_area = inter_w * inter_h

    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union_area = area_a + area_b - inter_area

    if union_area <= 0.0:
        return 0.0
    return float(inter_area / union_area)

def is_label_highlighted(frame_before: np.ndarray, frame_after: np.ndarray, label: LabelBox, config: dict) -> bool:
    """
    Checks if a label became highlighted (text turned bright white) after hovering.
    """
    if frame_before is None or frame_after is None:
        return False
        
    # Crop the label region from both frames
    # Add a small padding to capture the border
    pad = 2
    h_max, w_max = frame_before.shape[:2]
    y1 = max(0, label.y - pad)
    y2 = min(h_max, label.y + label.h + pad)
    x1 = max(0, label.x - pad)
    x2 = min(w_max, label.x + label.w + pad)
    
    roi_before = frame_before[y1:y2, x1:x2]
    roi_after = frame_after[y1:y2, x1:x2]
    
    gray_before = cv2.cvtColor(roi_before, cv2.COLOR_BGR2GRAY)
    gray_after = cv2.cvtColor(roi_after, cv2.COLOR_BGR2GRAY)
    
    # Compute absolute difference between before and after frames
    diff = cv2.absdiff(roi_before, roi_after)
    diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    
    # Threshold the difference to ignore slight video compression/noise artifacts
    _, thresh_diff = cv2.threshold(diff_gray, 25, 255, cv2.THRESH_BINARY)
    
    changed_pixels = cv2.countNonZero(thresh_diff)
    
    # If a significant number of pixels changed (e.g., text turned yellow or got a border), it's highlighted
    return changed_pixels > 20


def _label_change_score(frame_before: np.ndarray, frame_after: np.ndarray, label: LabelBox, brighten_delta: int) -> float:
    """
    Fraction of pixels within a label's ROI that got brighter by more than
    ``brighten_delta``. Signed brightening (not absdiff) so darkening noise
    and camera/monster motion count for less than an actual highlight.
    """
    pad = 2
    h_max, w_max = frame_before.shape[:2]
    y1 = max(0, label.y - pad)
    y2 = min(h_max, label.y + label.h + pad)
    x1 = max(0, label.x - pad)
    x2 = min(w_max, label.x + label.w + pad)

    roi_before = frame_before[y1:y2, x1:x2]
    roi_after = frame_after[y1:y2, x1:x2]
    if roi_before.size == 0 or roi_after.size == 0:
        return 0.0

    gray_before = cv2.cvtColor(roi_before, cv2.COLOR_BGR2GRAY).astype(np.int16)
    gray_after = cv2.cvtColor(roi_after, cv2.COLOR_BGR2GRAY).astype(np.int16)

    brightened = (gray_after - gray_before) > brighten_delta
    return float(np.count_nonzero(brightened)) / float(brightened.size)


def label_change_scores(frame_before: np.ndarray, frame_after: np.ndarray, labels: List[LabelBox], config: dict) -> List[float]:
    """
    Computes a per-label brightening score between two frames, one per label
    in ``labels``. Used to determine which of several (possibly overlapping)
    labels reacted to a hover, rather than just whether a single label changed.
    """
    if frame_before is None or frame_after is None:
        return [0.0] * len(labels)

    brighten_delta = config.get("brighten_delta", 30)
    return [_label_change_score(frame_before, frame_after, label, brighten_delta) for label in labels]


def find_highlighted_label(frame_before: np.ndarray, frame_after: np.ndarray, labels: List[LabelBox], config: dict) -> Optional[int]:
    """
    Finds the index (in ``labels``) of the single label that highlighted
    (brightened) after a hover, if any.

    Returns None when no label crosses ``min_changed_ratio``, or when the
    top two candidates are too close to call (guards against global scene
    flicker/animation triggering a false positive on an arbitrary label).
    """
    if not labels:
        return None

    scores = label_change_scores(frame_before, frame_after, labels, config)
    min_changed_ratio = config.get("min_changed_ratio", 0.04)
    argmax_margin = config.get("argmax_margin", 1.5)

    best_idx = int(np.argmax(scores))
    best_score = scores[best_idx]
    if best_score < min_changed_ratio:
        return None

    other_scores = [s for i, s in enumerate(scores) if i != best_idx]
    second_best = max(other_scores) if other_scores else 0.0
    if second_best > 0.0 and best_score < argmax_margin * second_best:
        return None

    return best_idx


def get_item_click_position(label: LabelBox, frame_width: int, frame_height: int, y_offset: int = 20) -> Tuple[float, float]:
    """
    Calculates the normalized (x, y) coordinates to click the 3D item under the label.
    """
    click_x = label.center_x
    click_y = label.bottom_y + y_offset
    
    norm_x = click_x / frame_width
    norm_y = click_y / frame_height
    
    return max(0.0, min(1.0, norm_x)), max(0.0, min(1.0, norm_y))
