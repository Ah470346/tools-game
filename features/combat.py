"""
features/combat.py

Generic combat engine executing standard target-selection and LMB/RMB click loops.
Avoids class-specific combo mechanisms to evade anti-cheat profiling.
"""

import json
import logging
import os
import time
from typing import Dict, Optional, Any
import numpy as np

from backends.input_base import IInputBackend
from backends.capture_base import ICaptureBackend
from core.humanizer import get_random_delay

logger = logging.getLogger(__name__)


class CombatController:
    """
    Manages combat execution flow, targeting enemies (via Tab or YOLO ONNX detector),
    and scheduling mouse buttons.
    """

    def __init__(self, capture: ICaptureBackend, simulator: IInputBackend,
                 config: Optional[Dict] = None, detector: Optional[Any] = None) -> None:
        """
        Initializes CombatController.

        Args:
            capture (ICaptureBackend): Active capture backend.
            simulator (IInputBackend): Active input backend.
            config (Dict, optional): Combat settings. If None, loads from config/settings.json.
            detector (Any, optional): Pre-initialized detector instance. If None, loaded lazily.
        """
        self.capture = capture
        self.input = simulator
        self.config = config or {}
        self.detector = detector

        if config is None:
            # Fallback to load settings.json
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config", "settings.json")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                        self.config = config_data.get("combat", {})
                    logger.info("CombatController: Loaded combat config from %s", config_path)
                except Exception as e:
                    logger.error("CombatController: Failed to load config: %s", e)
            else:
                logger.warning("CombatController: config/settings.json not found at %s", config_path)

        # Destructure settings
        self.target_source = self.config.get("target_source", "tab")
        self.tab_key = self.config.get("tab_key", "space")
        self.tab_interval_sec = self.config.get("tab_interval_sec", 2.0)
        
        self.left_click_cfg = self.config.get("left_click", {"enabled": True, "interval_sec": 0.5})
        self.right_click_cfg = self.config.get("right_click", {"enabled": False, "interval_sec": 1.0})
        self.click_position = self.config.get("click_position", [0.5, 0.5])
        
        # Internal tracking states
        self._last_tab_time = 0.0
        self._last_lmb_time = 0.0
        self._last_rmb_time = 0.0
        
        # Initialize randomized cooldowns to prevent static patterns
        self._current_lmb_cooldown = self.left_click_cfg.get("interval_sec", 0.5)
        self._current_rmb_cooldown = self.right_click_cfg.get("interval_sec", 1.0)
        self._current_tab_cooldown = self.tab_interval_sec

        # Track targets detected via YOLO
        self._yolo_target_pos: Optional[list] = None
        self._last_yolo_target_time = 0.0
        self._target_lock_start_time = 0.0

    def _init_detector(self) -> None:
        """Lazily initializes the MonsterDetector."""
        if self.detector is None:
            model_path = self.config.get("model_path", "models/monster.onnx")
            conf_threshold = self.config.get("conf_threshold", 0.40)
            nms_threshold = self.config.get("nms_threshold", 0.45)
            delta_threshold = self.config.get("delta_threshold", 0.01)
            logger.info("CombatController: Lazily loading MonsterDetector with model_path: %s, delta_threshold: %f", model_path, delta_threshold)
            from vision.detector import MonsterDetector
            self.detector = MonsterDetector(
                model_path=model_path,
                conf_threshold=conf_threshold,
                nms_threshold=nms_threshold,
                delta_threshold=delta_threshold
            )

    def _check_target_lock(self, frame: np.ndarray) -> bool:
        """Checks if a target is currently locked (via target HP bar color)."""
        check_cfg = self.config.get("target_check", {})
        if not check_cfg.get("enabled", False):
            return False

        pixel_coord = check_cfg.get("check_pixel")
        if not pixel_coord:
            return False

        height, width, _ = frame.shape
        px = int(pixel_coord[0] * (width - 1))
        py = int(pixel_coord[1] * (height - 1))

        if px < 0 or px >= width or py < 0 or py >= height:
            return False

        pixel_color = frame[py, px]
        b, g, r = int(pixel_color[0]), int(pixel_color[1]), int(pixel_color[2])
        
        # Predominantly red rule to be extremely robust against gradients/lighting
        is_locked = (r > 120) and (r > 1.3 * g) and (r > 1.4 * b)
        logger.debug("CombatController: Target lock check BGR=[%d, %d, %d], is_locked=%s", b, g, r, is_locked)
        return is_locked

    def has_target(self, frame: np.ndarray) -> bool:
        """
        Determines whether an active target is locked on screen.

        Args:
            frame (np.ndarray): Grabbed game window frame.

        Returns:
            bool: True if target is detected, False otherwise.
        """
        if self.target_source == "tab":
            check_cfg = self.config.get("target_check", {})
            if not check_cfg.get("enabled", False):
                # If target check is disabled, default to True (simulate locked target)
                return True
            return self._check_target_lock(frame)

        elif self.target_source == "yolo":
            now = time.time()
            is_locked = self._check_target_lock(frame)

            # Target Lock Timeout / Stuck Detection
            if is_locked:
                if self._target_lock_start_time == 0.0:
                    self._target_lock_start_time = now
                
                timeout = self.config.get("target_lock_timeout_sec", 5.0)
                if now - self._target_lock_start_time > timeout:
                    cancel_key = self.config.get("cancel_target_key", "esc")
                    logger.info("CombatController: Target lock timeout (stuck?). Pressing '%s' to unlock.", cancel_key)
                    self.input.key(cancel_key, "press")
                    self._yolo_target_pos = None
                    self._target_lock_start_time = 0.0
                    self._last_yolo_target_time = 0.0
                    return False
            else:
                self._target_lock_start_time = 0.0

            lock_duration = self.config.get("yolo_lock_duration_sec", 1.5)
            is_pending = self._yolo_target_pos is not None and (now - self._last_yolo_target_time < lock_duration)

            if not is_locked and not is_pending:
                self._yolo_target_pos = None

            # Always run YOLO to track / update position if locked or pending
            try:
                self._init_detector()
            except Exception as e:
                logger.error("CombatController: Failed to initialize YOLO detector: %s", e)
                return is_locked or is_pending

            if self.detector is None:
                logger.error("CombatController: Detector instance is not available.")
                return is_locked or is_pending

            detections = self.detector.detect(frame)

            if is_locked or is_pending:
                if detections:
                    # Find detection closest to our last target position (or center)
                    reference_pos = self._yolo_target_pos if self._yolo_target_pos is not None else [0.5, 0.5]
                    best_det = None
                    min_dist = float("inf")
                    for det in detections:
                        box = det.get("box", [0.5, 0.5, 0.0, 0.0])
                        xc, yc = box[0], box[1]
                        dist = np.sqrt((xc - reference_pos[0]) ** 2 + (yc - reference_pos[1]) ** 2)
                        if dist < min_dist:
                            min_dist = dist
                            best_det = det
                    
                    if best_det is not None:
                        box = best_det.get("box")
                        self._yolo_target_pos = [box[0], box[1]]
                        logger.debug("CombatController: Target tracked and updated to (%.3f, %.3f)", box[0], box[1])
                return True

            # If not locked and not pending, find a new target closest to the center
            if not detections:
                self._yolo_target_pos = None
                return False

            best_det = None
            min_dist = float("inf")
            for det in detections:
                box = det.get("box", [0.5, 0.5, 0.0, 0.0])
                xc, yc = box[0], box[1]
                dist = np.sqrt((xc - 0.5) ** 2 + (yc - 0.5) ** 2)
                if dist < min_dist:
                    min_dist = dist
                    best_det = det

            engage_range = self.config.get("engage_range_ratio", 1.0)
            if best_det is not None and min_dist <= engage_range:
                box = best_det.get("box")
                self._yolo_target_pos = [box[0], box[1]]
                self._last_yolo_target_time = now
                logger.debug("CombatController: YOLO target acquired at (%.3f, %.3f), dist=%.3f", box[0], box[1], min_dist)
                return True

            self._yolo_target_pos = None
            return False

    def execute_combat_actions(self) -> None:
        """
        Executes click actions on the target when locked, respecting individual cooldowns.
        """
        now = time.time()
        if self.target_source == "yolo" and self._yolo_target_pos is not None:
            cx, cy = self._yolo_target_pos
        else:
            cx, cy = self.click_position

        # LMB Action
        if self.left_click_cfg.get("enabled", False):
            if now - self._last_lmb_time >= self._current_lmb_cooldown:
                logger.info("CombatController: Clicking LMB at (%.3f, %.3f)", cx, cy)
                self.input.click(cx, cy, button="left")
                self._last_lmb_time = now
                # Randomize next interval to avoid anti-cheat pattern detection
                base_interval = self.left_click_cfg.get("interval_sec", 0.5)
                self._current_lmb_cooldown = get_random_delay(base_interval * 0.9, base_interval * 1.1)

        # RMB Action
        if self.right_click_cfg.get("enabled", False):
            if now - self._last_rmb_time >= self._current_rmb_cooldown:
                logger.info("CombatController: Clicking RMB at (%.3f, %.3f)", cx, cy)
                self.input.click(cx, cy, button="right")
                self._last_rmb_time = now
                # Randomize next interval
                base_interval = self.right_click_cfg.get("interval_sec", 1.0)
                self._current_rmb_cooldown = get_random_delay(base_interval * 0.9, base_interval * 1.1)

    def run_combat_cycle(self) -> bool:
        """
        Evaluates current target lock state and executes attacks or searches for targets.

        Returns:
            bool: True if actively attacking a target, False if no target is active (requires FSM search/move).
        """
        frame = self.capture.grab_frame()
        if frame is None or frame.size == 0:
            logger.warning("CombatController: Captured frame is empty or invalid.")
            return False

        if self.has_target(frame):
            self.execute_combat_actions()
            return True
        else:
            # No target active: trigger tab key to cycle/acquire target
            now = time.time()
            if now - self._last_tab_time >= self._current_tab_cooldown:
                logger.info("CombatController: No target. Pressing key '%s' to acquire target.", self.tab_key)
                self.input.key(self.tab_key, "press")
                self._last_tab_time = now
                # Randomize tab interval slightly
                self._current_tab_cooldown = get_random_delay(self.tab_interval_sec * 0.9, self.tab_interval_sec * 1.1)
            else:
                logger.debug("CombatController: Tab targeting on cooldown (elapsed: %.2fs)", now - self._last_tab_time)
            return False
