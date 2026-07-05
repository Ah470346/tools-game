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
            name (str): Key name/character (e.g. 'space', '1', 'f12')
            action (str): Keyboard action ('press', 'down', 'up')
        """
        pass
