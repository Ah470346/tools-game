"""
tests/test_auto_pot.py

Unit tests for features/auto_pot.py using mock captures and mock inputs.
Verifies that:
- Potion keys are pressed when thresholds are breached.
- Potion keys are NOT pressed when on cooldown.
- Proper threshold priorities are respected (lowest percent checked first).
"""

import time
from typing import Tuple
import numpy as np
import pytest

from backends.capture_base import ICaptureBackend
from backends.input_base import IInputBackend
from backends.mock_backends import MockInput
from features.auto_pot import PotionManager


class DummyCapture(ICaptureBackend):
    """Simple capture backend that returns a configurable frame."""

    def __init__(self, hp_color: Tuple[int, int, int], mp_color: Tuple[int, int, int], stm_color: Tuple[int, int, int]) -> None:
        self.hp_color = hp_color
        self.mp_color = mp_color
        self.stm_color = stm_color

    def grab_frame(self) -> np.ndarray:
        # Create a frame of size 100x100
        # We will set the specific pixels that PotionManager will check.
        # HP starts at [0.15, 0.95], ends at [0.35, 0.95].
        # MP starts at [0.40, 0.95], ends at [0.60, 0.95].
        # STM starts at [0.65, 0.95], ends at [0.85, 0.95].
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        # For our test settings:
        # HP 30% check: x_ratio = 0.15 + 0.3 * (0.35 - 0.15) = 0.15 + 0.06 = 0.21. y_ratio = 0.95.
        # px = int(0.21 * 99) = 20, py = int(0.95 * 99) = 94.
        frame[94, 20] = self.hp_color

        # HP 60% check: x_ratio = 0.15 + 0.6 * (0.35 - 0.15) = 0.15 + 0.12 = 0.27. y_ratio = 0.95.
        # px = int(0.27 * 99) = 26, py = 94.
        frame[94, 26] = self.hp_color

        # MP 35% check: x_ratio = 0.40 + 0.35 * (0.60 - 0.40) = 0.40 + 0.07 = 0.47. y_ratio = 0.95.
        # px = int(0.47 * 99) = 46, py = 94.
        frame[94, 46] = self.mp_color

        # STM 20% check: x_ratio = 0.65 + 0.20 * (0.85 - 0.65) = 0.65 + 0.04 = 0.69. y_ratio = 0.95.
        # px = int(0.69 * 99) = 68, py = 94.
        frame[94, 68] = self.stm_color

        return frame


@pytest.fixture
def base_config() -> Tuple[dict, dict]:
    regions = {
        "hp_bar": {
            "start": [0.15, 0.95],
            "end": [0.35, 0.95],
            "filled_color_bgr": [0, 0, 200],  # Red
            "color_tolerance": 30
        },
        "mp_bar": {
            "start": [0.40, 0.95],
            "end": [0.60, 0.95],
            "filled_color_bgr": [200, 0, 0],  # Blue
            "color_tolerance": 30
        },
        "stm_bar": {
            "start": [0.65, 0.95],
            "end": [0.85, 0.95],
            "filled_color_bgr": [0, 200, 0],  # Green
            "color_tolerance": 30
        }
    }
    thresholds = {
        "hp": [
            { "percent": 30, "key": "2", "cooldown_sec": 0.5 },
            { "percent": 60, "key": "1", "cooldown_sec": 0.5 }
        ],
        "mp": [
            { "percent": 35, "key": "3", "cooldown_sec": 0.5 }
        ],
        "stm": [
            { "percent": 20, "key": "4", "cooldown_sec": 0.5 }
        ]
    }
    return regions, thresholds


def test_auto_pot_all_full(base_config) -> None:
    """If colors match the filled BGR profile perfectly, no keys should be pressed."""
    regions, thresholds = base_config
    # Set pixels to target filled colors
    cap = DummyCapture(hp_color=(0, 0, 200), mp_color=(200, 0, 0), stm_color=(0, 200, 0))
    inp = MockInput()

    manager = PotionManager(capture=cap, simulator=inp, regions=regions, thresholds=thresholds)
    manager.check_and_use_pots()

    assert inp.log == []


def test_auto_pot_hp_below_60(base_config) -> None:
    """HP is below 60% but above 30%. Key '1' should be pressed."""
    regions, thresholds = base_config
    # 30% is filled (red), 60% is empty (black)
    class SpecificDummyCapture(ICaptureBackend):
        def __init__(self, hp_30: Tuple[int, int, int], hp_60: Tuple[int, int, int]) -> None:
            self.hp_30 = hp_30
            self.hp_60 = hp_60

        def grab_frame(self) -> np.ndarray:
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[94, 20] = self.hp_30  # 30%
            frame[94, 26] = self.hp_60  # 60%
            # Fill others to not trigger
            frame[94, 46] = (200, 0, 0)
            frame[94, 68] = (0, 200, 0)
            return frame

    cap = SpecificDummyCapture(hp_30=(0, 0, 200), hp_60=(0, 0, 0))
    inp = MockInput()

    manager = PotionManager(capture=cap, simulator=inp, regions=regions, thresholds=thresholds)
    manager.check_and_use_pots()

    assert inp.log == [("key", "1", "press")]


def test_auto_pot_hp_below_30_prioritizes(base_config) -> None:
    """HP is below 30% (and therefore also below 60%). Key '2' (30%) should be prioritized over key '1'."""
    regions, thresholds = base_config
    # Both 30% and 60% are empty (black)
    class SpecificDummyCapture(ICaptureBackend):
        def grab_frame(self) -> np.ndarray:
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            frame[94, 20] = (0, 0, 0)  # 30% empty
            frame[94, 26] = (0, 0, 0)  # 60% empty
            frame[94, 46] = (200, 0, 0)
            frame[94, 68] = (0, 200, 0)
            return frame

    cap = SpecificDummyCapture()
    inp = MockInput()

    manager = PotionManager(capture=cap, simulator=inp, regions=regions, thresholds=thresholds)
    manager.check_and_use_pots()

    # HP 30% is checked first because of ascending sort by percent.
    # When triggered, it breaks early. So only "2" is pressed.
    assert inp.log == [("key", "2", "press")]


def test_auto_pot_cooldowns(base_config) -> None:
    """Verifies that potion keys respect cooldowns and do not spam."""
    regions, thresholds = base_config
    cap = DummyCapture(hp_color=(0, 0, 0), mp_color=(200, 0, 0), stm_color=(0, 200, 0))
    inp = MockInput()

    manager = PotionManager(capture=cap, simulator=inp, regions=regions, thresholds=thresholds)

    # 1. Trigger (HP is empty, triggers "2")
    manager.check_and_use_pots()
    assert inp.log == [("key", "2", "press")]

    # 2. Trigger again immediately (still empty, but should be on cooldown)
    inp.clear()
    manager.check_and_use_pots()
    assert inp.log == []

    # 3. Wait for cooldown to expire
    time.sleep(0.6)
    manager.check_and_use_pots()
    assert inp.log == [("key", "2", "press")]
