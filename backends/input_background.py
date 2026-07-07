"""
backends/input_background.py

Concrete implementation of IInputBackend for Windows Background Control mode.
Sends simulated inputs to the game via standard Windows messages (PostMessage)
so that it does not hijack the physical mouse cursor, allowing multiple tabs to run.
"""

import logging
import time
import ctypes

from .input_base import IInputBackend
from core.coordinates import find_window_by_title
from core.humanizer import get_random_delay, add_jitter_ratio

logger = logging.getLogger(__name__)

# Optional Windows-only imports
try:
    import win32gui
    import win32con
    import win32api
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False
    logger.warning("pywin32 not available — BackgroundInput operating in mock mode.")


class BackgroundInput(IInputBackend):
    """
    Background input simulation backend utilizing PostMessage.
    Sends inputs directly to the window handle without taking cursor focus.
    """

    def __init__(self, window_title: str = "Priston Tale") -> None:
        """
        Initializes the background input simulation backend.

        Args:
            window_title (str): Substring of the game window title.
        """
        super().__init__()
        self._window_title = window_title

    def _get_hwnd_or_raise(self) -> int:
        """Finds game window handle or raises RuntimeError."""
        hwnd = find_window_by_title(self._window_title)
        if not hwnd:
            raise RuntimeError(
                f"Game window not found: '{self._window_title}'. "
                "Make sure Priston Tale is running."
            )
        return hwnd

    def _ratio_to_client(self, x_ratio: float, y_ratio: float, hwnd: int) -> tuple[int, int]:
        """Converts normalized ratios to window client coordinates."""
        if not _HAS_WIN32:
            return int(x_ratio * 800), int(y_ratio * 600)
            
        rect = win32gui.GetClientRect(hwnd)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        
        x_ratio = max(0.0, min(1.0, x_ratio))
        y_ratio = max(0.0, min(1.0, y_ratio))
        
        return int(x_ratio * width), int(y_ratio * height)

    def _char_to_vk(self, char: str) -> int:
        """Converts a character or key name to a Virtual Key (VK) code."""
        char = str(char).lower()
        if len(char) == 1 and 'a' <= char <= 'z':
            return ord(char.upper())
        elif len(char) == 1 and '0' <= char <= '9':
            return ord(char)
        elif char == 'space':
            return win32con.VK_SPACE
        elif char == 'tab':
            return win32con.VK_TAB
        elif char == 'enter':
            return win32con.VK_RETURN
        elif char == 'esc' or char == 'escape':
            return win32con.VK_ESCAPE
        elif char.startswith('f') and len(char) > 1 and char[1:].isdigit():
            # F1-F12
            f_num = int(char[1:])
            if 1 <= f_num <= 12:
                return win32con.VK_F1 + f_num - 1
        
        # Default to ord if no mapping found (may not be valid for all keys)
        return ord(char.upper()) if len(char) == 1 else 0

    # ------------------------------------------------------------------
    # IInputBackend
    # ------------------------------------------------------------------

    def move(self, x_ratio: float, y_ratio: float) -> None:
        """
        Moves the virtual cursor to normalized ratio coordinates using PostMessage.
        """
        if self.block_inputs:
            logger.debug("BackgroundInput.move blocked")
            return

        if not _HAS_WIN32:
            logger.debug("[MOCK] BackgroundInput.move(%.3f, %.3f)", x_ratio, y_ratio)
            return

        hwnd = self._get_hwnd_or_raise()
        cx, cy = self._ratio_to_client(x_ratio, y_ratio, hwnd)
        logger.debug("BackgroundInput.move: ratio(%.3f, %.3f) -> client(%d, %d)", x_ratio, y_ratio, cx, cy)
        
        lParam = (cy << 16) | cx
        win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lParam)

    def click(self, x_ratio: float, y_ratio: float, button: str = "left") -> None:
        """
        Clicks at the normalized ratio coordinates using PostMessage.
        """
        if self.block_inputs:
            logger.debug("BackgroundInput.click blocked")
            return

        if not _HAS_WIN32:
            logger.debug("[MOCK] BackgroundInput.click(%.3f, %.3f, %s)", x_ratio, y_ratio, button)
            return

        hwnd = self._get_hwnd_or_raise()
        # Add random jitter to coordinates
        j_x, j_y = add_jitter_ratio(x_ratio, y_ratio, max_pixels=5)
        cx, cy = self._ratio_to_client(j_x, j_y, hwnd)
        
        logger.debug("BackgroundInput.click: ratio(%.3f, %.3f) -> client(%d, %d) button=%s", j_x, j_y, cx, cy, button)
        self.key_history.append(f"click_{button}({j_x:.2f},{j_y:.2f})")
        
        lParam = (cy << 16) | cx
        
        # Move first
        win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lParam)
        time.sleep(get_random_delay(0.04, 0.08))
        
        if button == "left":
            win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
            time.sleep(get_random_delay(0.08, 0.15))
            win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)
        elif button == "right":
            win32gui.PostMessage(hwnd, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lParam)
            time.sleep(get_random_delay(0.08, 0.15))
            win32gui.PostMessage(hwnd, win32con.WM_RBUTTONUP, 0, lParam)
        elif button == "middle":
            win32gui.PostMessage(hwnd, win32con.WM_MBUTTONDOWN, win32con.MK_MBUTTON, lParam)
            time.sleep(get_random_delay(0.08, 0.15))
            win32gui.PostMessage(hwnd, win32con.WM_MBUTTONUP, 0, lParam)

    def key(self, name: str, action: str = "press") -> None:
        """
        Simulates keyboard input using PostMessage.
        """
        if self.block_inputs and action != "up":
            logger.debug("BackgroundInput.key blocked: key=%s, action=%s", name, action)
            return

        if action == "down":
            self.pressed_keys.add(name)
        elif action == "up":
            self.pressed_keys.discard(name)

        self.key_history.append(f"{name}_{action}")

        if not _HAS_WIN32:
            logger.debug("[MOCK] BackgroundInput.key(%s, %s)", name, action)
            return

        hwnd = self._get_hwnd_or_raise()
        vk_code = self._char_to_vk(name)
        
        if vk_code == 0:
            logger.warning("BackgroundInput: Could not map key '%s' to VK code.", name)
            return

        logger.debug("BackgroundInput.key: key=%s (VK: 0x%X), action=%s", name, vk_code, action)
        
        scan_code = win32api.MapVirtualKey(vk_code, 0)
        lParam_down = 1 | (scan_code << 16)
        lParam_up = 1 | (scan_code << 16) | (1 << 30) | (1 << 31)

        if action == "press":
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, lParam_down)
            time.sleep(get_random_delay(0.08, 0.15))
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, lParam_up)
        elif action == "down":
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, lParam_down)
        elif action == "up":
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, lParam_up)
        else:
            raise ValueError(f"Unknown key action: {action}")
