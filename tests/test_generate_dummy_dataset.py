"""
tests/test_generate_dummy_dataset.py

Unit test for scripts/generate_dummy_dataset.py.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import generate_dummy_dataset


def test_generate_dummy_dataset_files() -> None:
    """Verifies the folder structure and data.yaml creation in dummy generation."""
    with patch("scripts.generate_dummy_dataset.Path.mkdir") as mock_mkdir, \
         patch("builtins.open", mock_open=True) as mock_file, \
         patch("cv2.imwrite") as mock_imwrite:
        
        generate_dummy_dataset.create_dummy_dataset()
        
        # Verify directories creation was triggered
        assert mock_mkdir.call_count >= 4
        # Verify writing data.yaml and labels
        assert mock_file.call_count >= 11
        # Verify mock_imwrite generated 10 images (8 train + 2 val)
        assert mock_imwrite.call_count == 10
