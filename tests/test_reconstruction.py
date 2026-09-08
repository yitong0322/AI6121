import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from geometry import estimate_pose_ransac, triangulate_points, validate_triangulated_points
from reconstruction import Reconstruction, ReconstructionCfg


def test_baseline_estimation_uses_local_geometry():
    points3d = np.array([
        [-1.0, -0.5, 4.0], [0.0, -0.5, 5.0], [1.0, -0.5, 6.0],
        [-1.0, 0.5, 4.5], [0.0, 0.5, 5.5], [1.0, 0.5, 6.5],
        [-0.5, 0.0, 7.0], [0.5, 0.0, 7.5], [-0.2, 0.2, 8.0],
        [0.2, -0.2, 8.5],
    ])
    points_i = points3d[:, :2] / points3d[:, 2:3]
    translated = points3d + np.array([1.0, 0.0, 0.0])
    points_j = translated[:, :2] / translated[:, 2:3]
    keypoints = [
        [cv2.KeyPoint(float(x), float(y), 1.0) for x, y in points_i],
        [cv2.KeyPoint(float(x), float(y), 1.0) for x, y in points_j],
    ]
    matches = {(0, 1): [cv2.DMatch(i, i, 0.0) for i in range(len(points3d))]}
    reconstruction = Reconstruction(
        keypoints=keypoints,
        matches=matches,
        img_adjacency=np.array([[0, 1], [1, 0]], dtype=np.uint8),
        cfg=ReconstructionCfg(K=np.eye(3), min_inliers_baseline=8),
        images=[np.zeros((2, 2, 3), dtype=np.uint8)] * 2,
    )

    assert reconstruction.select_baseline(min_parallax_deg=0.1) == (0, 1)


def test_local_pnp_recovers_known_camera_pose():
    rng = np.random.default_rng(6121)
    points3d = rng.uniform([-1.0, -0.8, 3.0], [1.0, 0.8, 7.0], size=(20, 3))
    K = np.array([[800.0, 0.0, 320.0], [0.0, 810.0, 240.0], [0.0, 0.0, 1.0]])
    rotation = Rotation.from_euler("xyz", [4.0, -7.0, 3.0], degrees=True).as_matrix()
    translation = np.array([[0.2], [-0.1], [0.3]])
    camera_points = (rotation @ points3d.T + translation).T
    pixels = (K @ camera_points.T).T
    pixels = pixels[:, :2] / pixels[:, 2:3]

    recovered_rotation, recovered_translation, inliers = estimate_pose_ransac(
        points3d, pixels, K, reprojection_threshold=1.0, iterations=200
    )

    assert inliers.sum() == len(points3d)
    assert np.allclose(recovered_rotation, rotation, atol=1e-6)
    assert np.allclose(recovered_translation, translation, atol=1e-6)


def test_triangulation_rejects_point_behind_either_camera():
    rotation = np.eye(3)
    translation1 = np.zeros((3, 1))
    translation2 = np.array([[1.0], [0.0], [0.0]])
    points3d = np.array([[0.2, -0.1, 4.0], [0.4, 0.1, -2.0]])
    projection1 = np.hstack((rotation, translation1))
    projection2 = np.hstack((rotation, translation2))

    def project(projection):
        pixels = (projection @ np.column_stack((points3d, np.ones(len(points3d)))).T).T
        return pixels[:, :2] / pixels[:, 2:3]

    points1, points2 = project(projection1), project(projection2)
    reconstructed = triangulate_points(projection1, projection2, points1, points2)
    valid = validate_triangulated_points(
        reconstructed, rotation, translation1, rotation, translation2,
        np.eye(3), points1, points2, reprojection_threshold=1e-6,
    )

    assert valid.tolist() == [True, False]
