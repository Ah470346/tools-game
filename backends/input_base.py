"""
backends/input_base.py

This module defines the abstract interface for the simulated input backend.
All coordinates accepted by this interface are normalized ratios (0.0 to 1.0)
relative to the game client's active window area.
"""

from abc import ABC, abstractmethod


class IInputBackend(ABC):
    """
    Abstract Base Class for input simulation backends.
    Ensures absolute separation between input logic (e.g. pydirectinput, Interception, Arduino)
    and engine features.
    """

    def __init__(self) -> None:
        """Initializes the base input backend, tracking pressed keys and blocking status."""
        self.pressed_keys: set[str] = set()
        self.block_inputs: bool = False
        self.key_history: list[str] = []

    def release_all(self) -> None:
        """
        Releases all currently held/pressed keyboard keys.
        """
        keys_to_release = list(self.pressed_keys)
        self.pressed_keys.clear()
        for key_name in keys_to_release:
            # We call self.key bypassing block_inputs if necessary, but
            # self.key should generally allow release actions if we clear pressed_keys first
            # or if key checks action == 'up' or similar.
            # To be absolutely sure, we run key simulation directly.
            self.key(key_name, "up")

    @abstractmethod
    def move(self, x_ratio: float, y_ratio: float) -> None:
        """
        Moves the mouse cursor to the normalized coordinates.

        Args:
            x_ratio (float): X coordinate ratio (0.0 - 1.0)
            y_ratio (float): Y coordinate ratio (0.0 - 1.0)
        """
        pass

    @abstractmethod
    def click(self, x_ratio: float, y_ratio: float, button: str = "left") -> None:
        """
        Clicks at the normalized coordinates.

        Args:
            x_ratio (float): X coordinate ratio (0.0 - 1.0)
            y_ratio (float): Y coordinate ratio (0.0 - 1.0)
            button (str): Mouse button to click ('left', 'right', 'middle')
        """
        pass

    @abstractmethod
    def key(self, name: str, action: str = "press") -> None:
        """
        Simulates keyboard input.

        Args:
            name (str): Key name/character (e.g. 'v' to toggle inventory, '1', 'f12')
            action (str): Keyboard action ('press', 'down', 'up')
        """
        pass
