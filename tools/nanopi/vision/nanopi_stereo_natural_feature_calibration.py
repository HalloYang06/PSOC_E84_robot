#!/usr/bin/env python3
"""Estimate provisional stereo extrinsics from a fixed natural scene.

This tool reuses previously calibrated camera intrinsics, estimates only the
current relative pose, and scales translation with a measured baseline. Its
output is evidence-only and must be replaced by a fresh chessboard calibration.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np


CONTROL_BOUNDARY = "natural_feature_stereo_calibration_only_not_motion_permission"


def assess_quality(
    *,
    ratio_matches: int,
    pose_inliers: int,
    median_vertical_error_px: float,
    p90_vertical_error_px: float,
    min_ratio_matches: int,
    min_pose_inliers: int,
    max_median_vertical_error_px: float,
    max_p90_vertical_error_px: float,
) -> dict[str, Any]:
    reasons: list[str] = []
    if ratio_matches < min_ratio_matches:
        reasons.append("ratio_matches_below_minimum")
    if pose_inliers < min_pose_inliers:
        reasons.append("pose_inliers_below_minimum")
    if median_vertical_error_px > max_median_vertical_error_px:
        reasons.append("median_vertical_error_above_limit")
    if p90_vertical_error_px > max_p90_vertical_error_px:
        reasons.append("p90_vertical_error_above_limit")
    return {
        "state": "accepted" if not reasons else "rejected",
        "calibration_kind": "natural_feature_provisional",
        "reasons": reasons,
        "metrics": {
            "ratio_matches": int(ratio_matches),
            "pose_inliers": int(pose_inliers),
            "median_vertical_error_px": round(float(median_vertical_error_px), 5),
            "p90_vertical_error_px": round(float(p90_vertical_error_px), 5),
        },
        "gates": {
            "min_ratio_matches": int(min_ratio_matches),
            "min_pose_inliers": int(min_pose_inliers),
            "max_median_vertical_error_px": float(max_median_vertical_error_px),
            "max_p90_vertical_error_px": float(max_p90_vertical_error_px),
        },
        "control_boundary": CONTROL_BOUNDARY,
    }


def _matrix(payload: dict[str, Any], key: str) -> np.ndarray:
    value = payload.get(key)
    if value is None:
        raise ValueError(f"source calibration missing {key}")
    return np.asarray(value, dtype=np.float64)


def estimate_calibration(args: argparse.Namespace) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    source = json.loads(Path(args.intrinsics_json).read_text(encoding="utf-8-sig"))
    left = cv2.imread(str(args.left_image), cv2.IMREAD_COLOR)
    right = cv2.imread(str(args.right_image), cv2.IMREAD_COLOR)
    if left is None or right is None:
        raise ValueError("left or right image is unreadable")
    if left.shape[:2] != right.shape[:2]:
        raise ValueError("left and right image sizes differ")

    height, width = left.shape[:2]
    image_size = (width, height)
    left_mtx = _matrix(source, "left_intrinsics")
    right_mtx = _matrix(source, "right_intrinsics")
    left_dist = _matrix(source, "left_distortion").reshape(-1, 1)
    right_dist = _matrix(source, "right_distortion").reshape(-1, 1)

    sift = cv2.SIFT_create(nfeatures=args.max_features)
    left_keypoints, left_descriptors = sift.detectAndCompute(cv2.cvtColor(left, cv2.COLOR_BGR2GRAY), None)
    right_keypoints, right_descriptors = sift.detectAndCompute(cv2.cvtColor(right, cv2.COLOR_BGR2GRAY), None)
    if left_descriptors is None or right_descriptors is None:
        raise ValueError("natural scene did not produce descriptors in both cameras")

    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(left_descriptors, right_descriptors, k=2)
    matches = [first for first, second in pairs if first.distance < args.ratio_test * second.distance]
    if len(matches) < 8:
        raise ValueError(f"too few ratio-test matches: {len(matches)}")

    left_points = np.float64([left_keypoints[item.queryIdx].pt for item in matches])
    right_points = np.float64([right_keypoints[item.trainIdx].pt for item in matches])
    left_normalized = cv2.undistortPoints(left_points.reshape(-1, 1, 2), left_mtx, left_dist).reshape(-1, 2)
    right_normalized = cv2.undistortPoints(right_points.reshape(-1, 1, 2), right_mtx, right_dist).reshape(-1, 2)

    essential, essential_mask = cv2.findEssentialMat(
        left_normalized,
        right_normalized,
        np.eye(3),
        method=cv2.RANSAC,
        prob=0.999,
        threshold=args.normalized_ransac_threshold,
    )
    if essential is None or essential_mask is None:
        raise ValueError("essential matrix estimation failed")
    if essential.shape[0] > 3:
        essential = essential[:3, :3]
    _, rotation, translation_direction, pose_mask = cv2.recoverPose(
        essential,
        left_normalized,
        right_normalized,
        np.eye(3),
        mask=essential_mask,
    )
    translation = translation_direction / np.linalg.norm(translation_direction) * args.baseline_m

    r1, r2, p1, p2, q, roi1, roi2 = cv2.stereoRectify(
        left_mtx,
        left_dist,
        right_mtx,
        right_dist,
        image_size,
        rotation,
        translation,
        flags=cv2.CALIB_ZERO_DISPARITY,
        alpha=0,
    )
    left_rectified_points = cv2.undistortPoints(
        left_points.reshape(-1, 1, 2), left_mtx, left_dist, R=r1, P=p1
    ).reshape(-1, 2)
    right_rectified_points = cv2.undistortPoints(
        right_points.reshape(-1, 1, 2), right_mtx, right_dist, R=r2, P=p2
    ).reshape(-1, 2)
    pose_inliers = pose_mask.reshape(-1) > 0
    vertical_errors = np.abs(left_rectified_points[pose_inliers, 1] - right_rectified_points[pose_inliers, 1])
    if vertical_errors.size == 0:
        raise ValueError("pose recovery produced no usable inliers")

    quality = assess_quality(
        ratio_matches=len(matches),
        pose_inliers=int(pose_inliers.sum()),
        median_vertical_error_px=float(np.median(vertical_errors)),
        p90_vertical_error_px=float(np.percentile(vertical_errors, 90)),
        min_ratio_matches=args.min_ratio_matches,
        min_pose_inliers=args.min_pose_inliers,
        max_median_vertical_error_px=args.max_median_vertical_error_px,
        max_p90_vertical_error_px=args.max_p90_vertical_error_px,
    )
    calibration_id = f"natural_feature_provisional_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    payload = {
        "schema_version": "rehab_arm_stereo_calibration_v1",
        "calibration_id": calibration_id,
        "calibration_state": "calibrated" if quality["state"] == "accepted" else "rejected",
        "calibration_kind": "natural_feature_provisional",
        "transform_state": "provisional_natural_feature_not_hand_eye_calibrated",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "image_size": {"width": width, "height": height},
        "baseline_m": float(args.baseline_m),
        "left_intrinsics": left_mtx.tolist(),
        "right_intrinsics": right_mtx.tolist(),
        "left_distortion": left_dist.reshape(-1).tolist(),
        "right_distortion": right_dist.reshape(-1).tolist(),
        "R": rotation.tolist(),
        "T": translation.reshape(-1).tolist(),
        "essential_matrix": essential.tolist(),
        "rectification": {
            "R1": r1.tolist(),
            "R2": r2.tolist(),
            "P1": p1.tolist(),
            "P2": p2.tolist(),
            "Q": q.tolist(),
            "roi1": list(roi1),
            "roi2": list(roi2),
        },
        "quality": quality,
        "sample_source": {
            "left_image": str(args.left_image),
            "right_image": str(args.right_image),
            "source_intrinsics_calibration_id": source.get("calibration_id"),
            "feature_detector": "SIFT",
            "ratio_test": float(args.ratio_test),
            "normalized_ransac_threshold": float(args.normalized_ransac_threshold),
        },
        "warning": "Provisional fixed-scene extrinsics only; replace with chessboard stereo calibration before final metric or hand-eye use.",
        "control_boundary": CONTROL_BOUNDARY,
    }

    left_map = cv2.initUndistortRectifyMap(left_mtx, left_dist, r1, p1, image_size, cv2.CV_32FC1)
    right_map = cv2.initUndistortRectifyMap(right_mtx, right_dist, r2, p2, image_size, cv2.CV_32FC1)
    left_rectified = cv2.remap(left, left_map[0], left_map[1], cv2.INTER_LINEAR)
    right_rectified = cv2.remap(right, right_map[0], right_map[1], cv2.INTER_LINEAR)
    return payload, left_rectified, right_rectified


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-image", required=True)
    parser.add_argument("--right-image", required=True)
    parser.add_argument("--intrinsics-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--preview")
    parser.add_argument("--baseline-m", type=float, default=0.06)
    parser.add_argument("--max-features", type=int, default=3000)
    parser.add_argument("--ratio-test", type=float, default=0.72)
    parser.add_argument("--normalized-ransac-threshold", type=float, default=0.0015)
    parser.add_argument("--min-ratio-matches", type=int, default=40)
    parser.add_argument("--min-pose-inliers", type=int, default=25)
    parser.add_argument("--max-median-vertical-error-px", type=float, default=1.5)
    parser.add_argument("--max-p90-vertical-error-px", type=float, default=3.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload, left_rectified, right_rectified = estimate_calibration(args)
    print(json.dumps(payload["quality"], ensure_ascii=False, indent=2))
    if payload["calibration_state"] != "calibrated":
        print("quality gate rejected provisional calibration; output was not written")
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, output)
    if args.preview:
        preview = np.hstack([left_rectified, right_rectified])
        for y in range(40, preview.shape[0], 40):
            cv2.line(preview, (0, y), (preview.shape[1] - 1, y), (0, 255, 255), 1)
        cv2.imwrite(str(args.preview), preview)
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
