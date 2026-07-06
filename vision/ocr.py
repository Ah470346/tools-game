"""
vision/ocr.py

Utilizes optical character recognition (OCR) to read numerical HP, MP, and STM text values 
from designated UI coordinate boxes.
"""

import numpy as np
from typing import Optional, Tuple


import logging

logger = logging.getLogger(__name__)


class TextReader:
    """
    OCR utility for reading game status numbers (e.g. "x/y" HP/MP metrics).
    """

    def __init__(self, tesseract_path: Optional[str] = None) -> None:
        """
        Initializes the OCR engine.

        Args:
            tesseract_path (str, optional): Path to the tesseract executable.
        """
        self.tesseract_cmd = tesseract_path
        self.enabled = False

        try:
            import pytesseract
            self.pytesseract = pytesseract
            if self.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
            self.enabled = True
            logger.info("TextReader: OCR engine initialized successfully.")
        except ImportError:
            logger.warning("TextReader: pytesseract is not installed. OCR will be disabled.")
        except Exception as e:
            logger.error("TextReader: Failed to initialize OCR: %s", e)

    def read_values(self, roi: np.ndarray) -> Optional[Tuple[int, int]]:
        """
        Reads fractional values (e.g. current/max status) from a region of interest.

        Args:
            roi (np.ndarray): Image region showing HP/MP values.

        Returns:
            Optional[Tuple[int, int]]: Parsed current and maximum values, or None if failed.
        """
        if not self.enabled or roi is None or roi.size == 0:
            return None

        try:
            import cv2
            # 1. Preprocessing to make text extremely clear for OCR
            # Convert to grayscale if it is BGR
            if len(roi.shape) == 3:
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            else:
                gray = roi.copy()

            # Upscale image to make text bigger (3x cubic interpolation)
            upscaled = cv2.resize(gray, (0, 0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)

            # Apply Otsu's thresholding to get a clean binary (black/white)
            _, thresh = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Tesseract prefers black text on white background.
            # If the background is black, we invert the image.
            border_pixels = np.concatenate([
                thresh[0, :],          # top edge
                thresh[-1, :],         # bottom edge
                thresh[:, 0],          # left edge
                thresh[:, -1]          # right edge
            ])
            if np.mean(border_pixels) < 127:
                # Background is dark, invert to make background white and text black
                thresh = cv2.bitwise_not(thresh)

            # OCR Config:
            # --psm 7: Treat the image as a single text line.
            # tessedit_char_whitelist: only allow digits and slash.
            custom_config = r"--psm 7 -c tessedit_char_whitelist=0123456789/"
            
            # Run Tesseract
            text = self.pytesseract.image_to_string(thresh, config=custom_config).strip()
            logger.debug("TextReader OCR output: '%s'", text)

            if not text:
                return None

            # Parse string
            if "/" not in text:
                return None

            parts = text.split("/")
            if len(parts) == 2:
                current_str = "".join(filter(str.isdigit, parts[0]))
                max_str = "".join(filter(str.isdigit, parts[1]))
                if current_str and max_str:
                    return int(current_str), int(max_str)

            return None
        except Exception as e:
            logger.error("TextReader OCR reading failed: %s", e)
            return None

    def read_text(self, roi: np.ndarray) -> Optional[str]:
        """
        Reads general text from a region of interest (e.g. item names).

        Args:
            roi (np.ndarray): Image region showing text.

        Returns:
            Optional[str]: The parsed string, or None if failed.
        """
        if not self.enabled or roi is None or roi.size == 0:
            return None

        try:
            import cv2
            # 1. Preprocessing
            if len(roi.shape) == 3:
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            else:
                gray = roi.copy()

            # Upscale image
            upscaled = cv2.resize(gray, (0, 0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)

            # Thresholding
            _, thresh = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Invert background if necessary
            border_pixels = np.concatenate([
                thresh[0, :],
                thresh[-1, :],
                thresh[:, 0],
                thresh[:, -1]
            ])
            if np.mean(border_pixels) < 127:
                thresh = cv2.bitwise_not(thresh)

            # OCR Config:
            # General text reading using PSM 7 (single line)
            custom_config = r"--psm 7"
            
            # Run Tesseract
            text = self.pytesseract.image_to_string(thresh, config=custom_config).strip()
            logger.debug("TextReader OCR read_text output: '%s'", text)

            return text if text else None
        except Exception as e:
            logger.error("TextReader read_text failed: %s", e)
            return None

