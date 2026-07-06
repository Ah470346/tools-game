"""
tests/test_loot.py

Unit tests for vision/color_filter.py (find_item_labels) and features/loot.py (LootCollector).
"""

import sys
import os
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vision.color_filter import find_item_labels
from features.loot import LootCollector
from backends.mock_backends import MockCapture, MockInput


def test_find_item_labels_dummy() -> None:
    # 1. Test empty frame returns empty list
    assert find_item_labels(None) == []
    assert find_item_labels(np.zeros((0, 0, 3), dtype=np.uint8)) == []

    # 2. Test draw dummy rectangles and verify they are detected
    # Image size 800x600
    frame = np.zeros((600, 800, 3), dtype=np.uint8)
    
    # Draw two white rectangles (simulating text box labels)
    # Box 1: x=100, y=100, w=120, h=20
    cv2 = sys.modules.get("cv2")
    if cv2 is None:
        import cv2
    cv2.rectangle(frame, (100, 100), (220, 120), (255, 255, 255), -1)
    
    # Box 2: x=300, y=200, w=80, h=25
    cv2.rectangle(frame, (300, 200), (380, 225), (255, 255, 255), -1)

    boxes = find_item_labels(frame)
    
    # Should find at least the two generated candidate rectangles
    assert len(boxes) >= 2
    
    # Verify coordinates roughly match our drawn boxes
    box_coords = [(b[0], b[1], b[2], b[3]) for b in boxes]
    # Check if a box close to (100, 100, 120, 20) is found
    match1 = any(abs(b[0] - 100) < 5 and abs(b[1] - 100) < 5 and abs(b[2] - 120) < 5 and abs(b[3] - 20) < 5 for b in box_coords)
    # Check if a box close to (300, 200, 80, 25) is found
    match2 = any(abs(b[0] - 300) < 5 and abs(b[1] - 200) < 5 and abs(b[2] - 80) < 5 and abs(b[3] - 25) < 5 for b in box_coords)
    
    assert match1 is True
    assert match2 is True


@pytest.fixture
def loot_config() -> dict:
    return {
        "enabled": True,
        "show_names_key": "a",
        "whitelist": ["Celesto", "Devine", "Gold"],
        "blacklist": ["potion", "weak"]
    }


def test_loot_collector_matching(loot_config) -> None:
    cap = MockCapture()
    inp = MockInput()
    collector = LootCollector(capture=cap, simulator=inp, config=loot_config)

    # 1. Matches whitelist cases
    assert collector._matches_whitelist("Celesto Sheltom") is True
    assert collector._matches_whitelist("gold [500]") is True
    assert collector._matches_whitelist("Perfect Devine") is True

    # 2. Ignored cases (not in whitelist)
    assert collector._matches_whitelist("Iron Sword") is False

    # 3. Ignored cases (matches blacklist)
    assert collector._matches_whitelist("Weak Celesto potion") is False
    assert collector._matches_whitelist("HP potion") is False


@patch("features.loot.find_item_labels")
def test_loot_collector_cycle(mock_find_labels, loot_config) -> None:
    # Set up mock frame labels: one box at x=100, y=100, w=100, h=20
    mock_find_labels.return_value = [(100, 100, 100, 20)]

    # Mock OCR reader
    mock_ocr = MagicMock()
    mock_ocr.enabled = True
    # First candidate is "Celesto Sheltom" (whitelisted)
    mock_ocr.read_text.return_value = "Celesto Sheltom"

    # Create dummy BGR frame of size 1000x1000
    frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
    cap = MockCapture()
    cap.grab_frame = MagicMock(return_value=frame)
    inp = MockInput()

    collector = LootCollector(capture=cap, simulator=inp, config=loot_config)
    collector.ocr_reader = mock_ocr

    # Run cycle
    res = collector.run_loot_cycle()
    assert res is True

    # Check key logs:
    # 1. Holding 'a' down: key('a', 'down')
    # 2. Releasing 'a' up: key('a', 'up')
    # 3. Click at center of (100, 100, 100, 20) -> xc = 150, yc = 110. In 1000x1000, xc_norm = 0.15, yc_norm = 0.11
    assert ("key", "a", "down") in inp.log
    assert ("key", "a", "up") in inp.log
    assert ("click", 0.15, 0.11, "left") in inp.log
