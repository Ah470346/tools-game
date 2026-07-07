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
from vision.label_detector import LabelBox
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
    # Box 1: x=300, y=200, w=120, h=20
    cv2 = sys.modules.get("cv2")
    if cv2 is None:
        import cv2
    cv2.rectangle(frame, (300, 200), (420, 220), (255, 255, 255), -1)

    # Box 2: x=400, y=250, w=80, h=25
    cv2.rectangle(frame, (400, 250), (480, 275), (255, 255, 255), -1)

    boxes = find_item_labels(frame)

    # Should find at least the two generated candidate rectangles
    assert len(boxes) >= 2

    # Verify coordinates roughly match our drawn boxes
    box_coords = [(b[0], b[1], b[2], b[3]) for b in boxes]
    # Check if a box close to (300, 200, 120, 20) is found
    match1 = any(abs(b[0] - 300) < 5 and abs(b[1] - 200) < 5 and abs(b[2] - 120) < 5 and abs(b[3] - 20) < 5 for b in box_coords)
    # Check if a box close to (400, 250, 80, 25) is found
    match2 = any(abs(b[0] - 400) < 5 and abs(b[1] - 250) < 5 and abs(b[2] - 80) < 5 and abs(b[3] - 25) < 5 for b in box_coords)

    assert match1 is True
    assert match2 is True


@pytest.fixture(autouse=True)
def fast_delays(monkeypatch):
    """Loot cycles sleep via core.humanizer between every probe/pickup; make
    tests fast and deterministic by collapsing all humanized delays to 0."""
    monkeypatch.setattr("features.loot.humanizer.get_random_delay", lambda a, b=None: 0.0)


@pytest.fixture
def loot_collector() -> LootCollector:
    cap = MockCapture()
    inp = MockInput()
    collector = LootCollector(capture=cap, simulator=inp, config={"enabled": True, "mode": "whitelist"})
    # Whitelist/blacklist are normally loaded from config/loot_whitelist.json;
    # override directly here for deterministic, isolated tests.
    collector.whitelist = ["celesto", "devine", "gold"]
    collector.blacklist = ["potion", "weak"]
    return collector


def test_loot_collector_matching(loot_collector) -> None:
    # 1. Matches whitelist cases
    assert loot_collector._matches_whitelist("Celesto Sheltom") is True
    assert loot_collector._matches_whitelist("gold [500]") is True
    assert loot_collector._matches_whitelist("Perfect Devine") is True

    # 2. Ignored cases (not in whitelist)
    assert loot_collector._matches_whitelist("Iron Sword") is False

    # 3. Ignored cases (matches blacklist)
    assert loot_collector._matches_whitelist("Weak Celesto potion") is False
    assert loot_collector._matches_whitelist("HP potion") is False


def test_run_loot_cycle_clicks_verified_probe_point_not_label_geometry(loot_collector) -> None:
    """
    Two overlapping labels: the first OCRs to a blacklisted item up front and
    must never be probed; the second is occluded (OCR fails) until a hover
    probe highlights it, at which point re-OCR reveals a whitelisted item.
    The click must land on the actual probe point that triggered the
    highlight, not on the label's fixed geometric offset.
    """
    label_trash = LabelBox(50, 80, 150, 12)
    label_target = LabelBox(50, 90, 150, 12)

    dummy_frame = np.zeros((300, 400, 3), dtype=np.uint8)
    loot_collector.capture.grab_frame = MagicMock(return_value=dummy_frame)

    with patch("features.loot.detect_labels", return_value=[label_trash, label_target]), \
         patch("features.loot.find_highlighted_label", return_value=1) as mock_find, \
         patch.object(loot_collector.ocr_reader, "read_text") as mock_ocr:

        # Classify phase (in label order): label_trash -> blacklisted text,
        # label_target -> OCR fails (occluded). Then, once the probe
        # highlights label_target (index 1), it's re-OCR'd from the
        # brightened after-frame and comes back as a whitelisted item.
        mock_ocr.side_effect = ["Weak Potion", None, "87 Gold"]

        result = loot_collector.run_loot_cycle()

    assert result is True
    assert mock_ocr.call_count == 3
    assert mock_find.called

    move_calls = [c for c in loot_collector.input.log if c[0] == "move"]
    click_calls = [c for c in loot_collector.input.log if c[0] == "click"]
    assert len(click_calls) == 1
    assert len(move_calls) == 1  # first probe point already highlighted -> no further probing needed

    _, move_x, move_y = move_calls[0]
    _, click_x, click_y, button = click_calls[0]
    assert (move_x, move_y) == (click_x, click_y)
    assert button == "left"

    assert ("key", "a", "down") in loot_collector.input.log
    assert ("key", "a", "up") in loot_collector.input.log


def test_run_loot_cycle_no_highlight_returns_false_without_clicking(loot_collector) -> None:
    label = LabelBox(50, 80, 150, 12)
    dummy_frame = np.zeros((300, 400, 3), dtype=np.uint8)
    loot_collector.capture.grab_frame = MagicMock(return_value=dummy_frame)
    loot_collector.mode = "all"  # skip OCR classification entirely

    with patch("features.loot.detect_labels", return_value=[label]), \
         patch("features.loot.find_highlighted_label", return_value=None):
        result = loot_collector.run_loot_cycle()

    assert result is False
    click_calls = [c for c in loot_collector.input.log if c[0] == "click"]
    assert click_calls == []
    assert ("key", "a", "down") in loot_collector.input.log
    assert ("key", "a", "up") in loot_collector.input.log


def test_run_loot_cycle_releases_key_on_exception(loot_collector) -> None:
    with patch("features.loot.detect_labels", side_effect=RuntimeError("boom")):
        result = loot_collector.run_loot_cycle()

    assert result is False
    assert ("key", "a", "down") in loot_collector.input.log
    assert ("key", "a", "up") in loot_collector.input.log
