"""
core/coordinates.py

Translates normalized ratio coordinates (0.0 to 1.0) to screen pixel coordinates,
taking window positions, title bars, and offsets into account.
"""

from typing import Tuple


def ratio_to_screen(x_ratio: float, y_ratio: float, hwnd: int) -> Tuple[int, int]:
    """
    Converts ratio coordinates relative to the game client area to screen coordinates,
    accounting for window positioning and borders.

    Args:
        x_ratio (float): Horizontal ratio (0.0 to 1.0).
        y_ratio (float): Vertical ratio (0.0 to 1.0).
        hwnd (int): Window handle of the game.

    Returns:
        Tuple[int, int]: (x, y) coordinates on the screen.
    """
    # Placeholder implementation
    return 0, 0


def get_client_rect_and_region(hwnd: int) -> Tuple[int, int, int, int]:
    """
    Returns the client area bounding box for capture and rendering.

    Args:
        hwnd (int): Window handle of the game.

    Returns:
        Tuple[int, int, int, int]: (left, top, width, height) of the client region.
    """
    # Placeholder implementation
    return 0, 0, 800, 600
