"""
backends/input_direct.py

Concrete implementation of IInputBackend.
Sends simulated inputs directly to the game via standard Windows APIs (pydirectinput/SendInput).
"""

from .input_base import IInputBackend


class DirectInput(IInputBackend):
    """
    Direct input simulation backend utilizing pydirectinput or SendInput.
    """

    def __init__(self) -> None:
        """Initializes the direct input simulation backend."""
        pass

    def move(self, x_ratio: float, y_ratio: float) -> None:
        """Moves the mouse to target ratio coordinates."""
        pass

    def click(self, x_ratio: float, y_ratio: float, button: str = "left") -> None:
        """Clicks at target ratio coordinates."""
        pass

    def key(self, name: str, action: str = "press") -> None:
        """Sends key event to the game window."""
        pass
