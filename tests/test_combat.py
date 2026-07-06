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
    now = time.time()
    ctrl._active_target_id = 1
    ctrl._yolo_target_pos = [0.5, 0.5]
    ctrl._last_yolo_target_time = now
    ctrl._panel_last_seen_time = now
    ctrl._last_pos_confirm_time = now
    ctrl._engagement_start_time = now

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


def test_combat_yolo_stale_position_holds_fire(combat_config_yolo) -> None:
    """Regression: when YOLO stops confirming the target position (monster obscured)
    while the panel is still visible, the bot must keep reporting has_target=True
    (panel is authoritative) but execute_combat_actions must not click (stale
    position without blind-attack eligibility)."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    combat_config_yolo["stale_target_timeout_sec"] = 1.5
    combat_config_yolo["blind_attack_max_sec"] = 3.0
    combat_config_yolo["blind_attack_max_dist_ratio"] = 0.15
    det = DummyDetector([])  # YOLO sees nothing anymore
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]  # Panel visible
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    ctrl._active_target_id = 99
    ctrl._yolo_target_pos = [0.6, 0.6]  # dist to center ~0.14 (within blind range)
    ctrl._last_yolo_target_time = now
    ctrl._panel_last_seen_time = now
    ctrl._engagement_start_time = now
    # Position was last confirmed longer ago than the stale timeout but within blind window
    ctrl._last_pos_confirm_time = now - 2.0

    # Panel authoritative: has_target returns True (blind attack eligible)
    assert ctrl.has_target(red_frame) is True
    # Engagement is kept (anchor + ID) — no switch while the panel is visible
    assert ctrl._yolo_target_pos == [0.6, 0.6]
    assert ctrl._active_target_id == 99

    # But execute_combat_actions should click (blind attack)
    ctrl.execute_combat_actions()
    assert ("click", 0.6, 0.6, "left") in inp.log


def test_combat_yolo_engagement_max_sec_valve(combat_config_yolo) -> None:
    """When engagement runs longer than engagement_max_sec, the bot clears the target
    WITHOUT blacklisting (safety valve replaces old give-up timer)."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    combat_config_yolo["engagement_max_sec"] = 45.0
    det = DummyDetector([])
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    ctrl._active_target_id = 99
    ctrl._yolo_target_pos = [0.6, 0.6]
    ctrl._last_yolo_target_time = now
    ctrl._panel_last_seen_time = now
    ctrl._last_pos_confirm_time = now
    ctrl._engagement_start_time = now - 46.0  # Past 45s valve

    assert ctrl.has_target(red_frame) is False
    assert ctrl._active_target_id is None
    assert ctrl._yolo_target_pos is None
    # Safety valve does NOT blacklist
    assert 99 not in ctrl._blacklisted_targets


def test_combat_yolo_reassociates_to_melee_monster_near_player(combat_config_yolo) -> None:
    """Regression: a monster fighting in melee range stands right next to the
    character (inside the player exclusion zone). Re-association must still adopt
    it — otherwise every melee fight is abandoned after the first hit."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    combat_config_yolo["reassociate_delay_sec"] = 0.5
    # Detection right next to screen center (would be filtered as "player"
    # by acquisition-time filtering)
    det = DummyDetector([
        {"class_id": 0, "confidence": 0.9, "box": [0.52, 0.51, 0.1, 0.1]}
    ])
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    ctrl._active_target_id = 99
    ctrl._yolo_target_pos = [0.55, 0.53]  # Monster was approaching the player
    ctrl._last_yolo_target_time = now
    ctrl._panel_last_seen_time = now
    ctrl._last_pos_confirm_time = now - 0.6  # Coast delay elapsed
    ctrl._engagement_start_time = now

    assert ctrl.has_target(red_frame) is True
    # Adopted the melee monster next to the character
    assert ctrl._active_target_id == 1
    assert ctrl._yolo_target_pos == [0.52, 0.51]


def test_combat_yolo_panel_flicker_does_not_end_engagement(combat_config_yolo) -> None:
    """Regression: after grace expires, a single missed panel read must not be
    treated as the target's death — previously this blacklisted the monster
    mid-fight and switched to another one after every hit."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    combat_config_yolo["panel_gone_confirm_sec"] = 0.3
    det = DummyDetector([])
    # Frame with NO red pixels → panel read misses this frame
    black_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    ctrl._active_target_id = 99
    ctrl._yolo_target_pos = [0.6, 0.6]
    ctrl._last_yolo_target_time = now - 5.0  # Grace long expired (mid-fight)
    ctrl._panel_last_seen_time = now - 0.1   # Panel was seen an instant ago
    ctrl._last_pos_confirm_time = now
    ctrl._engagement_start_time = now

    assert ctrl.has_target(black_frame) is True
    # Engagement survives the flicker: same target, not blacklisted
    assert ctrl._active_target_id == 99
    assert 99 not in ctrl._blacklisted_targets


def test_combat_yolo_no_blacklist_on_normal_kill(combat_config_yolo) -> None:
    """When the panel appeared during the fight and then disappears (monster died),
    the target must be cleared WITHOUT blacklisting, and the next monster acquired."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.5,  # Panel never reads visible on this frame
    }
    combat_config_yolo["target_lock_grace_sec"] = 0.0
    combat_config_yolo["panel_gone_confirm_sec"] = 0.0
    det = DummyDetector([
        {"class_id": 0, "confidence": 0.9, "box": [0.6, 0.6, 0.1, 0.1]}
    ])
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    ctrl._active_target_id = 99
    ctrl._yolo_target_pos = [0.3, 0.3]
    ctrl._last_yolo_target_time = now - 5.0
    ctrl._panel_last_seen_time = now - 1.0  # Panel WAS seen after acquisition → real kill

    frame = cap.grab_frame()
    assert ctrl.has_target(frame) is False
    # Normal kill: old target NOT blacklisted, new one acquired
    assert 99 not in ctrl._blacklisted_targets
    assert ctrl._yolo_target_pos == [0.6, 0.6]
    assert ("click", 0.6, 0.6, "left") in inp.log


def test_combat_yolo_flicker_does_not_switch_target(combat_config_yolo) -> None:
    """Regression: a single-frame detection miss of the current target must NOT
    immediately re-associate to a neighboring monster while the current one is
    still alive (panel visible). The old position is held during the coast delay."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    combat_config_yolo["reassociate_delay_sec"] = 0.5
    # Only a *different* monster is detected this frame (near the old position)
    det = DummyDetector([
        {"class_id": 0, "confidence": 0.9, "box": [0.65, 0.55, 0.1, 0.1]}
    ])
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    ctrl._active_target_id = 99
    ctrl._yolo_target_pos = [0.6, 0.6]
    ctrl._last_yolo_target_time = now
    ctrl._last_pos_confirm_time = now  # Position confirmed just now → still coasting
    ctrl._panel_last_seen_time = now
    ctrl._engagement_start_time = now

    assert ctrl.has_target(red_frame) is True
    # Must keep the original target/position, not adopt the neighbor
    assert ctrl._active_target_id == 99
    assert ctrl._yolo_target_pos == [0.6, 0.6]


def test_combat_yolo_reassociates_after_coast_delay(combat_config_yolo) -> None:
    """After the coast delay, a close-by track (within reassociate_max_dist_ratio)
    is adopted; a distant one is not."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    combat_config_yolo["reassociate_delay_sec"] = 0.5
    combat_config_yolo["reassociate_max_dist_ratio"] = 0.08
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()

    # Case 1: track within max dist (d ≈ 0.036) → re-associate
    det_close = DummyDetector([
        {"class_id": 0, "confidence": 0.9, "box": [0.63, 0.62, 0.1, 0.1]}
    ])
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo,
                            detector=det_close)
    now = time.time()
    ctrl._active_target_id = 99
    ctrl._yolo_target_pos = [0.6, 0.6]
    ctrl._last_yolo_target_time = now
    ctrl._last_pos_confirm_time = now - 0.6  # Coast delay elapsed
    ctrl._panel_last_seen_time = now
    ctrl._engagement_start_time = now

    assert ctrl.has_target(red_frame) is True
    assert ctrl._active_target_id == 1  # Adopted the new track
    assert ctrl._yolo_target_pos == [0.63, 0.62]

    # Case 2: track too far (d = 0.12 > 0.08) → keep old position, no switch
    det_far = DummyDetector([
        {"class_id": 0, "confidence": 0.9, "box": [0.72, 0.6, 0.1, 0.1]}
    ])
    ctrl2 = CombatController(capture=cap, simulator=inp, config=combat_config_yolo,
                             detector=det_far)
    now = time.time()
    ctrl2._active_target_id = 99
    ctrl2._yolo_target_pos = [0.6, 0.6]
    ctrl2._last_yolo_target_time = now
    ctrl2._last_pos_confirm_time = now - 0.6
    ctrl2._panel_last_seen_time = now
    ctrl2._engagement_start_time = now

    assert ctrl2.has_target(red_frame) is True
    assert ctrl2._active_target_id == 99
    assert ctrl2._yolo_target_pos == [0.6, 0.6]


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


# --- Panel-authoritative targeting tests ---

def test_occlusion_never_blacklists_while_panel_visible(combat_config_yolo) -> None:
    """YOLO blind for 10s with panel still red: no blacklist, anchor kept,
    has_target stays True, bot doesn't click a second monster."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    combat_config_yolo["stale_target_timeout_sec"] = 1.5
    combat_config_yolo["blind_attack_max_sec"] = 3.0
    combat_config_yolo["engagement_max_sec"] = 45.0

    # Two monsters but detector returns neither (YOLO blind)
    det = DummyDetector([])
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]  # Panel visible
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    ctrl._active_target_id = 71
    ctrl._yolo_target_pos = [0.55, 0.55]  # Near center
    ctrl._last_yolo_target_time = now
    ctrl._panel_last_seen_time = now
    ctrl._engagement_start_time = now
    ctrl._last_pos_confirm_time = now - 10.0  # Blind for 10s

    # has_target returns True (panel authoritative, hold fire zone)
    assert ctrl.has_target(red_frame) is True
    # NOT blacklisted
    assert 71 not in ctrl._blacklisted_targets
    # Anchor kept
    assert ctrl._active_target_id == 71
    assert ctrl._yolo_target_pos == [0.55, 0.55]


def test_blind_attack_window(combat_config_yolo) -> None:
    """Position near center (0.55,0.55): between 1.5s-3.0s stale, blind attack
    clicks at the last known position. Beyond 3.0s: stops clicking, still no blacklist."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    combat_config_yolo["stale_target_timeout_sec"] = 1.5
    combat_config_yolo["blind_attack_max_sec"] = 3.0
    combat_config_yolo["blind_attack_max_dist_ratio"] = 0.15
    combat_config_yolo["engagement_max_sec"] = 45.0

    det = DummyDetector([])
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    ctrl._active_target_id = 42
    ctrl._yolo_target_pos = [0.55, 0.55]  # dist to center = 0.07
    ctrl._last_yolo_target_time = now
    ctrl._panel_last_seen_time = now
    ctrl._engagement_start_time = now

    # Within blind window (2.0s stale, < 3.0s)
    ctrl._last_pos_confirm_time = now - 2.0
    assert ctrl.has_target(red_frame) is True
    assert ctrl._blind_attack_active is True

    # execute_combat_actions should click
    ctrl.execute_combat_actions()
    assert ("click", 0.55, 0.55, "left") in inp.log

    # Beyond blind window (4.0s stale, > 3.0s)
    inp.log.clear()
    ctrl._last_pos_confirm_time = now - 4.0
    assert ctrl.has_target(red_frame) is True  # Panel still keeps engagement alive
    assert ctrl._blind_attack_active is False

    # execute_combat_actions should hold fire (stale + no blind)
    ctrl.execute_combat_actions()
    assert ("click", 0.55, 0.55, "left") not in inp.log
    # Still not blacklisted
    assert 42 not in ctrl._blacklisted_targets


def test_blind_attack_refused_far_from_center(combat_config_yolo) -> None:
    """Anchor at (0.2, 0.2): dist to center = 0.424 > 0.15, blind attack never triggers."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    combat_config_yolo["stale_target_timeout_sec"] = 1.5
    combat_config_yolo["blind_attack_max_sec"] = 3.0
    combat_config_yolo["blind_attack_max_dist_ratio"] = 0.15
    combat_config_yolo["engagement_max_sec"] = 45.0

    det = DummyDetector([])
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    ctrl._active_target_id = 50
    ctrl._yolo_target_pos = [0.2, 0.2]  # Far from center
    ctrl._last_yolo_target_time = now
    ctrl._panel_last_seen_time = now
    ctrl._engagement_start_time = now
    ctrl._last_pos_confirm_time = now - 2.0  # Within blind time window

    # has_target still True (panel authoritative) but blind attack NOT active
    assert ctrl.has_target(red_frame) is True
    assert ctrl._blind_attack_active is False

    # Should NOT click (stale position, too far from center for blind)
    ctrl.execute_combat_actions()
    assert inp.log == []


def test_reassociate_to_new_id_after_occlusion(combat_config_yolo) -> None:
    """Monster reappears at slightly different position (dist 0.05) with new tracker ID
    after occlusion. Should adopt the new ID and continue fighting."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.01,
    }
    combat_config_yolo["reassociate_delay_sec"] = 0.5
    combat_config_yolo["reassociate_max_dist_ratio"] = 0.12
    combat_config_yolo["engagement_max_sec"] = 45.0

    # New detection at (0.65, 0.62) — 0.05 from old (0.6, 0.6)
    det = DummyDetector([
        {"class_id": 0, "confidence": 0.9, "box": [0.65, 0.62, 0.1, 0.1]}
    ])
    red_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    red_frame[10:20, 10:20] = [0, 0, 200]
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    ctrl._active_target_id = 99
    ctrl._yolo_target_pos = [0.6, 0.6]
    ctrl._last_yolo_target_time = now
    ctrl._panel_last_seen_time = now
    ctrl._engagement_start_time = now
    ctrl._last_pos_confirm_time = now - 0.6  # Coast delay elapsed

    assert ctrl.has_target(red_frame) is True
    # Adopted new track ID (track_id=1 from DummyDetector)
    assert ctrl._active_target_id == 1
    assert ctrl._yolo_target_pos == [0.65, 0.62]


def test_kill_picks_next_target_near_corpse(combat_config_yolo) -> None:
    """After a kill at (0.3, 0.3), next target should prefer the monster nearer
    to the corpse (0.34, 0.34) over the one nearer to screen center (0.52, 0.52)."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.5,  # Panel not visible → kill path
    }
    combat_config_yolo["target_lock_grace_sec"] = 0.0
    combat_config_yolo["panel_gone_confirm_sec"] = 0.0
    combat_config_yolo["next_target_anchor_sec"] = 5.0
    combat_config_yolo["engage_range_ratio"] = 1.0

    det = DummyDetector([
        {"class_id": 0, "confidence": 0.9, "box": [0.52, 0.52, 0.1, 0.1]},
        {"class_id": 0, "confidence": 0.9, "box": [0.34, 0.34, 0.1, 0.1]},
    ])
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    # Simulate previous kill at (0.3, 0.3)
    ctrl._active_target_id = 99
    ctrl._yolo_target_pos = [0.3, 0.3]
    ctrl._last_yolo_target_time = now - 5.0
    ctrl._panel_last_seen_time = now - 1.0  # Panel was seen → real kill

    frame = cap.grab_frame()
    result = ctrl.has_target(frame)
    assert result is False  # New target clicked, waiting for panel

    # Should pick (0.34, 0.34) because _last_kill_pos = (0.3, 0.3) is the anchor
    assert ctrl._yolo_target_pos == [0.34, 0.34]
    assert ("click", 0.34, 0.34, "left") in inp.log


def test_failed_lock_still_blacklists(combat_config_yolo) -> None:
    """Regression guard: panel never goes red during lock grace → target still gets
    blacklisted (failed lock behavior preserved from before panel-authority change)."""
    combat_config_yolo["target_check"] = {
        "enabled": True,
        "region": {"start": [0.0, 0.0], "end": [1.0, 1.0]},
        "min_red_ratio": 0.5,
    }
    combat_config_yolo["target_lock_grace_sec"] = 0.0
    combat_config_yolo["panel_gone_confirm_sec"] = 0.0

    det = DummyDetector([])
    cap = DummyCapture((0, 0, 0))
    inp = MockInput()
    ctrl = CombatController(capture=cap, simulator=inp, config=combat_config_yolo, detector=det)

    now = time.time()
    ctrl._active_target_id = 77
    ctrl._yolo_target_pos = [0.6, 0.6]
    ctrl._last_yolo_target_time = now
    # Panel was NEVER seen for this target
    ctrl._panel_last_seen_time = now - 10.0

    frame = cap.grab_frame()
    ctrl.has_target(frame)

    assert ctrl._active_target_id is None
    assert 77 in ctrl._blacklisted_targets
