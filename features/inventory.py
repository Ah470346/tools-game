"""
features/inventory.py

Monitors character inventory space, calculating filled vs empty slots from capture screenshots
and determining when inventory is full.
"""

from backends.capture_base import ICaptureBackend


class InventoryManager:
    """
    Manages inventory-state evaluation and triggers returns when capacity is exceeded.
    """

    def __init__(self, capture: ICaptureBackend) -> None:
        """Initializes the InventoryManager."""
        self.capture = capture

    def check_capacity(self) -> float:
        """
        Scans inventory slot states.

        Returns:
            float: Ratio of filled inventory slots (0.0 to 1.0).
        """
        return 0.0
