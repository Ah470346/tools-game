"""
features/loot.py

Coordinates item collection routines, using vision/color_filter to identify items,
moving toward item locations, and collecting items while filtering based on configuration.
"""

from backends.input_base import IInputBackend
from backends.capture_base import ICaptureBackend


class LootCollector:
    """
    Finds and collects dropped items on the ground.
    """

    def __init__(self, capture: ICaptureBackend, simulator: IInputBackend) -> None:
        """Initializes the LootCollector."""
        self.capture = capture
        self.input = simulator

    def run_loot_cycle(self) -> None:
        """Looks for items, moves to them, and presses the pickup key."""
        pass
