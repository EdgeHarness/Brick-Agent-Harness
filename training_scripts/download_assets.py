"""Experimental prefetch helper for the current training path.

Downloads into ./assets (idempotent — skips whatever is already there):
    assets/base_model/   configured Hugging Face model snapshot
    assets/llama.cpp/    llama.cpp, for GGUF adapter conversion

Run where network access is allowed. A completed download may support later
network-isolated training, but this helper does not verify integrity, licensing,
runtime compatibility, or whether other dependencies attempt network access.

    python download_assets.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

# Default snapshot identifier. Availability, authentication, licensing, and
# equivalence to other distributions are external facts this script does not
# establish.
BASE_ID = os.environ.get("BASE_MODEL_ID", "unsloth/Llama-3.2-1B-Instruct")
LLAMACPP_REPO = os.environ.get("LLAMACPP_REPO", "https://github.com/ggml-org/llama.cpp")


def fetch_model():
    dst = os.path.join(ASSETS, "base_model")
    if os.path.isfile(os.path.join(dst, "config.json")):
        print(f"[model] already present -> {dst}")
        return dst
    from huggingface_hub import snapshot_download
    print(f"[model] downloading {BASE_ID} -> {dst}")
    snapshot_download(
        repo_id=BASE_ID, local_dir=dst,
        # weights + tokenizer + configs only; skip anything huge/irrelevant
        allow_patterns=["*.json", "*.safetensors", "*.model", "tokenizer*", "*.txt"])
    return dst


def fetch_llamacpp():
    dst = os.path.join(ASSETS, "llama.cpp")
    if os.path.isfile(os.path.join(dst, "convert_lora_to_gguf.py")):
        print(f"[llama.cpp] already present -> {dst}")
        return dst
    print(f"[llama.cpp] cloning -> {dst}")
    subprocess.run(["git", "clone", "--depth", "1", LLAMACPP_REPO, dst], check=True)
    return dst


def install_gguf_py(llamacpp_dir):
    """Install the gguf package that matches the cloned llama.cpp, so
    convert_lora_to_gguf.py (--to-gguf) can't hit a gguf-version mismatch.
    Best-effort: the pinned gguf in requirements.txt is the fallback."""
    gguf_py = os.path.join(llamacpp_dir, "gguf-py")
    if not os.path.isdir(gguf_py):
        return
    print("[gguf] installing matching gguf-py from the cloned llama.cpp")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", gguf_py], check=True)
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"[gguf] gguf-py install skipped ({e}); pinned gguf will be used.")


if __name__ == "__main__":
    os.makedirs(ASSETS, exist_ok=True)
    m = fetch_model()
    lc = fetch_llamacpp()
    install_gguf_py(lc)
    print(
        f"\nassets downloaded:\n  base_model: {m}\n  llama.cpp : {lc}\n"
        "verify licensing, integrity, and compatibility before training."
    )
