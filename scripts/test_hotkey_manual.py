"""
scripts/test_hotkey_manual.py

Manual validation script for Task 1.6 (Emergency Stop & Pause Hotkeys).
This script runs a mock engine loop that simulates bot actions, registers the global hotkeys,
and allows the developer to test F9 (Pause/Resume) and F12 (Emergency Stop) in real-time.

Requirements:
  - Run this script (under Admin privileges if on Windows with real hooks).
  - Press F9 to toggle pause/resume.
  - Press F12 to trigger emergency stop / exit.

Expected Outcomes:
  - Pressing F9: The console logs pause, active held keys are released, and new inputs are blocked.
    Pressing F9 again resumes execution.
  - Pressing F12: The console logs emergency stop, held keys are released, all input is blocked,
    and the loop exits cleanly.
"""

import sys
import os
import time

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backends.mock_backends import MockCapture, MockInput
from core.state_machine import StateMachine
from core.hotkey_manager import HotkeyManager


def main() -> None:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    print("====================================================================")
    print("         Task 1.6 - Manual Hotkey Validation Script                  ")
    print("====================================================================")
    print("Instructions:")
    print("  1. Press [F9] to PAUSE/RESUME.")
    print("  2. Press [F12] to trigger EMERGENCY STOP (KILL).")
    print("  3. Check the console logs to verify that:")
    print("     - F9 transitions state to PAUSED and blocks inputs.")
    print("     - F9 again resumes the previous state and unblocks inputs.")
    print("     - F12 releases all keys, blocks input, and stops the loop.")
    print("====================================================================\n")

    capture = MockCapture()
    input_backend = MockInput()
    fsm = StateMachine(capture, input_backend)
    
    # Simulate a running state
    fsm.running = True
    fsm.state = "FARMING"
    
    manager = HotkeyManager(fsm, input_backend)
    manager.start()

    print("Hotkey listener started. Entering simulation loop...")
    print(f"Current State: {fsm.state} (running={fsm.running})")

    try:
        loop_count = 0
        while fsm.running:
            loop_count += 1
            
            # Simulate bot holding keys down periodically
            if fsm.state == "FARMING" and not input_backend.block_inputs:
                if "w" not in input_backend.pressed_keys:
                    print("[Bot Action] Holding down 'w' key to walk...")
                    input_backend.key("w", "down")
                if "shift" not in input_backend.pressed_keys:
                    print("[Bot Action] Holding down 'shift' key to run...")
                    input_backend.key("shift", "down")
            
            # Print status update every 2 seconds
            if loop_count % 20 == 0:
                print(
                    f"[Status] State={fsm.state} | Blocked={input_backend.block_inputs} "
                    f"| Pressed Keys={list(input_backend.pressed_keys)}"
                )

            time.sleep(0.1)

        print(f"\nLoop exited. Final state: State={fsm.state} | running={fsm.running} | Blocked={input_backend.block_inputs}")
        print("Verification PASS if F12 stopped the loop, blocked input, and released all keys.")

    except KeyboardInterrupt:
        print("\nExiting via KeyboardInterrupt.")
    finally:
        manager.stop_listening()
        print("Hotkey listener stopped. Cleanup complete.")


if __name__ == "__main__":
    main()
