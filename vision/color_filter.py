"""
vision/color_filter.py

Extracts items or targets based on pixel color thresholds (e.g. rare items on the ground)
and performs template matching (e.g. gemstones, inventory templates).
"""

import numpy as np
from typing import List, Tuple


def find_color_regions(frame: np.ndarray, lower_bgr: Tuple[int, int, int], upper_bgr: Tuple[int, int, int]) -> List[Tuple[int, int, int, int]]:
    """
    Finds bounding boxes of regions matching specific color thresholds.

    Args:
        frame (np.ndarray): The source image frame.
        lower_bgr (Tuple[int, int, int]): Lower BGR boundaries.
        upper_bgr (Tuple[int, int, int]): Upper BGR boundaries.

    Returns:
        List[Tuple[int, int, int, int]]: List of (x, y, width, height) boxes.
    """
    # Placeholder implementation
    return []


def template_match(frame: np.ndarray, template: np.ndarray, threshold: float = 0.8) -> List[Tuple[int, int]]:
    """
    Locates positions of standard template images inside a source frame.

    Args:
        frame (np.ndarray): The source image frame.
        template (np.ndarray): Template image.
        threshold (float): Match correlation threshold.

    Returns:
        List[Tuple[int, int]]: Center positions of matches.
    """
    return []


def find_item_labels(frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """
    Finds bounding boxes of candidate rectangular item name labels on the screen.

    Args:
        frame (np.ndarray): BGR image frame.

    Returns:
        List[Tuple[int, int, int, int]]: List of (x, y, width, height) bounding boxes.
    """
    if frame is None or frame.size == 0:
        return []

    import cv2

    # 1. Preprocessing: Convert to grayscale and blur to remove noise
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.bilateralFilter(gray, 9, 75, 75)

    # 2. Canny Edge Detection to outline rectangular label borders
    edges = cv2.Canny(blurred, 50, 150)

    # 3. Find external contours representing closed shapes
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        # 4. Filter by typical item text box dimensions on 1024x768 / 1920x1080 screens:
        # Width: 30 to 250px, Height: 10 to 35px, Aspect Ratio: 2.0 to 12.0
        # Exclude HUD / UI elements by keeping y within gameplay area (15% to 80% screen height)
        height_limit = frame.shape[0]
        if 30 <= w <= 250 and 10 <= h <= 35:
            aspect_ratio = float(w) / float(h)
            if 2.0 <= aspect_ratio <= 12.0:
                if 0.15 * height_limit <= y <= 0.8 * height_limit:
                    boxes.append((x, y, w, h))

    # 5. Non-Maximum Suppression (NMS) to eliminate duplicate/nested overlapping boxes
    cleaned_boxes = []
    boxes = sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)  # Sort by area descending

    for box in boxes:
        overlap = False
        for c_box in cleaned_boxes:
            # Calculate intersection region
            ix1 = max(box[0], c_box[0])
            iy1 = max(box[1], c_box[1])
            ix2 = min(box[0] + box[2], c_box[0] + c_box[2])
            iy2 = min(box[1] + box[3], c_box[1] + c_box[3])

            inter_w = max(0, ix2 - ix1)
            inter_h = max(0, iy2 - iy1)
            inter_area = inter_w * inter_h
            box_area = box[2] * box[3]

            # If overlap > 50% of candidate box area, discard it
            if inter_area > 0.5 * box_area:
                overlap = True
                break
        if not overlap:
            cleaned_boxes.append(box)

    return cleaned_boxes

