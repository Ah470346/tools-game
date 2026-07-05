"""
tests/test_coordinates.py

Unit tests for core/coordinates.py.
Verifies ratio-to-screen coordinate conversions, clamping constraints,
and legacy region calculation helpers.
"""

from unittest.mock import MagicMock, patch

import pytest

import core.coordinates as coords


def test_ratio_to_screen_top_left():
    """Ratio (0.0, 0.0) converts to absolute client area top-left screen coordinate."""
    # Mock get_client_rect_screen to return a fixed client rect: left=100, top=200, right=900, bottom=800
    with patch.object(coords, "get_client_rect_screen", return_value=(100, 200, 900, 800)):
        x, y = coords.ratio_to_screen(0.0, 0.0, hwnd=123)
        assert x == 100
        assert y == 200


def test_ratio_to_screen_bottom_right():
    """Ratio (1.0, 1.0) converts to absolute client area bottom-right screen coordinate."""
    with patch.object(coords, "get_client_rect_screen", return_value=(100, 200, 900, 800)):
        x, y = coords.ratio_to_screen(1.0, 1.0, hwnd=123)
        assert x == 900
        assert y == 800


def test_ratio_to_screen_center():
    """Ratio (0.5, 0.5) converts to absolute client area center screen coordinate."""
    # Client width = 900 - 100 = 800; center relative X = 400; screen X = 100 + 400 = 500
    # Client height = 800 - 200 = 600; center relative Y = 300; screen Y = 200 + 300 = 500
    with patch.object(coords, "get_client_rect_screen", return_value=(100, 200, 900, 800)):
        x, y = coords.ratio_to_screen(0.5, 0.5, hwnd=123)
        assert x == 500
        assert y == 500


def test_ratio_to_screen_clamping():
    """Ratio coordinates beyond [0.0, 1.0] are clamped to prevent mouse moving off-screen."""
    with patch.object(coords, "get_client_rect_screen", return_value=(100, 200, 900, 800)):
        # Ratios > 1.0 clamped to 1.0
        x, y = coords.ratio_to_screen(1.5, 1.2, hwnd=123)
        assert x == 900
        assert y == 800

        # Ratios < 0.0 clamped to 0.0
        x, y = coords.ratio_to_screen(-0.5, -0.1, hwnd=123)
        assert x == 100
        assert y == 200


def test_get_client_rect_and_region():
    """get_client_rect_and_region returns (left, top, width, height)."""
    with patch.object(coords, "get_client_rect_screen", return_value=(100, 200, 900, 800)):
        left, top, width, height = coords.get_client_rect_and_region(hwnd=123)
        assert left == 100
        assert top == 200
        assert width == 800   # 900 - 100
        assert height == 600  # 800 - 200


def test_find_window_by_title_no_win32():
    """find_window_by_title returns 0 if win32gui is not available."""
    with patch.object(coords, "_HAS_WIN32", False):
        hwnd = coords.find_window_by_title("Priston Tale")
        assert hwnd == 0


def test_get_client_rect_screen_no_win32():
    """get_client_rect_screen returns fallback coordinates if win32gui is not available or hwnd is 0."""
    with patch.object(coords, "_HAS_WIN32", False):
        rect = coords.get_client_rect_screen(hwnd=123)
        assert rect == (100, 100, 900, 700)

    with patch.object(coords, "_HAS_WIN32", True):
        rect = coords.get_client_rect_screen(hwnd=0)
        assert rect == (100, 100, 900, 700)
