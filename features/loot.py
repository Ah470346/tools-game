"""
features/loot.py

LootController for finding and collecting dropped items using the Hybrid approach:
1. Hold A to show labels
2. Detect label rectangles (splitting stacked/overlapping labels into rows)
3. OCR every label up front to classify wanted/trash/unknown
4. Probe a small grid of points under each candidate label; after each probe,
   determine WHICH label (if any) actually highlighted (brightened) -- this
   is the item truly under the cursor, which may not be the label being probed
5. Click the verified probe point to pick up exactly one item per cycle
   (the caller re-invokes run_loot_cycle() to re-scan for the rest)
"""

import json
import logging
import os
import time
import difflib
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

from backends.input_base import IInputBackend
from backends.capture_base import ICaptureBackend
from vision.label_detector import detect_labels, find_highlighted_label, LabelBox
import core.humanizer as humanizer
import cv2
import glob

logger = logging.getLogger(__name__)


@dataclass
class _LabelRecord:
    """Classification state for one detected label during a loot sweep."""
    label: LabelBox
    text: str = ""
    status: str = "unknown"  # "wanted" | "trash" | "unknown"

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
        self.probe_config = self.config.get("probe", {})
        self.highlight_config = self.config.get("highlight", {})
        self.debug_save_frames = self.config.get("debug_save_frames", False)

        # Load Templates
        self.templates = {}
        self.template_threshold = self.config.get("template_threshold", 0.60)
        templates_dir = os.path.join(base_dir, "config", "templates")
        if os.path.exists(templates_dir):
            for file_path in glob.glob(os.path.join(templates_dir, "*.*")):
                if file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                    name = os.path.splitext(os.path.basename(file_path))[0]
                    img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        self.templates[name] = img
                        logger.debug(f"LootCollector: Loaded template '{name}'")
                    else:
                        logger.error(f"LootCollector: Failed to load template '{file_path}'")
                        
        logger.info(f"LootCollector initialized. Mode: {self.mode}, key: {self.scan_key}, Loaded {len(self.templates)} templates.")
        
        self.last_scan_time = 0.0

    def _match_template(self, frame, label: LabelBox) -> Optional[str]:
        """
        Crops the label ROI and performs template matching against all loaded templates.
        Returns the name of the template if a match is found, else None.
        """
        if not hasattr(self, 'templates') or not self.templates:
            return None
            
        h, w = frame.shape[:2]
        pad_y = 10
        pad_x = 120  # Generous horizontal padding to catch full text even if label box is just one word
        y1 = max(0, label.y - pad_y)
        y2 = min(h, label.y + label.h + pad_y)
        x1 = max(0, label.x - pad_x)
        x2 = min(w, label.x + label.w + pad_x)
        roi = frame[y1:y2, x1:x2]
        
        if roi.size == 0:
            return None
            
        import cv2
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        best_match_name = None
        best_match_val = -1.0
        
        for name, template in self.templates.items():
            # ROI must be larger or equal to template
            th, tw = template.shape[:2]
            if gray_roi.shape[0] < th or gray_roi.shape[1] < tw:
                continue
                
            res = cv2.matchTemplate(gray_roi, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            
            if max_val > best_match_val:
                best_match_val = max_val
                best_match_name = name
                
        if best_match_val >= getattr(self, 'template_threshold', 0.75):
            logger.info(f"LootCollector: Template matched '{best_match_name}' (score={best_match_val:.2f})")
            return best_match_name
            
        if best_match_val > 0:
            logger.debug(f"LootCollector: Best template match '{best_match_name}' failed threshold (score={best_match_val:.2f})")
            
        return None

    def run_loot_cycle(self) -> bool:
        """
        Runs one cycle of the hybrid looting flow.
        Picks up AT MOST one item per call -- the caller (main.py's LOOTING
        state) re-invokes this method to re-scan and pick up the rest, which
        also naturally re-detects labels that were occluded by the item just
        picked up.
        Returns True if an item was picked up, False otherwise.
        """
        if not self.enabled:
            return False

        if time.time() - self.last_scan_time < 10.0:
            return False

        start_time = time.time()
        logger.info("LootCollector: Starting loot sweep...")

        # 1. Hold scan key (A)
        self.input.key(self.scan_key, "down")
        try:
            # Wait for labels to render completely (adding humanized delay)
            time.sleep(humanizer.get_random_delay(0.7, 1.0))

            # 2. Grab frame and detect labels
            frame = self.capture.grab_frame()
            if frame is None:
                return False

            if self.debug_save_frames:
                import cv2
                os.makedirs("runs", exist_ok=True)
                cv2.imwrite("runs/loot_capture_debug.jpg", frame)

            labels = detect_labels(frame, self.label_config)
            logger.info(f"LootCollector: Detected {len(labels)} candidate labels")

            if not labels:
                return False

            h, w = frame.shape[:2]

            item_names = []
            
            # Iterate through each detected label, hover over it, read it, and click if it matches
            for label in labels:
                # Move mouse to the bottom edge of the table to highlight it without blocking the text
                norm_x = max(0.0, min(1.0, label.center_x / w))
                norm_y = max(0.0, min(1.0, label.bottom_y / h))
                
                self.input.move(norm_x, norm_y)
                time.sleep(0.15)  # Wait for UI to light up the table
                
                # Grab a new frame while hovering
                hover_frame = self.capture.grab_frame()
                if hover_frame is None:
                    item_names.append("Unknown")
                    continue
                    
                # Perform template matching on the highlighted label
                matched_name = self._match_template(hover_frame, label)
                
                if matched_name:
                    item_names.append(matched_name)
                    logger.info(f"LootCollector: Found target '{matched_name}', clicking at ({norm_x:.3f}, {norm_y:.3f})")
                    
                    self.input.click(norm_x, norm_y, button=self.pickup_button)
                    base_pickup = self.pickup_delay_ms / 1000.0
                    time.sleep(humanizer.get_random_delay(base_pickup * 0.9, base_pickup * 1.2))
                    time.sleep(humanizer.get_random_delay(0.7, 1.2))
                else:
                    item_names.append("Unknown")

            logger.info(f" ------------------------list item----------------------------[{', '.join(item_names)}]")
            
            # Mark scan time so we wait 10s before next scan
            self.last_scan_time = time.time()
            return False

        except Exception as e:
            logger.error(f"LootCollector error: {e}")
            return False
        finally:
            # 5. Always release the scan key, even on early return or exception.
            self.input.key(self.scan_key, "up")
