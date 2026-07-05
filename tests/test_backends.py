"""
tests/test_backends.py

Unit tests for the abstract backend interfaces and their mock implementations.
These tests verify that:
  - ICaptureBackend and IInputBackend cannot be instantiated directly.
  - MockCapture.grab_frame() returns a correctly shaped black BGR frame.
  - MockInput records move/click/key calls in the correct order with correct args.
"""

import numpy as np
import pytest

from backends.capture_base import ICaptureBackend
from backends.input_base import IInputBackend
from backends.mock_backends import MockCapture, MockInput


# ---------------------------------------------------------------------------
# ICaptureBackend — interface contract tests
# ---------------------------------------------------------------------------

def test_icapture_is_abstract() -> None:
    """ICaptureBackend cannot be instantiated — it is a pure ABC."""
    with pytest.raises(TypeError):
        ICaptureBackend()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# MockCapture tests
# ---------------------------------------------------------------------------

def test_mock_capture_returns_ndarray() -> None:
    """grab_frame() must return a numpy ndarray."""
    cap = MockCapture()
    frame = cap.grab_frame()
    assert isinstance(frame, np.ndarray)


def test_mock_capture_frame_shape() -> None:
    """grab_frame() returns a 3-channel (BGR) frame of expected dimensions."""
    cap = MockCapture()
    frame = cap.grab_frame()
    assert frame.shape == (MockCapture.FRAME_HEIGHT, MockCapture.FRAME_WIDTH, 3)


def test_mock_capture_frame_is_black() -> None:
    """grab_frame() returns an all-zero (black) frame."""
    cap = MockCapture()
    frame = cap.grab_frame()
    assert frame.sum() == 0


def test_mock_capture_is_icapture_instance() -> None:
    """MockCapture must satisfy the ICaptureBackend interface."""
    cap = MockCapture()
    assert isinstance(cap, ICaptureBackend)


# ---------------------------------------------------------------------------
# IInputBackend — interface contract tests
# ---------------------------------------------------------------------------

def test_iinput_is_abstract() -> None:
    """IInputBackend cannot be instantiated — it is a pure ABC."""
    with pytest.raises(TypeError):
        IInputBackend()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# MockInput tests
# ---------------------------------------------------------------------------

def test_mock_input_is_iinput_instance() -> None:
    """MockInput must satisfy the IInputBackend interface."""
    inp = MockInput()
    assert isinstance(inp, IInputBackend)


def test_mock_input_log_starts_empty() -> None:
    """A freshly created MockInput has an empty log."""
    inp = MockInput()
    assert inp.log == []


def test_mock_input_records_move() -> None:
    """move() appends a ('move', x, y) entry to the log."""
    inp = MockInput()
    inp.move(0.5, 0.25)
    assert inp.log == [("move", 0.5, 0.25)]


def test_mock_input_records_click_default_button() -> None:
    """click() defaults to left button and records the full entry."""
    inp = MockInput()
    inp.click(0.1, 0.9)
    assert inp.log == [("click", 0.1, 0.9, "left")]


def test_mock_input_records_click_right_button() -> None:
    """click() records the specified button."""
    inp = MockInput()
    inp.click(0.5, 0.5, "right")
    assert inp.log == [("click", 0.5, 0.5, "right")]


def test_mock_input_records_key_press() -> None:
    """key() records ('key', name, action) entry."""
    inp = MockInput()
    inp.key("space")
    assert inp.log == [("key", "space", "press")]


def test_mock_input_records_key_down_up() -> None:
    """key() records down then up actions separately."""
    inp = MockInput()
    inp.key("f1", "down")
    inp.key("f1", "up")
    assert inp.log == [("key", "f1", "down"), ("key", "f1", "up")]


def test_mock_input_records_sequence() -> None:
    """move → click → key appear in log in call order."""
    inp = MockInput()
    inp.move(0.5, 0.5)
    inp.click(0.5, 0.5, "left")
    inp.key("1", "press")
    assert inp.log == [
        ("move", 0.5, 0.5),
        ("click", 0.5, 0.5, "left"),
        ("key", "1", "press"),
    ]


def test_mock_input_clear() -> None:
    """clear() empties the log."""
    inp = MockInput()
    inp.move(0.1, 0.2)
    inp.clear()
    assert inp.log == []
