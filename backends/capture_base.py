"""
backends/capture_base.py

This module defines the abstract interface for the screen capture backend.
All concrete capture implementations must inherit from ICaptureBackend.
"""

from abc import ABC, abstractmethod
import numpy as np


class ICaptureBackend(ABC):
    """
    Abstract Base Class for capture backends.
    Allows swapping capture methods (Direct DXcam, Session, etc.) without altering core logic.
    """

    @abstractmethod
    def grab_frame(self) -> np.ndarray:
        """
        Captures a single frame of the game client.

        Returns:
            np.ndarray: The captured frame as a BGR numpy array.
        """
        pass
