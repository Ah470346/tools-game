"""
scripts/test_input.py

Manual validation script for Task 1.5 — Direct Input.

Run this script ON WINDOWS with Priston Tale VTC open:

    python scripts/test_input.py

This script will:
  1. Locate the game window and bring it to the foreground.
  2. Wait 2 seconds for focus.
  3. Move the mouse to the center of the game client area (0.5, 0.5).
  4. Perform a left-click to focus/interact.
  5. Press the 'v' key to verify keyboard input (character inventory should toggle).
  6. Press key '1' (character might cast skill/pot if bound).
  7. Move the mouse to (0.5, 0.7) and perform a right-click.

PASS criteria:
  - Game window is successfully brought to foreground.
  - Mouse moves exactly to the center and click is registered.
  - Character inventory screen toggles when 'v' is pressed.
  - Keyboard/mouse actions operate smoothly without GameGuard alerts.
"""

import json
import logging
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backends.input_direct import DirectInput
from core.coordinates import find_window_by_title

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("test_input")


def load_window_title() -> str:
    """Loads window title from settings.json."""
    settings_path = PROJECT_ROOT / "config" / "settings.json"
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("window_title", "Priston Tale")
    except FileNotFoundError:
        return "Priston Tale"


def main() -> None:
    # Check for administrator privileges
    if sys.platform == "win32":
        import ctypes
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False
            
        if not is_admin:
            print("\n" + "!" * 80)
            print("  [WARNING] SCRIPT IS NOT RUNNING AS ADMINISTRATOR!")
            print("  Priston Tale VTC (under GameGuard protection) runs with elevated privileges.")
            print("  If you run this script in a normal (non-Admin) terminal, Windows will silently")
            print("  block all simulated inputs. Character movement and keypresses will NOT work.")
            print("  Please close this terminal, open PowerShell/CMD as Administrator, and run again.")
            print("!" * 80 + "\n")

    title = load_window_title()
    logger.info("Starting DirectInput test for window: '%s'", title)

    # Bring window to foreground first (requires win32gui on Windows)
    if sys.platform == "win32":
        import win32gui
        hwnd = find_window_by_title(title)
        if hwnd:
            try:
                win32gui.SetForegroundWindow(hwnd)
                logger.info("Brought game window to foreground. Waiting 2 seconds...")
                time.sleep(2.0)
            except Exception as e:
                logger.warning("Could not set foreground window: %s", e)
        else:
            logger.error("Game window not found. Make sure Priston Tale is running.")
            sys.exit(1)

    # Initialize DirectInput backend
    inp = DirectInput(window_title=title)

    # 1. Test mouse move to center (0.5, 0.5)
    logger.info("Step 1: Moving mouse to center (0.5, 0.5)")
    inp.move(0.5, 0.5)
    time.sleep(1.0)

    # 2. Test left click
    logger.info("Step 2: Clicking left mouse button at center (0.5, 0.5)")
    inp.click(0.5, 0.5, button="left")
    time.sleep(1.5)

    # 3. Test keyboard press 'v'
    logger.info("Step 3: Pressing key 'v'")
    inp.key("v", action="press")
    time.sleep(1.5)

    # 4. Test keyboard press '1'
    logger.info("Step 4: Pressing key '1'")
    inp.key("1", action="press")
    time.sleep(1.5)

    # 5. Test mouse move and right click
    logger.info("Step 5: Right-clicking at (0.5, 0.7)")
    inp.click(0.5, 0.7, button="right")
    time.sleep(1.0)

    print("\n" + "=" * 60)
    print("  INPUT VERIFICATION COMPLETE")
    print("=" * 60)
    print("  Please check:")
    print("  1. Did the game window gain focus?")
    print("  2. Did the mouse cursor move to the center and click?")
    print("  3. Did the inventory window toggle open/close (from 'v' press)?")
    print("  4. Did the right click occur at the bottom center?")
    print("  If YES -> Direct Input is [PASS]")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    if sys.platform != "win32":
        print("[ERROR] This script uses pydirectinput/Windows APIs and must be run on Windows.")
        sys.exit(1)
    main()
