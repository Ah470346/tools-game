"""
scripts/collect_dataset.py

Dataset collection utility script for Task 2.1.
Captures game frames periodically using DirectCapture and saves them to data/raw/
with unique timestamp-based filenames.

Usage:
    python scripts/collect_dataset.py [options]

Options:
    --interval SECS     Sampling interval in seconds (default: 1.0)
    --hotkey KEY        Global hotkey to toggle capturing (default: f8)
    --window TITLE      Override game window title to capture
    --output-dir DIR    Override output directory (default: data/raw)
"""

import argparse
import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Ensure project root is in the python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backends.capture_direct import DirectCapture

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("collect_dataset")


def load_settings() -> dict:
    """Loads settings from config/settings.json."""
    config_path = PROJECT_ROOT / "config" / "settings.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error reading settings.json: {e}")
    return {}


class DatasetCollector:
    """Manages periodic game frame capture and saving for dataset creation."""

    def __init__(
        self,
        window_title: str,
        output_dir: str,
        interval: float,
        hotkey: str,
    ) -> None:
        self.window_title = window_title
        self.output_dir = Path(output_dir)
        self.interval = interval
        self.hotkey = hotkey

        self.active = False
        self.capture_backend: Optional[DirectCapture] = None
        self.total_saved = 0

    def setup(self) -> bool:
        """Sets up directories, backend, and registers hotkeys."""
        # 1. Ensure output directory exists
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Output directory verified: {self.output_dir.resolve()}")
        except Exception as e:
            logger.error(f"Failed to create output directory {self.output_dir}: {e}")
            return False

        # 2. Setup capture backend
        try:
            self.capture_backend = DirectCapture(
                window_title=self.window_title,
                prefer_backend="auto"
            )
            logger.info(
                f"DirectCapture initialized (target: '{self.window_title}', "
                f"backend: {self.capture_backend._backend})"
            )
        except Exception as e:
            logger.error(f"Failed to initialize DirectCapture: {e}")
            return False

        # 3. Register hotkey
        try:
            import keyboard
            keyboard.add_hotkey(self.hotkey, self.toggle_capture)
            logger.info(f"Registered global hotkey '{self.hotkey.upper()}' to toggle capture.")
        except Exception as e:
            logger.warning(
                f"Could not register global hotkey (requires Administrator privileges on Windows): {e}\n"
                f"Toggling capturing will not be available via hotkey."
            )

        return True

    def toggle_capture(self) -> None:
        """Toggles the capturing state."""
        self.active = not self.active
        status = "STARTED" if self.active else "PAUSED"
        logger.info(f"*** Capturing has been {status} ***")
        if self.active:
            logger.info(f"Saving frames every {self.interval}s to {self.output_dir}")

    def run(self) -> None:
        """Main execution loop."""
        print("====================================================================")
        print("         Priston Tale Auto Tool - Dataset Collector                  ")
        print("====================================================================")
        print(f"Target Window : {self.window_title}")
        print(f"Interval      : {self.interval} seconds")
        print(f"Output Folder : {self.output_dir.resolve()}")
        print(f"Toggle Hotkey : {self.hotkey.upper()}")
        print("--------------------------------------------------------------------")
        print("Instructions:")
        print(f"  - Press [{self.hotkey.upper()}] globally to start/pause capturing.")
        print("  - Press [Ctrl + C] in this console to stop and exit.")
        print("====================================================================\n")

        last_capture_time = 0.0

        try:
            while True:
                if self.active:
                    current_time = time.perf_counter()
                    if current_time - last_capture_time >= self.interval:
                        self.capture_and_save()
                        last_capture_time = time.perf_counter()
                
                # Sleep a tiny bit to avoid CPU hogging
                time.sleep(0.01)

        except KeyboardInterrupt:
            logger.info("Exiting on KeyboardInterrupt.")
        finally:
            self.cleanup()

    def capture_and_save(self) -> None:
        """Grabs a single frame and saves it to the output directory."""
        if not self.capture_backend:
            return

        try:
            frame = self.capture_backend.grab_frame()
            
            # Formulate timestamped filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"frame_{timestamp}.png"
            filepath = self.output_dir / filename

            # Save the frame
            cv2.imwrite(str(filepath), frame)
            self.total_saved += 1
            logger.info(f"[{self.total_saved}] Saved: {filename} (shape: {frame.shape})")

        except RuntimeError as e:
            # Handle lost window or capture error gracefully without crashing
            logger.warning(f"Capture warning: {e}. Pausing capture...")
            self.active = False
        except Exception as e:
            logger.error(f"Unexpected error during capture/save: {e}")

    def cleanup(self) -> None:
        """Cleans up hooks and resources."""
        logger.info("Cleaning up dataset collector...")
        try:
            import keyboard
            keyboard.remove_hotkey(self.hotkey)
            logger.info("Unregistered hotkey listener.")
        except Exception:
            pass
        logger.info(f"Finished. Total frames saved: {self.total_saved}")


def main() -> None:
    # 1. Parse arguments
    parser = argparse.ArgumentParser(description="Dataset Collection Utility")
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Sampling interval in seconds (default: 1.0)"
    )
    parser.add_argument(
        "--hotkey",
        type=str,
        default="f8",
        help="Global hotkey to toggle capturing (default: f8)"
    )
    parser.add_argument(
        "--window",
        type=str,
        default=None,
        help="Override target game window title"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Override output directory (default: data/raw)"
    )
    args = parser.parse_args()

    # 2. Load default configs
    settings = load_settings()
    
    # 3. Determine final params
    window_title = args.window or settings.get("window_title") or "Priston Tale"
    output_dir = args.output_dir or str(PROJECT_ROOT / "data" / "raw")

    # 4. Instantiate and run
    collector = DatasetCollector(
        window_title=window_title,
        output_dir=output_dir,
        interval=args.interval,
        hotkey=args.hotkey
    )

    if collector.setup():
        collector.run()
    else:
        logger.error("Failed to setup DatasetCollector. Exiting.")
        sys.exit(1)


if __name__ == "__main__":
    main()
