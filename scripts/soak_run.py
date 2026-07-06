"""
scripts/soak_run.py

Soak test execution script for Priston Tale Auto Tool MVP Lite.
Runs the main bot loop for a configurable duration (default 2.0 hours).
Allows validating stability, memory footprint, uptime, and hotkeys.

Usage:
    python scripts/soak_run.py [--active] [--duration_hours HOURS]
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import main

logger = logging.getLogger("soak_run")


def is_admin() -> bool:
    if sys.platform == "win32":
        import ctypes
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    return False


def main_soak() -> None:
    parser = argparse.ArgumentParser(description="Soak testing script for Priston Tale Auto Tool MVP Lite.")
    parser.add_argument("--active", action="store_true", help="Send real mouse/keyboard inputs (requires Admin privileges).")
    parser.add_argument("--duration_hours", type=float, default=2.0, help="Run duration in hours (default: 2.0).")
    args = parser.parse_args()

    duration_seconds = args.duration_hours * 3600.0

    print("====================================================================")
    print("         Task 1.10 - MVP Lite Soak Run (2-3 hour stability test)    ")
    print("====================================================================")
    print(f"Mode: {'ACTIVE (Simulating real keys/clicks)' if args.active else 'DRY-RUN (Mock mode)'}")
    print(f"Duration: {args.duration_hours} hours ({duration_seconds:.0f} seconds)")
    print("Instructions:")
    print("  1. Press [F9] to PAUSE/RESUME the bot.")
    print("  2. Press [F12] to EMERGENCY STOP and exit cleanly.")
    print("  3. Press [Ctrl + C] to force terminate in terminal.")
    print("====================================================================\n")

    if args.active and sys.platform == "win32" and not is_admin():
        print("\n" + "!" * 80)
        print("  [WARNING] ACTIVE MODE REQUESTED BUT SCRIPT IS NOT RUNNING AS ADMINISTRATOR!")
        print("  Direct input simulation will be ignored by GameGuard / Windows UIPI.")
        print("  Please restart this terminal as Administrator.")
        print("!" * 80 + "\n")

    try:
        # Run the bot main loop
        main.run_bot(active=args.active, loop_delay=0.1, max_duration=duration_seconds)
    except Exception as e:
        logger.error("Exception in soak run loop: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main_soak()
