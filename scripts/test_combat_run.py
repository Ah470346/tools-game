"""
scripts/test_combat_run.py

Manual validation script for Task 1.9 — Combat PHỔ DỤNG.
Runs the CombatController loop. Checks targeting and executes attacks.
Listens for F9 (Pause/Resume) and F12 (Emergency Stop) to ensure control.

Usage:
    python scripts/test_combat_run.py [--active] [--interval SEC]
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
from core.state_machine import StateMachine
from core.hotkey_manager import HotkeyManager
from features.combat import CombatController

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("test_combat_run")


def load_settings() -> dict:
    settings_path = PROJECT_ROOT / "config" / "settings.json"
    with open(settings_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual validation script for Combat Controller.")
    parser.add_argument("--active", action="store_true", help="Send actual click/key inputs instead of mocking them.")
    parser.add_argument("--interval", type=float, default=0.1, help="Check interval in seconds (default: 0.1).")
    args = parser.parse_args()

    settings = load_settings()
    title = settings.get("window_title", "Priston Tale")
    combat_cfg = settings.get("combat", {})

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
    print("         Task 1.9 - Combat Controller Manual Validation Script      ")
    print("====================================================================")
    print(f"Mode: {'ACTIVE (Sending real clicks/keys)' if args.active else 'DRY-RUN (Logging actions only)'}")
    print(f"Target Window: '{title}'")
    print(f"Update Interval: {args.interval}s")
    print("Instructions:")
    print("  1. Ensure the game is running and visible.")
    print("  2. Press [F9] to PAUSE/RESUME the bot.")
    print("  3. Press [F12] to EMERGENCY STOP and terminate.")
    print("  4. Press [Ctrl + C] to force terminate.")
    print("====================================================================\n")

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

    # Initialize state machine & hotkey manager for F12 / F9 hooks
    fsm = StateMachine(capture, input_backend)
    fsm.running = True
    fsm.state = "FARMING"

    hotkeys = HotkeyManager(fsm, input_backend)
    hotkeys.start()

    # Initialize CombatController
    combat_ctrl = CombatController(capture=capture, simulator=input_backend, config=combat_cfg)

    logger.info("Combat loop starting. Press F12 to stop.")

    try:
        while fsm.running:
            if fsm.state == "PAUSED":
                print("\033[H\033[J", end="")
                print("==============================================")
                print("             BOT STATUS: PAUSED               ")
                print("==============================================")
                print("Press [F9] to Resume, [F12] to Stop.")
                time.sleep(0.5)
                continue

            frame = capture.grab_frame()
            if frame is not None and frame.size > 0:
                h, w, _ = frame.shape
                
                # Check target pixel color info
                target_check = combat_cfg.get("target_check", {})
                pixel_coord = target_check.get("check_pixel")

                target_status_line = "Target check: disabled"
                if target_check.get("enabled", False) and pixel_coord:
                    px = int(pixel_coord[0] * (w - 1))
                    py = int(pixel_coord[1] * (h - 1))
                    if 0 <= px < w and 0 <= py < h:
                        color = frame[py, px]
                        b, g, r = int(color[0]), int(color[1]), int(color[2])
                        locked_color = (r > 120) and (r > 1.3 * g) and (r > 1.4 * b)
                        target_status_line = (
                            f"Target pixel: x={px}, y={py} | Color={list(color)} | "
                            f"Is Red: {locked_color} | Locked={combat_ctrl.has_target(frame)}"
                        )

                # Clear console and print status
                print("\033[H\033[J", end="")
                print("--- Combat Controller Live Monitor ---")
                print(f"FSM State: {fsm.state} (running={fsm.running})")
                print(target_status_line)
                print(f"Target Source: {combat_ctrl.target_source}")
                print(f"LMB Click: {'ENABLED' if combat_ctrl.left_click_cfg.get('enabled') else 'DISABLED'} (interval: {combat_ctrl.left_click_cfg.get('interval_sec')}s)")
                print(f"RMB Click: {'ENABLED' if combat_ctrl.right_click_cfg.get('enabled') else 'DISABLED'} (interval: {combat_ctrl.right_click_cfg.get('interval_sec')}s)")
                print("---------------------------------------")
                
                if not args.active:
                    print("Logged Inputs (Dry-Run Mock Log):")
                    # Show recent inputs
                    for item in input_backend.log[-8:]:
                        print(f"  {item}")
                    print("---------------------------------------")
                print("Press F9 to Pause/Resume, F12 to Stop.")

            # Check and execute combat cycle if inputs are not blocked
            if not input_backend.block_inputs:
                combat_ctrl.run_combat_cycle()

            time.sleep(args.interval)

    except KeyboardInterrupt:
        logger.info("Script interrupted by user. Stopping.")
    except Exception as e:
        logger.error("Error occurred in combat test loop: %s", e, exc_info=True)
    finally:
        hotkeys.stop_listening()
        logger.info("Validation script finished cleanup.")


if __name__ == "__main__":
    main()
