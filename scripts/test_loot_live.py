"""
scripts/test_loot_live.py

Live test for the Hybrid Looting feature.
Run this script while the game is open and items are on the ground.
"""

import sys
import os
import time
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backends.capture_direct import DirectCapture
from backends.input_direct import DirectInput
from features.loot import LootCollector

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test_loot")

def main():
    print("=" * 50)
    print("LOOT FEATURE LIVE TEST")
    print("=" * 50)
    print("Instructions:")
    print("1. Ensure Priston Tale is running and visible.")
    print("2. Drop a few items on the ground (e.g., gold, potions, gear).")
    print("3. Ensure your character is near the items.")
    print("4. The script will automatically switch to the game window...")
    
    print("\nInitializing backends...")
    try:
        capture = DirectCapture(window_title="Priston Tale", prefer_backend="auto")
        simulator = DirectInput(window_title="Priston Tale")
    except Exception as e:
        print(f"Failed to initialize backends: {e}")
        return
        
    print("\nBringing game window to foreground...")
    from core.coordinates import find_window_by_title, activate_window
    hwnd = find_window_by_title("Priston Tale")
    if hwnd:
        activate_window(hwnd)
        time.sleep(1) # wait for window to come to foreground
    else:
        print("Could not find game window to activate.")
        
    print("\nInitializing LootCollector...")
    collector = LootCollector(capture, simulator)
    
    # Force settings for the test
    collector.enabled = True
    # Test with whitelist mode first
    collector.mode = "whitelist"
    
    # Run for a few cycles so the user can observe the bot in action
    print("\nStarting loot cycle in whitelist mode (running 3 cycles)...")
    print(f"Whitelist loaded: {collector.whitelist}")
    print(f"Blacklist loaded: {collector.blacklist}")
    
    for i in range(3):
        print(f"\n--- Cycle {i+1} ---")
        result = collector.run_loot_cycle()
        print(f"Loot cycle finished. Items picked up: {result}")
        if result:
            break
        time.sleep(1)

    
    print("\n" + "=" * 50)
    print("Test finished. Please verify:")
    print("1. Did it press A to show labels?")
    print("2. Did it move the mouse to hover over items?")
    print("3. Did it only click items in the whitelist?")
    print("=" * 50)

if __name__ == "__main__":
    main()
