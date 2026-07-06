"""
scripts/test_targeting_persistence.py

Manual validation script: runs CombatController against the real game and logs
panel-authoritative targeting events.

PASS/FAIL criteria are printed at startup.
Run this with the game open and standing near monsters in a grinding spot.

Usage:
    python scripts/test_targeting_persistence.py
"""

import json
import logging
import os
import sys
import time

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backends.capture_direct import DirectCapture  # noqa: E402
from backends.input_direct import DirectInput       # noqa: E402
from features.combat import CombatController        # noqa: E402

# ---------------------------------------------------------------------------
# Logging: show relevant targeting events at INFO level
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_targeting_persistence")

# Suppress noisy libraries
for noisy in ("PIL", "dxcam", "comtypes"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Banner with pass/fail criteria
# ---------------------------------------------------------------------------
BANNER = """
============================================================
  Panel-Authoritative Targeting — Manual Validation
============================================================

PASS criteria:
  1. Melee monster occludes sprite ≥3s → log shows COASTING / BLIND_ATTACK
     then REASSOC / CONFIRMED on the same fight.
     Zero "Giving up and blacklisting" while panel is still visible.
     Character does NOT run to another monster mid-fight.

  2. After a kill, NEXT_TARGET picks the monster nearest to the corpse
     (when both a near-corpse and a near-center monster exist).

  3. Click on unreachable monster → "Failed to lock … Blacklisting"
     appears within lock_grace + panel_gone_confirm window.

FAIL criteria:
  - Any BLACKLIST while panel is visible.
  - Target switch mid-fight (active_target_id changes while panel red).
  - Character walks >¼ screen due to blind click.

Press Ctrl+C to stop.
============================================================
"""

print(BANNER)

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_path = os.path.join(base_dir, "config", "settings.json")
with open(config_path, "r", encoding="utf-8") as f:
    settings = json.load(f)

combat_cfg = settings.get("combat", {})
window_title = settings.get("window_title", "Priston Tale")

# ---------------------------------------------------------------------------
# Init backends
# ---------------------------------------------------------------------------
capture = DirectCapture(window_title=window_title)
capture.start()
inp = DirectInput()

combat = CombatController(capture=capture, simulator=inp, config=combat_cfg)

# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------
logger.info("Starting targeting persistence test loop (F12 to emergency stop)")

prev_target_id = None
prev_blind = False

try:
    while True:
        frame = capture.grab_frame()
        if frame is None or frame.size == 0:
            time.sleep(0.05)
            continue

        has = combat.has_target(frame)
        tid = combat._active_target_id
        pos = combat._yolo_target_pos
        blind = combat._blind_attack_active

        # Log transitions
        if tid != prev_target_id:
            if prev_target_id is not None and tid is not None:
                logger.info("[NEXT_TARGET] %s → %s  pos=%s", prev_target_id, tid, pos)
            elif tid is not None:
                logger.info("[ACQUIRE] target ID %s  pos=%s", tid, pos)
            else:
                logger.info("[CLEAR] target ID %s cleared", prev_target_id)
            prev_target_id = tid

        if blind and not prev_blind:
            logger.info("[BLIND_ATTACK] target ID %s  pos=%s", tid, pos)
        elif not blind and prev_blind:
            logger.info("[BLIND_END] target ID %s", tid)
        prev_blind = blind

        if has:
            combat.execute_combat_actions()

        # ~20 FPS
        time.sleep(0.05)

except KeyboardInterrupt:
    logger.info("Stopped by user.")
finally:
    capture.stop()
    print("\n--- Done. Review the log output against the PASS/FAIL criteria above. ---")
