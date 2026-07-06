"""
tests/test_train_yolo.py

Unit tests for scripts/train_yolo.py.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import train_yolo


def test_train_yolo_missing_data_exits() -> None:
    """Verifies that the script exits with status 1 if data.yaml does not exist."""
    test_args = ["train_yolo.py", "--data", "non_existent_data.yaml"]
    
    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit) as ex:
            train_yolo.main()
        assert ex.value.code == 1


@patch("scripts.train_yolo.Path.exists")
def test_train_yolo_success(mock_exists: MagicMock) -> None:
    """Verifies that the script executes training successfully when config exists."""
    # Mock data.yaml exists check
    mock_exists.return_value = True

    # Setup mock YOLO class and model
    mock_yolo_class = MagicMock()
    mock_model = MagicMock()
    mock_results = MagicMock()
    mock_results.results_dict = {
        "metrics/mAP50(B)": 0.88,
        "metrics/mAP50-95(B)": 0.55
    }
    mock_model.train.return_value = mock_results
    mock_yolo_class.return_value = mock_model

    # Create a mock module structure for ultralytics
    mock_ultralytics = MagicMock()
    mock_ultralytics.YOLO = mock_yolo_class

    test_args = [
        "train_yolo.py",
        "--data", "data/dataset/data.yaml",
        "--epochs", "5",
        "--imgsz", "640",
        "--batch", "4",
        "--device", "cpu",
        "--project", "runs/test_detect",
        "--name", "test_run"
    ]

    with patch.object(sys, "argv", test_args):
        with patch.dict(sys.modules, {"ultralytics": mock_ultralytics}):
            train_yolo.main()
        
        mock_yolo_class.assert_called_once_with("yolov8n.pt")
        mock_model.train.assert_called_once()
        train_kwargs = mock_model.train.call_args[1]
        
        assert train_kwargs["epochs"] == 5
        assert train_kwargs["imgsz"] == 640
        assert train_kwargs["batch"] == 4
        assert train_kwargs["device"] == "cpu"
        assert train_kwargs["project"] == str(Path("runs/test_detect").resolve())
        assert train_kwargs["name"] == "test_run"


@patch("scripts.train_yolo.Path.exists")
def test_train_yolo_missing_ultralytics(mock_exists: MagicMock) -> None:
    """Verifies that the script logs an error and exits if ultralytics is missing."""
    mock_exists.return_value = True

    test_args = ["train_yolo.py", "--data", "data/dataset/data.yaml"]

    with patch.object(sys, "argv", test_args):
        # Mock sys.modules to simulate ultralytics not being installed
        with patch.dict(sys.modules, {"ultralytics": None}):
            # Since sys.exit is not mocked, it should raise SystemExit(1)
            with pytest.raises(SystemExit) as ex:
                train_yolo.main()
            assert ex.value.code == 1

