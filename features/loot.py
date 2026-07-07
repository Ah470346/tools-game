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
from vision.ocr import TextReader
import core.humanizer as humanizer

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

    def _ocr_label(self, frame, label: LabelBox) -> Optional[str]:
        """Crops a label's ROI (with small padding) from a frame and OCRs it."""
        h, w = frame.shape[:2]
        pad = 2
        y1 = max(0, label.y - pad)
        y2 = min(h, label.y + label.h + pad)
        x1 = max(0, label.x - pad)
        x2 = min(w, label.x + label.w + pad)
        roi = frame[y1:y2, x1:x2]
        return self.ocr_reader.read_text(roi)

    def _classify_labels(self, frame, labels: List[LabelBox]) -> List[_LabelRecord]:
        """
        OCRs every detected label up front (while still holding the scan key)
        and classifies each as wanted/trash/unknown. Occluded labels whose OCR
        fails are left "unknown" and are re-classified later, once a hover
        highlight brightens them and OCR has a better chance of reading them.
        """
        records: List[_LabelRecord] = []
        for label in labels:
            if self.mode != "whitelist":
                records.append(_LabelRecord(label=label, text="", status="wanted"))
                continue

            text = self._ocr_label(frame, label)
            if not text:
                records.append(_LabelRecord(label=label, text="", status="unknown"))
            elif self._matches_whitelist(text):
                records.append(_LabelRecord(label=label, text=text, status="wanted"))
            else:
                records.append(_LabelRecord(label=label, text=text, status="trash"))
        return records

    def _generate_probe_points(self, label: LabelBox, w: int, h: int,
                                probed_px: List[Tuple[int, int]]) -> Iterator[Tuple[float, float]]:
        """
        Yields normalized (x, y) hover points on a small grid under ``label``,
        skipping points too close to ones already probed (overlapping labels
        share the same ground area, so re-probing the same spot is wasted).
        The first point matches the legacy fixed hover offset (center_x, bottom_y + 20px).
        """
        x_offsets = self.probe_config.get("x_offsets_px", [0, -14, 14])
        y_offsets = self.probe_config.get("y_offsets_px", [20, 12, 30])
        dedupe_dist = self.probe_config.get("dedupe_dist_px", 8)

        for dy in y_offsets:
            for dx in x_offsets:
                px = label.center_x + dx
                py = label.bottom_y + dy
                if any((px - ppx) ** 2 + (py - ppy) ** 2 < dedupe_dist ** 2 for ppx, ppy in probed_px):
                    continue
                probed_px.append((px, py))
                yield max(0.0, min(1.0, px / w)), max(0.0, min(1.0, py / h))

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

            # 3. OCR every label up front and classify wanted/trash/unknown
            records = self._classify_labels(frame, labels)
            candidates = [r for r in records if r.status != "trash"]

            # Sort candidates by distance from center of screen (character position)
            center_x, center_y = w // 2, h // 2

            def dist_to_center(rec: _LabelRecord) -> float:
                return (rec.label.center_x - center_x) ** 2 + (rec.label.center_y - center_y) ** 2

            candidates.sort(key=dist_to_center)

            all_labels = [r.label for r in records]
            max_probes = self.probe_config.get("max_probes_per_cycle", 24)
            probed_px: List[Tuple[int, int]] = []
            probes_done = 0

            # 4. Probe-sweep: hover a grid of points under each candidate label
            # until the game itself tells us (via highlight) which item is there.
            for rec in candidates:
                for norm_x, norm_y in self._generate_probe_points(rec.label, w, h, probed_px):
                    if time.time() - start_time > self.max_scan_duration_s:
                        logger.warning("LootCollector: Sweep timeout reached")
                        return False
                    if probes_done >= max_probes:
                        logger.warning("LootCollector: Max probes per cycle reached")
                        return False

                    frame_before = self.capture.grab_frame()
                    self.input.move(norm_x, norm_y)

                    base_hover = self.hover_confirm_delay_ms / 1000.0
                    time.sleep(humanizer.get_random_delay(base_hover * 0.9, base_hover * 1.1))

                    frame_after = self.capture.grab_frame()
                    probes_done += 1

                    if self.debug_save_frames:
                        import cv2
                        os.makedirs("runs", exist_ok=True)
                        cv2.imwrite("runs/hover_before.jpg", frame_before)
                        cv2.imwrite("runs/hover_after.jpg", frame_after)

                    idx = find_highlighted_label(frame_before, frame_after, all_labels, self.highlight_config)
                    if idx is None:
                        continue

                    winner = records[idx]
                    logger.debug(f"LootCollector: Probe ({norm_x:.3f}, {norm_y:.3f}) highlighted label #{idx} (status={winner.status})")

                    if winner.status == "unknown":
                        # Occluded label -- now that it's highlighted (brighter),
                        # OCR has a better chance of reading it correctly.
                        text = self._ocr_label(frame_after, winner.label)
                        winner.text = text or ""
                        winner.status = "wanted" if (text and self._matches_whitelist(text)) else "trash"

                    if winner.status == "wanted":
                        self.input.click(norm_x, norm_y, button=self.pickup_button)
                        base_pickup = self.pickup_delay_ms / 1000.0
                        time.sleep(humanizer.get_random_delay(base_pickup * 0.9, base_pickup * 1.2))
                        # Wait for character to walk to the item
                        time.sleep(humanizer.get_random_delay(0.7, 1.2))
                        return True

                    if winner is rec:
                        # This candidate is confirmed trash -- stop probing it.
                        break

            return False

        except Exception as e:
            logger.error(f"LootCollector error: {e}")
            return False
        finally:
            # 5. Always release the scan key, even on early return or exception.
            self.input.key(self.scan_key, "up")
