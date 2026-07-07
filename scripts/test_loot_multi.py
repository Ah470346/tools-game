"""
scripts/test_loot_multi.py

Manual validation script for multi-item loot pickup (overlapping labels).
Run this while Priston Tale is open with several items dropped close
together on the ground, so their name labels overlap/stack.

Two stages:
  Stage 1 (detection only, no mouse input): holds the scan key, detects
    labels, OCRs and classifies each, and saves an annotated preview image.
  Stage 2 (full cycle): runs LootCollector.run_loot_cycle() in a loop and
    reports what got picked up.

PASS/FAIL criteria are printed after each stage -- judge them against what
you actually see on screen and in the saved preview image.
"""

import sys
import os
import time
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from main import load_settings
from core.coordinates import find_window_by_title, activate_window
from backends.capture_direct import DirectCapture
from backends.input_direct import DirectInput
from vision.label_detector import detect_labels
from features.loot import LootCollector

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test_loot_multi")


def stage1_detection(collector: LootCollector, capture: DirectCapture) -> None:
    print("\n" + "=" * 60)
    print("STAGE 1: Label detection on overlapping items")
    print("=" * 60)
    print("Drop 3+ items close together so their name labels overlap, then wait...")
    time.sleep(3)

    collector.input.key(collector.scan_key, "down")
    time.sleep(1.0)
    frame = capture.grab_frame()
    collector.input.key(collector.scan_key, "up")

    if frame is None:
        print("FAIL: could not capture a frame.")
        return

    labels = detect_labels(frame, collector.label_config)
    print(f"Detected {len(labels)} label box(es).")

    import cv2
    canvas = frame.copy()
    for i, label in enumerate(labels):
        text = collector._ocr_label(frame, label) or ""
        if not text:
            color, status = (0, 255, 255), "unknown"  # yellow
        elif collector._matches_whitelist(text):
            color, status = (0, 255, 0), "wanted"  # green
        else:
            color, status = (0, 0, 255), "trash"  # red
        cv2.rectangle(canvas, (label.x, label.y), (label.x + label.w, label.y + label.h), color, 2)
        cv2.putText(canvas, f"#{i} {text} ({status})", (label.x, max(0, label.y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
        print(f"  #{i}: box=({label.x},{label.y},{label.w},{label.h}) text='{text}' status={status}")

    out_dir = PROJECT_ROOT / "runs"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "loot_multi_debug.jpg"
    cv2.imwrite(str(out_path), canvas)
    print(f"\nSaved annotated preview to: {out_path}")
    print("PASS criteria: box count matches the number of items visible on screen,")
    print("               and each name row on screen has its own box (not merged).")


def stage2_full_cycle(collector: LootCollector, cycles: int = 6) -> None:
    print("\n" + "=" * 60)
    print("STAGE 2: Full loot cycle (probe-sweep + pickup)")
    print("=" * 60)
    print(f"Running run_loot_cycle() for up to {cycles} cycles (1 pickup max per cycle)...")

    picked = 0
    for i in range(cycles):
        result = collector.run_loot_cycle()
        print(f"  Cycle {i + 1}: picked_up={result}")
        if result:
            picked += 1
        else:
            break
        time.sleep(0.5)

    print(f"\nTotal items picked up: {picked}")
    print("PASS criteria:")
    print("  - Every whitelisted item on the ground got picked up.")
    print("  - No clicks landed on blacklisted items or empty ground")
    print("    (watch the character during the run, or check logs above).")
    print("  - Each cycle picked up at most one item.")


def main() -> None:
    settings = load_settings()
    loot_cfg = settings.get("loot", {})
    window_title = settings.get("window_title", "Priston Tale")

    hwnd = find_window_by_title(window_title)
    if not hwnd:
        print(f"Could not find game window '{window_title}'. Is Priston Tale running?")
        sys.exit(1)
    activate_window(hwnd)
    time.sleep(1)

    capture = DirectCapture(window_title=window_title, prefer_backend="auto")
    simulator = DirectInput(window_title=window_title)
    collector = LootCollector(capture=capture, simulator=simulator, config=loot_cfg)
    collector.enabled = True

    print(f"Mode: {collector.mode} | Whitelist: {collector.whitelist} | Blacklist: {collector.blacklist}")

    stage1_detection(collector, capture)
    input("\nPress Enter to run Stage 2 (this will move the mouse and click)...")
    stage2_full_cycle(collector)


if __name__ == "__main__":
    main()
