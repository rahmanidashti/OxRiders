"""Hosts the OxRiders dashboard (server.py + web/index.html) on Modal so it is reachable from anywhere.

Settings (MODEL_URL, DASHBOARD_PASSWORD) come from the Modal secret "dashboard-secrets";
the local .env file is never uploaded. Feedback is stored on the Modal volume "oxriders-feedback".

Deploy:  modal deploy modal_dashboard.py
"""
from pathlib import Path

import modal

HERE = Path(__file__).parent
REMOTE_DIR = "/root/dashboard"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(HERE / "requirements.txt"))
    .env({"FEEDBACK_FILE": "/feedback/feedback.jsonl", "OXRIDERS_FEEDBACK_VOLUME": "oxriders-feedback"})
    .add_local_dir(
        HERE,
        REMOTE_DIR,
        ignore=[".env", ".env.*", ".venv", "**/__pycache__", ".DS_Store", "feedback", "candor-prototype.html", "logo.jpeg"],
    )
)

feedback = modal.Volume.from_name("oxriders-feedback", create_if_missing=True)
app = modal.App("my-llm-dashboard")


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("dashboard-secrets")],
    volumes={"/feedback": feedback},
    scaledown_window=15 * 60,
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def dashboard():
    import sys

    sys.path.insert(0, REMOTE_DIR)
    from server import app as web_app

    return web_app
