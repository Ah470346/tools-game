import pytest
import numpy as np
import cv2
from vision.label_detector import (
    LabelBox,
    detect_labels,
    is_label_highlighted,
    get_item_click_position,
    split_stacked_label,
    label_change_scores,
    find_highlighted_label,
)

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


def test_split_stacked_label_short_box_unchanged():
    gray = np.full((50, 50), 60, dtype=np.uint8)
    box = LabelBox(0, 0, 50, 14)
    config = {"single_row_max_height_px": 22}
    result = split_stacked_label(gray, box, config)
    assert result == [box]


def test_split_stacked_label_splits_two_stacked_rows():
    # Two label rows whose dark backgrounds overlap (no gap between them),
    # but whose bright text bands are visually separated.
    box = LabelBox(50, 80, 150, 27)
    gray = np.full((200, 300), 200, dtype=np.uint8)
    gray[80:107, 50:200] = 60  # combined dark background of both stacked labels
    gray[85:91, 55:190] = 220  # text row A
    gray[96:102, 55:190] = 220  # text row B

    config = {
        "min_brightness_bright": 150,
        "expected_row_height_px": 16,
        "min_label_height": 6,
        "max_stack_rows": 5,
        "single_row_max_height_px": 18,
    }
    result = split_stacked_label(gray, box, config)

    assert len(result) == 2
    result.sort(key=lambda b: b.y)
    assert result[0].y < result[1].y
    # Rows should not still be merged into one span
    assert result[1].y >= result[0].y + result[0].h - 2


def test_detect_labels_splits_stacked_overlapping_labels():
    # Bright ground (e.g. sandy map), with a dark semi-transparent label band
    # containing bright text -- detection must key off the dark band
    # confirmed by bright text inside it, not off bright text alone.
    frame = np.full((200, 300, 3), 200, dtype=np.uint8)
    # Combined dark background of both stacked labels (no gap between them).
    frame[80:107, 50:200] = 60
    # Two stacked labels' text rows, separated by a 2px gap small enough for
    # the closing morphology to bridge the dark band into one contour
    # (mirrors overlapping semi-transparent label backgrounds).
    cv2.rectangle(frame, (55, 85), (190, 94), (220, 220, 220), -1)  # text row A
    cv2.rectangle(frame, (55, 96), (190, 105), (220, 220, 220), -1)  # text row B

    config = {
        "min_brightness_dark": 0,
        "max_brightness_dark": 110,
        "min_brightness_bright": 150,
        "min_text_ratio": 0.02,
        "min_label_width": 20,
        "min_label_height": 6,
        "max_label_height": 20,
        "row_split_enabled": True,
        "single_row_max_height_px": 18,
        "expected_row_height_px": 16,
        "max_stack_rows": 5,
        "dedupe_iou": 0.85,
    }
    labels = detect_labels(frame, config)

    assert len(labels) == 2
    labels.sort(key=lambda b: b.center_y)
    assert labels[0].center_y < labels[1].center_y
    assert labels[0].h < 20 and labels[1].h < 20


def test_detect_labels_single_label_not_split():
    frame = np.full((200, 300, 3), 200, dtype=np.uint8)
    frame[83:96, 50:200] = 60  # dark label band
    cv2.rectangle(frame, (55, 86), (190, 92), (220, 220, 220), -1)  # text row

    config = {
        "min_brightness_dark": 0,
        "max_brightness_dark": 110,
        "min_brightness_bright": 150,
        "min_text_ratio": 0.02,
        "min_label_width": 20,
        "min_label_height": 6,
        "max_label_height": 20,
        "row_split_enabled": True,
        "single_row_max_height_px": 18,
        "expected_row_height_px": 16,
        "max_stack_rows": 5,
        "dedupe_iou": 0.85,
    }
    labels = detect_labels(frame, config)
    assert len(labels) == 1


def test_label_change_scores_identifies_correct_label():
    frame_before = np.full((100, 100, 3), 60, dtype=np.uint8)
    frame_after = frame_before.copy()
    box0 = LabelBox(10, 10, 20, 10)
    box1 = LabelBox(10, 40, 20, 10)
    box2 = LabelBox(10, 70, 20, 10)
    frame_after[40:50, 10:30] = 200  # only box1's ROI brightens

    config = {"brighten_delta": 30, "min_changed_ratio": 0.04, "argmax_margin": 1.5}
    scores = label_change_scores(frame_before, frame_after, [box0, box1, box2], config)
    assert scores[1] > scores[0]
    assert scores[1] > scores[2]

    idx = find_highlighted_label(frame_before, frame_after, [box0, box1, box2], config)
    assert idx == 1


def test_find_highlighted_label_none_on_uniform_brighten():
    # Simulates a global scene flicker/animation: every label's ROI brightens
    # equally, so no single label should be reported as "the" highlighted one.
    frame_before = np.full((100, 100, 3), 60, dtype=np.uint8)
    frame_after = np.full((100, 100, 3), 200, dtype=np.uint8)
    box0 = LabelBox(10, 10, 20, 10)
    box1 = LabelBox(10, 40, 20, 10)

    config = {"brighten_delta": 30, "min_changed_ratio": 0.04, "argmax_margin": 1.5}
    idx = find_highlighted_label(frame_before, frame_after, [box0, box1], config)
    assert idx is None


def test_find_highlighted_label_none_on_no_change():
    frame = np.full((100, 100, 3), 60, dtype=np.uint8)
    box0 = LabelBox(10, 10, 20, 10)
    config = {"brighten_delta": 30, "min_changed_ratio": 0.04}
    idx = find_highlighted_label(frame, frame, [box0], config)
    assert idx is None
