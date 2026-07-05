"""
core/hotkey_manager.py

Global hotkey listener using the keyboard library.
Listens for F12 (Kill/Emergency Stop) and F9 (Pause/Resume Toggle).
Runs in a separate thread managed internally by the keyboard library.
"""

import logging
from typing import Optional

from backends.input_base import IInputBackend
from core.state_machine import StateMachine

logger = logging.getLogger(__name__)


class HotkeyManager:
    """
    Manages global keyboard hotkeys for Emergency Stop and Pause/Resume.
    Uses the 'keyboard' library under the hood.
    """

    def __init__(
        self,
        state_machine: StateMachine,
        input_backend: IInputBackend,
        kill_key: str = "f12",
        pause_key: str = "f9",
    ) -> None:
        """
        Initializes the HotkeyManager.

        Args:
            state_machine (StateMachine): Active FSM.
            input_backend (IInputBackend): Active input backend.
            kill_key (str): Key name for emergency stop (default 'f12').
            pause_key (str): Key name for pause/resume toggle (default 'f9').
        """
        self.state_machine = state_machine
        self.input_backend = input_backend
        self.kill_key = kill_key
        self.pause_key = pause_key
        self._is_hooked = False

    def start(self) -> None:
        """
        Registers the global hotkeys.
        """
        try:
            import keyboard
            
            keyboard.add_hotkey(self.kill_key, self.kill)
            keyboard.add_hotkey(self.pause_key, self.toggle_pause)
            self._is_hooked = True
            logger.info(
                f"Global hotkeys registered: {self.kill_key.upper()} = Emergency Stop, "
                f"{self.pause_key.upper()} = Pause/Resume"
            )
        except Exception as e:
            logger.warning(
                f"Could not register global hotkeys (permissions/environment issue): {e}"
            )

    def stop_listening(self) -> None:
        """
        Unregisters all global hotkeys.
        """
        if self._is_hooked:
            try:
                import keyboard
                keyboard.remove_hotkey(self.kill_key)
                keyboard.remove_hotkey(self.pause_key)
                self._is_hooked = False
                logger.info("Global hotkeys unregistered.")
            except Exception as e:
                logger.warning(f"Error unregistering hotkeys: {e}")

    def kill(self) -> None:
        """
        Triggers emergency stop.
        Releases all keys, blocks further input immediately, and stops FSM.
        """
        logger.warning("[Emergency Stop] F12 pressed! Stopping bot execution...")
        # 1. Release keys immediately
        self.input_backend.release_all()
        # 2. Block any further input
        self.input_backend.block_inputs = True
        # 3. Stop state machine
        self.state_machine.stop()

    def toggle_pause(self) -> None:
        """
        Triggers pause/resume toggle.
        Releases keys and blocks input on pause; unblocks on resume.
        """
        logger.info(f"[Pause/Resume Toggle] {self.pause_key.upper()} pressed.")
        if not self.state_machine.running:
            logger.info("Engine is not running, pause toggle ignored.")
            return

        # If currently paused, we are about to resume
        if self.state_machine.state == "PAUSED":
            logger.info("Resuming execution...")
            self.input_backend.block_inputs = False
            self.state_machine.toggle_pause()
        else:
            logger.info("Pausing execution...")
            # Release all keys so bot doesn't keep running/moving
            self.input_backend.release_all()
            self.input_backend.block_inputs = True
            self.state_machine.toggle_pause()
