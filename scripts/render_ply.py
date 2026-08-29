#!/usr/bin/env python3
"""Render a colored PLY point cloud to three headless PCA-aligned views."""

import argparse
import os
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d


def equalize_axes(axis, x: np.ndarray, y: np.ndarray) -> None:
    x_min, x_max = np.percentile(x, [1, 99])
    y_min, y_max = np.percentile(y, [1, 99])
    half_span = max(x_max - x_min, y_max - y_min) / 2
    axis.set_xlim((x_min + x_max) / 2 - half_span, (x_min + x_max) / 2 + half_span)
    axis.set_ylim((y_min + y_max) / 2 - half_span, (y_min + y_max) / 2 + half_span)
    axis.set_aspect("equal", adjustable="box")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="Input colored PLY point cloud")
    parser.add_argument("output", type=Path, help="Output PNG preview")
    args = parser.parse_args()

    cloud = o3d.io.read_point_cloud(str(args.input))
    points = np.asarray(cloud.points)
    colors = np.asarray(cloud.colors)
    if len(points) == 0:
        raise SystemExit(f"Point cloud is empty: {args.input}")

    finite = np.isfinite(points).all(axis=1)
    points = points[finite]
    colors = colors[finite] if len(colors) == len(finite) else np.ones_like(points)

    center = np.median(points, axis=0)
    centered = points - center
    distances = np.linalg.norm(centered, axis=1)
    keep = distances <= np.percentile(distances, 99)
    centered = centered[keep]
    colors = colors[keep]

    _, _, axes = np.linalg.svd(centered, full_matrices=False)
    aligned = centered @ axes.T

    views = ((0, 1, "Front / principal plane"), (0, 2, "Top / depth"), (1, 2, "Side / depth"))
    figure, plot_axes = plt.subplots(1, 3, figsize=(15, 5), facecolor="#111111")
    for plot_axis, (x_idx, y_idx, title) in zip(plot_axes, views):
        plot_axis.set_facecolor("#111111")
        plot_axis.scatter(
            aligned[:, x_idx],
            aligned[:, y_idx],
            c=np.clip(colors, 0, 1),
            s=2.5,
            linewidths=0,
        )
        equalize_axes(plot_axis, aligned[:, x_idx], aligned[:, y_idx])
        plot_axis.set_title(title, color="white")
        plot_axis.tick_params(colors="#aaaaaa", labelsize=7)
        for spine in plot_axis.spines.values():
            spine.set_color("#555555")

    figure.suptitle(
        f"{args.input.name}: {len(centered):,} points (99% inlier view)",
        color="white",
        y=0.98,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.91))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, dpi=180, facecolor=figure.get_facecolor())
    print(f"Rendered {len(centered)} points to {args.output}")


if __name__ == "__main__":
    main()
