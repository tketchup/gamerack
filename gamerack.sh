#!/usr/bin/env bash
# Launcher for a source checkout — no installation needed.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
exec python3 -m gamerack "$@"
