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
from vision.tracker import TargetTracker

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

        # Initialize Tracker
        tracker_cfg = {}
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "config", "settings.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    settings_data = json.load(f)
                    tracker_cfg = settings_data.get("tracker", {})
            except Exception as e:
                logger.error("CombatController: Failed to load tracker config from settings: %s", e)
        
        iou_threshold = tracker_cfg.get("iou_threshold", 0.3)
        max_lost_frames = tracker_cfg.get("max_lost_frames", 15)
        self.tracker = TargetTracker(iou_threshold=iou_threshold, max_lost_frames=max_lost_frames)

        # Track targets detected via YOLO
        self._yolo_target_pos: Optional[list] = None
        self._active_target_id: Optional[int] = None
        self._last_yolo_target_time = 0.0
        self._lock_grace_sec = self.config.get("target_lock_grace_sec", 2.0)
        self._exclusion_zone = self.config.get("exclusion_zone_ratio", 0.06)

        # Blacklist for unreachable/stuck targets
        self._blacklisted_targets: dict[int, float] = {}
        self._blacklist_duration = self.config.get("blacklist_duration_sec", 15.0)

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

    def _is_target_panel_visible(self, frame: np.ndarray) -> bool:
        """Checks if the target info panel (HP bar) is visible in the top-right corner.

        When a monster is targeted in Priston Tale, a panel with its portrait,
        name, and HP bar appears in the top-right corner. This method checks
        for red HP bar pixels in that region to determine if a target is active.
        """
        check_cfg = self.config.get("target_check", {})
        if not check_cfg.get("enabled", False):
            return False

        region = check_cfg.get("region")
        if not region:
            return False

        start = region.get("start", [0.86, 0.12])
        end = region.get("end", [0.97, 0.23])

        height, width = frame.shape[:2]
        x1 = max(0, int(start[0] * (width - 1)))
        y1 = max(0, int(start[1] * (height - 1)))
        x2 = min(width, int(end[0] * (width - 1)))
        y2 = min(height, int(end[1] * (height - 1)))

        if x2 <= x1 or y2 <= y1:
            return False

        roi = frame[y1:y2, x1:x2]
        b_ch = roi[:, :, 0].astype(np.int32)
        g_ch = roi[:, :, 1].astype(np.int32)
        r_ch = roi[:, :, 2].astype(np.int32)

        red_mask = (r_ch > 120) & (r_ch > 1.3 * g_ch) & (r_ch > 1.4 * b_ch)
        red_ratio = float(np.sum(red_mask)) / max(red_mask.size, 1)

        min_ratio = check_cfg.get("min_red_ratio", 0.02)
        is_visible = red_ratio >= min_ratio

        logger.debug("CombatController: Target panel red_ratio=%.4f (threshold=%.4f) -> visible=%s",
                     red_ratio, min_ratio, is_visible)
        return is_visible

    def _select_best_target(self, tracked: list) -> Optional[dict]:
        """Selects the closest valid monster from tracked detections.

        Filters out blacklisted tracks and the player character (screen center),
        then returns the track nearest to center that is within engage range.

        Args:
            tracked (list): Active tracks from the TargetTracker.

        Returns:
            Optional[dict]: The best track, or None if no valid target is available.
        """
        candidates = []
        for t in tracked:
            if t["track_id"] in self._blacklisted_targets:
                continue

            xc, yc, w, h = t["box"]
            # The player character is at the screen center (0.5, 0.5).
            # If the center falls inside the bounding box, it's the player.
            is_player = (xc - w / 2 <= 0.5 <= xc + w / 2) and (yc - h / 2 <= 0.5 <= yc + h / 2)

            # Elliptical exclusion zone (taller than wide) to cover the rest of the character.
            dx = abs(xc - 0.5)
            dy = abs(yc - 0.5)
            in_exclusion_zone = (dx ** 2 + (dy / 2.0) ** 2) <= (self._exclusion_zone ** 2)

            if not is_player and not in_exclusion_zone:
                candidates.append(t)

        if not candidates:
            return None

        best = min(candidates, key=lambda t: np.sqrt(
            (t["box"][0] - 0.5) ** 2 + (t["box"][1] - 0.5) ** 2))
        dist = np.sqrt((best["box"][0] - 0.5) ** 2 + (best["box"][1] - 0.5) ** 2)
        engage_range = self.config.get("engage_range_ratio", 1.0)
        if dist > engage_range:
            return None
        return best

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
            panel_visible = self._is_target_panel_visible(frame)

            # Grace period: just clicked a new target, panel may not appear instantly
            is_grace = (self._yolo_target_pos is not None and
                        now - self._last_yolo_target_time < self._lock_grace_sec)

            if panel_visible or is_grace:
                # Target is alive in-game — stay locked, update click position from YOLO
                try:
                    self._init_detector()
                    if self.detector is not None:
                        detections = self.detector.detect(frame)
                        tracked = self.tracker.update(detections)

                        if self._active_target_id is not None and tracked:
                            match = next((t for t in tracked
                                          if t["track_id"] == self._active_target_id), None)
                            if match:
                                self._yolo_target_pos = [match["box"][0], match["box"][1]]
                                logger.debug("CombatController: Tracking target ID %d at (%.3f, %.3f)",
                                             self._active_target_id, match["box"][0], match["box"][1])
                            elif self._yolo_target_pos and tracked:
                                # Track ID lost but panel still visible — re-associate to closest
                                best = min(tracked, key=lambda t: np.sqrt(
                                    (t["box"][0] - self._yolo_target_pos[0]) ** 2 +
                                    (t["box"][1] - self._yolo_target_pos[1]) ** 2))
                                d = np.sqrt((best["box"][0] - self._yolo_target_pos[0]) ** 2 +
                                            (best["box"][1] - self._yolo_target_pos[1]) ** 2)
                                if d < 0.15:
                                    self._active_target_id = best["track_id"]
                                    self._yolo_target_pos = [best["box"][0], best["box"][1]]
                                    logger.info("CombatController: Re-associated to track ID %d",
                                                self._active_target_id)

                        # Panel is visible but we have no confirmed target position
                        # (e.g. previous target just died and its panel still lingers).
                        # Re-acquire the nearest real monster from YOLO instead of leaving
                        # the position unset, which would make execute_combat_actions fall
                        # back to screen center and attack the player character.
                        if self._yolo_target_pos is None:
                            best = self._select_best_target(tracked)
                            if best is not None:
                                self._active_target_id = best["track_id"]
                                self._yolo_target_pos = [best["box"][0], best["box"][1]]
                                self._last_yolo_target_time = now
                                logger.info("CombatController: Panel visible without lock — "
                                            "re-acquired target ID %d at (%.3f, %.3f)",
                                            self._active_target_id, best["box"][0], best["box"][1])
                except Exception as e:
                    logger.error("CombatController: YOLO position update error: %s", e)

                # Only report an active target when we actually know where to click.
                # Never return True without a position — that would trigger a click at
                # click_position (screen center = the player character).
                if self._yolo_target_pos is not None:
                    return True
                return False

            # Panel not visible and grace expired — target died or was lost (or failed to lock)
            if self._active_target_id is not None:
                # If we had a recent target but panel never showed, it might be stuck/unreachable.
                # Blacklist it so we don't keep trying to click the same unreachable monster.
                if not panel_visible and now - self._last_yolo_target_time >= self._lock_grace_sec:
                    logger.warning("CombatController: Failed to lock target ID %d. Blacklisting for %.1fs.",
                                   self._active_target_id, self._blacklist_duration)
                    self._blacklisted_targets[self._active_target_id] = now
                else:
                    logger.info("CombatController: Target panel gone. Clearing target ID %d.",
                                self._active_target_id)
                self._active_target_id = None
                self._yolo_target_pos = None

            # Clean up expired blacklist entries
            expired = [tid for tid, t in self._blacklisted_targets.items()
                       if now - t > self._blacklist_duration]
            for tid in expired:
                del self._blacklisted_targets[tid]

            # Find a new target via YOLO and click on it to lock
            try:
                self._init_detector()
                if self.detector is not None:
                    detections = self.detector.detect(frame)
                    tracked = self.tracker.update(detections)

                    # Pick the closest valid monster (excludes player/blacklist/out-of-range)
                    best = self._select_best_target(tracked)
                    if best is not None:
                        dist = np.sqrt((best["box"][0] - 0.5) ** 2 +
                                       (best["box"][1] - 0.5) ** 2)
                        self._active_target_id = best["track_id"]
                        self._yolo_target_pos = [best["box"][0], best["box"][1]]
                        self._last_yolo_target_time = now
                        logger.info("CombatController: Clicking new target ID %d at (%.3f, %.3f), dist=%.3f",
                                    self._active_target_id, best["box"][0], best["box"][1], dist)
                        self.input.click(best["box"][0], best["box"][1], button="left")
                        return False
            except Exception as e:
                logger.error("CombatController: YOLO target search error: %s", e)

            return False

    def execute_combat_actions(self) -> None:
        """
        Executes click actions on the target when locked, respecting individual cooldowns.
        """
        now = time.time()
        if self.target_source == "yolo":
            # In YOLO mode we must never fall back to click_position (screen center),
            # which is the player character. If we have no confirmed target position,
            # skip attacking this cycle.
            if self._yolo_target_pos is None:
                logger.debug("CombatController: No YOLO target position; skipping attack "
                             "to avoid clicking the player character.")
                return
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
            # No target active
            if self.target_source == "tab":
                now = time.time()
                if now - self._last_tab_time >= self._current_tab_cooldown:
                    logger.info("CombatController: No target. Pressing key '%s' to acquire target.", self.tab_key)
                    self.input.key(self.tab_key, "press")
                    self._last_tab_time = now
                    self._current_tab_cooldown = get_random_delay(self.tab_interval_sec * 0.9, self.tab_interval_sec * 1.1)
                else:
                    logger.debug("CombatController: Tab targeting on cooldown (elapsed: %.2fs)", now - self._last_tab_time)
            # In YOLO mode, target acquisition is handled inside has_target()
            return False
