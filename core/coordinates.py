"""
core/coordinates.py

Translates normalized ratio coordinates (0.0 to 1.0) to screen pixel coordinates,
taking window positions, title bars, and offsets into account.
All calculations are relative to the active client area of the game.
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Windows-only imports — guarded for non-Windows test environments
# ---------------------------------------------------------------------------
try:
    import win32gui
    import ctypes
    _HAS_WIN32 = True
    try:
        # Prevent Windows Display Scaling from altering screen coordinate calculations
        ctypes.windll.user32.SetProcessDPIAware()
    except AttributeError:
        pass
except ImportError:
    _HAS_WIN32 = False
    logger.warning("pywin32 not available — coordinates module operating in mock mode.")


def find_window_by_title(title: str) -> int:
    """
    Returns the HWND of the first window whose title contains `title` (case-insensitive).

    Args:
        title (str): Substring to search for in window titles.

    Returns:
        int: Window handle (HWND). 0 if not found or not on Windows.
    """
    if not _HAS_WIN32:
        return 0

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
        # Stop iteration in pywin32 occasionally raises a false-positive exception
        if not found:
            raise

    return found


def get_client_rect_screen(hwnd: int) -> Tuple[int, int, int, int]:
    """
    Returns the client area bounding box (left, top, right, bottom) in absolute screen coordinates.

    Args:
        hwnd (int): Window handle.

    Returns:
        Tuple[int, int, int, int]: (left, top, right, bottom) screen pixels.
    """
    if not _HAS_WIN32 or hwnd == 0:
        # Default mock size for test compatibility
        return 100, 100, 900, 700

    rect = win32gui.GetClientRect(hwnd)          # (0, 0, w, h) in client coords
    left_top = win32gui.ClientToScreen(hwnd, (rect[0], rect[1]))
    right_bottom = win32gui.ClientToScreen(hwnd, (rect[2], rect[3]))
    return left_top[0], left_top[1], right_bottom[0], right_bottom[1]


def ratio_to_screen(x_ratio: float, y_ratio: float, hwnd: int) -> Tuple[int, int]:
    """
    Converts ratio coordinates relative to the game client area (0.0 - 1.0)
    to absolute screen pixels, accounting for title-bars and window borders.

    Args:
        x_ratio (float): Horizontal ratio (0.0 to 1.0).
        y_ratio (float): Vertical ratio (0.0 to 1.0).
        hwnd (int): Window handle of the game.

    Returns:
        Tuple[int, int]: (x, y) coordinates on the screen.
    """
    left, top, right, bottom = get_client_rect_screen(hwnd)
    width = right - left
    height = bottom - top

    # Clamp ratios to valid bounds [0.0, 1.0] to prevent moving mouse outside client area
    x_ratio = max(0.0, min(1.0, x_ratio))
    y_ratio = max(0.0, min(1.0, y_ratio))

    screen_x = left + int(x_ratio * width)
    screen_y = top + int(y_ratio * height)
    return screen_x, screen_y


def get_client_rect_and_region(hwnd: int) -> Tuple[int, int, int, int]:
    """
    Legacy compatibility function. Returns client region as (left, top, width, height).

    Args:
        hwnd (int): Window handle.

    Returns:
        Tuple[int, int, int, int]: (left, top, width, height) of the client region.
    """
    left, top, right, bottom = get_client_rect_screen(hwnd)
    return left, top, (right - left), (bottom - top)


def activate_window(hwnd: int) -> bool:
    """
    Brings the specified window to the foreground.

    Args:
        hwnd (int): Window handle.

    Returns:
        bool: True if successful, False otherwise.
    """
    if not _HAS_WIN32 or hwnd == 0:
        return False
    
    try:
        import win32con
        import win32gui
        import ctypes
        
        # Press and release ALT to bypass Windows foreground lock
        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
        
        # Restore the window if it's minimized
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        # Bring it to the foreground
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception as e:
        logger.error("Failed to activate window: %s", e)
        return False
