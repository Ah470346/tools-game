"""
backends/capture_direct.py

Concrete implementation of ICaptureBackend for Windows Direct Control mode.

Capture strategy (chosen at construction time, not at every frame):
  1. DXcam   — Desktop Duplication API, fastest (~125 FPS in PoC). Preferred.
  2. BitBlt   — GDI fallback via win32gui/win32ui; slower but compatible.

Both paths return a BGR numpy array cropped to the game's *client* area so the
title bar / window border are excluded before any vision code sees the frame.

NOTE: This module is the only place that imports dxcam or win32* directly.
      core/, features/, and vision/ must never import these libraries.
"""

import ctypes
import logging
import sys
from typing import Optional, Tuple

import numpy as np

from backends.capture_base import ICaptureBackend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Windows-only imports — guarded so the module can be imported on
# any OS (tests run on macOS/Linux CI without pywin32/dxcam installed).
# ---------------------------------------------------------------------------
try:
    import win32gui
    import win32ui
    import win32con
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False
    logger.warning("pywin32 not available — BitBlt fallback disabled.")

try:
    import dxcam
    _HAS_DXCAM = True
except ImportError:
    dxcam = None  # type: ignore[assignment]  — keeps name in namespace for patching
    _HAS_DXCAM = False
    logger.warning("dxcam not available — DXcam backend disabled.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_window(title: str) -> int:
    """
    Returns the HWND of the first window whose title *contains* `title`.

    Args:
        title: Substring to search for in window titles.

    Returns:
        int: Window handle (HWND). 0 if not found.

    Raises:
        RuntimeError: If pywin32 is not installed.
    """
    if not _HAS_WIN32:
        raise RuntimeError("pywin32 is required to find game windows (Windows only).")

    found: int = 0

    def _cb(hwnd: int, _: None) -> bool:
        nonlocal found
        if title.lower() in win32gui.GetWindowText(hwnd).lower():
            found = hwnd
            return False  # stop enumeration
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        # Returning False from the callback stops EnumWindows but may trigger a
        # false-positive pywintypes.error due to a leftover error code in GetLastError().
        # If we successfully found the window, we can ignore this error.
        if not found:
            raise

    return found


def _get_client_rect_screen(hwnd: int) -> Tuple[int, int, int, int]:
    """
    Returns (left, top, right, bottom) of the client area in *screen* coordinates.

    Args:
        hwnd: Window handle.

    Returns:
        Tuple[int, int, int, int]: Client area bounding box on screen.
    """
    rect = win32gui.GetClientRect(hwnd)          # (0, 0, w, h) in client coords
    left_top = win32gui.ClientToScreen(hwnd, (rect[0], rect[1]))
    right_bottom = win32gui.ClientToScreen(hwnd, (rect[2], rect[3]))
    return left_top[0], left_top[1], right_bottom[0], right_bottom[1]


# ---------------------------------------------------------------------------
# DirectCapture
# ---------------------------------------------------------------------------

class DirectCapture(ICaptureBackend):
    """
    Screen capture backend for Windows Direct Control mode.

    Selects DXcam or BitBlt at construction time; the same backend is reused
    for every grab_frame() call.  Client-area cropping is applied in both paths
    so vision code always receives a clean game-only image.

    Args:
        window_title: Substring of the game window title (from settings.json).
        prefer_backend: 'auto' | 'dxcam' | 'bitblt'.  'auto' tries DXcam first.
    """

    def __init__(self, window_title: str = "Priston Tale",
                 prefer_backend: str = "auto") -> None:
        """Initialises the capture backend, probing availability."""
        self._window_title = window_title
        self._camera = None          # dxcam camera instance (if used)
        self._backend: str           # 'dxcam' | 'bitblt'
        self._last_frame: Optional[np.ndarray] = None

        use_dxcam = _HAS_DXCAM and prefer_backend in ("auto", "dxcam")

        if use_dxcam:
            self._backend = "dxcam"
            logger.info("DirectCapture: using DXcam backend.")
        elif _HAS_WIN32 and prefer_backend in ("auto", "bitblt"):
            self._backend = "bitblt"
            logger.info("DirectCapture: using BitBlt backend.")
        else:
            raise RuntimeError(
                "No capture backend available. "
                "Install dxcam (preferred) or pywin32 (fallback)."
            )

    # ------------------------------------------------------------------
    # ICaptureBackend
    # ------------------------------------------------------------------

    def grab_frame(self) -> np.ndarray:
        """
        Captures one BGR frame of the game's client area.

        Returns:
            np.ndarray: Shape (H, W, 3), dtype uint8, channel order BGR.

        Raises:
            RuntimeError: If the game window is not found.
        """
        if self._backend == "dxcam":
            return self._grab_dxcam()
        return self._grab_bitblt()

    # ------------------------------------------------------------------
    # Private — DXcam path
    # ------------------------------------------------------------------

    def _get_region(self) -> Tuple[int, int, int, int]:
        """Returns the current client-area bounding box for this frame."""
        hwnd = _find_window(self._window_title)
        if not hwnd:
            raise RuntimeError(
                f"Game window not found: '{self._window_title}'. "
                "Make sure Priston Tale is running."
            )
        return _get_client_rect_screen(hwnd)

    def _grab_dxcam(self) -> np.ndarray:
        """Grabs a frame using DXcam Desktop Duplication."""
        region = self._get_region()  # (left, top, right, bottom)

        # Create or recycle camera.  dxcam.create() is cheap if reused.
        if self._camera is None:
            self._camera = dxcam.create(output_color="BGR")

        frame = self._camera.grab(region=region, new_frame_only=False)
        if frame is None:
            # Fallback to last successful frame if available
            if self._last_frame is not None:
                l, t, r, b = region
                target_shape = (b - t, r - l, 3)
                if self._last_frame.shape == target_shape:
                    return self._last_frame

            logger.warning("DXcam returned None frame; returning black placeholder.")
            l, t, r, b = region
            return np.zeros((b - t, r - l, 3), dtype=np.uint8)

        # Cache the successful frame
        self._last_frame = frame
        return frame

    # ------------------------------------------------------------------
    # Private — BitBlt path
    # ------------------------------------------------------------------

    def _grab_bitblt(self) -> np.ndarray:
        """Grabs a frame using Windows GDI BitBlt (PrintWindow-compatible path)."""
        hwnd = _find_window(self._window_title)
        if not hwnd:
            raise RuntimeError(
                f"Game window not found: '{self._window_title}'. "
                "Make sure Priston Tale is running."
            )

        left, top, right, bottom = _get_client_rect_screen(hwnd)
        width = right - left
        height = bottom - top

        hwnd_dc = win32gui.GetDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bmp)

        # Use PrintWindow so it works even when the window is occluded.
        result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 1)
        if not result:
            logger.warning("PrintWindow returned 0; falling back to BitBlt.")
            save_dc.BitBlt((0, 0), (width, height), mfc_dc, (0, 0), win32con.SRCCOPY)

        bmp_info = bmp.GetInfo()
        bmp_str = bmp.GetBitmapBits(True)

        # BGRA → BGR
        img = np.frombuffer(bmp_str, dtype=np.uint8)
        img.shape = (bmp_info["bmHeight"], bmp_info["bmWidth"], 4)
        img = img[:, :, :3]

        win32gui.DeleteObject(bmp.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)

        return np.ascontiguousarray(img)

