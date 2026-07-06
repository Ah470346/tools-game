import json
import logging
import os
import time
from typing import Dict, Optional

from backends.input_base import IInputBackend
from backends.capture_base import ICaptureBackend
from vision.color_filter import find_item_labels
from vision.ocr import TextReader

logger = logging.getLogger(__name__)


class LootCollector:
    """
    Finds and collects dropped items on the ground.
    Uses OCR to match labels against a whitelist.
    """

    def __init__(self, capture: ICaptureBackend, simulator: IInputBackend, config: Optional[Dict] = None) -> None:
        """
        Initializes the LootCollector.

        Args:
            capture (ICaptureBackend): Active capture backend.
            simulator (IInputBackend): Active input backend.
            config (Dict, optional): Loot settings block. If None, loads from config/settings.json.
        """
        self.capture = capture
        self.input = simulator
        self.config = config or {}

        if not config:
            # Fallback to load settings.json
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config", "settings.json")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                        self.config = config_data.get("loot", {})
                    logger.info("LootCollector: Loaded config from %s", config_path)
                except Exception as e:
                    logger.error("LootCollector: Failed to load config: %s", e)
            else:
                logger.warning("LootCollector: config/settings.json not found at %s", config_path)

        # Destructure parameters
        self.enabled = self.config.get("enabled", True)
        self.show_names_key = self.config.get("show_names_key", "a")
        
        # Load Whitelist / Blacklist (lowercase for case-insensitive matching)
        self.whitelist = [item.lower() for item in self.config.get("whitelist", [])]
        self.blacklist = [item.lower() for item in self.config.get("blacklist", [])]

        # Load Tesseract OCR Path from config
        tesseract_path = None
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "config", "settings.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    tesseract_path = config_data.get("ocr", {}).get("tesseract_path")
            except Exception:
                pass

        self.ocr_reader = TextReader(tesseract_path=tesseract_path)
        logger.info("LootCollector initialized. Enabled: %s, show_names_key: %s", self.enabled, self.show_names_key)

    def _matches_whitelist(self, text: str) -> bool:
        """Helper to check if recognized text matches the whitelist and is not blacklisted."""
        text_lower = text.lower()
        
        # 1. Check blacklist first
        for blocked in self.blacklist:
            if blocked in text_lower:
                logger.debug("LootCollector: Ignored item '%s' (matches blacklist '%s')", text, blocked)
                return False

        # 2. Check whitelist
        for allowed in self.whitelist:
            if allowed in text_lower:
                logger.info("LootCollector: Match found! Item '%s' matches whitelist '%s'", text, allowed)
                return True

        logger.debug("LootCollector: Ignored item '%s' (not in whitelist)", text)
        return False

    def run_loot_cycle(self) -> bool:
        """
        Runs one cycle of candidate label scanning and looting.

        Returns:
            bool: True if an item was successfully clicked/picked up, False if no items found.
        """
        if not self.enabled or not self.ocr_reader.enabled:
            return False

        # 1. Hold name hotkey to display labels
        logger.debug("LootCollector: Holding show-names key '%s' down...", self.show_names_key)
        self.input.key(self.show_names_key, "down")
        
        # Short wait to let UI render name boxes
        time.sleep(0.15)

        try:
            # 2. Grab frame
            frame = self.capture.grab_frame()
            if frame is None or frame.size == 0:
                logger.warning("LootCollector: Captured empty frame.")
                return False

            height, width, _ = frame.shape

            # 3. Find rectangular label boxes
            label_boxes = find_item_labels(frame)
            logger.debug("LootCollector: Detected %d candidate item labels", len(label_boxes))

            # 4. Scan boxes
            for (x, y, w, h) in label_boxes:
                # Add tiny padding to prevent character clipping during cropping
                x_pad = max(0, x - 2)
                y_pad = max(0, y - 2)
                w_pad = min(width - x_pad, w + 4)
                h_pad = min(height - y_pad, h + 4)

                roi = frame[y_pad:y_pad + h_pad, x_pad:x_pad + w_pad]
                
                # Perform OCR read
                text = self.ocr_reader.read_text(roi)
                if text and self._matches_whitelist(text):
                    # Item matches! Release hotkey and click
                    logger.info("LootCollector: Attempting to collect whitelisted item: '%s'", text)
                    self.input.key(self.show_names_key, "up")
                    
                    # Calculate click coordinate: center horizontally, immediately below the bottom edge vertically
                    y_offset = self.config.get("click_y_offset_pixels", 8)
                    xc_click = x + w / 2
                    yc_click = y + h + y_offset

                    xc_ratio = xc_click / width
                    yc_ratio = yc_click / height

                    # Move and click
                    self.input.click(xc_ratio, yc_ratio, button="left")
                    
                    # Cooldown for character to walk to item
                    time.sleep(0.8)
                    return True

            # If loop finished and no item was clicked, release the key
            self.input.key(self.show_names_key, "up")
            logger.debug("LootCollector: No matching whitelisted items found on screen.")
            return False

        except Exception as e:
            logger.error("LootCollector: Error during looting loop: %s", e)
            self.input.key(self.show_names_key, "up")
            return False
