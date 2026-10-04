"""Talks to the models.

Chat: OpenAI-compatible model at MODEL_BASE_URL (fake demo model until it is set).
Verify: multiple-choice predictor at KEV_MODEL_URL.
"""
import os
import time
from typing import Iterator

import requests
from dotenv import load_dotenv

load_dotenv()

KEV_MODEL_URL = os.getenv("KEV_MODEL_URL", "").strip()
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL", "").strip()
MODEL_API_KEY = os.getenv("MODEL_API_KEY", "not-needed")
MODEL_NAMES = {
    "Base model": os.getenv("BASE_MODEL_NAME", "base"),
    "Fine-tuned model": os.getenv("FINETUNED_MODEL_NAME", "finetuned"),
}


def is_demo_mode() -> bool:
    return not MODEL_BASE_URL


def _demo_stream(messages: list[dict], model_label: str) -> Iterator[str]:
    question = messages[-1]["content"]
    reply = (
        f"(Demo reply from the **{model_label}**.)\n\n"
        f"You asked: _{question}_\n\n"
        "When you deploy your model on Modal and set `MODEL_BASE_URL`, "
        "real answers will appear here."
    )
    for word in reply.split(" "):
        yield word + " "
        time.sleep(0.03)


def stream_reply(messages: list[dict], model_label: str, temperature: float = 0.7) -> Iterator[str]:
    if is_demo_mode():
        yield from _demo_stream(messages, model_label)
        return

    from openai import OpenAI

    client = OpenAI(base_url=MODEL_BASE_URL, api_key=MODEL_API_KEY)
    stream = client.chat.completions.create(
        model=MODEL_NAMES[model_label],
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def predict(state: str, instructions: str, criteria: dict[str, str]) -> dict:
    """Ask the KEV model to pick one of `criteria` (e.g. {"A": "True", "B": "False"}).

    Returns the endpoint's JSON: prediction, label_meaning, confidence, probabilities, ...
    The first call after the model has been idle can take about a minute while it starts.
    """
    if not KEV_MODEL_URL:
        raise RuntimeError("KEV_MODEL_URL is not set in .env")
    response = requests.post(
        KEV_MODEL_URL,
        json={"state": state, "instructions": instructions, "criteria": criteria},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()
