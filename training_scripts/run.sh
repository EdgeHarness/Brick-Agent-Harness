#!/usr/bin/env bash
# Experimental convenience wrapper for a compatible Linux GPU environment.
# It installs dependencies when needed, generates synthetic data, downloads
# model/conversion assets, then attempts training and GGUF conversion. Review
# licensing, labels, hardware compatibility, and output quality separately.
set -euo pipefail
cd "$(dirname "$0")"

# 1. environment (venv + torch + deps), unless already inside a ready container
if ! python3 -c "import torch, transformers, peft" 2>/dev/null; then
  bash setup.sh
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# 2. generate experimental synthetic training data if it is absent
if [ ! -s data/toolcall.jsonl ]; then
  echo "no data/toolcall.jsonl — generating it from make_data.py"
  python make_data.py --out data/toolcall.jsonl
fi

# 3. fetch model + llama.cpp into ./assets (requires network when absent)
python download_assets.py

# 4. attempt training and conversion under ./out/toolcall-lora/
python train_lora.py --to-gguf

echo
echo "DONE. Adapter and GGUF are in: $(pwd)/out/toolcall-lora"
