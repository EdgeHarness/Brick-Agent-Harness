#!/usr/bin/env bash
# Experimental environment bootstrap for a Linux GPU machine.
# It creates/reuses a local venv and installs a selected torch wheel plus
# training dependencies. Driver, CUDA, Python, and package compatibility are
# not detected or guaranteed.
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel

# CUDA 12.1 is only the default wheel index. Select a TORCH_INDEX compatible
# with the target host and verify the resulting environment before training.
TORCH_INDEX=${TORCH_INDEX:-https://download.pytorch.org/whl/cu121}
python -c "import torch" 2>/dev/null || pip install torch --index-url "$TORCH_INDEX"

pip install -r requirements.txt
echo "environment ready in ./.venv"
