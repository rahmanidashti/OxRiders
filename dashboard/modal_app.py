"""Serves your model on Modal with vLLM (OpenAI-compatible API).

Serves two models from one URL:
  - "base"       -> the original model
  - "finetuned"  -> the same model + your LoRA adapter from fine-tuning

Deploy:  modal deploy modal_app.py
"""
import subprocess

import modal

# ---- Change these to your models ------------------------------------------
BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"    # model on Hugging Face you fine-tuned
# Your fine-tuned LoRA adapter on Hugging Face, e.g. "your-hf-username/your-lora".
# Leave empty ("") until fine-tuning is done: both choices in the app will use the base model.
LORA_ADAPTER = ""
GPU = "A10G"
# ---------------------------------------------------------------------------

image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "vllm==0.9.1", "huggingface_hub[hf_transfer]"
).env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})

hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
app = modal.App("my-llm")


@app.function(
    image=image,
    gpu=GPU,
    volumes={"/root/.cache/huggingface": hf_cache},
    # Create in Modal dashboard: secret "llm-secrets" with MODEL_API_KEY (and HF_TOKEN if private)
    secrets=[modal.Secret.from_name("llm-secrets")],
    scaledown_window=15 * 60,
    timeout=24 * 60 * 60,
)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=8000, startup_timeout=15 * 60)
def serve():
    import os

    from huggingface_hub import snapshot_download

    cmd = ["vllm", "serve", BASE_MODEL, "--host", "0.0.0.0", "--port", "8000",
           "--api-key", os.environ["MODEL_API_KEY"]]
    if LORA_ADAPTER:
        lora_path = snapshot_download(LORA_ADAPTER)
        cmd += ["--served-model-name", "base",
                "--enable-lora", "--lora-modules", f"finetuned={lora_path}"]
    else:
        cmd += ["--served-model-name", "base", "finetuned"]
    subprocess.Popen(cmd)
