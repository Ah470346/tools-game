"""
scripts/export_onnx.py

Export trained YOLOv8 PyTorch weights (.pt) to ONNX format for lightweight deployment.
Usage:
    python scripts/export_onnx.py --weights runs/detect/pt_monster/weights/best.pt
"""

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

# Ensure project root is in the python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("export_onnx")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export YOLOv8 PyTorch model to ONNX")
    parser.add_argument(
        "--weights",
        type=str,
        default="runs/detect/pt_monster/weights/best.pt",
        help="Path to the PyTorch .pt weights file (default: runs/detect/pt_monster/weights/best.pt)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="models",
        help="Output directory to place monster.onnx (default: models)"
    )
    args = parser.parse_args()

    weights_path = Path(args.weights)
    if not weights_path.exists():
        logger.error(f"Weights file not found at: {weights_path.resolve()}")
        # Check if runs folder has other names (e.g. if run multiple times)
        logger.info("Tip: Look inside your 'runs/detect/' folder for other training run names.")
        sys.exit(1)

    # Ensure output directory exists
    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Target model output directory verified: {output_dir.resolve()}")

    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error("ultralytics is not installed. Run: pip install -r requirements-train.txt")
        sys.exit(1)

    logger.info(f"Loading YOLO PyTorch weights from: {weights_path.resolve()}...")
    try:
        model = YOLO(str(weights_path))
    except Exception as e:
        logger.error(f"Failed to load YOLO model: {e}")
        sys.exit(1)

    logger.info("Exporting model to ONNX format (imgsz=640, dynamic=False)...")
    try:
        # Exporting to ONNX format
        # simplify=True reduces ONNX node overhead using onnx-simplifier if installed
        onnx_file_path = model.export(
            format="onnx",
            imgsz=640,
            dynamic=False,
            simplify=True
        )
        logger.info(f"Successfully exported ONNX weights to temporary location: {onnx_file_path}")
        
        # Move temporary onnx weights to final target models/monster.onnx
        target_path = output_dir / "monster.onnx"
        shutil.move(onnx_file_path, str(target_path))
        logger.info(f"YOLO model exported and saved to target location: {target_path.resolve()}")
        
    except Exception as e:
        logger.error(f"Failed to export YOLO model to ONNX: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
