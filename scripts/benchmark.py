"""
scripts/benchmark.py

Benchmarks the performance of the full capture + combat pipeline (vision-only).
Useful for verifying that the pipeline hits the >= 20 FPS requirement on CPU-only.
"""

import argparse
import logging
import time
import os
import sys

# Ensure project root is in pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import psutil
from backends.capture_direct import DirectCapture
from backends.input_direct import DirectInput
from features.combat import CombatController

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("benchmark")

def main():
    parser = argparse.ArgumentParser(description="Benchmark the Priston Tale automation pipeline.")
    parser.add_argument("--mode", type=str, choices=["tab", "yolo"], default="yolo", help="Targeting mode to benchmark.")
    parser.add_argument("--duration", type=int, default=15, help="Duration of the benchmark in seconds.")
    args = parser.parse_args()

    print("=" * 50)
    print(f"PIPELINE BENCHMARK (Mode: {args.mode})")
    print(f"Duration: {args.duration} seconds")
    print("=" * 50)

    print("\nInitializing backends...")
    try:
        capture = DirectCapture() # run as fast as possible
    except Exception as e:
        logger.error(f"Failed to init capture: {e}")
        return

    # Initialize input with block_inputs=True to prevent actually moving the mouse during benchmark
    # We just want to measure CPU and FPS of the loop.
    input_backend = DirectInput()
    input_backend.block_inputs = True  # Safety: don't actually click randomly

    print(f"Initializing CombatController in {args.mode} mode...")
    config = {
        "target_source": args.mode,
        "tab_key": "space",
        "tab_interval_sec": 2.0,
        "left_click": {"enabled": True, "interval_sec": 0.5},
        "right_click": {"enabled": False, "interval_sec": 1.0},
        "model_path": "models/monster.onnx", # if yolo
    }

    combat = CombatController(capture, input_backend, config=config)
    
    if args.mode == "yolo":
        # Force lazy load of the model so it doesn't skew benchmark timing
        print("Warming up YOLO model (this may take a few seconds on CPU)...")
        combat._init_detector()
        # Do one dummy detection to warm up ONNX runtime
        dummy_frame = capture.grab_frame()
        if dummy_frame is not None and combat.detector:
            combat.detector.detect(dummy_frame)
            
        # Start the background thread for yolo
        combat.start()

    print("\nStarting benchmark loop...")
    # Initialize CPU percentage tracker (first call returns 0.0)
    psutil.cpu_percent(interval=None)
    
    start_time = time.time()
    frames_processed = 0
    
    while time.time() - start_time < args.duration:
        frame = capture.grab_frame()
        if frame is not None:
            # We call run_combat_cycle without passing frame if yolo thread is running,
            # but we need to update the frame for the yolo thread first.
            if args.mode == "yolo":
                combat.update_frame(frame)
                combat.run_combat_cycle()
            else:
                combat.run_combat_cycle(frame)
            
            frames_processed += 1
            
        # Sleep slightly to prevent 100% core spinlock if capture is instantly returning the same frame
        # We aim to see if it naturally hits >= 20 FPS without artificially burning a CPU core.
        time.sleep(0.001) 

    end_time = time.time()
    
    if args.mode == "yolo":
        combat.stop()

    cpu_usage = psutil.cpu_percent(interval=None)
    elapsed = end_time - start_time
    fps = frames_processed / elapsed

    print("\n" + "=" * 50)
    print("BENCHMARK RESULTS")
    print("=" * 50)
    print(f"Mode:             {args.mode.upper()}")
    print(f"Duration:         {elapsed:.2f} seconds")
    print(f"Frames processed: {frames_processed}")
    print(f"Average FPS:      {fps:.2f} FPS")
    print(f"CPU Utilization:  {cpu_usage:.1f}%")
    print("=" * 50)

    if fps >= 20.0:
        print("\n[SUCCESS] FPS is >= 20.0. The pipeline meets the performance requirement!")
    else:
        print("\n[FAILED] FPS is < 20.0. The pipeline is too slow.")

if __name__ == "__main__":
    main()
