#!/usr/bin/env python3
"""Subsample COLMAP PatchMatch views and optionally restrict geometric sources."""

import argparse
from collections import defaultdict
from pathlib import Path


def read_visibility(images_txt: Path) -> dict[str, set[int]]:
    """Read the observed 3D point IDs for each image from a COLMAP text model."""
    data_lines = [
        line.strip()
        for line in images_txt.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if len(data_lines) % 2:
        raise SystemExit(f"Unexpected odd data-line count in: {images_txt}")

    visibility = {}
    for index in range(0, len(data_lines), 2):
        image_fields = data_lines[index].split()
        point_fields = data_lines[index + 1].split()
        name = image_fields[-1]
        point_ids = {
            int(point_fields[offset])
            for offset in range(2, len(point_fields), 3)
            if int(point_fields[offset]) >= 0
        }
        visibility[name] = point_ids
    return visibility


def restrict_sources(
    pairs: list[tuple[str, str]], visibility: dict[str, set[int]], num_sources: int
) -> list[tuple[str, str]]:
    """Use only reference views as sources, ranked by sparse-point covisibility."""
    references = [pair[0] for pair in pairs]
    missing = [name for name in references if name not in visibility]
    if missing:
        raise SystemExit(f"Reference view missing from COLMAP text model: {missing[0]}")

    restricted = []
    for reference, _ in pairs:
        reference_points = visibility[reference]
        ranked = sorted(
            (candidate for candidate in references if candidate != reference),
            key=lambda candidate: (
                len(reference_points & visibility[candidate]),
                candidate.split("_", 1)[0] == reference.split("_", 1)[0],
                candidate,
            ),
            reverse=True,
        )
        sources = ranked[:num_sources]
        if not sources:
            raise SystemExit(f"No source views available for: {reference}")
        restricted.append((reference, ", ".join(sources)))
    return restricted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--stride", type=int, required=True)
    parser.add_argument("--restrict-sources-to-references", action="store_true")
    parser.add_argument("--model-images", type=Path)
    parser.add_argument("--num-sources", type=int, default=20)
    args = parser.parse_args()
    if args.stride < 1:
        raise SystemExit("Stride must be at least 1")
    if args.num_sources < 1:
        raise SystemExit("Number of sources must be at least 1")
    if args.restrict_sources_to_references and args.model_images is None:
        raise SystemExit("--model-images is required when restricting sources")

    lines = args.config.read_text(encoding="utf-8").splitlines()
    if len(lines) % 2:
        raise SystemExit(f"Unexpected odd line count in: {args.config}")
    pairs = [(lines[index], lines[index + 1]) for index in range(0, len(lines), 2)]

    groups = defaultdict(list)
    for pair in pairs:
        prefix = pair[0].split("_", 1)[0]
        groups[prefix].append(pair)

    selected = []
    for group_pairs in groups.values():
        keep_indices = set(range(0, len(group_pairs), args.stride))
        keep_indices.add(len(group_pairs) - 1)
        selected.extend(pair for index, pair in enumerate(group_pairs) if index in keep_indices)
    selected.sort(key=lambda pair: pair[0])

    if args.restrict_sources_to_references:
        selected = restrict_sources(
            selected, read_visibility(args.model_images), args.num_sources
        )

    output_lines = [line for pair in selected for line in pair]
    args.config.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    print(f"PatchMatch reference views: {len(pairs)} -> {len(selected)} (stride {args.stride})")
    if args.restrict_sources_to_references:
        print(f"PatchMatch sources restricted to {args.num_sources} reference views")


if __name__ == "__main__":
    main()
