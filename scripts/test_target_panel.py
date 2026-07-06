"""
scripts/test_target_panel.py

Captures a frame from the game window and visualizes the target panel
detection region. Saves an annotated image showing the ROI and red pixel ratio.

Usage:
    1. Target a monster in-game (panel should be visible in top-right)
    2. Run: python scripts/test_target_panel.py
    3. Check the output image: scripts/target_panel_debug.png
    4. Run again with NO target selected to compare results.

Pass/Fail criteria:
    - With target: red_ratio should be > 0.02 (the threshold)
    - Without target: red_ratio should be < 0.02
"""

import json
import logging
import os
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_target_panel")


def main() -> None:
    # Load config
    config_path = PROJECT_ROOT / "config" / "settings.json"
    with open(config_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    combat_cfg = settings.get("combat", {})
    check_cfg = combat_cfg.get("target_check", {})
    region = check_cfg.get("region", {"start": [0.86, 0.12], "end": [0.97, 0.23]})
    min_red_ratio = check_cfg.get("min_red_ratio", 0.02)

    # Capture frame
    from backends.capture_direct import DirectCapture
    window_title = settings.get("window_title", "Priston Tale")
    capture = DirectCapture(window_title=window_title)
    frame = capture.grab_frame()

    if frame is None or frame.size == 0:
        logger.error("Failed to capture frame. Is the game running?")
        sys.exit(1)

    height, width = frame.shape[:2]
    logger.info("Captured frame: %dx%d", width, height)

    # Calculate region coordinates
    start = region["start"]
    end = region["end"]
    x1 = max(0, int(start[0] * (width - 1)))
    y1 = max(0, int(start[1] * (height - 1)))
    x2 = min(width, int(end[0] * (width - 1)))
    y2 = min(height, int(end[1] * (height - 1)))

    logger.info("Target panel region: (%d, %d) -> (%d, %d)", x1, y1, x2, y2)

    # Extract ROI and compute red ratio
    roi = frame[y1:y2, x1:x2]
    b_ch = roi[:, :, 0].astype(np.int32)
    g_ch = roi[:, :, 1].astype(np.int32)
    r_ch = roi[:, :, 2].astype(np.int32)

    red_mask = (r_ch > 120) & (r_ch > 1.3 * g_ch) & (r_ch > 1.4 * b_ch)
    red_ratio = float(np.sum(red_mask)) / max(red_mask.size, 1)

    is_visible = red_ratio >= min_red_ratio

    logger.info("=" * 50)
    logger.info("  Red pixel ratio : %.4f", red_ratio)
    logger.info("  Threshold       : %.4f", min_red_ratio)
    logger.info("  Panel visible   : %s", is_visible)
    logger.info("=" * 50)

    # Draw annotations on frame
    annotated = frame.copy()
    color = (0, 255, 0) if is_visible else (0, 0, 255)
    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
    label = f"red_ratio={red_ratio:.4f} ({'VISIBLE' if is_visible else 'NOT VISIBLE'})"
    cv2.putText(annotated, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    # Also save the ROI with red pixels highlighted
    roi_annotated = roi.copy()
    roi_annotated[red_mask.astype(bool)] = [0, 0, 255]  # highlight red pixels

    # Save outputs
    output_path = PROJECT_ROOT / "scripts" / "target_panel_debug.png"
    cv2.imwrite(str(output_path), annotated)
    logger.info("Full annotated frame saved: %s", output_path)

    roi_path = PROJECT_ROOT / "scripts" / "target_panel_roi.png"
    cv2.imwrite(str(roi_path), roi_annotated)
    logger.info("ROI with red highlights saved: %s", roi_path)


if __name__ == "__main__":
    main()
