#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_COLMAP=0

if [[ "${1:-}" == "--with-colmap" ]]; then
  WITH_COLMAP=1
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--with-colmap]" >&2
  exit 2
fi

if ! command -v conda >/dev/null 2>&1; then
  echo "Conda is required but was not found on PATH." >&2
  exit 1
fi

env_exists() {
  conda env list | awk 'NF && $1 !~ /^#/ {print $1}' | grep -qx "$1"
}

sync_env() {
  local env_name="$1"
  local env_file="$2"
  if env_exists "$env_name"; then
    echo "Updating Conda environment: $env_name"
    conda env update -n "$env_name" -f "$env_file" --prune
  else
    echo "Creating Conda environment: $env_name"
    conda env create -f "$env_file"
  fi
}

sync_env ai6121-sfm "$PROJECT_ROOT/environment.yml"

# Make the environment easy to select from JupyterLab and VS Code.
conda run -n ai6121-sfm python -m ipykernel install --user \
  --name ai6121-sfm --display-name "Python (AI6121 SfM)"

if [[ "$WITH_COLMAP" -eq 1 ]]; then
  sync_env ai6121-colmap "$PROJECT_ROOT/environment-colmap.yml"
fi

echo
echo "Environment setup complete."
echo "  Python baseline: conda activate ai6121-sfm"
if [[ "$WITH_COLMAP" -eq 1 ]]; then
  echo "  COLMAP benchmark: conda activate ai6121-colmap"
fi

