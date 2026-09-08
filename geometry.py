"""Small, explicit multiview-geometry primitives used by the reconstruction.

The routines here intentionally expose the linear algebra instead of delegating
SfM steps to a library-level reconstruction API.
"""

from typing import Optional, Tuple

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation


def _skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = np.asarray(vector, dtype=float).reshape(3)
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def _hartley_normalize(points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points, dtype=float)
    centroid = points.mean(axis=0)
    centered = points - centroid
    mean_distance = np.linalg.norm(centered, axis=1).mean()
    scale = np.sqrt(2.0) / max(mean_distance, 1e-12)
    transform = np.array(
        [[scale, 0.0, -scale * centroid[0]],
         [0.0, scale, -scale * centroid[1]],
         [0.0, 0.0, 1.0]]
    )
    homogeneous = np.column_stack((points, np.ones(len(points))))
    normalized = (transform @ homogeneous.T).T
    return normalized[:, :2], transform


def _fit_fundamental(points1: np.ndarray, points2: np.ndarray) -> np.ndarray:
    p1, t1 = _hartley_normalize(points1)
    p2, t2 = _hartley_normalize(points2)
    x1, y1 = p1.T
    x2, y2 = p2.T
    design = np.column_stack((
        x2 * x1, x2 * y1, x2,
        y2 * x1, y2 * y1, y2,
        x1, y1, np.ones(len(p1)),
    ))
    _, _, vh = np.linalg.svd(design)
    fundamental = vh[-1].reshape(3, 3)
    u, singular_values, vh = np.linalg.svd(fundamental)
    singular_values[-1] = 0.0
    fundamental = u @ np.diag(singular_values) @ vh
    fundamental = t2.T @ fundamental @ t1
    return fundamental / max(np.linalg.norm(fundamental), 1e-12)


def _sampson_error(matrix: np.ndarray, points1: np.ndarray, points2: np.ndarray) -> np.ndarray:
    x1 = np.column_stack((points1, np.ones(len(points1))))
    x2 = np.column_stack((points2, np.ones(len(points2))))
    lines2 = (matrix @ x1.T).T
    lines1 = (matrix.T @ x2.T).T
    residual = np.sum(x2 * lines2, axis=1)
    denominator = np.sum(lines1[:, :2] ** 2, axis=1) + np.sum(lines2[:, :2] ** 2, axis=1)
    return residual ** 2 / np.maximum(denominator, 1e-12)


def estimate_fundamental_ransac(
    points1: np.ndarray,
    points2: np.ndarray,
    threshold: float,
    iterations: int = 1000,
    seed: int = 6121,
) -> Tuple[np.ndarray, np.ndarray]:
    if len(points1) != len(points2) or len(points1) < 8:
        raise ValueError("At least eight point correspondences are required")
    rng = np.random.default_rng(seed)
    best_matrix: Optional[np.ndarray] = None
    best_mask = np.zeros(len(points1), dtype=bool)
    threshold_squared = float(threshold) ** 2
    for _ in range(iterations):
        sample = rng.choice(len(points1), 8, replace=False)
        try:
            candidate = _fit_fundamental(points1[sample], points2[sample])
        except np.linalg.LinAlgError:
            continue
        mask = _sampson_error(candidate, points1, points2) < threshold_squared
        if mask.sum() > best_mask.sum():
            best_matrix, best_mask = candidate, mask
    if best_matrix is None or best_mask.sum() < 8:
        raise ValueError("RANSAC could not estimate a fundamental matrix")
    refined = _fit_fundamental(points1[best_mask], points2[best_mask])
    refined_mask = _sampson_error(refined, points1, points2) < threshold_squared
    return refined, refined_mask


def _normalize_with_intrinsics(points: np.ndarray, K: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack((points, np.ones(len(points))))
    normalized = (np.linalg.inv(K) @ homogeneous.T).T
    return normalized[:, :2] / normalized[:, 2:3]


def estimate_essential_ransac(
    points1: np.ndarray,
    points2: np.ndarray,
    K: np.ndarray,
    threshold_pixels: float,
    iterations: int = 1000,
) -> Tuple[np.ndarray, np.ndarray]:
    normalized1 = _normalize_with_intrinsics(points1, K)
    normalized2 = _normalize_with_intrinsics(points2, K)
    focal = max(float(np.mean(np.diag(K)[:2])), 1.0)
    return estimate_fundamental_ransac(
        normalized1, normalized2, threshold_pixels / focal, iterations
    )


def decompose_essential(
    essential: np.ndarray,
    points1: np.ndarray,
    points2: np.ndarray,
    K: np.ndarray,
    inlier_mask: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    u, singular_values, vh = np.linalg.svd(essential)
    if np.linalg.det(u) < 0:
        u *= -1.0
    if np.linalg.det(vh) < 0:
        vh *= -1.0
    essential = u @ np.diag([singular_values[:2].mean(), singular_values[:2].mean(), 0.0]) @ vh
    u, _, vh = np.linalg.svd(essential)
    w = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    candidates = [(u @ w @ vh, u[:, 2:3]), (u @ w @ vh, -u[:, 2:3]),
                  (u @ w.T @ vh, u[:, 2:3]), (u @ w.T @ vh, -u[:, 2:3])]
    normalized1 = _normalize_with_intrinsics(points1[inlier_mask], K)
    normalized2 = _normalize_with_intrinsics(points2[inlier_mask], K)
    best = None
    best_count = -1
    for rotation, translation in candidates:
        if np.linalg.det(rotation) < 0:
            rotation = -rotation
            translation = -translation
        points3d = triangulate_points(
            np.hstack((np.eye(3), np.zeros((3, 1)))),
            np.hstack((rotation, translation)),
            normalized1,
            normalized2,
        )
        depth1 = points3d[:, 2]
        depth2 = (rotation @ points3d.T + translation).T[:, 2]
        cheirality_mask = np.isfinite(points3d).all(axis=1) & (depth1 > 0.0) & (depth2 > 0.0)
        count = int(np.count_nonzero(cheirality_mask))
        if count > best_count:
            best_count = count
            best = rotation, translation, cheirality_mask
    if best is None:
        raise ValueError("Essential matrix decomposition failed")
    return best


def triangulate_points(
    projection1: np.ndarray,
    projection2: np.ndarray,
    points1: np.ndarray,
    points2: np.ndarray,
) -> np.ndarray:
    points1 = np.asarray(points1, dtype=float)
    points2 = np.asarray(points2, dtype=float)
    result = []
    for (x1, y1), (x2, y2) in zip(points1, points2):
        design = np.vstack((
            x1 * projection1[2] - projection1[0],
            y1 * projection1[2] - projection1[1],
            x2 * projection2[2] - projection2[0],
            y2 * projection2[2] - projection2[1],
        ))
        _, _, vh = np.linalg.svd(design)
        homogeneous = vh[-1]
        if abs(homogeneous[3]) < 1e-12:
            result.append(np.full(3, np.nan))
        else:
            result.append(homogeneous[:3] / homogeneous[3])
    return np.asarray(result)


def validate_triangulated_points(
    points3d: np.ndarray,
    rotation1: np.ndarray,
    translation1: np.ndarray,
    rotation2: np.ndarray,
    translation2: np.ndarray,
    K: np.ndarray,
    points1: np.ndarray,
    points2: np.ndarray,
    reprojection_threshold: float,
) -> np.ndarray:
    points3d = np.asarray(points3d, dtype=float)
    points1 = np.asarray(points1, dtype=float)
    points2 = np.asarray(points2, dtype=float)

    def project(rotation: np.ndarray, translation: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        camera_points = (rotation @ points3d.T + translation.reshape(3, 1)).T
        pixels = (K @ camera_points.T).T
        pixels = pixels[:, :2] / np.maximum(pixels[:, 2:3], 1e-12)
        return camera_points[:, 2], pixels

    depth1, projected1 = project(rotation1, translation1)
    depth2, projected2 = project(rotation2, translation2)
    error1 = np.linalg.norm(projected1 - points1, axis=1)
    error2 = np.linalg.norm(projected2 - points2, axis=1)
    return (
        np.isfinite(points3d).all(axis=1)
        & (depth1 > 0.1)
        & (depth2 > 0.1)
        & (error1 <= reprojection_threshold)
        & (error2 <= reprojection_threshold)
    )


def estimate_pose_ransac(
    points3d: np.ndarray,
    points2d: np.ndarray,
    K: np.ndarray,
    reprojection_threshold: float,
    iterations: int = 500,
    seed: int = 6121,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(points3d) != len(points2d) or len(points3d) < 6:
        raise ValueError("At least six 3D-to-2D correspondences are required")
    normalized = _normalize_with_intrinsics(points2d, K)
    rng = np.random.default_rng(seed)
    best = None
    best_mask = np.zeros(len(points3d), dtype=bool)
    for _ in range(iterations):
        sample = rng.choice(len(points3d), min(6, len(points3d)), replace=False)
        design = []
        for xyz, (x, y) in zip(points3d[sample], normalized[sample]):
            row_x = np.zeros((2, 12))
            row_x[0, 0:4] = xyz[0], xyz[1], xyz[2], 1.0
            row_x[0, 8:12] = -x * np.array([xyz[0], xyz[1], xyz[2], 1.0])
            row_x[1, 4:8] = xyz[0], xyz[1], xyz[2], 1.0
            row_x[1, 8:12] = -y * np.array([xyz[0], xyz[1], xyz[2], 1.0])
            design.extend(row_x)
        try:
            _, _, vh = np.linalg.svd(np.asarray(design))
            camera = vh[-1].reshape(3, 4)
            scale = (np.linalg.norm(camera[0, :3]) + np.linalg.norm(camera[1, :3])) / 2.0
            rotation = camera[:, :3] / max(scale, 1e-12)
            u, _, vh_rotation = np.linalg.svd(rotation)
            rotation = u @ vh_rotation
            if np.linalg.det(rotation) < 0:
                rotation = -rotation
            translation = camera[:, 3:4] / max(scale, 1e-12)
        except np.linalg.LinAlgError:
            continue
        projected = (rotation @ points3d.T + translation).T
        valid_depth = projected[:, 2] > 1e-8
        projected = projected[:, :2] / np.maximum(projected[:, 2:3], 1e-8)
        errors = np.linalg.norm(projected - normalized, axis=1) * max(float(np.mean(np.diag(K)[:2])), 1.0)
        mask = valid_depth & (errors < reprojection_threshold)
        if mask.sum() > best_mask.sum():
            best = rotation, translation
            best_mask = mask
    if best is None or best_mask.sum() < 4:
        raise ValueError("RANSAC could not estimate camera pose")

    rotation, translation = best
    parameters = np.hstack((Rotation.from_matrix(rotation).as_rotvec(), translation.ravel()))
    focal = max(float(np.mean(np.diag(K)[:2])), 1.0)

    def residuals(values: np.ndarray) -> np.ndarray:
        refined_rotation = Rotation.from_rotvec(values[:3]).as_matrix()
        refined_translation = values[3:].reshape(3, 1)
        camera_points = (refined_rotation @ points3d[best_mask].T + refined_translation).T
        projections = camera_points[:, :2] / np.maximum(camera_points[:, 2:3], 1e-12)
        return ((projections - normalized[best_mask]) * focal).ravel()

    optimized = least_squares(
        residuals,
        parameters,
        loss="huber",
        f_scale=reprojection_threshold,
        max_nfev=100,
    ).x
    rotation = Rotation.from_rotvec(optimized[:3]).as_matrix()
    translation = optimized[3:].reshape(3, 1)
    projected = (rotation @ points3d.T + translation).T
    valid_depth = projected[:, 2] > 1e-8
    projections = projected[:, :2] / np.maximum(projected[:, 2:3], 1e-12)
    errors = np.linalg.norm(projections - normalized, axis=1) * focal
    return rotation, translation, valid_depth & (errors < reprojection_threshold)
