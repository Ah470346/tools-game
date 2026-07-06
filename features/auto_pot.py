import json
import logging
import os
import time
from typing import Dict, Optional
import numpy as np

from backends.input_base import IInputBackend
from backends.capture_base import ICaptureBackend

logger = logging.getLogger(__name__)


class PotionManager:
    """
    Handles auto pot logic, including checking status regions, matching thresholds,
    and observing key delays/cooldowns.
    """

    def __init__(self, capture: ICaptureBackend, simulator: IInputBackend,
                 regions: Optional[Dict] = None, thresholds: Optional[Dict] = None) -> None:
        """
        Initializes the PotionManager.

        Args:
            capture (ICaptureBackend): Active capture backend.
            simulator (IInputBackend): Active input backend.
            regions (Dict, optional): Bar coordinates & color profiles. If None, loads from config.
            thresholds (Dict, optional): Potion triggers and cooldowns. If None, loads from config.
        """
        self.capture = capture
        self.input = simulator
        self.regions = regions or {}
        self.thresholds = thresholds or {}
        self._last_pressed: Dict[str, float] = {}

        if regions is None or thresholds is None:
            # Fallback to load settings.json
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config", "settings.json")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                        if regions is None:
                            self.regions = config_data.get("regions", {})
                        if thresholds is None:
                            self.thresholds = config_data.get("thresholds", {})
                    logger.info("PotionManager: Loaded config from %s", config_path)
                except Exception as e:
                    logger.error("PotionManager: Failed to load config: %s", e)
            else:
                logger.warning("PotionManager: config/settings.json not found at %s", config_path)

    def check_and_use_pots(self) -> None:
        """
        Evaluates health, mana, and stamina levels from current frame pixels,
        and triggers potion keys if thresholds are breached, respecting cooldowns.
        """
        frame = self.capture.grab_frame()
        if frame is None or frame.size == 0:
            logger.warning("PotionManager: Captured empty or invalid frame.")
            return

        height, width, _ = frame.shape

        for stat in ["hp", "mp", "stm"]:
            bar_key = f"{stat}_bar"
            if bar_key not in self.regions:
                continue

            bar_config = self.regions[bar_key]
            start = bar_config.get("start")
            end = bar_config.get("end")
            filled_color_bgr = bar_config.get("filled_color_bgr")
            tolerance = bar_config.get("color_tolerance", 30)

            if not (start and end and filled_color_bgr):
                continue

            # Sort thresholds from lowest to highest percentage (most critical first)
            threshold_list = sorted(self.thresholds.get(stat, []), key=lambda x: x.get("percent", 0))

            for t in threshold_list:
                percent = t.get("percent")
                key_to_press = t.get("key")
                cooldown_sec = t.get("cooldown_sec", 1.0)

                if percent is None or not key_to_press:
                    continue

                # Calculate coordinates for the sample point along the bar
                ratio = percent / 100.0
                x_ratio = start[0] + ratio * (end[0] - start[0])
                y_ratio = start[1] + ratio * (end[1] - start[1])

                px = int(x_ratio * (width - 1))
                py = int(y_ratio * (height - 1))

                # Bounds safety check
                if px < 0 or px >= width or py < 0 or py >= height:
                    logger.error("PotionManager: Coordinate ratio (%f, %f) out of frame pixel bounds (%d, %d)",
                                 x_ratio, y_ratio, width, height)
                    continue

                pixel_color = frame[py, px]

                # Check Euclidean distance between current BGR and filled BGR color
                diff = np.array(pixel_color, dtype=np.int16) - np.array(filled_color_bgr, dtype=np.int16)
                dist = np.linalg.norm(diff)

                # If distance > tolerance, the bar is not filled at this percentage (needs pot)
                if dist > tolerance:
                    now = time.time()
                    last_time = self._last_pressed.get(key_to_press, 0.0)
                    if now - last_time >= cooldown_sec:
                        logger.info("PotionManager: %s at %d%% is EMPTY (color detected %s, target %s, dist %f). Pressing '%s'.",
                                    stat.upper(), percent, list(pixel_color), list(filled_color_bgr), dist, key_to_press)
                        self.input.key(key_to_press, "press")
                        self._last_pressed[key_to_press] = now
                    else:
                        logger.debug("PotionManager: Potion trigger for key '%s' ignored (on cooldown, elapsed: %.2fs)",
                                     key_to_press, now - last_time)
                    # Exit early for this stat type (only check the most critical breached threshold)
                    break

