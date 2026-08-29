#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REFERENCE_ROOT="$PROJECT_ROOT/references"
mkdir -p "$REFERENCE_ROOT"

sync_reference() {
  local name="$1"
  local url="$2"
  local commit="$3"
  local target="$REFERENCE_ROOT/$name"

  if [[ ! -d "$target/.git" ]]; then
    git clone --filter=blob:none "$url" "$target"
  elif [[ -n "$(git -C "$target" status --porcelain)" ]]; then
    echo "Refusing to update dirty reference checkout: $target" >&2
    return 1
  fi

  git -C "$target" fetch origin "$commit"
  git -C "$target" checkout --detach "$commit"
}

sync_reference \
  sakshikakde-SFM \
  https://github.com/sakshikakde/SFM.git \
  f43111e88f4d11519309a8a8d2995e3e0da162b0

sync_reference \
  RISHIT7-sfm-pipeline \
  https://github.com/RISHIT7/sfm-pipeline.git \
  ed3188aa47567ad7898f86e3ee67afa033ae8759

sync_reference \
  muneebaadil-structure-from-motion \
  https://github.com/muneebaadil/structure-from-motion.git \
  c37e51035bb0752e15ad3b1e9bb8524f14c55712

echo "Reference repositories are ready under $REFERENCE_ROOT"

