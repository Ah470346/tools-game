"""
vision/ocr.py

Utilizes optical character recognition (OCR) to read numerical HP, MP, and STM text values 
from designated UI coordinate boxes.
"""

import numpy as np
from typing import Optional, Tuple


class TextReader:
    """
    OCR utility for reading game status numbers (e.g. "x/y" HP/MP metrics).
    """

    def __init__(self) -> None:
        """Initializes the OCR engine."""
        pass

    def read_values(self, roi: np.ndarray) -> Optional[Tuple[int, int]]:
        """
        Reads fractional values (e.g. current/max status) from a region of interest.

        Args:
            roi (np.ndarray): Image region showing HP/MP values.

        Returns:
            Optional[Tuple[int, int]]: Parsed current and maximum values, or None if failed.
        """
        # Placeholder implementation
        return None
