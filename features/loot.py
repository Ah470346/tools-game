"""
features/loot.py

LootController for finding and collecting dropped items using the Hybrid approach:
1. Hold A to show labels
2. Detect label rectangles
3. Hover over each candidate to verify highlight
4. (Optional) OCR to filter via whitelist
5. Click to pick up
"""

import json
import logging
import os
import time
import difflib
import numpy as np
from typing import Dict, Optional

from backends.input_base import IInputBackend
from backends.capture_base import ICaptureBackend
from vision.label_detector import detect_labels, is_label_highlighted, get_item_click_position, LabelBox
from vision.ocr import TextReader
import core.humanizer as humanizer

logger = logging.getLogger(__name__)

class LootCollector:
    """
    Finds and collects dropped items on the ground.
    Uses a hybrid approach: detect labels -> hover confirm -> (optional) OCR whitelist -> pickup.
    """

    def __init__(self, capture: ICaptureBackend, simulator: IInputBackend, config: Optional[Dict] = None) -> None:
        self.capture = capture
        self.input = simulator
        self.config = config or {}

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        if not self.config:
            # Fallback to load settings.json
            config_path = os.path.join(base_dir, "config", "settings.json")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                        self.config = config_data.get("loot", {})
                except Exception as e:
                    logger.error("LootCollector: Failed to load config: %s", e)

        self.enabled = self.config.get("enabled", True)
        self.mode = self.config.get("mode", "whitelist")  # "whitelist" or "all"
        self.scan_key = self.config.get("scan_key", "a")
        self.pickup_button = self.config.get("pickup_button", "left")
        self.max_scan_duration_s = self.config.get("max_scan_duration_s", 5.0)
        self.hover_confirm_delay_ms = self.config.get("hover_confirm_delay_ms", 250)
        self.pickup_delay_ms = self.config.get("pickup_delay_ms", 100)
        self.label_config = self.config.get("label_detect", {})

        # Load Whitelist / Blacklist
        self.whitelist = []
        self.blacklist = []
        whitelist_path = os.path.join(base_dir, "config", "loot_whitelist.json")
        if os.path.exists(whitelist_path):
            try:
                with open(whitelist_path, "r", encoding="utf-8") as f:
                    wl_data = json.load(f)
                    self.whitelist = [item.lower() for item in wl_data.get("whitelist", [])]
                    self.blacklist = [item.lower() for item in wl_data.get("blacklist", [])]
            except Exception as e:
                logger.error("LootCollector: Failed to load whitelist: %s", e)

        # Initialize OCR
        tesseract_path = None
        settings_path = os.path.join(base_dir, "config", "settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    tesseract_path = config_data.get("ocr", {}).get("tesseract_path")
            except Exception:
                pass

        self.ocr_reader = TextReader(tesseract_path=tesseract_path)
        logger.info(f"LootCollector initialized. Mode: {self.mode}, key: {self.scan_key}")

    def _matches_whitelist(self, text: str) -> bool:
        if not text:
            return False
        text_lower = text.lower().strip()

        for blocked in self.blacklist:
            if blocked in text_lower:
                logger.debug(f"LootCollector: Ignored item '{text}' (blacklist '{blocked}')")
                return False

        if not self.whitelist:
            return True

        for allowed in self.whitelist:
            # Exact substring check first (fast path)
            if allowed in text_lower:
                logger.info(f"LootCollector: Match found! '{text}' matches '{allowed}' (exact)")
                return True
            # Fuzzy check to handle OCR errors (e.g. 'M' read as 'la')
            ratio = difflib.SequenceMatcher(None, allowed, text_lower).ratio()
            if ratio >= 0.75:
                logger.info(f"LootCollector: Fuzzy match! '{text}' ~ '{allowed}' (ratio={ratio:.2f})")
                return True

        logger.debug(f"LootCollector: Ignored item '{text}' (not in whitelist)")
        return False

    def run_loot_cycle(self) -> bool:
        """
        Runs one cycle of the hybrid looting flow.
        Returns True if at least one item was picked up.
        """
        if not self.enabled:
            return False

        start_time = time.time()
        logger.info(f"LootCollector: Starting loot sweep...")
        
        # 1. Hold scan key (A)
        self.input.key(self.scan_key, "down")
        
        # Wait for labels to render completely (adding humanized delay)
        time.sleep(humanizer.get_random_delay(0.7, 1.0))
        
        try:
            # 2. Grab frame and detect labels
            frame = self.capture.grab_frame()
            if frame is None:
                self.input.key(self.scan_key, "up")
                return False

            # Debug save to inspect captured image content
            import cv2
            os.makedirs("runs", exist_ok=True)
            cv2.imwrite("runs/loot_capture_debug.jpg", frame)
                
            labels = detect_labels(frame, self.label_config)
            logger.info(f"LootCollector: Detected {len(labels)} candidate labels")
            
            if not labels:
                self.input.key(self.scan_key, "up")
                return False
                
            # 3. Sort labels by distance from center of screen (character position)
            h, w = frame.shape[:2]
            center_x, center_y = w // 2, h // 2
            
            def dist_to_center(lbl: LabelBox):
                return (lbl.center_x - center_x)**2 + (lbl.center_y - center_y)**2
                
            labels.sort(key=dist_to_center)
            
            items_picked = 0
            
            # 4. Sweep each label
            for label in labels:
                if time.time() - start_time > self.max_scan_duration_s:
                    logger.warning("LootCollector: Sweep timeout reached")
                    break
                    
                # Grab before-hover frame
                frame_before = self.capture.grab_frame()
                
                # Hover over the item below the label to trigger highlight
                norm_x, norm_y = get_item_click_position(label, w, h)
                self.input.move(norm_x, norm_y)
                
                # Wait for highlight to trigger
                base_hover = self.hover_confirm_delay_ms / 1000.0
                time.sleep(humanizer.get_random_delay(base_hover * 0.9, base_hover * 1.1))
                
                # Grab after-hover frame
                frame_after = self.capture.grab_frame()
                
                # DEBUG: Save frames to disk to inspect what the bot is seeing
                import cv2
                cv2.imwrite("hover_before.jpg", frame_before)
                cv2.imwrite("hover_after.jpg", frame_after)
                
                # Verify highlight
                if is_label_highlighted(frame_before, frame_after, label, self.label_config):
                    logger.debug("LootCollector: Label highlight confirmed!")
                    
                    should_pickup = True
                    
                    if self.mode == "whitelist":
                        # Crop the highlighted label from the after frame
                        pad = 2
                        y1 = max(0, label.y - pad)
                        y2 = min(h, label.y + label.h + pad)
                        x1 = max(0, label.x - pad)
                        x2 = min(w, label.x + label.w + pad)
                        roi = frame_after[y1:y2, x1:x2]
                        
                        text = self.ocr_reader.read_text(roi)
                        if text:
                            logger.info(f"LootCollector: OCR text: '{text}'")
                            should_pickup = self._matches_whitelist(text)
                        else:
                            logger.warning("LootCollector: OCR failed to read text. Skipping.")
                            should_pickup = False
                            
                    if should_pickup:
                        # Click the item under the label
                        click_x, click_y = get_item_click_position(label, w, h)
                        self.input.click(click_x, click_y, button=self.pickup_button)
                        base_pickup = self.pickup_delay_ms / 1000.0
                        time.sleep(humanizer.get_random_delay(base_pickup * 0.9, base_pickup * 1.2))
                        
                        # Wait for character to walk to the item
                        time.sleep(humanizer.get_random_delay(0.7, 1.2))
                        items_picked += 1
                else:
                    logger.debug("LootCollector: Label did NOT highlight. Skipping.")
                    
            # 5. Release scan key
            self.input.key(self.scan_key, "up")
            return items_picked > 0
            
        except Exception as e:
            logger.error(f"LootCollector error: {e}")
            self.input.key(self.scan_key, "up")
            return False
