"""
scripts/test_tracker_visual.py

Manual validation script for Task 2.7 Target Tracker.
Draws tracked targets with persistent IDs onto sequential frames.
If the game window is running, it captures and tracks live;
otherwise, it launches a simulated visualizer with moving bounding boxes
to verify ID continuity.
"""

import sys
import os
import time
import logging
import numpy as np
import cv2
from pathlib import Path

# Ensure project root is in the path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.coordinates import find_window_by_title
from backends.capture_direct import DirectCapture
from vision.detector import MonsterDetector
from vision.tracker import TargetTracker
from main import load_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("test_tracker_visual")


def main() -> None:
    logger.info("Initializing Target Tracker Visualizer...")
    
    settings = load_settings()
    window_title = settings.get("window_title", "Priston Tale")
    combat_cfg = settings.get("combat", {})
    model_path = combat_cfg.get("model_path", "models/monster.onnx")

    hwnd = find_window_by_title(window_title) if sys.platform == "win32" else None
    
    if not hwnd:
        logger.warning(f"Could not find game window '{window_title}'. Launching in SIMULATED mode.")
        run_simulated_tracker()
        return

    # Real game mode
    if not os.path.exists(model_path):
        logger.error(f"ONNX model file not found at: {model_path}. Cannot run live tracking.")
        sys.exit(1)

    capture = DirectCapture(window_title=window_title, prefer_backend="auto")
    detector = MonsterDetector(
        model_path=model_path,
        conf_threshold=combat_cfg.get("conf_threshold", 0.40),
        nms_threshold=combat_cfg.get("nms_threshold", 0.45),
        delta_threshold=combat_cfg.get("delta_threshold", 0.01)
    )
    
    tracker_cfg = settings.get("tracker", {})
    tracker = TargetTracker(
        iou_threshold=tracker_cfg.get("iou_threshold", 0.3),
        max_lost_frames=tracker_cfg.get("max_lost_frames", 15)
    )

    logger.info("Starting Live Tracker Preview. Click on the popup window and press 'q' to exit.")
    
    while True:
        frame = capture.grab_frame()
        if frame is None or frame.size == 0:
            time.sleep(0.01)
            continue

        h, w, _ = frame.shape
        
        # Detect and update tracker
        detections = detector.detect(frame)
        tracked_objects = tracker.update(detections)

        # Draw detections with persistent IDs
        for obj in tracked_objects:
            box = obj["box"]
            track_id = obj["track_id"]
            
            # Convert normalized center coordinates back to pixels
            xc, yc, bw, bh = box[0] * w, box[1] * h, box[2] * w, box[3] * h
            x1 = int(xc - bw / 2)
            y1 = int(yc - bh / 2)
            x2 = int(xc + bw / 2)
            y2 = int(yc + bh / 2)

            # Draw green bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Draw persistent ID label
            label = f"ID: {track_id} ({obj['confidence']:.2f})"
            cv2.putText(frame, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Display output
        cv2.imshow("Tracker Preview (Press 'q' to Quit)", frame)
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()
    logger.info("Live visualizer exited.")


def run_simulated_tracker() -> None:
    """Runs a simulated window with moving targets to verify ID persistence."""
    logger.info("Initializing simulated targets...")

    tracker = TargetTracker(iou_threshold=0.3, max_lost_frames=10)
    
    # Track positions over time
    # Monster 1 starts left, moves right
    # Monster 2 starts right, moves left
    pos_m1 = [100.0, 240.0]
    pos_m2 = [500.0, 240.0]

    width, height = 640, 480
    
    logger.info("Starting simulation window. Press 'q' to exit.")

    for step in range(300):
        # Create blank canvas
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Update simulated coordinates (moving linearly)
        pos_m1[0] += 2.0  # move right
        pos_m2[0] -= 2.0  # move left
        
        # Bounding boxes (w=80, h=80)
        # Create simulated detections
        dets = []
        
        # If still on screen, add Monster 1
        if 0 < pos_m1[0] < width:
            dets.append({
                "class_id": 0,
                "confidence": 0.95,
                "box": [pos_m1[0]/width, pos_m1[1]/height, 80.0/width, 80.0/height]
            })
            
        # If still on screen, add Monster 2
        if 0 < pos_m2[0] < width:
            dets.append({
                "class_id": 0,
                "confidence": 0.90,
                "box": [pos_m2[0]/width, pos_m2[1]/height, 80.0/width, 80.0/height]
            })

        # Update tracker
        tracked_objects = tracker.update(dets)

        # Draw targets
        for obj in tracked_objects:
            box = obj["box"]
            track_id = obj["track_id"]
            
            # Convert normalized back to pixels
            xc, yc, bw, bh = box[0] * width, box[1] * height, box[2] * width, box[3] * height
            x1 = int(xc - bw / 2)
            y1 = int(yc - bh / 2)
            x2 = int(xc + bw / 2)
            y2 = int(yc + bh / 2)

            # Assign color based on ID
            color = (0, 255, 0) if track_id == 1 else (0, 165, 255)  # ID 1 is Green, ID 2 is Orange
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
            
            label = f"MONSTER ID: {track_id}"
            cv2.putText(canvas, label, (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Display window
        cv2.imshow("Simulated Target Tracker (Press 'q' to Quit)", canvas)
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()
    logger.info("Simulated visualizer exited.")


if __name__ == "__main__":
    main()
