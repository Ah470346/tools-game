"""
vision/detector.py

Performs object detection (e.g. monsters, loot objects) using the ONNX Runtime
independent of PyTorch runtime to reduce overhead and memory footprint.
"""

from typing import List, Dict, Any
import numpy as np


class MonsterDetector:
    """
    ONNX-based model inference wrapper for monster detection.
    """

    def __init__(self, model_path: str) -> None:
        """
        Initializes the detector with an ONNX model.

        Args:
            model_path (str): Path to the monster.onnx file.
        """
        self.model_path = model_path

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Runs inference on the provided frame.

        Args:
            frame (np.ndarray): The captured BGR frame.

        Returns:
            List[Dict[str, Any]]: Detections with bounding boxes, classes, confidence.
        """
        # Placeholder returning empty detections
        return []
