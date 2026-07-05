"""
tests/test_input_direct.py

Unit tests for backends/input_direct.py.
Exercises absolute mouse movement, click actions, and key press/hold simulation.
Guarded using unittest mocks to run on non-Windows OS.
"""

from unittest.mock import MagicMock, patch

import pytest

import backends.input_direct as _mod
from backends.input_base import IInputBackend


def test_direct_input_is_iinput_backend():
    """DirectInput must implement the IInputBackend interface."""
    cap = _mod.DirectInput()
    assert isinstance(cap, IInputBackend)


def test_get_hwnd_or_raise_raises_when_not_found():
    """_get_hwnd_or_raise raises RuntimeError if window title is not found."""
    with patch.object(_mod, "find_window_by_title", return_value=0):
        cap = _mod.DirectInput(window_title="MissingWindow")
        with pytest.raises(RuntimeError, match="Game window not found"):
            cap._get_hwnd_or_raise()


def test_move_calls_pydirectinput_moveTo():
    """move() translates ratio to screen and calls pydirectinput.moveTo."""
    mock_pydirectinput = MagicMock()
    with patch.multiple(_mod, _HAS_PYDIRECTINPUT=True, pydirectinput=mock_pydirectinput):
        with patch.object(_mod, "find_window_by_title", return_value=123):
            with patch.object(_mod, "ratio_to_screen", return_value=(450, 300)) as mock_ratio:
                cap = _mod.DirectInput()
                cap.move(0.5, 0.4)
                
                mock_ratio.assert_called_once_with(0.5, 0.4, 123)
                mock_pydirectinput.moveTo.assert_called_once_with(450, 300)


def test_click_calls_pydirectinput_click():
    """click() translates ratio to screen and calls pydirectinput.click with correct button."""
    mock_pydirectinput = MagicMock()
    with patch.multiple(_mod, _HAS_PYDIRECTINPUT=True, pydirectinput=mock_pydirectinput):
        with patch.object(_mod, "find_window_by_title", return_value=123):
            with patch.object(_mod, "ratio_to_screen", return_value=(500, 600)) as mock_ratio:
                cap = _mod.DirectInput()
                cap.click(0.6, 0.8, button="right")
                
                mock_ratio.assert_called_once_with(0.6, 0.8, 123)
                mock_pydirectinput.click.assert_called_once_with(500, 600, button="right")


def test_key_press_calls_pydirectinput_press():
    """key(..., action='press') calls pydirectinput.press."""
    mock_pydirectinput = MagicMock()
    with patch.multiple(_mod, _HAS_PYDIRECTINPUT=True, pydirectinput=mock_pydirectinput):
        cap = _mod.DirectInput()
        cap.key("space", action="press")
        mock_pydirectinput.press.assert_called_once_with("space")


def test_key_down_calls_pydirectinput_keyDown():
    """key(..., action='down') calls pydirectinput.keyDown."""
    mock_pydirectinput = MagicMock()
    with patch.multiple(_mod, _HAS_PYDIRECTINPUT=True, pydirectinput=mock_pydirectinput):
        cap = _mod.DirectInput()
        cap.key("f1", action="down")
        mock_pydirectinput.keyDown.assert_called_once_with("f1")


def test_key_up_calls_pydirectinput_keyUp():
    """key(..., action='up') calls pydirectinput.keyUp."""
    mock_pydirectinput = MagicMock()
    with patch.multiple(_mod, _HAS_PYDIRECTINPUT=True, pydirectinput=mock_pydirectinput):
        cap = _mod.DirectInput()
        cap.key("f1", action="up")
        mock_pydirectinput.keyUp.assert_called_once_with("f1")


def test_key_invalid_action_raises_value_error():
    """key() raises ValueError for unsupported actions."""
    mock_pydirectinput = MagicMock()
    with patch.multiple(_mod, _HAS_PYDIRECTINPUT=True, pydirectinput=mock_pydirectinput):
        cap = _mod.DirectInput()
        with pytest.raises(ValueError, match="Unknown key action"):
            cap.key("space", action="invalid_action")
