"""
backends/mock_backends.py

Mock implementations of ICaptureBackend and IInputBackend for use in unit tests
and offline development. These allow testing engine logic without a real game window.
"""

import logging
from typing import List, Tuple

import numpy as np

from backends.capture_base import ICaptureBackend
from backends.input_base import IInputBackend

logger = logging.getLogger(__name__)


class MockCapture(ICaptureBackend):
    """
    Mock capture backend returning a fixed black frame.
    Used for testing pipeline logic without a real screen source.
    """

    FRAME_HEIGHT: int = 600
    FRAME_WIDTH: int = 800

    def grab_frame(self) -> np.ndarray:
        """
        Returns a black BGR frame of fixed dimensions.

        Returns:
            np.ndarray: A 600×800×3 zero-filled numpy array (black frame).
        """
        return np.zeros((self.FRAME_HEIGHT, self.FRAME_WIDTH, 3), dtype=np.uint8)


class MockInput(IInputBackend):
    """
    Mock input backend that logs all commands instead of sending real OS input.
    Useful for verifying FSM/feature code calls the correct input methods in order.
    """

    def __init__(self) -> None:
        """Initializes the log of recorded commands."""
        self.log: List[Tuple] = []

    def move(self, x_ratio: float, y_ratio: float) -> None:
        """
        Records a mouse-move command.

        Args:
            x_ratio (float): X ratio (0.0 – 1.0).
            y_ratio (float): Y ratio (0.0 – 1.0).
        """
        entry = ("move", x_ratio, y_ratio)
        self.log.append(entry)
        logger.debug("MockInput.move(%.3f, %.3f)", x_ratio, y_ratio)

    def click(self, x_ratio: float, y_ratio: float, button: str = "left") -> None:
        """
        Records a mouse-click command.

        Args:
            x_ratio (float): X ratio (0.0 – 1.0).
            y_ratio (float): Y ratio (0.0 – 1.0).
            button (str): Mouse button ('left', 'right', 'middle').
        """
        entry = ("click", x_ratio, y_ratio, button)
        self.log.append(entry)
        logger.debug("MockInput.click(%.3f, %.3f, %s)", x_ratio, y_ratio, button)

    def key(self, name: str, action: str = "press") -> None:
        """
        Records a keyboard command.

        Args:
            name (str): Key name (e.g. 'space', 'f12').
            action (str): 'press', 'down', or 'up'.
        """
        entry = ("key", name, action)
        self.log.append(entry)
        logger.debug("MockInput.key(%s, %s)", name, action)

    def clear(self) -> None:
        """Clears the recorded command log."""
        self.log.clear()
