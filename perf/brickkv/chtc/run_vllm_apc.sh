#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 7 ]]; then
  echo "expected GPU label, GPU name, model archive, model archive digest, container digest, source revision, and source bundle digest" >&2
  exit 64
fi

gpu_short=$1
expected_gpu=$2
model_archive=$3
model_archive_digest=$4
container_digest=$5
source_revision=$6
source_bundle_digest=$7

if [[ -z "${CUDA_VISIBLE_DEVICES:-}" || "$CUDA_VISIBLE_DEVICES" == *,* ]]; then
  echo "exactly one HTCondor-assigned CUDA_VISIBLE_DEVICES entry is required" >&2
  exit 65
fi
if [[ ! "$model_archive_digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "MODEL_ARCHIVE_DIGEST must be sha256:<64 lowercase hex>" >&2
  exit 66
fi
if [[ ! "$container_digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "CONTAINER_DIGEST must be sha256:<64 lowercase hex>" >&2
  exit 67
fi
if [[ ! "$source_revision" =~ ^[0-9a-f]{40}$ && ! "$source_revision" =~ ^[0-9a-f]{64}$ ]]; then
  echo "SOURCE_REVISION must be a full lowercase Git object ID" >&2
  exit 69
fi
if [[ ! "$source_bundle_digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "SOURCE_BUNDLE_DIGEST must be sha256:<64 lowercase hex>" >&2
  exit 74
fi
if [[ "${BRICKKV_CONTAINER_IMAGE:-}" != *@"$container_digest" ]]; then
  echo "container image is not pinned to the declared digest" >&2
  exit 70
fi
if [[ ! -f "$model_archive" ]]; then
  echo "transferred model archive is missing: $model_archive" >&2
  exit 71
fi

actual_model_archive_digest=$(sha256sum "$model_archive" | awk '{print $1}')
if [[ "sha256:$actual_model_archive_digest" != "$model_archive_digest" ]]; then
  echo "model archive digest mismatch" >&2
  exit 72
fi

actual_source_bundle_digest=$(
  python -m perf.brickkv.source_bundle --revision "$source_revision"
)
if [[ "$actual_source_bundle_digest" != "$source_bundle_digest" ]]; then
  echo "transferred source bundle digest mismatch" >&2
  exit 75
fi

zstd -dc -- "$model_archive" | python -m perf.brickkv.safe_extract model
mapfile -t configs < <(find model -type f -name config.json -print)
if [[ ${#configs[@]} -ne 1 ]]; then
  echo "model archive must contain exactly one config.json" >&2
  exit 73
fi
model_root=$(dirname "${configs[0]}")

python -m perf.brickkv.gpu_matrix \
  --execute \
  --study perf/brickkv/gpu_prefix_study.py \
  --model "$model_root" \
  --model-archive-digest "$model_archive_digest" \
  --container-digest "$container_digest" \
  --expected-gpu "$expected_gpu" \
  --source-revision "$source_revision" \
  --source-bundle-digest "$source_bundle_digest" \
  --output "results-$gpu_short"
