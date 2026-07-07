"""
core/humanizer.py

Implements organic delays and human-like cursor movements (e.g. Bezier curves,
random hitbox offset, click duration noise) to evade anti-cheat heuristics.
"""

import math
import random
from typing import List, Tuple

def generate_bezier_path(start: Tuple[int, int], end: Tuple[int, int], steps: int = 15) -> List[Tuple[int, int]]:
    """
    Generates a realistic curved mouse movement path between two points using a quadratic Bezier curve.
    Adds a random control point to simulate non-linear human movement.

    Args:
        start (Tuple[int, int]): Starting screen coordinate.
        end (Tuple[int, int]): Ending screen coordinate.
        steps (int): Number of steps in the path.

    Returns:
        List[Tuple[int, int]]: List of intermediate coordinates to follow.
    """
    if steps < 2:
        return [start, end]
        
    x0, y0 = start
    x2, y2 = end
    
    # Calculate a random control point to make the curve organic.
    # We take the midpoint and offset it perpendicularly by a random amount.
    mx, my = (x0 + x2) / 2, (y0 + y2) / 2
    dx, dy = (x2 - x0), (y2 - y0)
    
    distance = math.hypot(dx, dy)
    
    # Random deviation proportional to the distance moved (e.g., up to 20% of distance)
    # If distance is very small, deviation is small.
    deviation = random.uniform(-0.2, 0.2) * distance
    
    if distance > 0:
        # Perpendicular vector normalized
        nx, ny = -dy / distance, dx / distance
    else:
        nx, ny = 0, 0
        
    x1 = mx + nx * deviation
    y1 = my + ny * deviation

    path = []
    for i in range(steps):
        t = i / (steps - 1)
        # Quadratic bezier formula: (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
        u = 1 - t
        px = (u**2) * x0 + 2 * u * t * x1 + (t**2) * x2
        py = (u**2) * y0 + 2 * u * t * y1 + (t**2) * y2
        path.append((int(px), int(py)))
        
    return path

def get_random_delay(min_sec: float, max_sec: float) -> float:
    """
    Returns a humanized randomized delay between min and max duration.
    Uses a clipped normal distribution (Gaussian) centered in the middle of the range,
    making extreme values less likely than central ones.

    Args:
        min_sec (float): Minimum duration.
        max_sec (float): Maximum duration.

    Returns:
        float: Generated delay in seconds.
    """
    mean = (min_sec + max_sec) / 2
    std_dev = (max_sec - min_sec) / 6  # 99.7% of values within 3 standard deviations
    
    delay = random.gauss(mean, std_dev)
    # Clip to bounds
    return max(min_sec, min(delay, max_sec))

def add_jitter_ratio(x_ratio: float, y_ratio: float, max_pixels: int = 5, base_width: int = 1920, base_height: int = 1080) -> Tuple[float, float]:
    """
    Adds a small random pixel jitter to normalized ratio coordinates.
    
    Args:
        x_ratio (float): Original X ratio (0.0 to 1.0)
        y_ratio (float): Original Y ratio (0.0 to 1.0)
        max_pixels (int): Maximum pixel deviation.
        base_width (int): Reference width to calculate ratio offset.
        base_height (int): Reference height to calculate ratio offset.
        
    Returns:
        Tuple[float, float]: Jittered (x_ratio, y_ratio)
    """
    x_offset = random.uniform(-max_pixels, max_pixels) / base_width
    y_offset = random.uniform(-max_pixels, max_pixels) / base_height
    
    return max(0.0, min(1.0, x_ratio + x_offset)), max(0.0, min(1.0, y_ratio + y_offset))
