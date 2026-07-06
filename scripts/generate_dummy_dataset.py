"""
scripts/generate_dummy_dataset.py

Generates a synthetic dummy dataset in YOLO format under data/dataset/
so the user can test the training script (scripts/train_yolo.py) immediately
without manual annotation on Roboflow.
"""

import os
import sys
from pathlib import Path
import numpy as np
import cv2

# Ensure project root is in python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def create_dummy_dataset() -> None:
    dataset_dir = PROJECT_ROOT / "data" / "dataset"
    print(f"Creating dummy dataset at: {dataset_dir.resolve()}...")

    # Define paths
    train_img_dir = dataset_dir / "train" / "images"
    train_lbl_dir = dataset_dir / "train" / "labels"
    val_img_dir = dataset_dir / "val" / "images"
    val_lbl_dir = dataset_dir / "val" / "labels"

    # Create directories
    for d in [train_img_dir, train_lbl_dir, val_img_dir, val_lbl_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Create data.yaml
    yaml_content = f"""path: {dataset_dir.as_posix()}
train: train/images
val: val/images
test:  # optional

names:
  0: monster
"""
    with open(dataset_dir / "data.yaml", "w", encoding="utf-8") as f:
        f.write(yaml_content)
    print("Created data.yaml")

    # Helper to generate fake image and label
    def make_fake_sample(img_path: Path, lbl_path: Path) -> None:
        # Create a random RGB image (640x640)
        img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
        # Draw some colored rectangles to simulate "monsters"
        cv2.rectangle(img, (200, 200), (400, 400), (0, 0, 255), -1)  # Red box
        cv2.rectangle(img, (100, 450), (250, 550), (0, 255, 0), -1)  # Green box
        cv2.imwrite(str(img_path), img)

        # Label format: class_id x_center y_center width height (normalized 0.0 - 1.0)
        # Bounding box 1: center (300, 300), size (200, 200) -> norm: (0.46875, 0.46875, 0.3125, 0.3125)
        # Bounding box 2: center (175, 500), size (150, 100) -> norm: (0.2734, 0.78125, 0.234375, 0.15625)
        label_content = (
            "0 0.46875 0.46875 0.3125 0.3125\n"
            "0 0.2734 0.78125 0.234375 0.15625\n"
        )
        with open(lbl_path, "w", encoding="utf-8") as f:
            f.write(label_content)

    # Generate 8 train images, 2 val images
    print("Generating train images...")
    for i in range(8):
        make_fake_sample(
            train_img_dir / f"dummy_train_{i}.png",
            train_lbl_dir / f"dummy_train_{i}.txt"
        )

    print("Generating val images...")
    for i in range(2):
        make_fake_sample(
            val_img_dir / f"dummy_val_{i}.png",
            val_lbl_dir / f"dummy_val_{i}.txt"
        )

    print("\nDummy dataset successfully generated!")
    print(f"Dataset path: {dataset_dir.resolve()}")


if __name__ == "__main__":
    create_dummy_dataset()
