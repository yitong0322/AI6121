#!/usr/bin/env python3
"""Execute the upstream i-sfm notebook headlessly on a custom dataset."""

import argparse
import os
from pathlib import Path

import nbformat
from nbclient import NotebookClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def replace_required(source: str, old: str, new: str) -> str:
    if old not in source:
        raise ValueError(f"Expected notebook fragment was not found: {old!r}")
    return source.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path, help="Directory containing numbered images and K.txt")
    parser.add_argument("output_dir", type=Path, help="Directory for PLY and executed notebook")
    parser.add_argument("--nfeatures", type=int, default=3000)
    parser.add_argument("--min-baseline-inliers", type=int, default=50)
    parser.add_argument("--min-parallax-deg", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=1200, help="Per-cell timeout in seconds")
    args = parser.parse_args()

    dataset = args.dataset.resolve()
    output_dir = args.output_dir.resolve()
    if not dataset.is_dir() or not (dataset / "K.txt").is_file():
        raise SystemExit(f"Dataset must contain numbered images and K.txt: {dataset}")

    notebook_path = PROJECT_ROOT / "main.ipynb"
    notebook = nbformat.read(notebook_path, as_version=4)

    # Configure the supplied notebook while preserving its reconstruction logic.
    cell = notebook.cells[1]
    cell.source = replace_required(
        cell.source,
        "dataset_path = './datasets/templeRing'",
        f"dataset_path = r'{dataset}'",
    )
    cell.source = replace_required(
        cell.source,
        "output_dir = Path('./outputs')",
        f"output_dir = Path(r'{output_dir}')",
    )
    cell.source = replace_required(
        cell.source,
        "output_dir.mkdir(exist_ok=True)",
        "output_dir.mkdir(parents=True, exist_ok=True)",
    )

    cell = notebook.cells[2]
    cell.source = replace_required(cell.source, "use_flann=False", "use_flann=True")
    cell.source = replace_required(cell.source, "nfeatures=0", f"nfeatures={args.nfeatures}")
    cell.source = replace_required(cell.source, "fm.plot_feature_histogram()", "# Headless: feature plot skipped")
    cell.source = replace_required(
        cell.source,
        "fm.filter_geometric()",
        "fm.filter_geometric()\nfm.build_adjacency()",
    )
    cell.source = replace_required(cell.source, "fm.plot_best_match()", "# Headless: match plot skipped")

    cell = notebook.cells[3]
    cell.source = replace_required(
        cell.source,
        "min_inliers_baseline=50",
        f"min_inliers_baseline={args.min_baseline_inliers}",
    )
    cell.source = replace_required(
        cell.source,
        "num_threads = cpu_cores",
        "num_threads = min(cpu_cores, 4)",
    )
    cell.source = replace_required(
        cell.source,
        "recon.select_baseline(top_percent=0.25)",
        "recon.select_baseline("
        f"top_percent=0.25, min_parallax_deg={args.min_parallax_deg})",
    )

    cell = notebook.cells[6]
    cell.source = replace_required(
        cell.source,
        'visualize_current_state(recon, "Final Reconstruction")',
        "# Headless: interactive reconstruction view skipped",
    )

    cell = notebook.cells[8]
    cell.source = replace_required(cell.source, '"templeRing.ply"', '"i_sfm_reconstruction.ply"')
    notebook.cells[9].source = "# Headless: Open3D interactive view skipped"
    notebook.cells[10].source = "# Headless: optional view skipped"

    notebook.cells.insert(
        0,
        nbformat.v4.new_code_cell(
            'import os\nos.environ["MPLBACKEND"] = "Agg"\nos.environ["OPEN3D_CPU_RENDERING"] = "true"'
        ),
    )
    notebook.metadata.kernelspec = {
        "display_name": "Python (AI6121 SfM)",
        "language": "python",
        "name": "ai6121-sfm",
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    executed_path = output_dir / "i_sfm_executed.ipynb"
    os.chdir(PROJECT_ROOT)
    client = NotebookClient(
        notebook,
        timeout=args.timeout,
        kernel_name="ai6121-sfm",
        resources={"metadata": {"path": str(PROJECT_ROOT)}},
    )
    try:
        client.execute()
    finally:
        nbformat.write(notebook, executed_path)

    print(f"Executed notebook: {executed_path}")
    print(f"Point cloud:       {output_dir / 'i_sfm_reconstruction.ply'}")


if __name__ == "__main__":
    main()
