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
from core.coordinates import find_window_by_title, get_client_rect_screen

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


# Helpers are now imported from core.coordinates


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
        hwnd = find_window_by_title(self._window_title)
        if not hwnd:
            raise RuntimeError(
                f"Game window not found: '{self._window_title}'. "
                "Make sure Priston Tale is running."
            )
        return get_client_rect_screen(hwnd)

    def _grab_dxcam(self) -> np.ndarray:
        """Grabs a frame using DXcam Desktop Duplication."""
        try:
            region = self._get_region()  # (left, top, right, bottom)
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("DXcam failed to get region: %s", e)
            return np.zeros((600, 800, 3), dtype=np.uint8)

        l, t, r, b = region
        
        # 1. Check for minimized window
        if r - l <= 0 or b - t <= 0:
            logger.warning("Game window is minimized or invalid size (%dx%d)", r - l, b - t)
            return np.zeros((600, 800, 3), dtype=np.uint8)

        # 2. Get screen size dynamically to clamp region coordinates
        import sys
        max_w = 1920
        max_h = 1080
        if sys.platform == "win32":
            try:
                import win32api
                max_w = win32api.GetSystemMetrics(0)
                max_h = win32api.GetSystemMetrics(1)
            except Exception:
                pass

        # Clamp region to screen bounds to prevent DXcam ValueError
        l_clamp = max(0, min(max_w, l))
        t_clamp = max(0, min(max_h, t))
        r_clamp = max(0, min(max_w, r))
        b_clamp = max(0, min(max_h, b))

        # Check if the clamped region is empty
        if r_clamp - l_clamp <= 0 or b_clamp - t_clamp <= 0:
            logger.warning("Clamped region is empty: (%d, %d, %d, %d)", l_clamp, t_clamp, r_clamp, b_clamp)
            return np.zeros((600, 800, 3), dtype=np.uint8)

        region_clamped = (l_clamp, t_clamp, r_clamp, b_clamp)

        # Create or recycle camera.
        if self._camera is None:
            self._camera = dxcam.create(output_color="BGR")

        try:
            frame = self._camera.grab(region=region_clamped, new_frame_only=False)
        except Exception as e:
            logger.warning("DXcam grab raised exception: %s. Re-creating camera...", e)
            try:
                self._camera = dxcam.create(output_color="BGR")
                frame = self._camera.grab(region=region_clamped, new_frame_only=False)
            except Exception as e2:
                logger.error("DXcam grab failed even after recreation: %s", e2)
                frame = None

        if frame is None:
            # Fallback to last successful frame if available
            if self._last_frame is not None:
                target_shape = (b - t, r - l, 3)
                if self._last_frame.shape == target_shape:
                    return self._last_frame

            logger.warning("DXcam returned None frame; returning black placeholder.")
            return np.zeros((b - t, r - l, 3), dtype=np.uint8)

        # If the frame is smaller than the requested client region (due to clamping),
        # pad it with black pixels so that coordinates remain 1:1 with the game client.
        target_w = r - l
        target_h = b - t
        if frame.shape[1] != target_w or frame.shape[0] != target_h:
            padded_frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            offset_x = l_clamp - l
            offset_y = t_clamp - t
            h_grab = frame.shape[0]
            w_grab = frame.shape[1]
            # Ensure we don't go out of bounds if frame shape is somehow anomalous
            max_h = min(h_grab, target_h - offset_y)
            max_w = min(w_grab, target_w - offset_x)
            if max_h > 0 and max_w > 0:
                padded_frame[offset_y:offset_y+max_h, offset_x:offset_x+max_w] = frame[:max_h, :max_w]
            frame = padded_frame

        self._last_frame = frame
        return frame

    # ------------------------------------------------------------------
    # Private — BitBlt path
    # ------------------------------------------------------------------

    def _grab_bitblt(self) -> np.ndarray:
        """Grabs a frame using Windows GDI BitBlt (PrintWindow-compatible path)."""
        hwnd = find_window_by_title(self._window_title)
        if not hwnd:
            raise RuntimeError(
                f"Game window not found: '{self._window_title}'. "
                "Make sure Priston Tale is running."
            )

        left, top, right, bottom = get_client_rect_screen(hwnd)
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

