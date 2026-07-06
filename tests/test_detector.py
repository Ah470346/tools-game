"""
tests/test_detector.py

Unit tests for vision/detector.py.
Tests model initialization, inference caching, and delta threshold checks using mock onnxruntime.
"""

import sys
import os
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vision.detector import MonsterDetector


@pytest.fixture
def mock_ort():
    """Fixture to mock onnxruntime imports and classes."""
    mock_ort = MagicMock()
    mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]
    
    # Mock inputs
    mock_input = MagicMock()
    mock_input.name = "images"
    mock_input.shape = [1, 3, 640, 640]
    
    mock_session = MagicMock()
    mock_session.get_inputs.return_value = [mock_input]
    
    # Mock return values for session.run (1 bounding box at center)
    # Shape: (1, 5, 8400) -> 4 box coordinates + 1 class probability
    dummy_output = np.zeros((1, 5, 8400), dtype=np.float32)
    # Put a mock prediction at index 0
    # xc, yc, w, h
    dummy_output[0, 0, 0] = 320.0
    dummy_output[0, 1, 0] = 320.0
    dummy_output[0, 2, 0] = 60.0
    dummy_output[0, 3, 0] = 60.0
    # Confidence for class 0
    dummy_output[0, 4, 0] = 0.95
    
    mock_session.run.return_value = [dummy_output]
    mock_ort.InferenceSession.return_value = mock_session
    
    # Inject mock into sys.modules
    with patch.dict(sys.modules, {"onnxruntime": mock_ort}):
        yield mock_ort, mock_session


@patch("os.path.exists")
def test_detector_initialization(mock_exists, mock_ort) -> None:
    """Tests that MonsterDetector initializes correctly with ONNX Runtime."""
    mock_exists.return_value = True
    
    detector = MonsterDetector(
        model_path="dummy_monster.onnx",
        conf_threshold=0.5,
        nms_threshold=0.4,
        delta_threshold=0.01
    )
    
    assert detector.model_path == "dummy_monster.onnx"
    assert detector.conf_threshold == 0.5
    assert detector.nms_threshold == 0.4
    assert detector.delta_threshold == 0.01
    assert detector.input_name == "images"
    assert detector.input_width == 640
    assert detector.input_height == 640


@patch("os.path.exists")
def test_detector_inference_no_delta(mock_exists, mock_ort) -> None:
    """Verifies that inference runs every time when delta_threshold is 0.0 (disabled)."""
    mock_exists.return_value = True
    _, mock_session = mock_ort
    
    detector = MonsterDetector(
        model_path="dummy_monster.onnx",
        conf_threshold=0.5,
        nms_threshold=0.4,
        delta_threshold=0.0
    )
    
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # 1st run
    dets1 = detector.detect(frame)
    assert len(dets1) == 1
    assert dets1[0]["confidence"] == pytest.approx(0.95)
    
    # 2nd run with same frame
    dets2 = detector.detect(frame)
    assert len(dets2) == 1
    
    # Should have called session.run twice
    assert mock_session.run.call_count == 2


@patch("os.path.exists")
def test_detector_delta_cache_hit_and_miss(mock_exists, mock_ort) -> None:
    """Verifies cache hits for small delta, and cache misses for large delta/first frame."""
    mock_exists.return_value = True
    _, mock_session = mock_ort
    
    detector = MonsterDetector(
        model_path="dummy_monster.onnx",
        conf_threshold=0.5,
        nms_threshold=0.4,
        delta_threshold=0.02
    )
    
    # Frame 1 (blank frame)
    frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
    dets1 = detector.detect(frame1)
    assert len(dets1) == 1
    assert mock_session.run.call_count == 1
    
    # Frame 2: Identical frame -> Cache Hit -> No call to session.run
    dets2 = detector.detect(frame1)
    assert len(dets2) == 1
    assert mock_session.run.call_count == 1  # Still 1
    
    # Frame 3: Very minor difference (below threshold of 0.02) -> Cache Hit
    frame3 = np.zeros((480, 640, 3), dtype=np.uint8)
    frame3[0, 0, 0] = 5  # negligible diff
    dets3 = detector.detect(frame3)
    assert len(dets3) == 1
    assert mock_session.run.call_count == 1  # Still 1
    
    # Frame 4: Significant change (above threshold) -> Cache Miss -> Calls session.run
    frame4 = np.ones((480, 640, 3), dtype=np.uint8) * 100
    dets4 = detector.detect(frame4)
    assert len(dets4) == 1
    assert mock_session.run.call_count == 2  # Incremented to 2
