"""Hosts this Streamlit app on Modal so it is reachable from anywhere.

Settings (model URLs, keys, DASHBOARD_PASSWORD) come from the Modal secret
"dashboard-secrets"; the local .env file is never uploaded.

Deploy:  modal deploy modal_dashboard.py
"""
import subprocess
from pathlib import Path

import modal

HERE = Path(__file__).parent
REMOTE_DIR = "/root/dashboard"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(HERE / "requirements.txt"))
    .add_local_dir(
        HERE,
        REMOTE_DIR,
        ignore=[".env", ".env.*", ".venv", "**/__pycache__", ".DS_Store", ".streamlit/secrets.toml"],
    )
)

app = modal.App("my-llm-dashboard")


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("dashboard-secrets")],
    # One container: Streamlit keeps each visitor's session in memory.
    max_containers=1,
    scaledown_window=15 * 60,
)
@modal.concurrent(max_inputs=100)
@modal.web_server(port=8000, startup_timeout=60)
def dashboard():
    subprocess.Popen(
        [
            "streamlit", "run", "app.py",
            "--server.port", "8000",
            "--server.address", "0.0.0.0",
            "--server.headless", "true",
            "--server.enableCORS", "false",
            "--server.enableXsrfProtection", "false",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=REMOTE_DIR,
    )
