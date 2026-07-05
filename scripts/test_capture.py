"""
scripts/test_capture.py

Manual validation script for Task 1.3 — Direct Capture.

Run this script ON WINDOWS with Priston Tale VTC open and GameGuard active:

    python scripts/test_capture.py

PASS criteria (matches Gate 0 results):
  - Average FPS printed is ≥ 20 (≥ 60 ideal, PoC achieved 125).
  - Saved PNG is not black and shows the actual game screen.
  - No crash or error during the 100-frame capture loop.

FAIL:
  - Average FPS < 20, or
  - Saved PNG is entirely black, or
  - Any exception is raised.
"""

import json
import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so we can import backends/
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backends.capture_direct import DirectCapture

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_capture")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"
NUM_FRAMES = 100
OUTPUT_PNG = PROJECT_ROOT / "scripts" / "capture_test_frame.png"


def load_window_title() -> str:
    """Reads window_title from config/settings.json."""
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("window_title", "Priston Tale")
    except FileNotFoundError:
        logger.warning("settings.json not found — using default window title.")
        return "Priston Tale"


def run_capture_test(window_title: str) -> None:
    """
    Grabs NUM_FRAMES frames, measures average FPS, saves the last frame as PNG.

    Args:
        window_title: Substring of the game window title.
    """
    logger.info("Initialising DirectCapture (window: '%s') ...", window_title)
    cap = DirectCapture(window_title=window_title, prefer_backend="auto")
    logger.info("Backend selected: %s", cap._backend)

    frames_captured = 0
    last_frame: np.ndarray | None = None

    logger.info("Capturing %d frames — do NOT move/resize the game window.", NUM_FRAMES)
    t_start = time.perf_counter()

    for i in range(NUM_FRAMES):
        frame = cap.grab_frame()
        frames_captured += 1
        last_frame = frame
        if (i + 1) % 20 == 0:
            elapsed = time.perf_counter() - t_start
            fps_so_far = frames_captured / elapsed
            logger.info("  Frame %d/%d — running FPS: %.1f", i + 1, NUM_FRAMES, fps_so_far)

    t_end = time.perf_counter()
    elapsed_total = t_end - t_start
    avg_fps = frames_captured / elapsed_total

    # ---------------------------------------------------------------------------
    # Report
    # ---------------------------------------------------------------------------
    print()
    print("=" * 60)
    print("  CAPTURE TEST RESULTS")
    print("=" * 60)
    print(f"  Frames captured : {frames_captured}")
    print(f"  Elapsed time    : {elapsed_total:.2f} s")
    print(f"  Average FPS     : {avg_fps:.2f}")
    print(f"  Frame shape     : {last_frame.shape if last_frame is not None else 'N/A'}")

    if last_frame is not None:
        mean_pixel = last_frame.mean()
        is_black = mean_pixel < 1.0
        print(f"  Mean pixel value: {mean_pixel:.2f}  {'⚠ FRAME IS BLACK' if is_black else '✓ Frame has content'}")

        # Save PNG for visual inspection
        cv2.imwrite(str(OUTPUT_PNG), last_frame)
        print(f"  Saved PNG       : {OUTPUT_PNG}")
    print("=" * 60)

    # ---------------------------------------------------------------------------
    # Pass / Fail verdict
    # ---------------------------------------------------------------------------
    passed = True
    reasons = []

    if avg_fps < 20:
        passed = False
        reasons.append(f"FPS {avg_fps:.1f} < 20 (minimum required)")
    if last_frame is not None and last_frame.mean() < 1.0:
        passed = False
        reasons.append("Captured frame is black — check window title or GameGuard interference")

    print()
    if passed:
        print("  ✅ PASS — capture is working correctly.")
    else:
        print("  ❌ FAIL:")
        for r in reasons:
            print(f"     - {r}")
    print()


if __name__ == "__main__":
    title = load_window_title()
    try:
        run_capture_test(title)
    except RuntimeError as e:
        logger.error("RuntimeError: %s", e)
        print("\n  ❌ FAIL — could not run capture test:")
        print(f"     {e}")
        sys.exit(1)
