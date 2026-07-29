#!/bin/bash
# Experimental Slurm submission for a compatible GPU center with
# Apptainer/Singularity. A prebuilt image contains the current model snapshot,
# synthetic data, and tooling, but site policy and runtime compatibility still
# need verification.
# Submit with:  sbatch run.slurm
#
# On a build node with network access, build the .sif from the definition:
#     apptainer build toolcall-lora.sif apptainer.def
#   (older Singularity:  singularity build toolcall-lora.sif apptainer.def)
#
#SBATCH --job-name=toolcall-lora
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=lora_%j.log

set -euo pipefail

# Some centers require a module load; uncomment whichever applies:
# module load apptainer      # or:  module load singularity

RUNNER=$(command -v apptainer || command -v singularity)
SIF=${SIF:-toolcall-lora.sif}
OUTDIR=${OUTDIR:-$PWD/out}
mkdir -p "$OUTDIR"

# --nv requests GPU exposure; bind the writable output directory so attempted
# training artifacts land on the shared filesystem.
"$RUNNER" exec --nv \
  --bind "$OUTDIR:/workspace/out" \
  "$SIF" \
  python /workspace/train_lora.py --output /workspace/out/toolcall-lora --to-gguf

echo "done. adapter + gguf in: $OUTDIR/toolcall-lora"
