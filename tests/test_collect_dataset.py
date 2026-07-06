"""
tests/test_collect_dataset.py

Unit tests for scripts/collect_dataset.py.
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import collect_dataset


def test_load_settings() -> None:
    """Verifies settings load correctly (either mock or empty)."""
    with patch("builtins.open", mock_open=True) as mock_file:
        with patch("json.load", return_value={"window_title": "Test Game Window"}):
            settings = collect_dataset.load_settings()
            assert settings.get("window_title") == "Test Game Window"


def test_dataset_collector_init() -> None:
    """Verifies DatasetCollector initial state."""
    collector = collect_dataset.DatasetCollector(
        window_title="Test Window",
        output_dir="data/test_raw",
        interval=2.0,
        hotkey="f7"
    )
    assert collector.window_title == "Test Window"
    assert collector.output_dir == Path("data/test_raw")
    assert collector.interval == 2.0
    assert collector.hotkey == "f7"
    assert not collector.active
    assert collector.total_saved == 0


def test_dataset_collector_toggle() -> None:
    """Verifies toggle_capture switches the active state."""
    collector = collect_dataset.DatasetCollector(
        window_title="Test Window",
        output_dir="data/test_raw",
        interval=2.0,
        hotkey="f7"
    )
    assert not collector.active
    collector.toggle_capture()
    assert collector.active
    collector.toggle_capture()
    assert not collector.active


@patch("scripts.collect_dataset.DirectCapture")
@patch("keyboard.add_hotkey")
def test_dataset_collector_setup(mock_add_hotkey: MagicMock, mock_direct_capture: MagicMock) -> None:
    """Verifies setup initializes output directory, backend, and hotkeys."""
    collector = collect_dataset.DatasetCollector(
        window_title="Test Window",
        output_dir="data/test_raw_temp",
        interval=2.0,
        hotkey="f7"
    )
    
    # Mock the directory creation so it doesn't actually create a directory in pytest
    with patch.object(Path, "mkdir") as mock_mkdir:
        success = collector.setup()
        assert success
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_direct_capture.assert_called_once_with(window_title="Test Window", prefer_backend="auto")
        mock_add_hotkey.assert_called_once_with("f7", collector.toggle_capture)


@patch("cv2.imwrite")
def test_capture_and_save_success(mock_imwrite: MagicMock) -> None:
    """Verifies capture_and_save saves a frame correctly and increments total_saved."""
    collector = collect_dataset.DatasetCollector(
        window_title="Test Window",
        output_dir="data/test_raw",
        interval=2.0,
        hotkey="f7"
    )
    
    # Mock capture backend
    mock_backend = MagicMock()
    fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_backend.grab_frame.return_value = fake_frame
    collector.capture_backend = mock_backend
    collector.active = True
    
    # Call capture_and_save
    collector.capture_and_save()
    
    assert collector.total_saved == 1
    mock_imwrite.assert_called_once()
    # Check that it saves inside output_dir
    save_path = Path(mock_imwrite.call_args[0][0])
    assert save_path.parent == Path("data/test_raw")
    assert save_path.name.startswith("frame_")
    assert save_path.name.endswith(".png")


def test_capture_and_save_runtime_error_pauses_capture() -> None:
    """Verifies if grab_frame raises RuntimeError, capturing is paused automatically."""
    collector = collect_dataset.DatasetCollector(
        window_title="Test Window",
        output_dir="data/test_raw",
        interval=2.0,
        hotkey="f7"
    )
    
    # Mock capture backend to raise RuntimeError
    mock_backend = MagicMock()
    mock_backend.grab_frame.side_effect = RuntimeError("Window not found")
    collector.capture_backend = mock_backend
    collector.active = True
    
    # Call capture_and_save
    collector.capture_and_save()
    
    # active should be set to False
    assert not collector.active
    assert collector.total_saved == 0
