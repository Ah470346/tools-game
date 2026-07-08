"""
scripts/debug_label_mask.py

Manual validation script for the dark-band label detector. Run this while
Priston Tale is open with item name labels visible on the ground, so you can
visually confirm the opened mask keeps a solid bar per label (and tune
`max_brightness_dark` / `open_kernel_w` / `min_solidity` in
config/settings.json if the live scene introduces false positives or misses
labels).

Holds the scan key, grabs one frame, and writes each detection stage to
`runs/`:
  - label_raw.jpg          the captured frame
  - label_dark_mask.jpg    dark label-background mask (before morphology)
  - label_closed_mask.jpg  mask after morphological close (text holes filled)
  - label_opened_mask.jpg  mask after horizontal open (what findContours sees)
  - label_boxes.jpg        the captured frame with detected boxes drawn

PASS criteria: label_opened_mask.jpg keeps one solid horizontal bar per item
name (monsters/trees/scenery eroded away), and label_boxes.jpg draws one box
per item name visible on screen.
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np

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
    min_solidity = label_cfg.get("min_solidity", 0.5)
    close_w = label_cfg.get("close_kernel_w", 25)
    close_h = label_cfg.get("close_kernel_h", 3)
    open_w = label_cfg.get("open_kernel_w", 61)
    open_h = label_cfg.get("open_kernel_h", 1)

    mask = cv2.inRange(value, min_dark, max_dark)
    cv2.imwrite(str(out_dir / "label_dark_mask.jpg"), mask)

    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (close_w, close_h))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel)
    cv2.imwrite(str(out_dir / "label_closed_mask.jpg"), closed)

    open_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (open_w, open_h))
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, open_kernel)
    cv2.imwrite(str(out_dir / "label_opened_mask.jpg"), opened)

    # ------------------------------------------------------------------
    # Stage-by-stage diagnostics: replicate detect_labels' filter chain
    # and count where candidates are dropped, so the log alone explains a
    # 0-detection result (bad frame vs. too-tight thresholds).
    # ------------------------------------------------------------------
    h_img, w_img = frame.shape[:2]
    dark_cov = float(np.count_nonzero(mask)) / float(mask.size)
    open_cov = float(np.count_nonzero(opened)) / float(opened.size)
    print(f"\n[diag] frame={w_img}x{h_img}  V min/mean/max={value.min()}/{value.mean():.0f}/{value.max()}")
    print(f"[diag] dark-mask coverage={dark_cov:.1%}  opened-mask coverage={open_cov:.1%}")

    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_w = label_cfg.get("min_label_width", 30)
    min_h = label_cfg.get("min_label_height", 10)
    single_row_max_h = label_cfg.get("single_row_max_height_px", 22)
    max_stack_rows = label_cfg.get("max_stack_rows", 5)
    row_split_enabled = label_cfg.get("row_split_enabled", True)
    max_h_filter = (single_row_max_h * max_stack_rows) if row_split_enabled else label_cfg.get("max_label_height", 60)

    n_size = n_aspect = n_pos = n_solid = n_pass = 0
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (min_w <= w <= 400 and min_h <= h <= max_h_filter):
            n_size += 1
            continue
        aspect = float(w) / float(h)
        if not (1.5 <= aspect <= 20.0):
            n_aspect += 1
            continue
        if not ((0.05 * h_img <= y <= 0.95 * h_img) and (0.05 * w_img <= x <= 0.95 * w_img)):
            n_pos += 1
            continue
        solidity = cv2.contourArea(contour) / float(w * h)
        if solidity < min_solidity:
            n_solid += 1
            print(f"[diag] contour ({x},{y},{w},{h}) passed geometry but solidity={solidity:.2f} < {min_solidity}")
            continue
        n_pass += 1
    print(f"[diag] contours: total={len(contours)} rejected[size={n_size} aspect={n_aspect} pos={n_pos} solidity={n_solid}] passed={n_pass}")

    labels = detect_labels(frame, label_cfg)
    print(f"Detected {len(labels)} label box(es).")

    canvas = frame.copy()
    for i, label in enumerate(labels):
        cv2.rectangle(canvas, (label.x, label.y), (label.x + label.w, label.y + label.h), (0, 255, 0), 2)
        cv2.putText(canvas, f"#{i}", (label.x, max(0, label.y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)
        print(f"  #{i}: box=({label.x},{label.y},{label.w},{label.h})")
    cv2.imwrite(str(out_dir / "label_boxes.jpg"), canvas)

    print(f"\nSaved debug images to: {out_dir}")
    print("PASS criteria: label_opened_mask.jpg keeps a solid horizontal bar")
    print("               per item name (monsters/trees/scenery eroded away),")
    print("               and label_boxes.jpg draws one box per item name")
    print("               visible on screen.")
    print(f"\nCurrent thresholds: dark_range=({min_dark},{max_dark}), "
          f"close_kernel=({close_w},{close_h}), open_kernel=({open_w},{open_h}), "
          f"min_solidity={min_solidity}")
    print("If monsters/scenery get picked up, raise open_kernel_w or min_solidity.")
    print("If short labels are missed, lower open_kernel_w (but too low re-admits")
    print("monster-width blobs). Adjust max_brightness_dark if the dark band is")
    print("missed on a darker/brighter map.")


if __name__ == "__main__":
    main()
