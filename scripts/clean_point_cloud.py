#!/usr/bin/env python3
"""Remove black-background artifacts and statistical outliers from a colored PLY."""

import argparse
from pathlib import Path

import numpy as np
import open3d as o3d


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--min-color", type=float, default=0.06, help="Minimum max RGB value, in [0, 1]")
    parser.add_argument("--neighbors", type=int, default=30)
    parser.add_argument("--std-ratio", type=float, default=1.75)
    args = parser.parse_args()

    cloud = o3d.io.read_point_cloud(str(args.input))
    points = np.asarray(cloud.points)
    if len(points) == 0:
        raise SystemExit(f"No points found in: {args.input}")

    finite = np.isfinite(points).all(axis=1)
    if cloud.has_colors():
        colors = np.asarray(cloud.colors)
        finite &= np.max(colors, axis=1) >= args.min_color
    cloud = cloud.select_by_index(np.flatnonzero(finite))
    color_filtered_count = len(cloud.points)

    cloud, _ = cloud.remove_statistical_outlier(
        nb_neighbors=args.neighbors,
        std_ratio=args.std_ratio,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_point_cloud(str(args.output), cloud):
        raise SystemExit(f"Failed to write: {args.output}")

    print(f"Input points:          {len(points)}")
    print(f"After color filtering: {color_filtered_count}")
    print(f"After outlier removal: {len(cloud.points)}")
    print(f"Clean point cloud:     {args.output}")


if __name__ == "__main__":
    main()
