import json
import logging
import os
import time
import threading
from typing import Dict, Optional
import numpy as np

from backends.input_base import IInputBackend
from backends.capture_base import ICaptureBackend
from vision.ocr import TextReader

logger = logging.getLogger(__name__)

class PotionManager:
    """
    Handles auto pot logic, including checking status regions, matching thresholds,
    and observing key delays/cooldowns. Runs OCR in a background thread if enabled.
    """

    def __init__(self, capture: ICaptureBackend, simulator: IInputBackend,
                 regions: Optional[Dict] = None, thresholds: Optional[Dict] = None) -> None:
        self.capture = capture
        self.input = simulator
        self.regions = regions or {}
        self.thresholds = thresholds or {}
        self._last_pressed: Dict[str, float] = {}

        if not self.regions or not self.thresholds:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config", "settings.json")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                        if not self.regions:
                            self.regions = config_data.get("regions", {})
                        if not self.thresholds:
                            self.thresholds = config_data.get("thresholds", {})
                    logger.info("PotionManager: Loaded config from %s", config_path)
                except Exception as e:
                    logger.error("PotionManager: Failed to load config: %s", e)
            else:
                logger.warning("PotionManager: config/settings.json not found at %s", config_path)

        # Threading states
        self._running = False
        self._thread_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._ocr_thread: Optional[threading.Thread] = None

        self._last_hp_percent: Optional[float] = None
        self._last_mp_percent: Optional[float] = None

        # Initialize OCR TextReader
        self.ocr_enabled = False
        self.hp_ocr_region = None
        self.mp_ocr_region = None
        self.ocr_reader = None

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "config", "settings.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    ocr_cfg = config_data.get("ocr", {})
                    if ocr_cfg.get("enabled", False):
                        self.ocr_enabled = True
                        tess_path = ocr_cfg.get("tesseract_path")
                        self.ocr_reader = TextReader(tesseract_path=tess_path)
                        self.hp_ocr_region = ocr_cfg.get("hp_ocr_region")
                        self.mp_ocr_region = ocr_cfg.get("mp_ocr_region")
                        logger.info("PotionManager: OCR enabled with HP region: %s, MP region: %s", 
                                    self.hp_ocr_region, self.mp_ocr_region)
            except Exception as e:
                logger.error("PotionManager: Failed to initialize OCR: %s", e)

    def start(self) -> None:
        """Starts the background OCR worker thread."""
        if self.ocr_enabled and self.ocr_reader is not None:
            self._running = True
            self._ocr_thread = threading.Thread(target=self._ocr_worker_loop, daemon=True)
            self._ocr_thread.start()
            logger.info("PotionManager: OCR background worker started.")

    def stop(self) -> None:
        """Stops the background OCR worker thread."""
        self._running = False
        if self._ocr_thread is not None and self._ocr_thread.is_alive():
            self._ocr_thread.join(timeout=1.0)
            self._ocr_thread = None
            logger.info("PotionManager: OCR background worker stopped.")

    def update_frame(self, frame: np.ndarray) -> None:
        """Called by the main loop to provide the latest frame."""
        with self._thread_lock:
            self._latest_frame = frame

    def _ocr_worker_loop(self) -> None:
        """Background thread loop to process OCR without blocking the main FSM loop."""
        while self._running:
            frame = None
            with self._thread_lock:
                if self._latest_frame is not None:
                    # Optional: copy frame if you are mutating it, but we are just slicing
                    frame = self._latest_frame

            if frame is None or frame.size == 0:
                time.sleep(0.1)
                continue

            height, width, _ = frame.shape
            
            # HP OCR
            if self.hp_ocr_region:
                start_ratio = self.hp_ocr_region.get("start")
                end_ratio = self.hp_ocr_region.get("end")
                if start_ratio and end_ratio:
                    x_start, y_start = int(start_ratio[0] * width), int(start_ratio[1] * height)
                    x_end, y_end = int(end_ratio[0] * width), int(end_ratio[1] * height)
                    if 0 <= x_start < x_end <= width and 0 <= y_start < y_end <= height:
                        roi = frame[y_start:y_end, x_start:x_end]
                        res = self.ocr_reader.read_values(roi)
                        if res is not None:
                            curr, mx = res
                            if mx > 0:
                                with self._thread_lock:
                                    self._last_hp_percent = (curr / mx) * 100.0

            # MP OCR
            if self.mp_ocr_region:
                start_ratio = self.mp_ocr_region.get("start")
                end_ratio = self.mp_ocr_region.get("end")
                if start_ratio and end_ratio:
                    x_start, y_start = int(start_ratio[0] * width), int(start_ratio[1] * height)
                    x_end, y_end = int(end_ratio[0] * width), int(end_ratio[1] * height)
                    if 0 <= x_start < x_end <= width and 0 <= y_start < y_end <= height:
                        roi = frame[y_start:y_end, x_start:x_end]
                        res = self.ocr_reader.read_values(roi)
                        if res is not None:
                            curr, mx = res
                            if mx > 0:
                                with self._thread_lock:
                                    self._last_mp_percent = (curr / mx) * 100.0

            # Throttle OCR execution to save CPU and let other threads run
            time.sleep(0.3)

    def check_and_use_pots(self, frame: Optional[np.ndarray] = None) -> None:
        """
        Evaluates health, mana, and stamina levels using async OCR (with color-scanning fallback)
        and triggers potion keys if thresholds are breached, respecting cooldowns.
        """
        # Read the latest frame safely
        if frame is None:
            if self._running:
                with self._thread_lock:
                    frame = self._latest_frame
            else:
                frame = self.capture.grab_frame()

        if frame is None or frame.size == 0:
            logger.warning("PotionManager: Captured empty or invalid frame.")
            return

        height, width, _ = frame.shape

        for stat in ["hp", "mp", "stm"]:
            threshold_list = sorted(self.thresholds.get(stat, []), key=lambda x: x.get("percent", 0))
            if not threshold_list:
                continue

            # 1. Attempt OCR for HP and MP if configured
            ocr_success = False
            current_percent = None

            if self.ocr_enabled and stat in ["hp", "mp"]:
                if self._running:
                    with self._thread_lock:
                        if stat == "hp" and self._last_hp_percent is not None:
                            current_percent = self._last_hp_percent
                            ocr_success = True
                        elif stat == "mp" and self._last_mp_percent is not None:
                            current_percent = self._last_mp_percent
                            ocr_success = True
                else:
                    # Synchronous fallback for tests
                    region = self.hp_ocr_region if stat == "hp" else self.mp_ocr_region
                    if region:
                        start_ratio = region.get("start")
                        end_ratio = region.get("end")
                        if start_ratio and end_ratio:
                            x_start, y_start = int(start_ratio[0] * width), int(start_ratio[1] * height)
                            x_end, y_end = int(end_ratio[0] * width), int(end_ratio[1] * height)
                            if 0 <= x_start < x_end <= width and 0 <= y_start < y_end <= height:
                                roi = frame[y_start:y_end, x_start:x_end]
                                ocr_res = self.ocr_reader.read_values(roi)
                                if ocr_res is not None:
                                    current_val, max_val = ocr_res
                                    if max_val > 0:
                                        current_percent = (current_val / max_val) * 100.0
                                        ocr_success = True

            # 2. Fallback to pixel color check if OCR is disabled or failed
            if not ocr_success:
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

            # 3. Evaluate thresholds
            for t in threshold_list:
                percent = t.get("percent")
                key_to_press = t.get("key")
                cooldown_sec = t.get("cooldown_sec", 1.0)

                if percent is None or not key_to_press:
                    continue

                is_empty = False
                trigger_reason = ""

                if ocr_success and current_percent is not None:
                    # Using OCR value
                    if current_percent < percent:
                        is_empty = True
                        trigger_reason = f"OCR percentage {current_percent:.1f}% is below threshold {percent}%"
                else:
                    # Using Color Scanning fallback
                    ratio = percent / 100.0
                    x_ratio = start[0] + ratio * (end[0] - start[0])
                    y_ratio = start[1] + ratio * (end[1] - start[1])

                    px = int(x_ratio * (width - 1))
                    py = int(y_ratio * (height - 1))

                    if px < 0 or px >= width or py < 0 or py >= height:
                        continue

                    pixel_color = frame[py, px]
                    diff = np.array(pixel_color, dtype=np.int16) - np.array(filled_color_bgr, dtype=np.int16)
                    dist = np.linalg.norm(diff)

                    if dist > tolerance:
                        is_empty = True
                        trigger_reason = f"color detected {list(pixel_color)} (expected {list(filled_color_bgr)}, dist {dist:.2f})"

                if is_empty:
                    now = time.time()
                    last_time = self._last_pressed.get(key_to_press, 0.0)
                    if now - last_time >= cooldown_sec:
                        logger.info("PotionManager: %s threshold breached: %s. Pressing '%s'.",
                                    stat.upper(), trigger_reason, key_to_press)
                        self.input.key(key_to_press, "press")
                        self._last_pressed[key_to_press] = now
                    else:
                        logger.debug("PotionManager: Potion trigger for key '%s' ignored (on cooldown, elapsed: %.2fs)",
                                     key_to_press, now - last_time)
                    break

