"""
backends/input_direct.py

Concrete implementation of IInputBackend for Windows Direct Control mode.
Sends simulated inputs directly to the game via standard Windows APIs (pydirectinput/SendInput).
All coordinates received are normalized ratios (0.0 to 1.0) and are mapped to screen pixels
using the client area metrics via core/coordinates.py.

NOTE: This module is the only input module that imports pydirectinput directly.
      core/, features/, and vision/ must never import this library.
"""

import logging
import time
import ctypes

from .input_base import IInputBackend
from core.coordinates import find_window_by_title, ratio_to_screen
from core.humanizer import generate_bezier_path, get_random_delay, add_jitter_ratio

logger = logging.getLogger(__name__)


def is_admin() -> bool:
    """Checks if the script is running with administrator privileges on Windows."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Optional Windows-only imports — guarded so the module can be imported on
# any OS (tests run on macOS/Linux CI without pydirectinput installed).
# ---------------------------------------------------------------------------
try:
    import pydirectinput
    # Disable pydirectinput fail-safe because it can throw exceptions when mouse
    # reaches corners of screen, which is common in automation.
    pydirectinput.FAILSAFE = False
    _HAS_PYDIRECTINPUT = True
except ImportError:
    pydirectinput = None  # type: ignore[assignment]
    _HAS_PYDIRECTINPUT = False
    logger.warning("pydirectinput not available — DirectInput backend operating in mock mode.")


# --- Ctypes structures for SendInput (cross-platform safe definitions) ---
class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort)
    ]

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class Input_I(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput)
    ]

class Input(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ii", Input_I)
    ]


class DirectInput(IInputBackend):
    """
    Direct input simulation backend utilizing pydirectinput.
    """

    def __init__(self, window_title: str = "Priston Tale") -> None:
        """
        Initializes the direct input simulation backend.

        Args:
            window_title (str): Substring of the game window title.
        """
        super().__init__()
        self._window_title = window_title
        if not is_admin():
            logger.warning(
                "[WARNING] Script is NOT running as Administrator! "
                "Games protected by GameGuard (like Priston Tale) run with elevated privileges. "
                "If this script is not elevated, Windows UIPI will silently block all simulated mouse/keyboard inputs. "
                "Please run the terminal as Administrator."
            )


    def _get_hwnd_or_raise(self) -> int:
        """Finds game window handle or raises RuntimeError."""
        hwnd = find_window_by_title(self._window_title)
        if not hwnd:
            raise RuntimeError(
                f"Game window not found: '{self._window_title}'. "
                "Make sure Priston Tale is running and not minimized."
            )
        return hwnd

    def _send_input_move(self, screen_x: int, screen_y: int) -> None:
        """
        Moves the mouse cursor to absolute screen coordinates using SendInput API
        mapped to the virtual desktop space to handle multiple monitors and DPI scaling.
        """
        # Get virtual screen metrics
        # SM_XVIRTUALSCREEN = 76, SM_YVIRTUALSCREEN = 77
        # SM_CXVIRTUALSCREEN = 78, SM_CYVIRTUALSCREEN = 79
        v_left = ctypes.windll.user32.GetSystemMetrics(76)
        v_top = ctypes.windll.user32.GetSystemMetrics(77)
        v_width = ctypes.windll.user32.GetSystemMetrics(78)
        v_height = ctypes.windll.user32.GetSystemMetrics(79)

        if v_width == 0 or v_height == 0:
            v_left = 0
            v_top = 0
            v_width = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
            v_height = ctypes.windll.user32.GetSystemMetrics(1) # SM_CYSCREEN

        # Normalize coordinates to 0 - 65535 absolute range mapping to virtual desktop
        dx = int((screen_x - v_left) * 65535 / max(1, v_width - 1))
        dy = int((screen_y - v_top) * 65535 / max(1, v_height - 1))

        INPUT_MOUSE = 0
        MOUSEEVENTF_MOVE = 0x0001
        MOUSEEVENTF_ABSOLUTE = 0x8000
        MOUSEEVENTF_VIRTUALDESK = 0x4000

        extra = ctypes.c_ulong(0)
        ii_ = Input_I()
        ii_.mi = MouseInput(
            dx,
            dy,
            0,
            MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
            0,
            ctypes.pointer(extra)
        )
        x_input = Input(INPUT_MOUSE, ii_)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))

    # ------------------------------------------------------------------
    # IInputBackend
    # ------------------------------------------------------------------

    def move(self, x_ratio: float, y_ratio: float) -> None:
        """
        Moves the mouse cursor to normalized ratio coordinates.

        Args:
            x_ratio (float): X coordinate ratio (0.0 - 1.0)
            y_ratio (float): Y coordinate ratio (0.0 - 1.0)
        """
        if self.block_inputs:
            logger.debug("DirectInput.move blocked")
            return

        if not _HAS_PYDIRECTINPUT:
            logger.debug("[MOCK] DirectInput.move(%.3f, %.3f)", x_ratio, y_ratio)
            return

        hwnd = self._get_hwnd_or_raise()
        screen_x, screen_y = ratio_to_screen(x_ratio, y_ratio, hwnd)
        logger.debug("DirectInput.move: ratio(%.3f, %.3f) -> screen(%d, %d)", x_ratio, y_ratio, screen_x, screen_y)
        
        import sys
        if sys.platform == "win32":
            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            path = generate_bezier_path((pt.x, pt.y), (screen_x, screen_y), steps=12)
            
            for px, py in path:
                self._send_input_move(px, py)
                time.sleep(get_random_delay(0.001, 0.005))
                
            time.sleep(0.05)
            # Tiny mouse_event jiggle (relative) to force the game to register hover state
            MOUSEEVENTF_MOVE = 0x0001
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, 1, 1, 0, 0)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, ctypes.c_ulong(-1), ctypes.c_ulong(-1), 0, 0)
        else:
            pydirectinput.moveTo(screen_x, screen_y)

    def click(self, x_ratio: float, y_ratio: float, button: str = "left") -> None:
        """
        Clicks at the normalized ratio coordinates.

        Args:
            x_ratio (float): X coordinate ratio (0.0 - 1.0)
            y_ratio (float): Y coordinate ratio (0.0 - 1.0)
            button (str): Mouse button to click ('left', 'right', 'middle')
        """
        if self.block_inputs:
            logger.debug("DirectInput.click blocked")
            return

        if not _HAS_PYDIRECTINPUT:
            logger.debug("[MOCK] DirectInput.click(%.3f, %.3f, %s)", x_ratio, y_ratio, button)
            return

        hwnd = self._get_hwnd_or_raise()
        # Add random jitter to coordinates
        j_x, j_y = add_jitter_ratio(x_ratio, y_ratio, max_pixels=5)
        screen_x, screen_y = ratio_to_screen(j_x, j_y, hwnd)
        logger.debug("DirectInput.click: ratio(%.3f, %.3f) -> screen(%d, %d) button=%s", j_x, j_y, screen_x, screen_y, button)
        self.key_history.append(f"click_{button}({j_x:.2f},{j_y:.2f})")
        
        import sys
        if sys.platform == "win32":
            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            path = generate_bezier_path((pt.x, pt.y), (screen_x, screen_y), steps=8)
            
            for px, py in path:
                self._send_input_move(px, py)
                time.sleep(get_random_delay(0.001, 0.004))
                
            time.sleep(get_random_delay(0.02, 0.06))
            pydirectinput.mouseDown(button=button)
            time.sleep(get_random_delay(0.04, 0.12))
            pydirectinput.mouseUp(button=button)
        else:
            pydirectinput.mouseDown(x=screen_x, y=screen_y, button=button)
            time.sleep(0.1)
            pydirectinput.mouseUp(x=screen_x, y=screen_y, button=button)

    def key(self, name: str, action: str = "press") -> None:
        """
        Simulates keyboard input.

        Args:
            name (str): Key name (e.g. 'v' to toggle inventory, '1', 'f12')
            action (str): Keyboard action ('press', 'down', 'up')
        """
        if self.block_inputs and action != "up":
            logger.debug("DirectInput.key blocked: key=%s, action=%s", name, action)
            return

        if action == "down":
            self.pressed_keys.add(name)
        elif action == "up":
            self.pressed_keys.discard(name)

        self.key_history.append(f"{name}_{action}")

        if not _HAS_PYDIRECTINPUT:
            logger.debug("[MOCK] DirectInput.key(%s, %s)", name, action)
            return

        logger.debug("DirectInput.key: key=%s, action=%s", name, action)
        if action == "press":
            pydirectinput.keyDown(name)
            time.sleep(get_random_delay(0.04, 0.12))
            pydirectinput.keyUp(name)
        elif action == "down":
            pydirectinput.keyDown(name)
        elif action == "up":
            pydirectinput.keyUp(name)
        else:
            raise ValueError(f"Unknown key action: {action}")
