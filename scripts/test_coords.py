"""
scripts/test_coords.py

Manual validation script for Task 1.4 — Coordinate Scaling & Border Offset.

Run this script ON WINDOWS with Priston Tale VTC open:

    python scripts/test_coords.py

This script will:
  1. Find the window handle of the game.
  2. Retrieve the client region boundaries.
  3. Cycle through 5 points in ratio space (top-left, top-right, center, bottom-left, bottom-right).
  4. Move the mouse cursor directly to each point on the screen using ctypes.SetCursorPos.

PASS criteria:
  - The mouse cursor must land precisely on the corresponding positions *inside* the game's active area.
  - The corners (0.1, 0.1) should point to the inside window contents, offset from the title bar and borders.
  - The behavior remains correct even if the game window is moved or resized.

FAIL:
  - The mouse cursor lands on the title bar, border, or outside the client area for coordinate ratios.
  - Cursor positions are misaligned by more than 3 pixels.
"""

import ctypes
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

from core.coordinates import find_window_by_title, get_client_rect_screen, ratio_to_screen

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("test_coords")


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
    # 1. Load configuration and find window
    title = load_window_title()
    logger.info("Looking for window: '%s'", title)
    
    hwnd = find_window_by_title(title)
    if not hwnd:
        logger.error("Game window '%s' not found. Please ensure the game is running.", title)
        sys.exit(1)

    logger.info("Found game window. HWND: %d", hwnd)
    
    # 2. Get client rect and print info
    left, top, right, bottom = get_client_rect_screen(hwnd)
    width = right - left
    height = bottom - top
    logger.info("Client Area screen coordinates: Left=%d, Top=%d, Right=%d, Bottom=%d", left, top, right, bottom)
    logger.info("Client size: %dx%d", width, height)

    # 3. Define 5 test ratio points
    test_points = [
        ("Top-Left Corner (10%, 10%)", 0.1, 0.1),
        ("Top-Right Corner (90%, 10%)", 0.9, 0.1),
        ("Center of screen (50%, 50%)", 0.5, 0.5),
        ("Bottom-Left Corner (10%, 90%)", 0.1, 0.9),
        ("Bottom-Right Corner (90%, 90%)", 0.9, 0.9),
    ]

    print("\n" + "=" * 60)
    print("  COORDINATE TEST STARTING IN 3 SECONDS")
    print("  Please make sure the game window is visible.")
    print("=" * 60 + "\n")
    time.sleep(3.0)

    # 4. Perform mouse positioning
    for name, rx, ry in test_points:
        screen_x, screen_y = ratio_to_screen(rx, ry, hwnd)
        logger.info("Testing Point: %s -> Ratio=(%.1f, %.1f) -> Screen=(%d, %d)", name, rx, ry, screen_x, screen_y)
        
        # Move mouse using standard Windows API directly via ctypes
        ctypes.windll.user32.SetCursorPos(screen_x, screen_y)
        
        # Pause to let the user visually inspect the cursor position
        time.sleep(1.5)

    print("\n" + "=" * 60)
    print("  COORDINATE TEST COMPLETE")
    print("=" * 60)
    print("  Verification checklist:")
    print("  1. Did the cursor move to all 5 positions inside the client area?")
    print("  2. Did it stay clear of the windows borders and title bar?")
    print("  3. Repeat the test after moving/resizing the game window. Does it remain accurate?")
    print("  If YES to all -> Coordinate scaling is [PASS]")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    if sys.platform != "win32":
        print("[ERROR] This script uses ctypes.windll.user32.SetCursorPos and must be run on Windows.")
        sys.exit(1)
    main()
