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
    # Set up detector returning one target within range
    detections = [
        {"class_id": 0, "confidence": 0.9, "box": [0.6, 0.6, 0.1, 0.1]}
    ]
    det = DummyDetector(detections)
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    frame = cap.grab_frame()
    assert ctrl.has_target(frame) is True
    assert ctrl._yolo_target_pos == [0.6, 0.6]

    # Verify combat execution clicks at the target coordinates
    ctrl.execute_combat_actions()
    assert ("click", 0.6, 0.6, "left") in inp.log
    assert ("click", 0.6, 0.6, "right") in inp.log


def test_combat_yolo_closest_target(combat_config_yolo) -> None:
    # Set up detector returning two targets:
    # Target 1: [0.8, 0.8] (distance from 0.5, 0.5 is 0.424)
    # Target 2: [0.4, 0.4] (distance from 0.5, 0.5 is 0.141)
    detections = [
        {"class_id": 0, "confidence": 0.8, "box": [0.8, 0.8, 0.1, 0.1]},
        {"class_id": 0, "confidence": 0.9, "box": [0.4, 0.4, 0.1, 0.1]}
    ]
    det = DummyDetector(detections)
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    frame = cap.grab_frame()
    assert ctrl.has_target(frame) is True
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


def test_combat_yolo_target_lock_tracks_moving_position(combat_config_yolo) -> None:
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "check_pixel": [0.5, 0.05],
        "expected_color_bgr": [0, 49, 181],
        "color_tolerance": 30
    }

    detections = [
        {"class_id": 0, "confidence": 0.9, "box": [0.6, 0.6, 0.1, 0.1]}
    ]
    det = DummyDetector(detections)

    # 1. Mismatched color (no target lock) -> should run YOLO detection
    cap_no_lock = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap_no_lock, simulator=inp, config=combat_config_yolo, detector=det)

    frame_no_lock = cap_no_lock.grab_frame()
    assert ctrl.has_target(frame_no_lock) is True
    assert ctrl._yolo_target_pos == [0.6, 0.6]
    assert det.detect_calls == 1

    # 2. Matching color (target lock active) -> should call YOLO to track/update moving target position
    cap_locked = DummyCapture((0, 49, 181))
    ctrl.capture = cap_locked
    
    # Simulate target moving to [0.7, 0.7]
    det.detections = [
        {"class_id": 0, "confidence": 0.9, "box": [0.7, 0.7, 0.1, 0.1]}
    ]
    det.detect_calls = 0

    frame_locked = cap_locked.grab_frame()
    assert ctrl.has_target(frame_locked) is True
    # The coordinate should follow the target to [0.7, 0.7]
    assert ctrl._yolo_target_pos == [0.7, 0.7]
    assert det.detect_calls == 1  # YOLO detector run to track target!


def test_combat_yolo_target_lock_timeout(combat_config_yolo) -> None:
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "check_pixel": [0.5, 0.05],
        "expected_color_bgr": [0, 49, 181],
        "color_tolerance": 30
    }
    combat_config_yolo["target_lock_timeout_sec"] = 0.2
    combat_config_yolo["cancel_target_key"] = "esc"

    det = DummyDetector([
        {"class_id": 0, "confidence": 0.9, "box": [0.6, 0.6, 0.1, 0.1]}
    ])
    cap_locked = DummyCapture((0, 49, 181)) # Locked
    inp = MockInput()
    ctrl = CombatController(capture=cap_locked, simulator=inp, config=combat_config_yolo, detector=det)

    frame = cap_locked.grab_frame()
    # 1. First lock check -> lock starts, sets _target_lock_start_time
    assert ctrl.has_target(frame) is True
    assert ctrl._target_lock_start_time > 0.0
    assert ("key", "esc", "press") not in inp.log

    # 2. Wait for timeout duration
    time.sleep(0.3)

    # 3. Second lock check after timeout -> should trigger esc press and release lock
    assert ctrl.has_target(frame) is False
    assert ctrl._target_lock_start_time == 0.0
    assert ("key", "esc", "press") in inp.log


