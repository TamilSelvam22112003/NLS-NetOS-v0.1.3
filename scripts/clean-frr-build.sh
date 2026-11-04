#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
rm -rf "$ROOT_DIR/build"
echo "Removed generated FRR build/staging directories."
