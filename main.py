"""
main.py

Entry point for the Priston Tale Auto Tool.
"""

import json
import logging
import os
import sys
import time
from typing import Dict, Optional, Set

from backends.capture_direct import DirectCapture
from backends.input_direct import DirectInput
from backends.mock_backends import MockCapture, MockInput
from backends.input_base import IInputBackend
from core.coordinates import find_window_by_title
from core.state_machine import StateMachine
from core.hotkey_manager import HotkeyManager
from features.auto_pot import PotionManager
from features.combat import CombatController

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main")


class StatsInputWrapper(IInputBackend):
    """
    Wraps an IInputBackend to count keyboard and mouse click statistics.
    """

    def __init__(self, base_backend: IInputBackend, hp_keys: Set[str], mp_keys: Set[str], stm_keys: Set[str]) -> None:
        self._base = base_backend
        super().__init__()
        self.hp_keys = hp_keys
        self.mp_keys = mp_keys
        self.stm_keys = stm_keys
        
        self.hp_pot_count = 0
        self.mp_pot_count = 0
        self.stm_pot_count = 0
        self.lmb_click_count = 0
        self.rmb_click_count = 0
        self.tab_count = 0

    @property
    def block_inputs(self) -> bool:
        return self._base.block_inputs

    @block_inputs.setter
    def block_inputs(self, val: bool) -> None:
        self._base.block_inputs = val

    @property
    def pressed_keys(self) -> Set[str]:
        return self._base.pressed_keys

    @pressed_keys.setter
    def pressed_keys(self, val: Set[str]) -> None:
        self._base.pressed_keys = val

    @property
    def key_history(self) -> list[str]:
        return self._base.key_history

    @key_history.setter
    def key_history(self, val: list[str]) -> None:
        self._base.key_history = val

    def release_all(self) -> None:
        self._base.release_all()

    def move(self, x_ratio: float, y_ratio: float) -> None:
        self._base.move(x_ratio, y_ratio)

    def click(self, x_ratio: float, y_ratio: float, button: str = "left") -> None:
        if not self.block_inputs:
            if button == "left":
                self.lmb_click_count += 1
            elif button == "right":
                self.rmb_click_count += 1
        self._base.click(x_ratio, y_ratio, button)

    def key(self, name: str, action: str = "press") -> None:
        if not self.block_inputs and action == "press":
            if name in self.hp_keys:
                self.hp_pot_count += 1
            elif name in self.mp_keys:
                self.mp_pot_count += 1
            elif name in self.stm_keys:
                self.stm_pot_count += 1
            else:
                self.tab_count += 1
        self._base.key(name, action)


def load_settings() -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config", "settings.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load settings.json: %s", e)
    return {}


def run_bot(active: bool = False, loop_delay: float = 0.1, max_duration: Optional[float] = None) -> None:
    """
    Initializes and runs the main bot execution loop.

    Args:
        active (bool): If True, sends real inputs using DirectInput (requires Admin).
        loop_delay (float): Delay in seconds between loop cycles.
        max_duration (float, optional): Maximum run duration in seconds (useful for tests/soak limits).
    """
    settings = load_settings()
    window_title = settings.get("window_title", "Priston Tale")
    
    # Differentiate potion keys based on thresholds
    thresholds = settings.get("thresholds", {})
    hp_keys = {t.get("key") for t in thresholds.get("hp", []) if t.get("key")}
    mp_keys = {t.get("key") for t in thresholds.get("mp", []) if t.get("key")}
    stm_keys = {t.get("key") for t in thresholds.get("stm", []) if t.get("key")}

    logger.info("Initializing MVP Lite components...")
    
    hwnd = find_window_by_title(window_title) if sys.platform == "win32" else None

    # Initialize Capture Backend
    if sys.platform == "win32" and hwnd:
        try:
            prefer_backend = settings.get("capture", {}).get("backend", "auto")
            capture_backend = DirectCapture(window_title=window_title, prefer_backend=prefer_backend)
            logger.info("DirectCapture backend initialized.")
        except Exception as e:
            logger.error("Failed to initialize DirectCapture: %s. Falling back to MockCapture.", e)
            capture_backend = MockCapture()
    else:
        logger.info("Game window not active or non-Windows OS. Initializing MockCapture.")
        capture_backend = MockCapture()

    # Initialize Input Backend
    if active and sys.platform == "win32" and hwnd:
        raw_input = DirectInput(window_title=window_title)
        logger.info("DirectInput backend initialized (Active Mode).")
    else:
        raw_input = MockInput()
        logger.info("MockInput backend initialized (Dry-Run / Safe Mode).")

    # Wrap input backend for stats tracking
    input_backend = StatsInputWrapper(raw_input, hp_keys, mp_keys, stm_keys)

    # Initialize FSM State Machine
    fsm = StateMachine(capture_backend, input_backend)
    fsm.running = True
    fsm.transition_to("FARMING", "System initialized and started")

    # Initialize Hotkey Manager
    hotkey_manager = HotkeyManager(fsm, input_backend)
    hotkey_manager.start()

    # Initialize feature controllers
    potion_manager = PotionManager(
        capture=capture_backend, 
        simulator=input_backend, 
        regions=settings.get("regions", {}), 
        thresholds=thresholds
    )
    combat_controller = CombatController(
        capture=capture_backend, 
        simulator=input_backend, 
        config=settings.get("combat", {})
    )
    from features.loot import LootCollector
    loot_collector = LootCollector(
        capture=capture_backend, 
        simulator=input_backend, 
        config=settings.get("loot", {})
    )

    start_time = time.time()
    last_log_time = start_time
    was_attacking = False
    last_loot_time = 0.0

    logger.info("Main FSM loop started. Press F9 to Pause/Resume, F12 to Stop.")

    try:
        while fsm.running:
            current_time = time.time()
            uptime = current_time - start_time

            # Stop loop if max duration exceeded
            if max_duration is not None and uptime >= max_duration:
                logger.info("Max duration reached (%.1fs). Terminating bot.", max_duration)
                fsm.stop()
                break

            # Handle FSM state update
            if fsm.state == "FARMING":
                # Execute pot checks
                potion_manager.check_and_use_pots()
                
                # Execute combat logic if inputs are not blocked
                if not input_backend.block_inputs:
                    is_attacking = combat_controller.run_combat_cycle()
                    # Transition to LOOTING if we were attacking but now target is lost/dead, respecting loot cooldown (e.g. 8s) and loot collector status
                    if was_attacking and not is_attacking:
                        if loot_collector.enabled and (current_time - last_loot_time >= 8.0):
                            fsm.transition_to("LOOTING", "Target eliminated, checking ground loot")
                            last_loot_time = current_time
                    was_attacking = is_attacking
            elif fsm.state == "LOOTING":
                # Execute pot checks
                potion_manager.check_and_use_pots()
                
                if not input_backend.block_inputs:
                    has_more_loot = loot_collector.run_loot_cycle()
                    if not has_more_loot:
                        fsm.transition_to("FARMING", "Loot cycle complete, returning to farming")
                        was_attacking = False
            elif fsm.state == "PAUSED":
                # Bot is paused, don't execute actions
                pass

            # Log stats periodically (every 10 seconds)
            if current_time - last_log_time >= 10.0:
                logger.info(
                    "--- BOT STATISTICS ---\n"
                    "  Uptime: %.1fs\n"
                    "  FSM State: %s\n"
                    "  Attacks (LMB/RMB): %d / %d\n"
                    "  Target Key Presses: %d\n"
                    "  Potions (HP/MP/STM): %d / %d / %d\n"
                    "----------------------",
                    uptime, fsm.state,
                    input_backend.lmb_click_count, input_backend.rmb_click_count,
                    input_backend.tab_count,
                    input_backend.hp_pot_count, input_backend.mp_pot_count, input_backend.stm_pot_count
                )
                last_log_time = current_time

            time.sleep(loop_delay)

    except KeyboardInterrupt:
        logger.info("FSM Loop interrupted via Ctrl+C.")
    finally:
        # Final cleanup
        hotkey_manager.stop_listening()
        input_backend.release_all()
        logger.info("Bot execution terminated. Final stats logged below.")
        
        # Log chronological key/click history (truncated if too long to prevent log bloat)
        history = input_backend.key_history
        if len(history) <= 150:
            history_str = ", ".join(history)
        else:
            history_str = f"{', '.join(history[:100])} ... [truncated {len(history)-150} items] ... {', '.join(history[-50:])}"
            
        logger.info(
            "--- FINAL BOT STATISTICS ---\n"
            "  Uptime: %.1fs\n"
            "  Attacks (LMB/RMB): %d / %d\n"
            "  Target Key Presses: %d\n"
            "  Potions (HP/MP/STM): %d / %d / %d\n"
            "  Keys/Clicks Pressed: %d\n"
            "  Key Event History: %s\n"
            "----------------------------",
            time.time() - start_time,
            input_backend.lmb_click_count, input_backend.rmb_click_count,
            input_backend.tab_count,
            input_backend.hp_pot_count, input_backend.mp_pot_count, input_backend.stm_pot_count,
            len(history),
            history_str
        )


def main() -> None:
    """Main boot function."""
    print("FSM boot ok")
    # By default, run dry-run mode for 1 second if called directly (for smoke tests/exiting)
    # The real manual run will use scripts/soak_run.py.
    run_bot(active=False, loop_delay=0.1, max_duration=1.0)
    sys.exit(0)


if __name__ == "__main__":
    main()
