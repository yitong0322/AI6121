#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 5 ]]; then
  echo "Usage: $0 IMAGE_DIR WORKSPACE [K_TXT] [exhaustive|sequential] [MASK_DIR]" >&2
  exit 2
fi

IMAGE_DIR="$(realpath "$1")"
WORKSPACE="$2"
K_FILE="${3:-}"
MATCHER="${4:-exhaustive}"
MASK_DIR="${5:-}"

if [[ ! -d "$IMAGE_DIR" ]]; then
  echo "Image directory does not exist: $IMAGE_DIR" >&2
  exit 1
fi
if [[ "$MATCHER" != "exhaustive" && "$MATCHER" != "sequential" ]]; then
  echo "Matcher must be 'exhaustive' or 'sequential'." >&2
  exit 2
fi
if [[ -n "$MASK_DIR" ]]; then
  MASK_DIR="$(realpath "$MASK_DIR")"
  if [[ ! -d "$MASK_DIR" ]]; then
    echo "Mask directory does not exist: $MASK_DIR" >&2
    exit 1
  fi
fi
if [[ -e "$WORKSPACE" ]] && find "$WORKSPACE" -mindepth 1 -print -quit | grep -q .; then
  echo "Workspace must be new or empty: $WORKSPACE" >&2
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

mkdir -p "$WORKSPACE/sparse" "$WORKSPACE/txt"
DATABASE="$WORKSPACE/database.db"
IMAGE_LIST="$WORKSPACE/images.txt"

# COLMAP scans every file under image_path unless an explicit list is supplied;
# keep calibration/readme text files out of the feature-extraction queue.
find "$IMAGE_DIR" -regextype posix-extended -maxdepth 1 -type f \
  -iregex '.*\.(jpg|jpeg|png|bmp|tif|tiff)' -printf '%f\n' \
  | LC_ALL=C sort > "$IMAGE_LIST"
if [[ ! -s "$IMAGE_LIST" ]]; then
  echo "No supported image files were found in: $IMAGE_DIR" >&2
  exit 1
fi

CAMERA_ARGS=(--ImageReader.single_camera 1)
if [[ -n "$MASK_DIR" ]]; then
  CAMERA_ARGS+=(--ImageReader.mask_path "$MASK_DIR")
fi
if [[ -n "$K_FILE" ]]; then
  if [[ ! -f "$K_FILE" ]]; then
    echo "Calibration file does not exist: $K_FILE" >&2
    exit 1
  fi
  read -r FX _ CX < <(sed -n '1p' "$K_FILE")
  read -r _ FY CY < <(sed -n '2p' "$K_FILE")
  CAMERA_ARGS+=(--ImageReader.camera_model PINHOLE)
  CAMERA_ARGS+=(--ImageReader.camera_params "$FX,$FY,$CX,$CY")
fi

"${COLMAP[@]}" feature_extractor \
  --database_path "$DATABASE" \
  --image_path "$IMAGE_DIR" \
  --image_list_path "$IMAGE_LIST" \
  "${CAMERA_ARGS[@]}"

"${COLMAP[@]}" "${MATCHER}_matcher" --database_path "$DATABASE"

"${COLMAP[@]}" mapper \
  --database_path "$DATABASE" \
  --image_path "$IMAGE_DIR" \
  --output_path "$WORKSPACE/sparse"

mapfile -t MODEL_DIRS < <(find "$WORKSPACE/sparse" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort)
if [[ ${#MODEL_DIRS[@]} -eq 0 ]]; then
  echo "COLMAP finished but did not produce a sparse model." >&2
  exit 1
fi

BEST_MODEL=""
BEST_ANALYSIS=""
BEST_REGISTERED=-1
for MODEL_DIR in "${MODEL_DIRS[@]}"; do
  ANALYSIS="$("${COLMAP[@]}" model_analyzer --path "$MODEL_DIR" 2>&1)"
  REGISTERED="$(awk '/Registered images:/ {print $NF}' <<< "$ANALYSIS")"
  if [[ "$REGISTERED" =~ ^[0-9]+$ ]] && (( REGISTERED > BEST_REGISTERED )); then
    BEST_MODEL="$MODEL_DIR"
    BEST_ANALYSIS="$ANALYSIS"
    BEST_REGISTERED="$REGISTERED"
  fi
done
if [[ -z "$BEST_MODEL" ]]; then
  echo "Could not identify the largest COLMAP sparse model." >&2
  exit 1
fi
printf '%s\n' "$BEST_ANALYSIS" | tee "$WORKSPACE/metrics.txt"

"${COLMAP[@]}" model_converter \
  --input_path "$BEST_MODEL" \
  --output_path "$WORKSPACE/txt" \
  --output_type TXT

"${COLMAP[@]}" model_converter \
  --input_path "$BEST_MODEL" \
  --output_path "$WORKSPACE/sparse.ply" \
  --output_type PLY

echo "COLMAP model: $BEST_MODEL"
echo "Point cloud:  $WORKSPACE/sparse.ply"
echo "Metrics:      $WORKSPACE/metrics.txt"
