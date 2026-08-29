#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 || $# -gt 5 ]]; then
  echo "Usage: $0 IMAGE_DIR SPARSE_MODEL DENSE_WORKSPACE [photometric|geometric] [REFERENCE_STRIDE]" >&2
  exit 2
fi

IMAGE_DIR="$(realpath "$1")"
SPARSE_MODEL="$(realpath "$2")"
DENSE_WORKSPACE="$3"
CONSISTENCY="${4:-photometric}"
REFERENCE_STRIDE="${5:-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$CONSISTENCY" != "photometric" && "$CONSISTENCY" != "geometric" ]]; then
  echo "Consistency must be 'photometric' or 'geometric'." >&2
  exit 2
fi
if [[ ! "$REFERENCE_STRIDE" =~ ^[1-9][0-9]*$ ]]; then
  echo "Reference stride must be a positive integer." >&2
  exit 2
fi
if [[ "$CONSISTENCY" == "geometric" ]]; then
  GEOM_CONSISTENCY=1
  FUSION_INPUT=geometric
else
  GEOM_CONSISTENCY=0
  FUSION_INPUT=photometric
fi

if [[ ! -d "$IMAGE_DIR" ]]; then
  echo "Image directory does not exist: $IMAGE_DIR" >&2
  exit 1
fi
if [[ ! -d "$SPARSE_MODEL" ]]; then
  echo "Sparse model does not exist: $SPARSE_MODEL" >&2
  exit 1
fi
if [[ -e "$DENSE_WORKSPACE" ]] && find "$DENSE_WORKSPACE" -mindepth 1 -print -quit | grep -q .; then
  echo "Dense workspace must be new or empty: $DENSE_WORKSPACE" >&2
  exit 1
fi

if command -v colmap >/dev/null 2>&1; then
  COLMAP=(colmap)
elif command -v conda >/dev/null 2>&1 && conda env list | awk 'NF {print $1}' | grep -qx ai6121-colmap; then
  COLMAP=(conda run --no-capture-output -n ai6121-colmap colmap)
else
  echo "COLMAP was not found. Run: bash scripts/bootstrap.sh --with-colmap" >&2
  exit 1
fi

mkdir -p "$DENSE_WORKSPACE"

"${COLMAP[@]}" image_undistorter \
  --image_path "$IMAGE_DIR" \
  --input_path "$SPARSE_MODEL" \
  --output_path "$DENSE_WORKSPACE" \
  --output_type COLMAP

if (( REFERENCE_STRIDE > 1 )); then
  python3 "$SCRIPT_DIR/subsample_patch_match.py" \
    "$DENSE_WORKSPACE/stereo/patch-match.cfg" \
    --stride "$REFERENCE_STRIDE"
fi

if [[ "$CONSISTENCY" == "geometric" ]] && (( REFERENCE_STRIDE > 1 )); then
  # Geometric consistency needs an initial depth map for every source view.
  # First estimate the selected references using all full-rate source images.
  "${COLMAP[@]}" patch_match_stereo \
    --workspace_path "$DENSE_WORKSPACE" \
    --workspace_format COLMAP \
    --PatchMatchStereo.geom_consistency 0 \
    --PatchMatchStereo.filter 0

  MODEL_TEXT="$DENSE_WORKSPACE/sparse-text"
  mkdir -p "$MODEL_TEXT"
  "${COLMAP[@]}" model_converter \
    --input_path "$SPARSE_MODEL" \
    --output_path "$MODEL_TEXT" \
    --output_type TXT
  python3 "$SCRIPT_DIR/subsample_patch_match.py" \
    "$DENSE_WORKSPACE/stereo/patch-match.cfg" \
    --stride 1 \
    --restrict-sources-to-references \
    --model-images "$MODEL_TEXT/images.txt"
fi

"${COLMAP[@]}" patch_match_stereo \
  --workspace_path "$DENSE_WORKSPACE" \
  --workspace_format COLMAP \
  --PatchMatchStereo.geom_consistency "$GEOM_CONSISTENCY"

"${COLMAP[@]}" stereo_fusion \
  --workspace_path "$DENSE_WORKSPACE" \
  --workspace_format COLMAP \
  --input_type "$FUSION_INPUT" \
  --output_path "$DENSE_WORKSPACE/fused.ply"

echo "Dense point cloud: $DENSE_WORKSPACE/fused.ply"
