import pytest
import numpy as np
from vision.label_detector import LabelBox, detect_labels, is_label_highlighted, get_item_click_position

def test_label_box():
    box = LabelBox(10, 20, 100, 30)
    assert box.center_x == 60
    assert box.center_y == 35
    assert box.bottom_y == 50

def test_detect_labels_empty():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    config = {}
    labels = detect_labels(frame, config)
    assert len(labels) == 0

def test_get_item_click_position():
    box = LabelBox(100, 100, 50, 20)
    click_x, click_y = get_item_click_position(box, 800, 600, y_offset=10)
    # center_x = 125, bottom_y = 120 + 10 = 130
    assert click_x == 125 / 800
    assert click_y == 130 / 600

def test_is_label_highlighted():
    config = {"min_brightness_bright": 150}
    # Create dark frame
    frame_before = np.full((100, 100, 3), 50, dtype=np.uint8)
    # Create bright frame
    frame_after = np.full((100, 100, 3), 200, dtype=np.uint8)
    
    box = LabelBox(10, 10, 20, 20)
    
    # Check that difference is detected
    is_hl = is_label_highlighted(frame_before, frame_after, box, config)
    assert is_hl is True
    
    # Check that identical frames don't trigger
    is_hl_false = is_label_highlighted(frame_before, frame_before, box, config)
    assert is_hl_false is False
