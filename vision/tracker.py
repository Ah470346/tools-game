import numpy as np
from typing import List, Dict, Any, Tuple


class Track:
    """
    Represents an individual tracked target with a persistent ID.
    """

    def __init__(self, track_id: int, box: List[float], class_id: int, confidence: float) -> None:
        self.track_id = track_id
        self.box = box  # [xc_norm, yc_norm, w_norm, h_norm]
        self.class_id = class_id
        self.confidence = confidence
        self.lost_count = 0


def calculate_iou(box_a: List[float], box_b: List[float]) -> float:
    """
    Calculates Intersection over Union (IoU) of two bounding boxes in normalized ratio coordinates.
    Both boxes are in [xc, yc, w, h] format.
    """
    xc_a, yc_a, w_a, h_a = box_a
    xc_b, yc_b, w_b, h_b = box_b

    # Convert to [x1, y1, x2, y2] (top-left, bottom-right corners)
    x1_a, y1_a = xc_a - w_a / 2, yc_a - h_a / 2
    x2_a, y2_a = xc_a + w_a / 2, yc_a + h_a / 2

    x1_b, y1_b = xc_b - w_b / 2, yc_b - h_b / 2
    x2_b, y2_b = xc_b + w_b / 2, yc_b + h_b / 2

    # Intersection box
    ix1 = max(x1_a, x1_b)
    iy1 = max(y1_a, y1_b)
    ix2 = min(x2_a, x2_b)
    iy2 = min(y2_a, y2_b)

    intersection_w = max(0.0, ix2 - ix1)
    intersection_h = max(0.0, iy2 - iy1)
    intersection_area = intersection_w * intersection_h

    # Union area
    area_a = w_a * h_a
    area_b = w_b * h_b
    union_area = area_a + area_b - intersection_area

    if union_area <= 0.0:
        return 0.0

    return float(intersection_area / union_area)


class TargetTracker:
    """
    Tracks detected targets over multiple frames to avoid context-switching/jittery targeting.
    Uses pure-Python IoU association greedy matching.
    """

    def __init__(self, iou_threshold: float = 0.3, max_lost_frames: int = 15,
                 max_match_dist_ratio: float = 0.0,
                 coast_output_frames: int = 0) -> None:
        """
        Initializes the target tracker.

        Args:
            iou_threshold (float): Minimum IoU threshold to consider association matches.
            max_lost_frames (int): Maximum consecutive frames a track can be lost before deletion.
            max_match_dist_ratio (float): Fallback association by center distance (normalized)
                for pairs that IoU could not match. 0.0 disables the fallback.
            coast_output_frames (int): If >0, tracks with 0 < lost_count <= this value
                are included in the output with ``coasting=True`` and their last-known box.
                0 disables coasting output (default, preserving legacy behaviour).
        """
        self.iou_threshold = iou_threshold
        self.max_lost_frames = max_lost_frames
        self.max_match_dist_ratio = max_match_dist_ratio
        self.coast_output_frames = coast_output_frames
        self.next_track_id = 1
        self.tracks: List[Track] = []

    def update(self, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Updates tracker state with new detections and matches IDs.

        Args:
            detections (List[Dict[str, Any]]): Bounding boxes from the detector:
                [{"class_id": int, "confidence": float, "box": [xc, yc, w, h]}]

        Returns:
            List[Dict[str, Any]]: Active tracked objects with a "track_id" key.
        """
        # 1. Handle no new detections
        if not detections:
            for track in self.tracks:
                track.lost_count += 1
            # Remove expired tracks
            self.tracks = [t for t in self.tracks if t.lost_count <= self.max_lost_frames]
            return self._build_output()

        # 2. Match existing tracks with detections using IoU matrix
        num_tracks = len(self.tracks)
        num_dets = len(detections)

        matched_tracks = set()
        matched_dets = set()

        if num_tracks > 0:
            # Build IoU matrix
            iou_matrix = np.zeros((num_tracks, num_dets), dtype=np.float32)
            for t_idx, track in enumerate(self.tracks):
                for d_idx, det in enumerate(detections):
                    iou_matrix[t_idx, d_idx] = calculate_iou(track.box, det["box"])

            # Greedy match based on maximum IoU
            while True:
                # Find maximum IoU value in the matrix
                unmatched_iou = iou_matrix.copy()
                # Zero out rows/cols already matched
                for t in matched_tracks:
                    unmatched_iou[t, :] = -1.0
                for d in matched_dets:
                    unmatched_iou[:, d] = -1.0

                max_val = np.max(unmatched_iou)
                if max_val < self.iou_threshold:
                    break

                # Get index of max value
                indices = np.where(unmatched_iou == max_val)
                t_idx, d_idx = int(indices[0][0]), int(indices[1][0])

                matched_tracks.add(t_idx)
                matched_dets.add(d_idx)

        # 3. Update status of matched tracks
        for t_idx in matched_tracks:
            # Find which detection matched this track
            # Greedy matching ensures a 1-to-1 matching
            for d_idx in matched_dets:
                if iou_matrix[t_idx, d_idx] >= self.iou_threshold:
                    det = detections[d_idx]
                    track = self.tracks[t_idx]
                    track.box = det["box"]
                    track.confidence = det["confidence"]
                    track.lost_count = 0
                    break

        # 3b. Fallback association by center distance for pairs IoU could not match.
        # Fast monster movement or camera scroll (the character running) shifts
        # boxes so far between frames that IoU drops to 0 even though it is the
        # same target — without this, the track ID churns and downstream target
        # locking loses the monster mid-fight.
        if self.max_match_dist_ratio > 0.0:
            while True:
                best_pair = None
                best_dist = self.max_match_dist_ratio
                for t_idx, track in enumerate(self.tracks):
                    if t_idx in matched_tracks:
                        continue
                    for d_idx, det in enumerate(detections):
                        if d_idx in matched_dets:
                            continue
                        dist = float(np.sqrt(
                            (track.box[0] - det["box"][0]) ** 2 +
                            (track.box[1] - det["box"][1]) ** 2))
                        if dist < best_dist:
                            best_dist = dist
                            best_pair = (t_idx, d_idx)
                if best_pair is None:
                    break
                t_idx, d_idx = best_pair
                matched_tracks.add(t_idx)
                matched_dets.add(d_idx)
                det = detections[d_idx]
                track = self.tracks[t_idx]
                track.box = det["box"]
                track.confidence = det["confidence"]
                track.lost_count = 0

        # 4. Increment lost count for unmatched tracks
        for t_idx, track in enumerate(self.tracks):
            if t_idx not in matched_tracks:
                track.lost_count += 1

        # 5. Create new tracks for unmatched detections
        for d_idx, det in enumerate(detections):
            if d_idx not in matched_dets:
                new_track = Track(
                    track_id=self.next_track_id,
                    box=det["box"],
                    class_id=det["class_id"],
                    confidence=det["confidence"]
                )
                self.tracks.append(new_track)
                self.next_track_id += 1

        # 6. Remove expired tracks
        self.tracks = [t for t in self.tracks if t.lost_count <= self.max_lost_frames]

        # 7. Return active (currently visible) tracks formatted as detections
        return self._build_output()

    def _build_output(self) -> List[Dict[str, Any]]:
        """Builds the output list from current tracks.

        Visible tracks (lost_count == 0) always appear with ``coasting=False``.
        If ``coast_output_frames > 0``, tracks with
        ``0 < lost_count <= coast_output_frames`` are appended with
        ``coasting=True`` and their last-known (frozen) box.
        """
        result: List[Dict[str, Any]] = []
        for track in self.tracks:
            if track.lost_count == 0:
                result.append({
                    "class_id": track.class_id,
                    "confidence": track.confidence,
                    "box": track.box,
                    "track_id": track.track_id,
                    "coasting": False,
                })
            elif (self.coast_output_frames > 0
                  and 0 < track.lost_count <= self.coast_output_frames):
                result.append({
                    "class_id": track.class_id,
                    "confidence": track.confidence,
                    "box": track.box,
                    "track_id": track.track_id,
                    "coasting": True,
                })
        return result
