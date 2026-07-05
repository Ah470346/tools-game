"""
tests/test_hotkey.py

Unit tests for the HotkeyManager.
Verifies that:
- Keyboard hotkeys are successfully registered/mocked.
- F12 (KILL) triggers key releases (<200ms), blocks inputs, and transitions FSM to IDLE.
- F9 (PAUSE/RESUME) toggles the FSM state between PAUSED and the previous state,
  releasing keys/blocking inputs on pause and unblocking on resume.
"""

import time
from unittest.mock import MagicMock, patch
import pytest

from backends.mock_backends import MockCapture, MockInput
from core.state_machine import StateMachine
from core.hotkey_manager import HotkeyManager


def test_hotkey_registration():
    """Verifies that HotkeyManager registers hotkeys using the keyboard library."""
    cap = MockCapture()
    inp = MockInput()
    fsm = StateMachine(cap, inp)

    with patch("keyboard.add_hotkey") as mock_add_hotkey:
        manager = HotkeyManager(fsm, inp, kill_key="f12", pause_key="f9")
        manager.start()
        
        # Verify add_hotkey was called for both keys
        assert mock_add_hotkey.call_count == 2
        mock_add_hotkey.assert_any_call("f12", manager.kill)
        mock_add_hotkey.assert_any_call("f9", manager.toggle_pause)
        assert manager._is_hooked is True

        with patch("keyboard.remove_hotkey") as mock_remove_hotkey:
            manager.stop_listening()
            assert mock_remove_hotkey.call_count == 2
            mock_remove_hotkey.assert_any_call("f12")
            mock_remove_hotkey.assert_any_call("f9")
            assert manager._is_hooked is False


def test_f12_kill_releases_keys_and_blocks_under_200ms():
    """
    Verifies that calling kill() releases all active keys and sets block_inputs
    within 200ms.
    """
    cap = MockCapture()
    inp = MockInput()
    fsm = StateMachine(cap, inp)
    fsm.running = True
    fsm.state = "FARMING"

    # Simulate some keys being held down by the bot
    inp.key("w", "down")
    inp.key("shift", "down")
    assert "w" in inp.pressed_keys
    assert "shift" in inp.pressed_keys

    manager = HotkeyManager(fsm, inp)

    # Time the kill action
    start_time = time.perf_counter()
    manager.kill()
    end_time = time.perf_counter()

    elapsed_ms = (end_time - start_time) * 1000.0

    # Ensure key release and block happened extremely fast (<200ms)
    assert elapsed_ms < 200.0

    # Verify keys were released
    assert len(inp.pressed_keys) == 0
    # The MockInput log should contain key up commands for 'w' and 'shift'
    up_keys = [entry[1] for entry in inp.log if entry[0] == "key" and entry[2] == "up"]
    assert "w" in up_keys
    assert "shift" in up_keys

    # Verify input is now blocked
    assert inp.block_inputs is True

    # Try sending new input and verify it is ignored
    inp.clear()
    inp.move(0.5, 0.5)
    inp.click(0.5, 0.5)
    inp.key("space", "down")
    # Verify no log entries recorded because of blocking
    assert len(inp.log) == 0

    # Verify FSM is stopped and in IDLE state
    assert fsm.running is False
    assert fsm.state == "IDLE"


def test_f9_pause_resume_toggle():
    """
    Verifies that F9 toggles the state between the active state and PAUSED,
    releasing keys and blocking inputs on pause, and restoring on resume.
    """
    cap = MockCapture()
    inp = MockInput()
    fsm = StateMachine(cap, inp)
    fsm.running = True
    fsm.state = "FARMING"

    # Simulate a key held down
    inp.key("a", "down")
    assert "a" in inp.pressed_keys

    manager = HotkeyManager(fsm, inp)

    # First toggle - Pause
    manager.toggle_pause()

    assert fsm.state == "PAUSED"
    assert fsm.running is True
    assert inp.block_inputs is True
    assert len(inp.pressed_keys) == 0
    # Verify 'a' release was called
    up_keys = [entry[1] for entry in inp.log if entry[0] == "key" and entry[2] == "up"]
    assert "a" in up_keys

    # Second toggle - Resume
    inp.clear()
    manager.toggle_pause()

    assert fsm.state == "FARMING"
    assert fsm.running is True
    assert inp.block_inputs is False

    # Try sending inputs, should work now
    inp.move(0.1, 0.2)
    assert len(inp.log) == 1
    assert inp.log[0] == ("move", 0.1, 0.2)


def test_pause_toggle_ignored_when_fsm_not_running():
    """Verifies that F9 toggle has no effect if FSM is not running."""
    cap = MockCapture()
    inp = MockInput()
    fsm = StateMachine(cap, inp)
    fsm.running = False
    fsm.state = "IDLE"

    manager = HotkeyManager(fsm, inp)
    manager.toggle_pause()

    assert fsm.state == "IDLE"
    assert inp.block_inputs is False
