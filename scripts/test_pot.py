"""
scripts/test_pot.py

Manual validation script for Task 1.8 — Smart Auto Pot.
Locates the Priston Tale VTC window, runs a capture loop, samples the pixels
at percentage levels defined in config/settings.json, and evaluates thresholds.

Usage:
    python scripts/test_pot.py [--active] [--interval SEC]

Options:
    --active       Send actual keyboard inputs to the game (requires Admin privileges).
                   Without this flag, runs in DRY-RUN mode using MockInput.
    --interval     Cycle interval (default 0.2s).
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
import numpy as np

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backends.capture_direct import DirectCapture
from backends.input_direct import DirectInput
from backends.mock_backends import MockInput
from core.coordinates import find_window_by_title
from features.auto_pot import PotionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("test_pot")


def load_settings() -> dict:
    settings_path = PROJECT_ROOT / "config" / "settings.json"
    with open(settings_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual validation script for Smart Auto Pot.")
    parser.add_argument("--active", action="store_true", help="Send actual keyboard inputs instead of mocking them.")
    parser.add_argument("--interval", type=float, default=0.2, help="Check interval in seconds (default: 0.2).")
    args = parser.parse_args()

    settings = load_settings()
    title = settings.get("window_title", "Priston Tale")

    # Check for administrator privileges if active mode
    if args.active and sys.platform == "win32":
        import ctypes
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False
            
        if not is_admin:
            print("\n" + "!" * 80)
            print("  [WARNING] ACTIVE MODE REQUESTED BUT SCRIPT IS NOT RUNNING AS ADMINISTRATOR!")
            print("  Priston Tale VTC runs with elevated privileges. Direct input simulation will be ignored by the OS.")
            print("  Please restart this terminal as Administrator.")
            print("!" * 80 + "\n")

    print("====================================================================")
    print("         Task 1.8 - Smart Auto Pot Manual Validation Script         ")
    print("====================================================================")
    print(f"Mode: {'ACTIVE (Sending real keystrokes)' if args.active else 'DRY-RUN (Logging key actions only)'}")
    print(f"Target Window: '{title}'")
    print(f"Check Interval: {args.interval}s")
    print("Instructions:")
    print("  1. Ensure the game is running and visible.")
    print("  2. In active mode, make sure focus is correct.")
    print("  3. Press [Ctrl + C] to terminate the script.")
    print("====================================================================\n")

    # Locate game window
    if sys.platform == "win32":
        hwnd = find_window_by_title(title)
        if not hwnd:
            logger.error("Game window '%s' not found. Make sure Priston Tale is running.", title)
            sys.exit(1)
        else:
            logger.info("Found game window with HWND: %d", hwnd)
    else:
        logger.warning("Not running on Windows. DXcam/BitBlt and DirectInput will be mock-simulated where needed.")

    # Initialize capture backend
    try:
        prefer_backend = settings.get("capture", {}).get("backend", "auto")
        capture = DirectCapture(window_title=title, prefer_backend=prefer_backend)
        logger.info("Initialized DirectCapture backend.")
    except Exception as e:
        logger.error("Failed to initialize capture backend: %s. Exiting.", e)
        sys.exit(1)

    # Initialize input backend
    if args.active and sys.platform == "win32":
        input_backend = DirectInput(window_title=title)
        logger.info("Initialized DirectInput backend (Active mode).")
    else:
        input_backend = MockInput()
        logger.info("Initialized MockInput backend (Dry-run/Non-Windows mode).")

    # Initialize PotionManager
    regions = settings.get("regions", {})
    thresholds = settings.get("thresholds", {})
    potion_manager = PotionManager(capture=capture, simulator=input_backend, regions=regions, thresholds=thresholds)

    logger.info("Auto Pot loop starting. Press Ctrl+C to stop.")

    try:
        while True:
            # Grab frame and display calibration helper info
            frame = capture.grab_frame()
            if frame is not None and frame.size > 0:
                h, w, _ = frame.shape
                calibration_logs = []
                for stat in ["hp", "mp", "stm"]:
                    bar_key = f"{stat}_bar"
                    if bar_key not in regions:
                        continue
                    bar_config = regions[bar_key]
                    start = bar_config.get("start")
                    end = bar_config.get("end")
                    filled_color_bgr = bar_config.get("filled_color_bgr")
                    tolerance = bar_config.get("color_tolerance", 30)

                    if not (start and end and filled_color_bgr):
                        continue

                    # Check color at 100% (fully filled) and at some configured thresholds
                    # to show what color is currently sampled.
                    threshold_percents = [x.get("percent", 0) for x in thresholds.get(stat, [])]
                    # Also include 100% for reference
                    for pct in sorted(set(threshold_percents + [100])):
                        ratio = pct / 100.0
                        x_ratio = start[0] + ratio * (end[0] - start[0])
                        y_ratio = start[1] + ratio * (end[1] - start[1])

                        px = int(x_ratio * (w - 1))
                        py = int(y_ratio * (h - 1))

                        if 0 <= px < w and 0 <= py < h:
                            color = frame[py, px]
                            diff = np.array(color, dtype=np.int16) - np.array(filled_color_bgr, dtype=np.int16)
                            dist = np.linalg.norm(diff)
                            status_str = "FILLED" if dist <= tolerance else "EMPTY"
                            calibration_logs.append(
                                f"{stat.upper()} {pct}% (pixel x={px},y={py}): color={list(color)}, dist={dist:.1f}, status={status_str}"
                            )

                # Print sampled info to console for calibration support
                print("\033[H\033[J", end="") # Clear screen (works on modern terminals)
                print("--- Potion Manager Color Calibration Monitor ---")
                for log_line in calibration_logs:
                    print(log_line)
                print("-------------------------------------------------")
                if not args.active:
                    print("Logged Inputs (Dry-Run Mock Log):")
                    # Show recent inputs
                    for item in input_backend.log[-5:]:
                        print(f"  {item}")
                    print("-------------------------------------------------")
                print("Press Ctrl+C to exit.")

            # Run potion manager logic
            potion_manager.check_and_use_pots()

            time.sleep(args.interval)

    except KeyboardInterrupt:
        logger.info("Script interrupted by user. Stopping.")
    except Exception as e:
        logger.error("Error occurred in test loop: %s", e, exc_info=True)


if __name__ == "__main__":
    main()
