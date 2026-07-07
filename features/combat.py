"""
features/combat.py

Generic combat engine executing standard target-selection and LMB/RMB click loops.
Avoids class-specific combo mechanisms to evade anti-cheat profiling.
"""

import json
import logging
import os
import time
import threading
from typing import Dict, List, Optional, Any
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
        max_match_dist_ratio = tracker_cfg.get("max_match_dist_ratio", 0.0)
        coast_output_frames = tracker_cfg.get("coast_output_frames", 0)
        self.tracker = TargetTracker(iou_threshold=iou_threshold, max_lost_frames=max_lost_frames,
                                     max_match_dist_ratio=max_match_dist_ratio,
                                     coast_output_frames=coast_output_frames)

        # Track targets detected via YOLO
        self._yolo_target_pos: Optional[list] = None
        self._active_target_id: Optional[int] = None
        self._last_yolo_target_time = 0.0
        self._lock_grace_sec = self.config.get("target_lock_grace_sec", 2.0)
        self._exclusion_zone = self.config.get("exclusion_zone_ratio", 0.06)

        # Last time YOLO actually confirmed the target's position on screen.
        # Guards against clicking a frozen coordinate after the monster is lost.
        self._last_pos_confirm_time = 0.0
        self._stale_timeout = self.config.get("stale_target_timeout_sec", 1.5)
        self._reassoc_delay = self.config.get("reassociate_delay_sec", 0.5)
        self._reassoc_max_dist = self.config.get("reassociate_max_dist_ratio", 0.08)

        # Panel debounce: a single bad panel read must not end the engagement.
        self._panel_last_seen_time = 0.0
        self._panel_gone_confirm_sec = self.config.get("panel_gone_confirm_sec", 0.3)

        # Panel-authoritative: engagement safety valve replaces the old give-up timer.
        self._engagement_max_sec = self.config.get("engagement_max_sec", 45.0)
        self._engagement_start_time = 0.0

        # Blind attack: keep clicking last-known position when YOLO is blind but panel
        # confirms the monster is alive and near the player character.
        self._blind_attack_max_sec = self.config.get("blind_attack_max_sec", 3.0)
        self._blind_attack_max_dist = self.config.get("blind_attack_max_dist_ratio", 0.15)
        self._blind_attack_active = False

        # After a kill, use the corpse position as anchor for next-target selection.
        self._next_target_anchor_sec = self.config.get("next_target_anchor_sec", 5.0)
        self._last_kill_pos: Optional[list] = None
        self._last_kill_time = 0.0

        # Blacklist for unreachable/stuck targets
        self._blacklisted_targets: dict[int, float] = {}
        self._blacklist_duration = self.config.get("blacklist_duration_sec", 15.0)

        # Threading states
        self._running = False
        self._thread_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._yolo_thread: Optional[threading.Thread] = None
        self._latest_tracks: list = []

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

    def start(self) -> None:
        """Starts the background YOLO worker thread."""
        if self.target_source == "yolo":
            self._running = True
            self._yolo_thread = threading.Thread(target=self._yolo_worker_loop, daemon=True)
            self._yolo_thread.start()
            logger.info("CombatController: YOLO background worker started.")

    def stop(self) -> None:
        """Stops the background YOLO worker thread."""
        self._running = False
        if self._yolo_thread is not None and self._yolo_thread.is_alive():
            self._yolo_thread.join(timeout=1.0)
            self._yolo_thread = None
            logger.info("CombatController: YOLO background worker stopped.")

    def update_frame(self, frame: np.ndarray) -> None:
        """Called by the main loop to provide the latest frame."""
        with self._thread_lock:
            self._latest_frame = frame

    def _yolo_worker_loop(self) -> None:
        """Background thread loop to run detector and tracker without blocking the main FSM loop."""
        self._init_detector()
        while self._running:
            frame = None
            with self._thread_lock:
                if self._latest_frame is not None:
                    frame = self._latest_frame

            if frame is None or frame.size == 0 or self.detector is None:
                time.sleep(0.05)
                continue

            try:
                detections = self.detector.detect(frame)
                with self._thread_lock:
                    # Update tracker inside lock since it mutates state
                    self._latest_tracks = self.tracker.update(detections)
            except Exception as e:
                logger.error("CombatController: YOLO background thread error: %s", e)

            # Let the thread yield slightly
            time.sleep(0.02)

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

    def _is_player_track(self, t: dict) -> bool:
        """Returns True if a track is (or overlaps) the player character at screen center."""
        xc, yc, w, h = t["box"]
        # The player character is at the screen center (0.5, 0.5).
        # If the center falls inside the bounding box, it's the player.
        is_player = (xc - w / 2 <= 0.5 <= xc + w / 2) and (yc - h / 2 <= 0.5 <= yc + h / 2)

        # Elliptical exclusion zone (taller than wide) to cover the rest of the character.
        dx = abs(xc - 0.5)
        dy = abs(yc - 0.5)
        in_exclusion_zone = (dx ** 2 + (dy / 2.0) ** 2) <= (self._exclusion_zone ** 2)
        return is_player or in_exclusion_zone

    def _lock_confirmed(self) -> bool:
        """Returns True if the target panel was seen after the current target was acquired."""
        return self._panel_last_seen_time >= self._last_yolo_target_time

    def _recent_kill_anchor(self) -> Optional[list]:
        """Returns the last kill position if recent enough, else None."""
        if (self._last_kill_pos is not None
                and time.time() - self._last_kill_time < self._next_target_anchor_sec):
            return self._last_kill_pos
        return None

    def _select_best_target(self, tracked: list,
                            anchor: Optional[List[float]] = None) -> Optional[dict]:
        """Selects the closest valid monster from tracked detections.

        Filters out blacklisted tracks, coasting tracks, and the player character
        (screen center), then returns the track nearest to *anchor* (or screen
        center if no anchor) that is within engage range.

        Args:
            tracked (list): Active tracks from the TargetTracker.
            anchor (list, optional): [x, y] anchor point for distance sorting.
                Falls back to screen center (0.5, 0.5).

        Returns:
            Optional[dict]: The best track, or None if no valid target is available.
        """
        ax, ay = anchor if anchor else [0.5, 0.5]
        candidates = [t for t in tracked
                      if t["track_id"] not in self._blacklisted_targets
                      and not t.get("coasting", False)
                      and not self._is_player_track(t)]

        if not candidates:
            return None

        best = min(candidates, key=lambda t: np.sqrt(
            (t["box"][0] - ax) ** 2 + (t["box"][1] - ay) ** 2))
        # Engage range is always measured from screen center (limits character travel)
        dist = np.sqrt((best["box"][0] - 0.5) ** 2 + (best["box"][1] - 0.5) ** 2)
        engage_range = self.config.get("engage_range_ratio", 1.0)
        if dist > engage_range:
            return None
        return best

    def has_target(self, frame: Optional[np.ndarray] = None) -> bool:
        """
        Determines whether an active target is locked on screen.

        Args:
            frame (np.ndarray, optional): Grabbed game window frame.

        Returns:
            bool: True if target is detected, False otherwise.
        """
        if frame is None:
            if self._running:
                with self._thread_lock:
                    frame = self._latest_frame
            else:
                frame = self.capture.grab_frame()
        if frame is None or frame.size == 0:
            return False

        if self.target_source == "tab":
            check_cfg = self.config.get("target_check", {})
            if not check_cfg.get("enabled", False):
                # If target check is disabled, default to True (simulate locked target)
                return True
            return self._check_target_lock(frame)

        elif self.target_source == "yolo":
            now = time.time()
            panel_visible = self._is_target_panel_visible(frame)
            if panel_visible:
                self._panel_last_seen_time = now

            # Grace period: just clicked a new target, panel may not appear instantly
            is_grace = (self._yolo_target_pos is not None and
                        now - self._last_yolo_target_time < self._lock_grace_sec)

            # Debounce: while engaged, a single missed panel read (red-ratio flicker)
            # must not be treated as the target's death — that would switch monsters
            # mid-fight and blacklist one that is still alive.
            panel_recent = (self._active_target_id is not None and
                            now - self._panel_last_seen_time < self._panel_gone_confirm_sec)

            if panel_visible or is_grace or panel_recent:
                # Target is alive in-game — stay locked, update click position from YOLO
                try:
                    if self._running:
                        with self._thread_lock:
                            tracked = list(self._latest_tracks)
                    else:
                        self._init_detector()
                        if self.detector is not None:
                            detections = self.detector.detect(frame)
                            tracked = self.tracker.update(detections)
                        else:
                            tracked = []
                    visible = [t for t in tracked if not t.get("coasting", False)]
                    coasting = [t for t in tracked if t.get("coasting", False)]

                    if self._active_target_id is not None:
                        # 1. Active ID in visible tracks → update pos + confirm time
                        match = next((t for t in visible
                                      if t["track_id"] == self._active_target_id), None)
                        if match:
                            self._yolo_target_pos = [match["box"][0], match["box"][1]]
                            self._last_pos_confirm_time = now
                            logger.debug("CombatController: Tracking target ID %d at (%.3f, %.3f)",
                                         self._active_target_id, match["box"][0], match["box"][1])
                        else:
                            # 2. Active ID in coasting tracks → update pos from memory,
                            #    do NOT refresh confirm_time (position is "remembered")
                            coast_match = next((t for t in coasting
                                                if t["track_id"] == self._active_target_id), None)
                            if coast_match:
                                self._yolo_target_pos = [coast_match["box"][0], coast_match["box"][1]]
                                logger.debug("CombatController: Coasting target ID %d at (%.3f, %.3f)",
                                             self._active_target_id,
                                             coast_match["box"][0], coast_match["box"][1])
                            elif (self._yolo_target_pos and
                                  now - self._last_pos_confirm_time >= self._reassoc_delay):
                                # 3. Re-associate: only from visible tracks (not coasting)
                                candidates = [t for t in visible
                                              if t["track_id"] not in self._blacklisted_targets]
                                if candidates:
                                    best = min(candidates, key=lambda t: np.sqrt(
                                        (t["box"][0] - self._yolo_target_pos[0]) ** 2 +
                                        (t["box"][1] - self._yolo_target_pos[1]) ** 2))
                                    d = np.sqrt((best["box"][0] - self._yolo_target_pos[0]) ** 2 +
                                                (best["box"][1] - self._yolo_target_pos[1]) ** 2)
                                    if d < self._reassoc_max_dist:
                                        self._active_target_id = best["track_id"]
                                        self._yolo_target_pos = [best["box"][0], best["box"][1]]
                                        self._last_pos_confirm_time = now
                                        logger.info("CombatController: Re-associated to track ID %d",
                                                    self._active_target_id)

                    # 4. Bootstrap: panel visible but not engaged with anything
                    if self._active_target_id is None and self._yolo_target_pos is None:
                        best = self._select_best_target(tracked, anchor=self._recent_kill_anchor())
                        if best is not None:
                            self._active_target_id = best["track_id"]
                            self._yolo_target_pos = [best["box"][0], best["box"][1]]
                            self._last_yolo_target_time = now
                            self._last_pos_confirm_time = now
                            self._engagement_start_time = now
                            logger.info("CombatController: Panel visible without lock — "
                                        "re-acquired target ID %d at (%.3f, %.3f)",
                                        self._active_target_id, best["box"][0], best["box"][1])
                except Exception as e:
                    logger.error("CombatController: YOLO position update error: %s", e)

                # Decision: report target status based on panel authority
                if self._yolo_target_pos is not None:
                    since_confirm = now - self._last_pos_confirm_time

                    if self._lock_confirmed():
                        # PANEL IS THE SOURCE OF TRUTH — never give-up/blacklist here

                        # Safety valve: engagement running abnormally long
                        if now - self._engagement_start_time > self._engagement_max_sec:
                            logger.warning("CombatController: Engagement exceeded %.0fs safety valve. "
                                           "Clearing target ID %s (NOT blacklisting).",
                                           self._engagement_max_sec, self._active_target_id)
                            self._active_target_id = None
                            self._yolo_target_pos = None
                            self._blind_attack_active = False
                            return False

                        if since_confirm <= self._stale_timeout:
                            # Fresh position — attack normally
                            self._blind_attack_active = False
                            return True

                        # Position is stale: consider blind attack
                        if (panel_visible
                                and self._pos_dist_to_center() <= self._blind_attack_max_dist
                                and since_confirm <= self._blind_attack_max_sec):
                            self._blind_attack_active = True
                            logger.debug("CombatController: Blind attack on target ID %s "
                                         "(stale %.1fs, dist_to_center=%.3f)",
                                         self._active_target_id, since_confirm,
                                         self._pos_dist_to_center())
                            return True

                        # Stale beyond blind window — hold fire but keep engagement
                        self._blind_attack_active = False
                        logger.debug("CombatController: Target ID %s position stale "
                                     "(%.1fs). Holding fire (panel authoritative).",
                                     self._active_target_id, since_confirm)
                        return True  # Keep FSM in FARMING — panel says target is alive

                    else:
                        # Lock not yet confirmed (grace window)
                        self._blind_attack_active = False
                        if since_confirm <= self._stale_timeout:
                            return True
                        return False
                return False

            # Panel not visible and grace expired — target died or was lost (or failed to lock)
            self._blind_attack_active = False
            if self._active_target_id is not None:
                lock_succeeded = self._lock_confirmed()
                if not lock_succeeded:
                    logger.warning("CombatController: Failed to lock target ID %d. Blacklisting for %.1fs.",
                                   self._active_target_id, self._blacklist_duration)
                    self._blacklisted_targets[self._active_target_id] = now
                else:
                    logger.info("CombatController: Target panel gone (target died). "
                                "Clearing target ID %d.", self._active_target_id)
                    # Record kill position for anchor-based next-target selection
                    if self._yolo_target_pos is not None:
                        self._last_kill_pos = list(self._yolo_target_pos)
                        self._last_kill_time = now
                self._active_target_id = None
                self._yolo_target_pos = None

            # Clean up expired blacklist entries
            expired = [tid for tid, t in self._blacklisted_targets.items()
                       if now - t > self._blacklist_duration]
            for tid in expired:
                del self._blacklisted_targets[tid]

            # Find a new target via YOLO and click on it to lock
            try:
                if self._running:
                    with self._thread_lock:
                        tracked = list(self._latest_tracks)
                else:
                    self._init_detector()
                    if self.detector is not None:
                        detections = self.detector.detect(frame)
                        tracked = self.tracker.update(detections)
                    else:
                        tracked = []

                best = self._select_best_target(tracked, anchor=self._recent_kill_anchor())
                if best is not None:
                    dist = np.sqrt((best["box"][0] - 0.5) ** 2 +
                                   (best["box"][1] - 0.5) ** 2)
                    self._active_target_id = best["track_id"]
                    self._yolo_target_pos = [best["box"][0], best["box"][1]]
                    self._last_yolo_target_time = now
                    self._last_pos_confirm_time = now
                    self._engagement_start_time = now
                    logger.info("CombatController: Clicking new target ID %d at (%.3f, %.3f), dist=%.3f",
                                self._active_target_id, best["box"][0], best["box"][1], dist)
                    self.input.click(best["box"][0], best["box"][1], button="left")
                    return False
            except Exception as e:
                logger.error("CombatController: YOLO target search error: %s", e)

            return False

    def _pos_dist_to_center(self) -> float:
        """Distance from current target position to screen center."""
        if self._yolo_target_pos is None:
            return float('inf')
        return float(np.sqrt((self._yolo_target_pos[0] - 0.5) ** 2 +
                             (self._yolo_target_pos[1] - 0.5) ** 2))

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
            if now - self._last_pos_confirm_time > self._stale_timeout and not self._blind_attack_active:
                logger.debug("CombatController: Target position stale; holding fire.")
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

    def run_combat_cycle(self, frame: Optional[np.ndarray] = None) -> bool:
        """
        Evaluates current target lock state and executes attacks or searches for targets.

        Returns:
            bool: True if actively attacking a target, False if no target is active (requires FSM search/move).
        """
        if frame is None:
            if self._running:
                with self._thread_lock:
                    frame = self._latest_frame
            else:
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
