"""
scripts/verify_delta_detection.py

Verification script for Task 2.6 Delta Detection.
Loads settings, initializes the detector with monster.onnx, captures live frames
from the game window, and measures performance benefits (caching vs model inference).
"""

import sys
import os
import time
import logging
import numpy as np
from pathlib import Path

# Ensure project root is in the path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.coordinates import find_window_by_title
from backends.capture_direct import DirectCapture
from vision.detector import MonsterDetector
from main import load_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("verify_delta_detection")


def main() -> None:
    logger.info("Starting Delta Detection Verification...")
    
    # Load settings
    settings = load_settings()
    window_title = settings.get("window_title", "Priston Tale")
    combat_cfg = settings.get("combat", {})
    delta_threshold = combat_cfg.get("delta_threshold", 0.01)
    model_path = combat_cfg.get("model_path", "models/monster.onnx")

    logger.info(f"Configuration: delta_threshold={delta_threshold}, model_path={model_path}")

    # Verify model exists
    if not os.path.exists(model_path):
        logger.error(f"ONNX model file not found at: {model_path}")
        logger.error("Please run scripts/export_onnx.py first to create the ONNX model.")
        sys.exit(1)

    # Initialize Capture
    hwnd = find_window_by_title(window_title) if sys.platform == "win32" else None
    if not hwnd:
        logger.warning(f"Could not find game window '{window_title}'. Verification will run using simulated frames.")
        run_simulated_verification(model_path, delta_threshold)
        return

    capture = DirectCapture(window_title=window_title, prefer_backend="auto")
    logger.info("DirectCapture initialized.")

    # Initialize Detector
    detector = MonsterDetector(
        model_path=model_path,
        conf_threshold=combat_cfg.get("conf_threshold", 0.40),
        nms_threshold=combat_cfg.get("nms_threshold", 0.45),
        delta_threshold=delta_threshold
    )
    logger.info("MonsterDetector initialized.")

    logger.info("Capturing 100 frames to evaluate delta detection caching...")
    logger.info("Keep the game window stationary for the first 50 frames, then move the camera/character for the next 50 frames.")
    
    # Wait for user to prepare
    for i in range(3, 0, -1):
        logger.info(f"Starting in {i}...")
        time.sleep(1.0)

    inference_times = []
    cached_times = []
    cache_hits = 0
    cache_misses = 0

    for idx in range(100):
        frame = capture.grab_frame()
        if frame is None or frame.size == 0:
            time.sleep(0.03)
            continue

        # Measure timing
        t_start = time.perf_counter()
        
        # Check if it would hit the cache manually to measure timing separately
        # We simulate the exact logic in detector.py to categorize the timings
        is_cache_hit = False
        if detector.delta_threshold > 0.0 and detector._prev_frame is not None:
            import cv2
            small_gray = cv2.cvtColor(cv2.resize(frame, (160, 160)), cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(small_gray, detector._prev_frame)
            mean_diff = float(np.mean(diff) / 255.0)
            if mean_diff < detector.delta_threshold:
                is_cache_hit = True

        # Call the actual detector
        detections = detector.detect(frame)
        t_elapsed = (time.perf_counter() - t_start) * 1000.0  # in ms

        if is_cache_hit:
            cached_times.append(t_elapsed)
            cache_hits += 1
        else:
            inference_times.append(t_elapsed)
            cache_misses += 1

        if idx % 10 == 0:
            logger.info(f"Processed {idx}/100 frames... (Current Cache Hits: {cache_hits}, Misses: {cache_misses})")
        
        time.sleep(0.03)  # ~30 FPS capture rate

    # Print summary
    avg_inf = np.mean(inference_times) if inference_times else 0.0
    avg_cache = np.mean(cached_times) if cached_times else 0.0
    total_runs = cache_hits + cache_misses
    cache_ratio = (cache_hits / total_runs) * 100 if total_runs > 0 else 0.0
    
    cpu_time_saved_pct = 0.0
    if avg_inf > 0.0:
        cpu_time_saved_pct = ((avg_inf - avg_cache) * cache_hits) / (avg_inf * total_runs) * 100

    print("\n" + "=" * 60)
    print("  DELTA DETECTION VERIFICATION REPORT (LIVE GAME)")
    print("=" * 60)
    print(f"  Total Frames Evaluated : {total_runs}")
    print(f"  Cache Hits (Cached)    : {cache_hits} ({cache_ratio:.1f}%)")
    print(f"  Cache Misses (Inference): {cache_misses} ({100.0 - cache_ratio:.1f}%)")
    print(f"  Avg Inference Time     : {avg_inf:.2f} ms")
    print(f"  Avg Cache Hit Check Time: {avg_cache:.2f} ms")
    print(f"  Estimated CPU Time Saved: {cpu_time_saved_pct:.1f}%")
    print("=" * 60)
    
    if cache_hits > 0 and cache_misses > 0:
        print("  VERIFICATION RESULT: SUCCESS (Delta detection caching is working as intended)!")
    elif delta_threshold > 0.0 and cache_hits == 0:
        print("  VERIFICATION RESULT: WARNING (No cache hits recorded. Ensure the screen was stationary).")
    else:
        print("  VERIFICATION RESULT: PASSED (Dry-run completes successfully).")
    print("=" * 60 + "\n")


def run_simulated_verification(model_path: str, delta_threshold: float) -> None:
    logger.info("Running verification with simulated frames...")
    
    # Initialize Detector
    detector = MonsterDetector(
        model_path=model_path,
        conf_threshold=0.40,
        nms_threshold=0.45,
        delta_threshold=delta_threshold
    )

    # Generate identical frames
    frame_stationary = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Run first frame -> Cache Miss
    t0 = time.perf_counter()
    detector.detect(frame_stationary)
    time_miss = (time.perf_counter() - t0) * 1000.0

    # Run second identical frame -> Cache Hit
    t1 = time.perf_counter()
    detector.detect(frame_stationary)
    time_hit = (time.perf_counter() - t1) * 1000.0

    # Generate different frame -> Cache Miss
    frame_moving = np.ones((480, 640, 3), dtype=np.uint8) * 128
    t2 = time.perf_counter()
    detector.detect(frame_moving)
    time_miss2 = (time.perf_counter() - t2) * 1000.0

    print("\n" + "=" * 60)
    print("  DELTA DETECTION VERIFICATION REPORT (SIMULATED)")
    print("=" * 60)
    print(f"  First Frame (Cache Miss)  : {time_miss:.2f} ms")
    print(f"  Second Frame (Cache Hit)  : {time_hit:.2f} ms")
    print(f"  Moving Frame (Cache Miss) : {time_miss2:.2f} ms")
    print(f"  Time Saved per Cache Hit  : {time_miss - time_hit:.2f} ms ({(1 - time_hit/time_miss)*100:.1f}% reduction)")
    print("=" * 60)
    
    if time_hit < time_miss * 0.1:
        print("  VERIFICATION RESULT: SUCCESS (Simulated Cache hit is > 10x faster)!")
    else:
        print("  VERIFICATION RESULT: FAILED (Cache hit is not significantly faster)!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
