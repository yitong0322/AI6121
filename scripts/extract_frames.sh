#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 VIDEO OUTPUT_DIR [FPS]" >&2
  exit 2
fi

VIDEO="$1"
OUTPUT_DIR="$2"
FPS="${3:-2}"

if [[ ! -f "$VIDEO" ]]; then
  echo "Video does not exist: $VIDEO" >&2
  exit 1
fi

if [[ -d "$OUTPUT_DIR" ]] && find "$OUTPUT_DIR" -mindepth 1 -print -quit | grep -q .; then
  echo "Output directory is not empty: $OUTPUT_DIR" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

if command -v ffmpeg >/dev/null 2>&1; then
  FFMPEG=(ffmpeg)
elif command -v conda >/dev/null 2>&1 && conda env list | awk 'NF {print $1}' | grep -qx ai6121-sfm; then
  FFMPEG=(conda run --no-capture-output -n ai6121-sfm ffmpeg)
else
  echo "FFmpeg was not found. Run: bash scripts/bootstrap.sh" >&2
  exit 1
fi

"${FFMPEG[@]}" -hide_banner -i "$VIDEO" \
  -vf "fps=$FPS,scale='min(1920,iw)':-2" \
  -start_number 0 -q:v 2 "$OUTPUT_DIR/%02d.jpg"

echo "Frames written to $OUTPUT_DIR"
