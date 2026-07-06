"""
tests/test_tracker.py

Unit tests for vision/tracker.py.
Verifies Intersection over Union (IoU) calculation, ID association, tracking persistence,
and track lifecycle management.
"""

import sys
import os
import pytest

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vision.tracker import TargetTracker, calculate_iou


def test_calculate_iou() -> None:
    # 1. Identical boxes (IoU should be 1.0)
    box_a = [0.5, 0.5, 0.2, 0.2]
    assert calculate_iou(box_a, box_a) == pytest.approx(1.0)

    # 2. Fully disjoint boxes (IoU should be 0.0)
    box_b = [0.1, 0.1, 0.1, 0.1]
    box_c = [0.8, 0.8, 0.1, 0.1]
    assert calculate_iou(box_b, box_c) == 0.0

    # 3. Partial overlap
    # box1: xc=0.5, yc=0.5, w=0.2, h=0.2 -> x range [0.4, 0.6], y range [0.4, 0.6]. Area = 0.04
    # box2: xc=0.6, yc=0.5, w=0.2, h=0.2 -> x range [0.5, 0.7], y range [0.4, 0.6]. Area = 0.04
    # Intersection: x range [0.5, 0.6], y range [0.4, 0.6] -> w=0.1, h=0.2. Area = 0.02
    # Union: 0.04 + 0.04 - 0.02 = 0.06
    # IoU: 0.02 / 0.06 = 1/3
    box1 = [0.5, 0.5, 0.2, 0.2]
    box2 = [0.6, 0.5, 0.2, 0.2]
    assert calculate_iou(box1, box2) == pytest.approx(1.0 / 3.0)


def test_tracker_creation_and_persistence() -> None:
    tracker = TargetTracker(iou_threshold=0.3, max_lost_frames=3)

    # Frame 1: Create two tracks
    dets1 = [
        {"class_id": 0, "confidence": 0.9, "box": [0.4, 0.4, 0.1, 0.1]},
        {"class_id": 0, "confidence": 0.8, "box": [0.7, 0.7, 0.1, 0.1]}
    ]

    tracks1 = tracker.update(dets1)
    assert len(tracks1) == 2
    assert tracks1[0]["track_id"] == 1
    assert tracks1[1]["track_id"] == 2

    # Frame 2: Shifted boxes (should retain track IDs 1 and 2)
    dets2 = [
        {"class_id": 0, "confidence": 0.92, "box": [0.41, 0.41, 0.1, 0.1]},
        {"class_id": 0, "confidence": 0.85, "box": [0.69, 0.69, 0.1, 0.1]}
    ]

    tracks2 = tracker.update(dets2)
    assert len(tracks2) == 2
    assert tracks2[0]["track_id"] == 1
    assert tracks2[1]["track_id"] == 2
    assert tracks2[0]["box"] == [0.41, 0.41, 0.1, 0.1]
    assert tracks2[1]["box"] == [0.69, 0.69, 0.1, 0.1]


def test_tracker_lost_and_expired() -> None:
    tracker = TargetTracker(iou_threshold=0.3, max_lost_frames=2)

    # Frame 1: Create target
    dets1 = [{"class_id": 0, "confidence": 0.9, "box": [0.5, 0.5, 0.1, 0.1]}]
    tracks1 = tracker.update(dets1)
    assert len(tracks1) == 1
    assert tracks1[0]["track_id"] == 1

    # Frame 2: Target disappears -> returns empty visible list, but track is kept internally
    tracks2 = tracker.update([])
    assert len(tracks2) == 0
    assert len(tracker.tracks) == 1
    assert tracker.tracks[0].lost_count == 1

    # Frame 3: Target still missing -> lost_count = 2 (reaches max_lost_frames limit of 2)
    tracks3 = tracker.update([])
    assert len(tracks3) == 0
    assert len(tracker.tracks) == 1
    assert tracker.tracks[0].lost_count == 2

    # Frame 4: Target still missing -> lost_count = 3 > max_lost_frames -> track deleted
    tracks4 = tracker.update([])
    assert len(tracks4) == 0
    assert len(tracker.tracks) == 0


def test_tracker_centroid_fallback_keeps_id_on_fast_movement() -> None:
    """Regression: camera scroll / fast monster movement shifts the box so far
    between frames that IoU drops to 0. The centroid-distance fallback must
    keep the same track ID instead of churning to a new one."""
    tracker = TargetTracker(iou_threshold=0.3, max_lost_frames=15,
                            max_match_dist_ratio=0.1)

    # Frame 1: monster at (0.5, 0.5), box 0.05 wide
    dets1 = [{"class_id": 0, "confidence": 0.9, "box": [0.5, 0.5, 0.05, 0.05]}]
    tracks1 = tracker.update(dets1)
    assert tracks1[0]["track_id"] == 1

    # Frame 2: box jumped 0.08 away — zero IoU overlap, but within fallback dist
    dets2 = [{"class_id": 0, "confidence": 0.9, "box": [0.58, 0.5, 0.05, 0.05]}]
    tracks2 = tracker.update(dets2)
    assert len(tracks2) == 1
    assert tracks2[0]["track_id"] == 1
    assert tracks2[0]["box"] == [0.58, 0.5, 0.05, 0.05]

    # Frame 3: jumped beyond the fallback distance (0.15 > 0.1) — new track
    dets3 = [{"class_id": 0, "confidence": 0.9, "box": [0.73, 0.5, 0.05, 0.05]}]
    tracks3 = tracker.update(dets3)
    assert len(tracks3) == 1
    assert tracks3[0]["track_id"] == 2


def test_tracker_centroid_fallback_prefers_nearest() -> None:
    """With two candidate detections, the fallback adopts the nearest one and
    the other becomes a new track."""
    tracker = TargetTracker(iou_threshold=0.3, max_lost_frames=15,
                            max_match_dist_ratio=0.1)

    dets1 = [{"class_id": 0, "confidence": 0.9, "box": [0.5, 0.5, 0.05, 0.05]}]
    tracker.update(dets1)

    dets2 = [
        {"class_id": 0, "confidence": 0.9, "box": [0.59, 0.5, 0.05, 0.05]},
        {"class_id": 0, "confidence": 0.9, "box": [0.56, 0.5, 0.05, 0.05]},
    ]
    tracks2 = tracker.update(dets2)
    assert len(tracks2) == 2
    by_id = {t["track_id"]: t for t in tracks2}
    # Track 1 followed the nearer detection; the farther one got a new ID
    assert by_id[1]["box"] == [0.56, 0.5, 0.05, 0.05]
    assert by_id[2]["box"] == [0.59, 0.5, 0.05, 0.05]


def test_tracker_centroid_fallback_disabled_by_default() -> None:
    """Without max_match_dist_ratio, a zero-IoU jump still churns the ID
    (original behavior preserved)."""
    tracker = TargetTracker(iou_threshold=0.3, max_lost_frames=15)

    dets1 = [{"class_id": 0, "confidence": 0.9, "box": [0.5, 0.5, 0.05, 0.05]}]
    tracker.update(dets1)

    dets2 = [{"class_id": 0, "confidence": 0.9, "box": [0.58, 0.5, 0.05, 0.05]}]
    tracks2 = tracker.update(dets2)
    assert tracks2[0]["track_id"] == 2


def test_tracker_reassociation() -> None:
    tracker = TargetTracker(iou_threshold=0.3, max_lost_frames=2)

    # Frame 1: Target visible
    dets1 = [{"class_id": 0, "confidence": 0.9, "box": [0.5, 0.5, 0.1, 0.1]}]
    tracks1 = tracker.update(dets1)
    assert tracks1[0]["track_id"] == 1

    # Frame 2: Target temporarily lost (e.g. occlusion)
    tracks2 = tracker.update([])
    assert len(tracks2) == 0

    # Frame 3: Target reappears at similar coordinates -> should match and KEEP same ID 1
    dets3 = [{"class_id": 0, "confidence": 0.9, "box": [0.51, 0.51, 0.1, 0.1]}]
    tracks3 = tracker.update(dets3)
    assert len(tracks3) == 1
    assert tracks3[0]["track_id"] == 1
    assert tracks3[0]["box"] == [0.51, 0.51, 0.1, 0.1]
