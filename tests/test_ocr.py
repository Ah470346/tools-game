"""
tests/test_ocr.py

Unit tests for vision/ocr.py.
Verifies parsing of OCR text values from simulated Tesseract outputs.
"""

import sys
import os
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vision.ocr import TextReader


@pytest.fixture
def mock_pytesseract():
    """Fixture to mock pytesseract."""
    mock_pt = MagicMock()
    with patch.dict(sys.modules, {"pytesseract": mock_pt}):
        yield mock_pt


def test_ocr_reader_initialization(mock_pytesseract) -> None:
    """Verifies OCR initialization properties."""
    reader = TextReader(tesseract_path="C:\\mock_tesseract.exe")
    assert reader.tesseract_cmd == "C:\\mock_tesseract.exe"
    assert reader.enabled is True
    assert mock_pytesseract.pytesseract.tesseract_cmd == "C:\\mock_tesseract.exe"


def test_ocr_reader_disabled_when_import_fails() -> None:
    """Verifies that the reader disables gracefully if pytesseract fails to import."""
    with patch.dict(sys.modules, {"pytesseract": None}):
        reader = TextReader()
        assert reader.enabled is False
        assert reader.read_values(np.zeros((10, 10), dtype=np.uint8)) is None


def test_ocr_reader_parsing(mock_pytesseract) -> None:
    """Verifies text extraction parsing logic under various mock text outputs."""
    reader = TextReader()
    assert reader.enabled is True

    dummy_roi = np.zeros((20, 50, 3), dtype=np.uint8)

    # Test case 1: Standard spaced slash
    mock_pytesseract.image_to_string.return_value = " 1200 / 3000 \n"
    res = reader.read_values(dummy_roi)
    assert res == (1200, 3000)

    # Test case 2: Tight slash
    mock_pytesseract.image_to_string.return_value = "150/450"
    res = reader.read_values(dummy_roi)
    assert res == (150, 450)

    # Test case 3: Single digit values
    mock_pytesseract.image_to_string.return_value = "7/8"
    res = reader.read_values(dummy_roi)
    assert res == (7, 8)

    # Test case 4: Missing slash -> should fail and return None
    mock_pytesseract.image_to_string.return_value = "1200"
    res = reader.read_values(dummy_roi)
    assert res is None

    # Test case 5: Garbage text -> should fail
    mock_pytesseract.image_to_string.return_value = "abc / def"
    res = reader.read_values(dummy_roi)
    assert res is None

    # Test case 6: Empty text -> should fail
    mock_pytesseract.image_to_string.return_value = ""
    res = reader.read_values(dummy_roi)
    assert res is None
