"""
core/humanizer.py

Implements organic delays and human-like cursor movements (e.g. Bezier curves,
random hitbox offset, click duration noise) to evade anti-cheat heuristics.
"""

from typing import List, Tuple


def generate_bezier_path(start: Tuple[int, int], end: Tuple[int, int], steps: int = 15) -> List[Tuple[int, int]]:
    """
    Generates a realistic curved mouse movement path between two points.

    Args:
        start (Tuple[int, int]): Starting screen coordinate.
        end (Tuple[int, int]): Ending screen coordinate.
        steps (int): Number of steps in the path.

    Returns:
        List[Tuple[int, int]]: List of intermediate coordinates to follow.
    """
    # Placeholder implementation
    return [start, end]


def get_random_delay(min_sec: float, max_sec: float) -> float:
    """
    Returns a humanized randomized delay between min and max duration.

    Args:
        min_sec (float): Minimum duration.
        max_sec (float): Maximum duration.

    Returns:
        float: Generated delay in seconds.
    """
    import random
    return random.uniform(min_sec, max_sec)
