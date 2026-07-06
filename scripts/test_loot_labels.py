"""
scripts/test_loot_labels.py

Validation script for Task 2.9 Smart Loot Filter.
Detects rectangular name labels on screen, runs OCR, matches against whitelist,
and saves a visual preview image with color-coded bounding boxes.
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
from vision.color_filter import find_item_labels
from features.loot import LootCollector
from main import load_settings

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("test_loot_labels")


def main() -> None:
    logger.info("Initializing Loot Filter validation script...")
    settings = load_settings()
    loot_cfg = settings.get("loot", {})
    window_title = settings.get("window_title", "Priston Tale")

    # Initialize LootCollector (loads configurations & Tesseract reader)
    collector = LootCollector(capture=None, simulator=None, config=loot_cfg)
    
    if not collector.ocr_reader.enabled:
        logger.error("Tesseract OCR is disabled. Ensure Tesseract is installed and your path is correct.")
        sys.exit(1)

    hwnd = find_window_by_title(window_title) if sys.platform == "win32" else None
    
    if not hwnd:
        logger.warning(f"Could not find game window '{window_title}'. Running in SIMULATED mode.")
        run_simulated_loot(collector)
        return

    # Live Mode
    from backends.capture_direct import DirectCapture
    from backends.input_direct import DirectInput
    
    capture = DirectCapture(window_title=window_title, prefer_backend="auto")
    simulator = DirectInput()
    collector.capture = capture
    collector.input = simulator

    logger.info("Starting live Loot Filter checks. Press Ctrl+C to exit.")
    
    try:
        # Hold names hotkey
        logger.info(f"Holding show-names key '{collector.show_names_key}' down to detect labels...")
        simulator.key(collector.show_names_key, "down")
        time.sleep(0.2)

        frame = capture.grab_frame()
        
        # Release key immediately
        simulator.key(collector.show_names_key, "up")

        if frame is None or frame.size == 0:
            logger.error("Failed to capture frame from game.")
            sys.exit(1)

        import cv2
        height, width, _ = frame.shape
        label_boxes = find_item_labels(frame)
        logger.info(f"Found {len(label_boxes)} candidate item labels on screen.")

        # Create output canvas
        output_canvas = frame.copy()

        for (x, y, w, h) in label_boxes:
            roi = frame[y:y+h, x:x+w]
            text = collector.ocr_reader.read_text(roi)
            
            if text:
                is_match = collector._matches_whitelist(text)
                color = (0, 255, 0) if is_match else (0, 0, 255) # Green = whitelist, Red = blacklist/normal
                label_status = "Loot" if is_match else "Ignore"
                
                # Draw box
                cv2.rectangle(output_canvas, (x, y), (x + w, y + h), color, 2)
                # Draw text tag above box
                cv2.putText(output_canvas, f"{text} ({label_status})", (x, y - 5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
                logger.info(f"Label detected: [{text}] -> {label_status} at center ({x + w//2}, {y + h//2})")
            else:
                # Blue = unrecognized text
                cv2.rectangle(output_canvas, (x, y), (x + w, y + h), (255, 0, 0), 1)

        # Save output image
        output_dir = PROJECT_ROOT / "runs"
        output_dir.mkdir(exist_ok=True)
        preview_path = output_dir / "loot_labels_preview.png"
        cv2.imwrite(str(preview_path), output_canvas)
        logger.info(f"Saved live loot labels preview to: {preview_path}")

    except KeyboardInterrupt:
        logger.info("Validation stopped.")


def run_simulated_loot(collector: LootCollector) -> None:
    """Generates a mock screen containing simulated item labels to test detection & OCR."""
    logger.info("Generating simulated screen with mock item labels...")
    
    import cv2
    
    # 800x600 dark background frame
    frame = np.zeros((600, 800, 3), dtype=np.uint8)
    frame[:, :] = [40, 40, 40] # Dark gray grass/terrain simulation

    # Add mock labels (gray boxes with white/yellow borders and text)
    # Box 1: Celesto Sheltom (whitelisted)
    cv2.rectangle(frame, (100, 100), (280, 122), (80, 80, 80), -1)
    cv2.rectangle(frame, (100, 100), (280, 122), (180, 180, 180), 1)
    cv2.putText(frame, "Celesto Sheltom", (110, 116), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    # Box 2: Weak HP potion (blacklisted)
    cv2.rectangle(frame, (350, 200), (510, 222), (80, 80, 80), -1)
    cv2.rectangle(frame, (350, 200), (510, 222), (180, 180, 180), 1)
    cv2.putText(frame, "Weak HP potion", (360, 216), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    # Box 3: Gold [1500] (whitelisted)
    cv2.rectangle(frame, (200, 400), (330, 422), (80, 80, 80), -1)
    cv2.rectangle(frame, (200, 400), (330, 422), (180, 180, 180), 1)
    cv2.putText(frame, "Gold 1500", (210, 416), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    # 1. Run detection
    label_boxes = find_item_labels(frame)
    print(f"DEBUG: detected label_boxes={label_boxes}")
    
    # 2. Match and draw results
    output_canvas = frame.copy()
    print("\n" + "=" * 60)
    print("  SIMULATED LOOT FILTER REPORT")
    print("=" * 60)
    
    for (x, y, w, h) in label_boxes:
        roi = frame[y:y+h, x:x+w]
        text = collector.ocr_reader.read_text(roi)
        print(f"  DEBUG Box ({x}, {y}) read: '{text}'")
        
        if text:
            is_match = collector._matches_whitelist(text)
            color = (0, 255, 0) if is_match else (0, 0, 255)
            status_text = "PICKUP (Whitelist Match)" if is_match else "IGNORE (Blacklisted/Rác)"
            
            print(f"  Detected Box: '{text}' -> {status_text} at center ({x + w//2}, {y + h//2})")
            cv2.rectangle(output_canvas, (x, y), (x + w, y + h), color, 2)
            cv2.putText(output_canvas, f"{text}", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        else:
            cv2.rectangle(output_canvas, (x, y), (x + w, y + h), (255, 0, 0), 1)

    # Save simulated result
    output_dir = PROJECT_ROOT / "runs"
    output_dir.mkdir(exist_ok=True)
    sim_path = output_dir / "simulated_loot_preview.png"
    cv2.imwrite(str(sim_path), output_canvas)
    
    print("=" * 60)
    print(f"  Saved simulated loot preview to: {sim_path}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
