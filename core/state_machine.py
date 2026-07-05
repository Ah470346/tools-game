"""
core/state_machine.py

Main Finite State Machine (FSM) controlling bot states (IDLE, FARMING, LOOTING, etc.).
Remains backend-agnostic by receiving interfaces rather than concrete classes.
"""

import logging
from typing import Optional
from backends.capture_base import ICaptureBackend
from backends.input_base import IInputBackend

logger = logging.getLogger(__name__)


class StateMachine:
    """
    Finite State Machine that manages the core loop and state transitions.
    """

    def __init__(self, capture_backend: ICaptureBackend, input_backend: IInputBackend) -> None:
        """
        Initializes the FSM.

        Args:
            capture_backend (ICaptureBackend): Active capture backend.
            input_backend (IInputBackend): Active input backend.
        """
        self.capture = capture_backend
        self.input = input_backend
        self.state = "IDLE"
        self.running = False

    def transition_to(self, new_state: str, reason: str = "") -> None:
        """
        Handles state transitions and logs the event.

        Args:
            new_state (str): State to transition into.
            reason (str): Short explanation of the transition.
        """
        logger.info(f"Transition: {self.state} -> {new_state} | Reason: {reason}")
        self.state = new_state

    def update(self) -> None:
        """Runs one update step in the active state."""
        pass
