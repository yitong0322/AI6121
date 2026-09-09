# AI6121 SfM project workflow

This project uses an in-repository multi-view reconstruction pipeline. OpenCV
and SciPy solve individual subproblems; the project code controls matching,
incremental registration, triangulation updates, bundle-adjustment scheduling,
evaluation, and point-cloud export.

## Setup

```bash
bash scripts/bootstrap.sh
bash scripts/fetch_references.sh
conda activate ai6121-sfm
python -m pytest -q tests/test_environment.py
```

The environment uses Python 3.10 with NumPy, OpenCV/SIFT, Open3D, SciPy,
JupyterLab, FFmpeg, and related utilities.

## Data layout

Each scene contains images in capture order and a 3x3 calibration matrix:

```text
00.jpg  01.jpg  02.jpg  ...  K.txt
```

Keep image resolution, focal length, and zoom consistent within a scene. The
local TempleRing dataset is available at `./templeRing` for a baseline run.

## Reconstruction

Start the project notebook directly:

```bash
conda activate ai6121-sfm
jupyter lab main.ipynb
```

Set `dataset_path` and run the cells in order. The pipeline is:

1. Extract SIFT features and match them with FLANN or BFMatcher.
2. Filter matches geometrically.
3. Select an initial pair using match count and parallax.
4. Estimate the initial relative pose with `findEssentialMat` and `recoverPose`.
5. Triangulate the initial points with `triangulatePoints`.
6. Register additional images with `solvePnPRansac`.
7. Triangulate new observations and update the project-owned point/observation
   structures.
8. Run SciPy `least_squares` bundle adjustment at controlled intervals.
9. Evaluate reprojection error and export the PLY point cloud.

The OpenCV and SciPy calls above solve local geometry or optimization problems;
no single external program is responsible for the complete SfM workflow.

Optional preprocessing utilities are available for frame extraction,
foreground masks, and headless PLY previews. They are independent of the
reconstruction control flow.

## Reporting and attribution

The report should identify the OpenCV and SciPy functions used, explain the
project-owned multi-image control flow, cite any reference repositories and
their licenses, and describe all modifications to borrowed code. It must also
declare the use of generative AI for code writing and debugging.

Generated outputs belong under `outputs/` and should not be committed.
