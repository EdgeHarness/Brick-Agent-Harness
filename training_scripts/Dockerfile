# Experimental tool-calling LoRA training image.
# Building requires network access, compatible container/GPU tooling, and
# enough storage for dependencies, a model snapshot, and llama.cpp. A built
# image may support a later network-isolated run, but that path still requires
# local compatibility, artifact-integrity, and training-data review.
FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY train_lora.py download_assets.py make_data.py system_prompt.txt ./

# Generate the experimental synthetic data, then fetch model + llama.cpp.
# Neither the labels nor the downloaded artifacts are validated by this build.
RUN mkdir -p data && python make_data.py --out data/toolcall.jsonl
RUN python download_assets.py
ENV LLAMACPP_DIR=/workspace/assets/llama.cpp
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

# Defaults attempt to produce a PEFT adapter and GGUF conversion. Pass flags
# after the image name to override; mount /workspace/out to retain artifacts.
ENTRYPOINT ["python", "train_lora.py"]
CMD ["--to-gguf"]
