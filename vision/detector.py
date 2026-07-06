"""
vision/detector.py

Performs object detection (e.g. monsters, loot objects) using the ONNX Runtime
independent of PyTorch runtime to reduce overhead and memory footprint.
"""

from typing import List, Dict, Any, Optional
import numpy as np
import cv2
import os
import logging

logger = logging.getLogger(__name__)


class MonsterDetector:
    """
    ONNX-based model inference wrapper for monster detection.
    """

    def __init__(self, model_path: str, conf_threshold: float = 0.40, nms_threshold: float = 0.45, delta_threshold: float = 0.0) -> None:
        """
        Initializes the detector with an ONNX model.

        Args:
            model_path (str): Path to the monster.onnx file.
            conf_threshold (float): Confidence threshold for detections.
            nms_threshold (float): Non-Maximum Suppression threshold.
            delta_threshold (float): Frame difference threshold for caching detections.
        """
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self.delta_threshold = delta_threshold

        # Caching states for delta detection
        self._prev_frame: Optional[np.ndarray] = None
        self._prev_detections: List[Dict[str, Any]] = []

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ONNX model file not found at: {model_path}")

        try:
            import onnxruntime as ort
        except ImportError as e:
            logger.error("onnxruntime is not installed. Please install it using pip.")
            raise e

        # Initialize ONNX inference session
        # Auto-select CUDA Execution Provider if GPU is available, else CPU
        providers = ort.get_available_providers()
        logger.info(f"Available ONNX providers: {providers}")
        
        # Prefer CUDA or CPU
        active_providers = []
        if "CUDAExecutionProvider" in providers:
            active_providers.append("CUDAExecutionProvider")
        active_providers.append("CPUExecutionProvider")

        logger.info(f"Loading ONNX model using providers: {active_providers}")
        self.session = ort.InferenceSession(model_path, providers=active_providers)
        
        # Get model input details
        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape  # Expect [1, 3, 640, 640]
        self.input_width = self.input_shape[3]
        self.input_height = self.input_shape[2]

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Runs inference on the provided frame.

        Args:
            frame (np.ndarray): The captured BGR frame.

        Returns:
            List[Dict[str, Any]]: List of detections where each detection is:
                {
                    "class_id": int,
                    "confidence": float,
                    "box": [x_center_ratio, y_center_ratio, width_ratio, height_ratio]
                }
        """
        if frame is None or frame.size == 0:
            return []

        # 0. Delta detection (CPU optimization)
        if self.delta_threshold > 0.0:
            # Resize frame to a small, noise-tolerant resolution and convert to grayscale
            small_gray = cv2.cvtColor(cv2.resize(frame, (160, 160)), cv2.COLOR_BGR2GRAY)
            if self._prev_frame is not None:
                # Compute absolute difference
                diff = cv2.absdiff(small_gray, self._prev_frame)
                # Compute normalized mean difference
                mean_diff = float(np.mean(diff) / 255.0)
                logger.debug("MonsterDetector: Frame delta: %.5f (threshold: %.5f)", mean_diff, self.delta_threshold)
                if mean_diff < self.delta_threshold:
                    # Screen did not change significantly, return cached detections
                    return self._prev_detections

            self._prev_frame = small_gray

        # 1. Preprocessing
        # Resize to model input size (640x640)
        resized = cv2.resize(frame, (self.input_width, self.input_height))
        # BGR to RGB
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        # Normalize
        normalized = rgb.astype(np.float32) / 255.0
        # HWC to CHW
        chw = np.transpose(normalized, (2, 0, 1))
        # Add batch dimension
        blob = np.expand_dims(chw, axis=0)

        # 2. Run Inference
        outputs = self.session.run(None, {self.input_name: blob})
        output = outputs[0]  # Shape: (1, 4 + NC, 8400)

        # 3. Postprocessing
        predictions = np.squeeze(output)  # Shape: (4 + NC, 8400)
        predictions = np.transpose(predictions, (1, 0))  # Shape: (8400, 6)

        boxes = []
        confidences = []
        class_ids = []

        # Each row in predictions: [x_center, y_center, w, h, class_0_conf, class_1_conf, ...]
        for row in predictions:
            # Extract scores (all classes)
            scores = row[4:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]

            if confidence >= self.conf_threshold:
                # Bounding box coordinates on the 640x640 image
                xc, yc, w, h = row[:4]
                
                # Convert center coordinates to top-left corner coordinates for NMSBoxes
                x = int(xc - w / 2)
                y = int(yc - h / 2)
                
                boxes.append([x, y, int(w), int(h)])
                confidences.append(float(confidence))
                class_ids.append(int(class_id))

        # Apply Non-Maximum Suppression (NMS)
        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.conf_threshold, self.nms_threshold)
        
        detections = []
        if len(indices) > 0:
            # cv2.dnn.NMSBoxes returns indices as a flat array/list
            for i in indices.flatten():
                x, y, w, h = boxes[i]
                
                # Calculate normalized center ratio coordinates (0.0 to 1.0)
                # Note: x and y in 'boxes' are top-left, we convert back to center coordinates
                xc_norm = (x + w / 2) / self.input_width
                yc_norm = (y + h / 2) / self.input_height
                w_norm = w / self.input_width
                h_norm = h / self.input_height
                
                detections.append({
                    "class_id": class_ids[i],
                    "confidence": confidences[i],
                    "box": [xc_norm, yc_norm, w_norm, h_norm]
                })

        # Cache the current detections
        if self.delta_threshold > 0.0:
            self._prev_detections = detections

        return detections

