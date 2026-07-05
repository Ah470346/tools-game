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

from .input_base import IInputBackend
from core.coordinates import find_window_by_title, ratio_to_screen

logger = logging.getLogger(__name__)

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
        self._window_title = window_title

    def _get_hwnd_or_raise(self) -> int:
        """Finds game window handle or raises RuntimeError."""
        hwnd = find_window_by_title(self._window_title)
        if not hwnd:
            raise RuntimeError(
                f"Game window not found: '{self._window_title}'. "
                "Make sure Priston Tale is running and not minimized."
            )
        return hwnd

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
        if not _HAS_PYDIRECTINPUT:
            logger.debug("[MOCK] DirectInput.move(%.3f, %.3f)", x_ratio, y_ratio)
            return

        hwnd = self._get_hwnd_or_raise()
        screen_x, screen_y = ratio_to_screen(x_ratio, y_ratio, hwnd)
        logger.debug("DirectInput.move: ratio(%.3f, %.3f) -> screen(%d, %d)", x_ratio, y_ratio, screen_x, screen_y)
        pydirectinput.moveTo(screen_x, screen_y)

    def click(self, x_ratio: float, y_ratio: float, button: str = "left") -> None:
        """
        Clicks at the normalized ratio coordinates.

        Args:
            x_ratio (float): X coordinate ratio (0.0 - 1.0)
            y_ratio (float): Y coordinate ratio (0.0 - 1.0)
            button (str): Mouse button to click ('left', 'right', 'middle')
        """
        if not _HAS_PYDIRECTINPUT:
            logger.debug("[MOCK] DirectInput.click(%.3f, %.3f, %s)", x_ratio, y_ratio, button)
            return

        hwnd = self._get_hwnd_or_raise()
        screen_x, screen_y = ratio_to_screen(x_ratio, y_ratio, hwnd)
        logger.debug("DirectInput.click: ratio(%.3f, %.3f) -> screen(%d, %d) button=%s", x_ratio, y_ratio, screen_x, screen_y, button)
        pydirectinput.click(screen_x, screen_y, button=button)

    def key(self, name: str, action: str = "press") -> None:
        """
        Simulates keyboard input.

        Args:
            name (str): Key name (e.g. 'space', '1', 'f12')
            action (str): Keyboard action ('press', 'down', 'up')
        """
        if not _HAS_PYDIRECTINPUT:
            logger.debug("[MOCK] DirectInput.key(%s, %s)", name, action)
            return

        logger.debug("DirectInput.key: key=%s, action=%s", name, action)
        if action == "press":
            pydirectinput.press(name)
        elif action == "down":
            pydirectinput.keyDown(name)
        elif action == "up":
            pydirectinput.keyUp(name)
        else:
            raise ValueError(f"Unknown key action: {action}")
