import cv2
import numpy as np

from reconstruction import Reconstruction, ReconstructionCfg


def test_baseline_parallax_accepts_opencv_255_inlier_mask(monkeypatch):
    keypoints = [
        [cv2.KeyPoint(0.0, 0.0, 1.0)],
        [cv2.KeyPoint(float(np.tan(np.deg2rad(3.0))), 0.0, 1.0)],
    ]
    matches = {(0, 1): [cv2.DMatch(0, 0, 0.0)]}
    reconstruction = Reconstruction(
        keypoints=keypoints,
        matches=matches,
        img_adjacency=np.array([[0, 1], [1, 0]], dtype=np.uint8),
        cfg=ReconstructionCfg(K=np.eye(3), min_inliers_baseline=1),
        images=[np.zeros((1, 1, 3), dtype=np.uint8)] * 2,
    )

    monkeypatch.setattr(
        cv2,
        "findEssentialMat",
        lambda *args, **kwargs: (np.eye(3), np.ones((1, 1), dtype=np.uint8)),
    )
    monkeypatch.setattr(
        cv2,
        "recoverPose",
        lambda *args, **kwargs: (
            1,
            np.eye(3),
            np.array([[1.0], [0.0], [0.0]]),
            np.full((1, 1), 255, dtype=np.uint8),
        ),
    )

    assert reconstruction.select_baseline(min_parallax_deg=2.0) == (0, 1)
