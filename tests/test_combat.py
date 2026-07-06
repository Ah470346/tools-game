"""
tests/test_combat.py

Unit tests for features/combat.py using dummy captures and mock inputs.
"""

import time
from typing import Tuple
import numpy as np
import pytest

from backends.capture_base import ICaptureBackend
from backends.mock_backends import MockInput
from features.combat import CombatController


class DummyCapture(ICaptureBackend):
    """Simple capture backend that returns a configurable frame."""

    def __init__(self, target_color: Tuple[int, int, int]) -> None:
        self.target_color = target_color

    def grab_frame(self) -> np.ndarray:
        # Create a frame of size 100x100
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        
        # Set target check pixel: check_pixel is [0.5, 0.05] (x=50, y=5)
        # px = int(0.5 * 99) = 49, py = int(0.05 * 99) = 4
        frame[4, 49] = self.target_color
        return frame


@pytest.fixture
def combat_config() -> dict:
    return {
        "target_source": "tab",
        "tab_key": "space",
        "tab_interval_sec": 0.5,
        "left_click": {
            "enabled": True,
            "interval_sec": 0.3
        },
        "right_click": {
            "enabled": True,
            "interval_sec": 0.4
        },
        "click_position": [0.5, 0.5],
        "target_check": {
            "enabled": True,
            "check_pixel": [0.5, 0.05],
            "expected_color_bgr": [0, 0, 180],
            "color_tolerance": 40
        }
    }


def test_combat_has_target(combat_config) -> None:
    # Matching color
    cap_target = DummyCapture((0, 0, 180))
    inp = MockInput()
    ctrl = CombatController(capture=cap_target, simulator=inp, config=combat_config)
    
    frame = cap_target.grab_frame()
    assert ctrl.has_target(frame) is True

    # Mismatch color
    cap_no_target = DummyCapture((0, 0, 0))
    frame_no = cap_no_target.grab_frame()
    assert ctrl.has_target(frame_no) is False


def test_combat_tab_locking(combat_config) -> None:
    # No target present -> should press space
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config)
    
    # 1st cycle: should trigger tab_key
    res1 = ctrl.run_combat_cycle()
    assert res1 is False
    assert inp.log == [("key", "space", "press")]
    
    # Reset input log
    inp.log.clear()
    
    # 2nd cycle immediately: tab targeting should be on cooldown
    res2 = ctrl.run_combat_cycle()
    assert res2 is False
    assert inp.log == []
    
    # Wait for tab interval (0.5s)
    time.sleep(0.6)
    
    res3 = ctrl.run_combat_cycle()
    assert res3 is False
    assert inp.log == [("key", "space", "press")]


def test_combat_click_attacks(combat_config) -> None:
    # Target present -> should click LMB and RMB
    cap = DummyCapture((0, 0, 180))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config)
    
    # 1st cycle: click both
    res1 = ctrl.run_combat_cycle()
    assert res1 is True
    # The order of logs might be LMB then RMB
    assert ("click", 0.5, 0.5, "left") in inp.log
    assert ("click", 0.5, 0.5, "right") in inp.log
    
    inp.log.clear()
    
    # 2nd cycle immediately: both on cooldown
    res2 = ctrl.run_combat_cycle()
    assert res2 is True
    assert inp.log == []
    
    # Wait 0.35s: LMB should fire but not RMB (0.4s cooldown)
    time.sleep(0.35)
    res3 = ctrl.run_combat_cycle()
    assert res3 is True
    assert ("click", 0.5, 0.5, "left") in inp.log
    assert ("click", 0.5, 0.5, "right") not in inp.log


class DummyDetector:
    """Mock detector for testing YOLO targeting."""

    def __init__(self, detections: list) -> None:
        self.detections = detections
        self.detect_calls = 0

    def detect(self, frame: np.ndarray) -> list:
        self.detect_calls += 1
        return self.detections


@pytest.fixture
def combat_config_yolo() -> dict:
    return {
        "target_source": "yolo",
        "model_path": "dummy_model.onnx",
        "left_click": {
            "enabled": True,
            "interval_sec": 0.3
        },
        "right_click": {
            "enabled": True,
            "interval_sec": 0.4
        },
        "click_position": [0.5, 0.5],
        "engage_range_ratio": 0.5
    }


def test_combat_yolo_targeting(combat_config_yolo) -> None:
    """First has_target call with YOLO: clicks the target, returns False (grace).
    Subsequent call during grace period returns True."""
    detections = [
        {"class_id": 0, "confidence": 0.9, "box": [0.6, 0.6, 0.1, 0.1]}
    ]
    det = DummyDetector(detections)
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    frame = cap.grab_frame()
    # First call: no panel visible, finds target, clicks it, returns False
    assert ctrl.has_target(frame) is False
    assert ctrl._yolo_target_pos == [0.6, 0.6]
    # A targeting click should have been issued
    assert ("click", 0.6, 0.6, "left") in inp.log

    # Second call during grace period: returns True (waiting for panel)
    assert ctrl.has_target(frame) is True

    # Verify combat execution clicks at the target coordinates
    inp.log.clear()
    ctrl.execute_combat_actions()
    assert ("click", 0.6, 0.6, "left") in inp.log
    assert ("click", 0.6, 0.6, "right") in inp.log


def test_combat_yolo_closest_target(combat_config_yolo) -> None:
    """Should pick the target closest to screen center."""
    detections = [
        {"class_id": 0, "confidence": 0.8, "box": [0.8, 0.8, 0.1, 0.1]},
        {"class_id": 0, "confidence": 0.9, "box": [0.4, 0.4, 0.1, 0.1]}
    ]
    det = DummyDetector(detections)
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    frame = cap.grab_frame()
    ctrl.has_target(frame)
    # Should pick [0.4, 0.4] since it is closer to the center [0.5, 0.5]
    assert ctrl._yolo_target_pos == [0.4, 0.4]


def test_combat_yolo_out_of_range(combat_config_yolo) -> None:
    # Target 1: [0.9, 0.9] (distance is 0.565 > engage_range_ratio of 0.5)
    detections = [
        {"class_id": 0, "confidence": 0.9, "box": [0.9, 0.9, 0.1, 0.1]}
    ]
    det = DummyDetector(detections)
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    frame = cap.grab_frame()
    assert ctrl.has_target(frame) is False
    assert ctrl._yolo_target_pos is None


def test_combat_yolo_no_detections(combat_config_yolo) -> None:
    det = DummyDetector([])
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    frame = cap.grab_frame()
    assert ctrl.has_target(frame) is False
    assert ctrl._yolo_target_pos is None


def test_combat_yolo_panel_visible_keeps_target(combat_config_yolo) -> None:
    """When target panel is visible (red pixels in region), bot stays locked."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01
    }

    detections = [
        {"class_id": 0, "confidence": 0.9, "box": [0.6, 0.6, 0.1, 0.1]}
    ]
    det = DummyDetector(detections)

    # Create a frame with red pixels to simulate panel visible
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]  # Red patch in BGR
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    # Simulate having an active target
    ctrl._active_target_id = 1
    ctrl._yolo_target_pos = [0.5, 0.5]

    # Panel is visible → should return True and stay locked
    assert ctrl.has_target(red_frame) is True

    # Simulate target moving to [0.6, 0.6] — position should update
    assert ctrl._yolo_target_pos == [0.6, 0.6]


def test_combat_yolo_panel_visible_no_lock_reacquires(combat_config_yolo) -> None:
    """Regression: panel visible but no active lock (moment right after a kill) must
    re-acquire a real monster, never fall back to clicking screen center (the player)."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    det = DummyDetector([
        {"class_id": 0, "confidence": 0.9, "box": [0.6, 0.6, 0.1, 0.1]}
    ])
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]  # Red patch => panel visible
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    # No lock at all, but panel reads visible (lingering red after previous kill)
    assert ctrl._active_target_id is None
    assert ctrl._yolo_target_pos is None

    assert ctrl.has_target(red_frame) is True
    # Must have re-acquired the real monster, not the player center
    assert ctrl._yolo_target_pos == [0.6, 0.6]

    inp.log.clear()
    ctrl.execute_combat_actions()
    assert ("click", 0.6, 0.6, "left") in inp.log
    # Never clicks the player at screen center
    assert ("click", 0.5, 0.5, "left") not in inp.log


def test_combat_yolo_panel_visible_only_player_no_click(combat_config_yolo) -> None:
    """Regression: panel visible but the only detection is the player character
    (screen center). Must report no target and must NOT click the player."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    # Detection whose box contains (0.5, 0.5) -> excluded as the player
    det = DummyDetector([
        {"class_id": 0, "confidence": 0.9, "box": [0.5, 0.5, 0.2, 0.2]}
    ])
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    assert ctrl.has_target(red_frame) is False
    assert ctrl._yolo_target_pos is None

    ctrl.execute_combat_actions()
    # No click at all — especially not on the player at [0.5, 0.5]
    assert inp.log == []


def test_combat_yolo_panel_gone_clears_target(combat_config_yolo) -> None:
    """When target panel disappears, bot clears target and finds new one."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.5  # Very high threshold → panel never "visible"
    }
    combat_config_yolo["target_lock_grace_sec"] = 0.0  # No grace

    det = DummyDetector([
        {"class_id": 0, "confidence": 0.9, "box": [0.6, 0.6, 0.1, 0.1]}
    ])
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    # Simulate having a previously locked target
    ctrl._active_target_id = 99
    ctrl._yolo_target_pos = [0.3, 0.3]
    ctrl._last_yolo_target_time = 0.0  # grace expired

    frame = cap.grab_frame()
    # Panel not visible, grace expired → should clear old target and click new one
    result = ctrl.has_target(frame)
    assert result is False
    assert ctrl._active_target_id is not None  # New target acquired
    assert ctrl._yolo_target_pos == [0.6, 0.6]
    assert ("click", 0.6, 0.6, "left") in inp.log
