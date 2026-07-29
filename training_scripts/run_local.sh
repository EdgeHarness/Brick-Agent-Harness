#!/usr/bin/env bash
# Experimental Docker wrapper. Requires Docker, compatible NVIDIA
# container/GPU tooling, network access during build, and adequate storage.
# It attempts to write adapter/conversion artifacts under ./out.
set -euo pipefail
cd "$(dirname "$0")"

docker build -t toolcall-lora .

mkdir -p "$PWD/out"
docker run --rm --gpus all \
  -v "$PWD/out:/workspace/out" \
  toolcall-lora --to-gguf

echo "done -> $PWD/out/toolcall-lora"
