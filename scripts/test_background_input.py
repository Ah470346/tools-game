"""
scripts/test_background_input.py

Validation script to test background mouse and keyboard input simulation using Windows PostMessage.
This allows sending inputs directly to the game window handle (HWND) without bringing it
to the foreground or moving the physical mouse cursor.

Run this script ON WINDOWS with Priston Tale VTC open:
    python scripts/test_background_input.py

Instructions:
  1. Open the game.
  2. Focus another window (like this terminal or Notepad). Do NOT keep the game active.
  3. Run this script.
  4. Watch if the game window responds (e.g. inventory screen toggles, character clicks).
"""

import json
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("test_background_input")

if sys.platform != "win32":
    print("[ERROR] This script uses Windows APIs and must be run on Windows.")
    sys.exit(1)

import win32gui
import win32con
import win32api
import ctypes

def load_window_title() -> str:
    """Loads window title from settings.json."""
    settings_path = PROJECT_ROOT / "config" / "settings.json"
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("window_title", "Priston Tale")
    except FileNotFoundError:
        return "Priston Tale"

def find_all_game_hwnds(title_substring: str) -> list[int]:
    """Finds all windows (including child windows) matching the title substring."""
    hwnds = []
    
    def enum_windows_callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            text = win32gui.GetWindowText(hwnd)
            if title_substring.lower() in text.lower():
                hwnds.append(hwnd)
        return True
        
    win32gui.EnumWindows(enum_windows_callback, None)
    return hwnds

def send_background_key(hwnd: int, vk_code: int, delay: float = 0.1):
    """Sends a key press and release to a specific window handle using PostMessage."""
    scan_code = win32api.MapVirtualKey(vk_code, 0)
    
    # lParam for WM_KEYDOWN
    lParam_down = 1 | (scan_code << 16)
    # lParam for WM_KEYUP
    lParam_up = 1 | (scan_code << 16) | (1 << 30) | (1 << 31)
    
    logger.info("Sending Key %s (VK: 0x%X) to HWND %d", chr(vk_code) if 32 <= vk_code <= 126 else str(vk_code), vk_code, hwnd)
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk_code, lParam_down)
    time.sleep(delay)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk_code, lParam_up)

def send_background_click(hwnd: int, x: int, y: int, button: str = "left", delay: float = 0.1):
    """Sends a mouse click at coordinates (x, y) relative to the client area of HWND."""
    lParam = (y << 16) | x
    
    logger.info("Sending %s Click at client coordinates (%d, %d) to HWND %d", button, x, y, hwnd)
    
    # Send move event first to position virtual cursor within window
    win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lParam)
    time.sleep(0.02)
    
    if button == "left":
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
        time.sleep(delay)
        win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lParam)
    elif button == "right":
        win32gui.PostMessage(hwnd, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lParam)
        time.sleep(delay)
        win32gui.PostMessage(hwnd, win32con.WM_RBUTTONUP, 0, lParam)

def main():
    title = load_window_title()
    hwnds = find_all_game_hwnds(title)
    
    if not hwnds:
        logger.error("No windows found matching '%s'. Make sure Priston Tale is running.", title)
        sys.exit(1)
        
    logger.info("Found %d matching window(s): %s", len(hwnds), hwnds)
    
    # We will test on the first found window
    target_hwnd = hwnds[0]
    
    # Get window rect
    rect = win32gui.GetClientRect(target_hwnd)
    width = rect[2] - rect[0]
    height = rect[3] - rect[1]
    logger.info("Target HWND: %d, Client Area: %dx%d", target_hwnd, width, height)
    
    print("\n" + "=" * 60)
    print("  BACKGROUND INPUT TESTING")
    print("=" * 60)
    print("  Instructions:")
    print("  1. Keep the game window visible on screen (do not minimize).")
    print("  2. Click on ANOTHER window (like this command prompt) to focus it.")
    print("  3. The test will run in 3 seconds.")
    print("=" * 60)
    
    for i in range(3, 0, -1):
        print(f"Starting in {i}...")
        time.sleep(1.0)
        
    # Test 1: Keyboard key 'V' (Inventory)
    # Virtual Key code for 'V' is 0x56
    logger.info("--- Test 1: Sending 'V' to toggle inventory ---")
    send_background_key(target_hwnd, 0x56)
    
    # Wait a bit
    time.sleep(2.0)
    
    # Test 2: Keyboard key '1' (Quickbar)
    # Virtual Key code for '1' is 0x31
    logger.info("--- Test 2: Sending '1' ---")
    send_background_key(target_hwnd, 0x31)
    
    time.sleep(2.0)
    
    # Test 3: Mouse click in the middle of client area
    logger.info("--- Test 3: Sending Left Click to middle of client area ---")
    center_x = width // 2
    center_y = height // 2
    send_background_click(target_hwnd, center_x, center_y, button="left")
    
    time.sleep(2.0)
    
    print("\n" + "=" * 60)
    print("  TEST COMPLETED")
    print("=" * 60)
    print("  Please check the game client:")
    print("  1. Did the inventory window toggle open/close?")
    print("  2. Did key '1' activate anything (pot or skill) on the quickbar?")
    print("  3. Did the click at the center focus the window or trigger any action?")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
