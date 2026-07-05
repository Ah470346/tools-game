"""
features/navigation.py

Coordinates navigational logic: moving through waypoints, tracking mini-map signals,
executing town return cycles (bán rác, mua thuốc, sửa đồ), and returning to grinding zones.
"""

from backends.input_base import IInputBackend


class NavigationController:
    """
    Manages point-to-point movement and town loop execution.
    """

    def __init__(self, simulator: IInputBackend) -> None:
        """Initializes the NavigationController."""
        self.input = simulator

    def navigate_to_waypoint(self, point: tuple) -> None:
        """Moves the character towards a specific point/coordinate."""
        pass

    def run_town_routine(self) -> None:
        """Executes the standard town restock, repair, and sell routines."""
        pass
