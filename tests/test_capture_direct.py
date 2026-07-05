"""
tests/test_capture_direct.py

Unit tests for backends/capture_direct.py.

These tests exercise only the parts that do NOT require a real game window
or Windows-only libraries (dxcam / pywin32).  They verify:
  - DirectCapture raises RuntimeError when no backend is available.
  - DirectCapture properly implements ICaptureBackend.
  - _HAS_DXCAM / _HAS_WIN32 flags are booleans.

Platform-specific integration tests (actual window lookup, real FPS) are in
scripts/test_capture.py and must be run manually on the Windows game machine.
"""

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import backends.capture_direct as _mod
from backends.capture_base import ICaptureBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_direct_capture_with_mock_dxcam():
    """Returns a DirectCapture backed by a mock dxcam that returns a green frame."""
    fake_frame = np.zeros((600, 800, 3), dtype=np.uint8)
    fake_frame[:, :, 1] = 128  # green channel to distinguish from black

    mock_camera = MagicMock()
    mock_camera.grab.return_value = fake_frame

    mock_dxcam = MagicMock()
    mock_dxcam.create.return_value = mock_camera

    # Patch module-level globals so no real Windows library is needed
    with patch.multiple(
        _mod,
        _HAS_DXCAM=True,
        _HAS_WIN32=True,
        dxcam=mock_dxcam,
    ):
        # Also mock the window-lookup helper so it returns a fake HWND
        with patch.object(_mod, "_find_window", return_value=12345):
            with patch.object(_mod, "_get_client_rect_screen", return_value=(0, 0, 800, 600)):
                cap = _mod.DirectCapture(window_title="Priston Tale", prefer_backend="dxcam")
                cap._camera = mock_camera  # inject already-created mock camera
                yield cap, fake_frame


# ---------------------------------------------------------------------------
# Backend availability flags
# ---------------------------------------------------------------------------

def test_has_dxcam_is_bool():
    assert isinstance(_mod._HAS_DXCAM, bool)


def test_has_win32_is_bool():
    assert isinstance(_mod._HAS_WIN32, bool)


# ---------------------------------------------------------------------------
# Constructor — no backend available
# ---------------------------------------------------------------------------

def test_direct_capture_raises_when_no_backend():
    """If both dxcam and pywin32 are unavailable, constructor raises RuntimeError."""
    with patch.multiple(_mod, _HAS_DXCAM=False, _HAS_WIN32=False):
        with pytest.raises(RuntimeError, match="No capture backend available"):
            _mod.DirectCapture()


# ---------------------------------------------------------------------------
# DirectCapture with mocked DXcam
# ---------------------------------------------------------------------------

def test_direct_capture_is_icapture_backend():
    """DirectCapture must satisfy the ICaptureBackend interface."""
    mock_dxcam = MagicMock()
    mock_dxcam.create.return_value = MagicMock()
    with patch.multiple(_mod, _HAS_DXCAM=True, _HAS_WIN32=True, dxcam=mock_dxcam):
        cap = _mod.DirectCapture(prefer_backend="dxcam")
    assert isinstance(cap, ICaptureBackend)


def test_grab_frame_dxcam_returns_ndarray():
    """grab_frame() via DXcam path returns a numpy ndarray."""
    fake_frame = np.zeros((600, 800, 3), dtype=np.uint8)
    mock_camera = MagicMock()
    mock_camera.grab.return_value = fake_frame
    mock_dxcam = MagicMock()
    mock_dxcam.create.return_value = mock_camera

    with patch.multiple(_mod, _HAS_DXCAM=True, _HAS_WIN32=True, dxcam=mock_dxcam):
        with patch.object(_mod, "_find_window", return_value=1):
            with patch.object(_mod, "_get_client_rect_screen", return_value=(0, 0, 800, 600)):
                cap = _mod.DirectCapture(prefer_backend="dxcam")
                cap._camera = mock_camera
                frame = cap.grab_frame()

    assert isinstance(frame, np.ndarray)
    assert frame.ndim == 3
    assert frame.shape[2] == 3  # BGR


def test_grab_frame_dxcam_none_returns_black():
    """If DXcam returns None twice, grab_frame() returns a black frame (not crash)."""
    mock_camera = MagicMock()
    mock_camera.grab.return_value = None  # simulate no new frame
    mock_dxcam = MagicMock()
    mock_dxcam.create.return_value = mock_camera

    with patch.multiple(_mod, _HAS_DXCAM=True, _HAS_WIN32=True, dxcam=mock_dxcam):
        with patch.object(_mod, "_find_window", return_value=1):
            with patch.object(_mod, "_get_client_rect_screen", return_value=(0, 0, 800, 600)):
                cap = _mod.DirectCapture(prefer_backend="dxcam")
                cap._camera = mock_camera
                frame = cap.grab_frame()

    assert isinstance(frame, np.ndarray)
    assert frame.sum() == 0  # black placeholder


def test_grab_frame_raises_when_window_not_found():
    """grab_frame() raises RuntimeError if game window cannot be located."""
    mock_dxcam = MagicMock()
    with patch.multiple(_mod, _HAS_DXCAM=True, _HAS_WIN32=True, dxcam=mock_dxcam):
        with patch.object(_mod, "_find_window", return_value=0):
            cap = _mod.DirectCapture(prefer_backend="dxcam")
            with pytest.raises(RuntimeError, match="Game window not found"):
                cap.grab_frame()

