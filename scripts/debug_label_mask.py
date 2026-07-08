"""
scripts/debug_label_mask.py

Manual validation script for the dark-band label detector. Run this while
Priston Tale is open with item name labels visible on the ground, so you can
visually confirm the dark mask lands on the label backgrounds (and tune
`max_brightness_dark` / `close_kernel_w` / `min_text_ratio` in
config/settings.json if the live scene introduces false positives or misses
labels).

Holds the scan key, grabs one frame, and writes each detection stage to
`runs/`:
  - label_raw.jpg          the captured frame
  - label_dark_mask.jpg    dark label-background mask (before morphological close)
  - label_closed_mask.jpg  mask after morphological close (what findContours sees)
  - label_boxes.jpg        the captured frame with detected boxes drawn

PASS criteria: label_dark_mask.jpg lights up on the label background bands
(not the whole ground or unrelated dark scene elements), and label_boxes.jpg
draws one box per item name visible on screen.
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import cv2

from main import load_settings
from core.coordinates import find_window_by_title, activate_window
from backends.capture_direct import DirectCapture
from backends.input_direct import DirectInput
from vision.label_detector import detect_labels


def main() -> None:
    settings = load_settings()
    loot_cfg = settings.get("loot", {})
    label_cfg = loot_cfg.get("label_detect", {})
    scan_key = loot_cfg.get("scan_key", "a")
    window_title = settings.get("window_title", "Priston Tale")

    hwnd = find_window_by_title(window_title)
    if not hwnd:
        print(f"Could not find game window '{window_title}'. Is Priston Tale running?")
    activate_window(hwnd)

    capture = DirectCapture(window_title=window_title, prefer_backend="auto")
    simulator = DirectInput(window_title=window_title)

    print(">>> YOU HAVE 5 SECONDS TO CLICK INTO THE GAME NOW! <<<")
    time.sleep(5)

    print(">>> AUTO-PRESSING SCAN KEY TO REVEAL LABELS... <<<")
    simulator.key(scan_key, "down")
    time.sleep(1.0)
    frame = capture.grab_frame()
    simulator.key(scan_key, "up")

    if frame is None:
        print("FAIL: could not capture a frame.")
        return

    out_dir = PROJECT_ROOT / "runs"
    out_dir.mkdir(exist_ok=True)

    cv2.imwrite(str(out_dir / "label_raw.jpg"), frame)

    value = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[:, :, 2]
    min_dark = label_cfg.get("min_brightness_dark", 0)
    max_dark = label_cfg.get("max_brightness_dark", 110)
    min_bright = label_cfg.get("min_brightness_bright", 150)
    min_text_ratio = label_cfg.get("min_text_ratio", 0.02)
    close_w = label_cfg.get("close_kernel_w", 25)
    close_h = label_cfg.get("close_kernel_h", 3)

    mask = cv2.inRange(value, min_dark, max_dark)
    cv2.imwrite(str(out_dir / "label_dark_mask.jpg"), mask)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (close_w, close_h))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    cv2.imwrite(str(out_dir / "label_closed_mask.jpg"), closed)

    text_mask = value >= min_bright

    labels = detect_labels(frame, label_cfg)
    print(f"Detected {len(labels)} label box(es).")

    canvas = frame.copy()
    for i, label in enumerate(labels):
        roi_text = text_mask[label.y:label.y + label.h, label.x:label.x + label.w]
        text_ratio = float(roi_text.sum()) / float(label.w * label.h) if label.w * label.h > 0 else 0.0
        cv2.rectangle(canvas, (label.x, label.y), (label.x + label.w, label.y + label.h), (0, 255, 0), 2)
        cv2.putText(canvas, f"#{i}", (label.x, max(0, label.y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)
        print(f"  #{i}: box=({label.x},{label.y},{label.w},{label.h}) text_ratio={text_ratio:.3f}")
    cv2.imwrite(str(out_dir / "label_boxes.jpg"), canvas)

    print(f"\nSaved debug images to: {out_dir}")
    print("PASS criteria: label_dark_mask.jpg lights up on the label background")
    print("               bands (not the whole ground or unrelated dark scene")
    print("               elements), and label_boxes.jpg draws one box per")
    print("               item name visible on screen.")
    print(f"\nCurrent thresholds: dark_range=({min_dark},{max_dark}), "
          f"close_kernel=({close_w},{close_h}), min_text_ratio={min_text_ratio}")
    print("If dark ground/scenery gets picked up, lower max_brightness_dark")
    print("or raise min_text_ratio in config/settings.json.")
    print("If label bands are missed/split, adjust max_brightness_dark or")
    print("close_kernel_w/h in config/settings.json.")


if __name__ == "__main__":
    main()
