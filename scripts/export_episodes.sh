#!/usr/bin/env bash
set -euo pipefail
mkdir -p data/episodes
ts=$(date +%Y%m%d-%H%M%S)
tarball="data/episodes/episodes-$ts.tar.gz"
tar -czf "$tarball" data/episodes/events.* 2>/dev/null || true
shasum -a 256 "$tarball" || true
echo "wrote $tarball"
