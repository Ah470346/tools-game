import numpy as np
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backends.capture_base import ICaptureBackend
from backends.mock_backends import MockInput
from vision.detector import MonsterDetector
from features.combat import CombatController

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DummyCapture(ICaptureBackend):
    def __init__(self) -> None:
        pass
    def grab_frame(self) -> np.ndarray:
        # Return a simple 640x640 dummy BGR image (black frame)
        return np.zeros((640, 640, 3), dtype=np.uint8)

def main():
    model_path = "models/monster.onnx"
    if not os.path.exists(model_path):
        logger.error(f"Model file not found at {model_path}")
        sys.exit(1)

    logger.info("Initializing detector and combat controller...")
    cap = DummyCapture()
    inp = MockInput()
    
    config = {
        "target_source": "yolo",
        "model_path": model_path,
        "left_click": {"enabled": True, "interval_sec": 0.5},
        "right_click": {"enabled": False, "interval_sec": 1.0},
        "engage_range_ratio": 1.0
    }
    
    try:
        ctrl = CombatController(capture=cap, simulator=inp, config=config)
        logger.info("Running combat cycle with dummy frame...")
        # Since dummy frame is pure black, detector should run and return no detections.
        res = ctrl.run_combat_cycle()
        logger.info(f"Combat cycle result (should be False since no monsters are on a black screen): {res}")
        logger.info("Verification of model loading and inference structure: SUCCESS")
    except Exception as e:
        logger.error(f"Error during smoke test: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
