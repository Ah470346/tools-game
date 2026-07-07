"""
vision/label_detector.py

Detects item labels on the ground and verifies if they are highlighted (hovered).
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple

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
        if min_w <= w <= 400 and min_h <= h <= max_h:
            aspect_ratio = float(w) / float(h)
            if 1.5 <= aspect_ratio <= 20.0:
                # Restrict to gameplay area (avoiding extreme edges for UI)
                if (0.05 * height_limit <= y <= 0.95 * height_limit) and (0.05 * width_limit <= x <= 0.95 * width_limit):
                    boxes.append(LabelBox(x, y, w, h))
                    
    # Non-Maximum Suppression to remove overlapping boxes
    boxes.sort(key=lambda b: b.w * b.h, reverse=True)
    cleaned_boxes = []
    
    for box in boxes:
        overlap = False
        for c_box in cleaned_boxes:
            ix1 = max(box.x, c_box.x)
            iy1 = max(box.y, c_box.y)
            ix2 = min(box.x + box.w, c_box.x + c_box.w)
            iy2 = min(box.y + box.h, c_box.y + c_box.h)
            
            inter_w = max(0, ix2 - ix1)
            inter_h = max(0, iy2 - iy1)
            
            if inter_w > 0 and inter_h > 0:
                inter_area = inter_w * inter_h
                box_area = box.w * box.h
                if inter_area > 0.5 * box_area:
                    overlap = True
                    break
        if not overlap:
            cleaned_boxes.append(box)
            
    return cleaned_boxes

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

def get_item_click_position(label: LabelBox, frame_width: int, frame_height: int, y_offset: int = 20) -> Tuple[float, float]:
    """
    Calculates the normalized (x, y) coordinates to click the 3D item under the label.
    """
    click_x = label.center_x
    click_y = label.bottom_y + y_offset
    
    norm_x = click_x / frame_width
    norm_y = click_y / frame_height
    
    return max(0.0, min(1.0, norm_x)), max(0.0, min(1.0, norm_y))
