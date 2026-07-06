"""
scripts/test_ocr_live.py

Live manual validation script for Task 2.8 OCR reading of HP/MP.
Initializes the capture backend and OCR reader, crops the target regions,
runs OCR and prints the result. If Tesseract is not configured or the game is off,
runs a simulated OCR test using a generated image with text to confirm preprocessing.
"""

import sys
import os
import time
import logging
import numpy as np
from pathlib import Path

# Ensure project root is in the path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.coordinates import find_window_by_title
from backends.capture_direct import DirectCapture
from vision.ocr import TextReader
from main import load_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("test_ocr_live")


def main() -> None:
    logger.info("Initializing OCR live test...")
    settings = load_settings()
    ocr_cfg = settings.get("ocr", {})
    tesseract_path = ocr_cfg.get("tesseract_path")
    window_title = settings.get("window_title", "Priston Tale")

    # Initialize Reader
    reader = TextReader(tesseract_path=tesseract_path)

    # Check if Tesseract is available/enabled
    if not reader.enabled:
        logger.error("Tesseract OCR is disabled. Ensure 'pytesseract' is installed and your 'tesseract_path' is correct.")
        sys.exit(1)

    hwnd = find_window_by_title(window_title) if sys.platform == "win32" else None
    
    if not hwnd:
        logger.warning(f"Could not find game window '{window_title}'. Running in SIMULATED mode.")
        run_simulated_ocr(reader)
        return

    # Live Mode
    capture = DirectCapture(window_title=window_title, prefer_backend="auto")
    logger.info("DirectCapture initialized.")

    hp_region = ocr_cfg.get("hp_ocr_region", {"start": [0.41, 0.81], "end": [0.45, 0.83]})
    mp_region = ocr_cfg.get("mp_ocr_region", {"start": [0.59, 0.81], "end": [0.63, 0.83]})

    logger.info("Starting live OCR loops. Capturing HP and MP ROIs every 1.0s. Press Ctrl+C to exit.")
    
    try:
        while True:
            frame = capture.grab_frame()
            if frame is None or frame.size == 0:
                time.sleep(0.1)
                continue

            h, w, _ = frame.shape
            
            # Read HP
            hp_start = hp_region.get("start")
            hp_end = hp_region.get("end")
            if hp_start and hp_end:
                x_start = int(hp_start[0] * w)
                y_start = int(hp_start[1] * h)
                x_end = int(hp_end[0] * w)
                y_end = int(hp_end[1] * h)
                hp_roi = frame[y_start:y_end, x_start:x_end]
                
                hp_res = reader.read_values(hp_roi)
                if hp_res:
                    curr_hp, max_hp = hp_res
                    logger.info(f"HP OCR: {curr_hp} / {max_hp} ({curr_hp/max_hp*100:.1f}%)")
                else:
                    logger.warning("HP OCR: Failed to read text (falling back to color checks)")

            # Read MP
            mp_start = mp_region.get("start")
            mp_end = mp_region.get("end")
            if mp_start and mp_end:
                x_start = int(mp_start[0] * w)
                y_start = int(mp_start[1] * h)
                x_end = int(mp_end[0] * w)
                y_end = int(mp_end[1] * h)
                mp_roi = frame[y_start:y_end, x_start:x_end]
                
                mp_res = reader.read_values(mp_roi)
                if mp_res:
                    curr_mp, max_mp = mp_res
                    logger.info(f"MP OCR: {curr_mp} / {max_mp} ({curr_mp/max_mp*100:.1f}%)")
                else:
                    logger.warning("MP OCR: Failed to read text (falling back to color checks)")

            print("-" * 40)
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("OCR live test stopped.")


def run_simulated_ocr(reader: TextReader) -> None:
    """Generates a mock status image with numbers to verify preprocessing & OCR reading."""
    logger.info("Generating a simulated BGR image containing status numbers...")
    
    # Create a simple canvas
    canvas = np.zeros((40, 150, 3), dtype=np.uint8)
    # Draw dark blue background (simulating MP bar background)
    canvas[:, :] = [100, 30, 30]

    # Draw white status text using OpenCV (e.g. "1240 / 3000")
    # Using simple Hershey simplex font
    cv2 = sys.modules.get("cv2")
    if cv2 is None:
        import cv2
    
    text = "1240/3000"
    cv2.putText(canvas, text, (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

    # Save mock image to check
    output_dir = PROJECT_ROOT / "runs"
    output_dir.mkdir(exist_ok=True)
    mock_img_path = output_dir / "simulated_ocr_input.png"
    cv2.imwrite(str(mock_img_path), canvas)
    logger.info(f"Saved simulated OCR input image to: {mock_img_path}")

    # Process and read values
    t_start = time.perf_counter()
    result = reader.read_values(canvas)
    t_elapsed = (time.perf_counter() - t_start) * 1000.0

    print("\n" + "=" * 60)
    print("  SIMULATED HP/MP OCR TEST REPORT")
    print("=" * 60)
    print(f"  Input Text (Simulated) : '{text}'")
    print(f"  OCR Read Result        : {result}")
    print(f"  Execution Time         : {t_elapsed:.2f} ms")
    print("=" * 60)
    
    if result == (1240, 3000):
        print("  VERIFICATION RESULT: SUCCESS (OCR parsed values correctly)!")
    else:
        print("  VERIFICATION RESULT: FAILED (OCR failed to parse mock values)!")
        print("  Ensure you have Tesseract installed on your PC and added to PATH.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
