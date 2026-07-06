"""
scripts/train_yolo.py

Training helper script for Task 2.3.
Loads dataset config and trains a YOLOv8 Nano model using ultralytics.

Usage:
    python scripts/train_yolo.py --data path/to/data.yaml [options]
"""

import argparse
import logging
import os
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
logger = logging.getLogger("train_yolo")


def main() -> None:
    # 1. Parse arguments
    parser = argparse.ArgumentParser(description="Priston Tale YOLO Training Script")
    parser.add_argument(
        "--data",
        type=str,
        default="data/dataset/data.yaml",
        help="Path to the dataset data.yaml file (default: data/dataset/data.yaml)"
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=100,
        help="Number of training epochs (default: 100)"
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Training image size (default: 640)"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=16,
        help="Batch size (default: 16)"
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Target device: 'cpu', '0', etc. (default: 'auto' - auto-select GPU if available)"
    )
    parser.add_argument(
        "--project",
        type=str,
        default="runs/detect",
        help="Output directory project path (default: runs/detect)"
    )
    parser.add_argument(
        "--name",
        type=str,
        default="pt_monster",
        help="Training run name (default: pt_monster)"
    )
    
    args = parser.parse_args()

    # 2. Check if data config file exists
    data_path = Path(args.data)
    if not data_path.exists():
        logger.error(
            f"Dataset configuration file not found at: {data_path.resolve()}\n"
            f"Please make sure your Roboflow dataset is exported and placed correctly."
        )
        sys.exit(1)

    # 3. Determine device
    device = args.device
    if device == "auto":
        try:
            import torch
            device = "0" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
            logger.warning("torch not found, falling back to CPU device.")

    logger.info(f"Target training device selected: {device}")

    # 4. Import ultralytics & train
    try:
        from ultralytics import YOLO
    except ImportError:
        logger.error(
            "ultralytics library is not installed. "
            "Please run: pip install -r requirements-train.txt"
        )
        sys.exit(1)

    logger.info("Initializing YOLOv8 Nano model (yolov8n.pt)...")
    try:
        model = YOLO("yolov8n.pt")
    except Exception as e:
        logger.error(f"Failed to load/download yolov8n.pt: {e}")
        sys.exit(1)

    logger.info(
        f"Starting training on {data_path.resolve()} "
        f"for {args.epochs} epochs (imgsz={args.imgsz}, batch={args.batch})..."
    )

    try:
        project_abs = Path(args.project).resolve()
        results = model.train(
            data=str(data_path.resolve()),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=device,
            project=str(project_abs),
            name=args.name,
        )
    except Exception as e:
        logger.error(f"Error during training: {e}")
        sys.exit(1)

    # 5. Output summary
    logger.info("Training complete!")

    # Find the output directory of the run
    run_dir = Path(args.project).resolve() / args.name
    best_weights_path = run_dir / "weights" / "best.pt"
    
    print("\n" + "=" * 60)
    print("  YOLO TRAINING COMPLETE SUMMARY")
    print("=" * 60)
    if best_weights_path.exists():
        print(f"  Best Weights Path: {best_weights_path.resolve()}")
    else:
        # Runs might suffix names (e.g. pt_monster2) if they already exist
        print(f"  Check weights folder inside: {run_dir.resolve()}")
    
    # Print metrics if available in results
    if results is not None and hasattr(results, "results_dict"):
        # results_dict normally contains metrics
        mAP50 = results.results_dict.get("metrics/mAP50(B)", "N/A")
        mAP50_95 = results.results_dict.get("metrics/mAP50-95(B)", "N/A")
        print(f"  mAP@0.5          : {mAP50}")
        print(f"  mAP@0.5:0.95     : {mAP50_95}")
    elif hasattr(model, "metrics"):
        # Fallback if results lacks dict but model has validation metrics
        mAP50 = getattr(model.metrics, "box.map50", "N/A")
        print(f"  mAP@0.5          : {mAP50}")
    
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
