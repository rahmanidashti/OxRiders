"""OxRiders backend: serves the page (web/index.html), its images (web/assets) and the API it calls.

  POST /api/agent     passage + question + candidate answer -> model decision (answer or "I don't know")
  GET  /api/config    threshold and starter examples
  GET  /api/eval      evaluation results for the dashboard (data/dashboard_data.json)
  GET  /umap/...      dataset map: chart script and points from viz/dataset_umap
  POST /api/feedback  thumbs up/down on an agent response (appended to a JSONL file)

Settings (environment or .env): MODEL_URL, DASHBOARD_PASSWORD (optional login),
FEEDBACK_FILE (default feedback/feedback.jsonl), OXRIDERS_THRESHOLD (default 0.6),
UMAP_DIR (default ../viz/dataset_umap).

Run locally:  uvicorn server:app --reload
"""
import hashlib
import hmac
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from decision import CRITERIA, FALSE, IDK, THRESHOLD, TRUE, build_request, decide

load_dotenv()

HERE = Path(__file__).resolve().parent
# MODEL_URL replaces the older name KEV_MODEL_URL, which existing secrets may still use.
MODEL_URL = (os.getenv("MODEL_URL") or os.getenv("KEV_MODEL_URL", "")).strip()
PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
FEEDBACK_FILE = Path(os.getenv("FEEDBACK_FILE", HERE / "feedback" / "feedback.jsonl"))
FEEDBACK_VOLUME = os.getenv("OXRIDERS_FEEDBACK_VOLUME", "")  # set by modal_dashboard.py
EVAL_FILE = HERE / "data" / "dashboard_data.json"
EXAMPLES_FILE = HERE / "data" / "examples.jsonl"
UMAP_DIR = Path(os.getenv("UMAP_DIR", HERE.parent / "viz" / "dataset_umap"))
COOKIE = "oxriders_auth"

app = FastAPI(title="OxRiders", docs_url=None, redoc_url=None)
app.mount("/assets", StaticFiles(directory=HERE / "web" / "assets"), name="assets")
app.add_middleware(GZipMiddleware, minimum_size=1024)  # the dataset map points are ~3 MB of JSON
_feedback_lock = threading.Lock()


# ---------- login ----------

def _token():
    return hmac.new(PASSWORD.encode(), b"oxriders-session", hashlib.sha256).hexdigest()


def _authorized(request):
    return not PASSWORD or hmac.compare_digest(request.cookies.get(COOKIE, ""), _token())


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path in ("/login", "/healthz", "/favicon.ico") or path.startswith("/assets/") or _authorized(request):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not logged in"}, status_code=401)
    return RedirectResponse("/login")


LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>OxRiders – Log in</title><link rel="icon" type="image/png" href="/assets/favicon.png">
<style>
:root{--bg:#F4F5F8;--surface:#fff;--ink:#161A22;--muted:#5C6575;--line:#CDD2DB;--accent:#2447D6;--bad:#B4402F}
@media (prefers-color-scheme: dark){:root{--bg:#0E1117;--surface:#161B23;--ink:#E9ECF2;--muted:#9AA3B2;--line:#364050;--accent:#7F96FF;--bad:#F08472}}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif;padding:16px}
form{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:28px;width:min(360px,100%);display:flex;flex-direction:column;gap:12px}
h1{margin:0 0 4px;font-size:24px}p{margin:0;color:var(--muted)}
input{font:inherit;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:transparent;color:inherit}
button{font:inherit;font-weight:600;padding:10px;border:0;border-radius:10px;background:var(--accent);color:#fff;cursor:pointer}
.err{color:var(--bad)}
.logo{display:block;margin:0 auto 4px;width:200px;height:200px;border-radius:16px}
</style></head><body><form method="post" action="/login">
<img src="/assets/logo.jpg" alt="OxRiders" width="200" height="200" class="logo">
<p>Enter the password to continue.</p>
<input type="password" name="password" aria-label="Password" autofocus required>
<button type="submit">Log in</button>__ERROR__</form></body></html>"""


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return LOGIN_PAGE.replace("__ERROR__", "")


@app.post("/login")
async def login(request: Request):
    form = parse_qs((await request.body()).decode())
    entered = form.get("password", [""])[0]
    if PASSWORD and hmac.compare_digest(entered.encode(), PASSWORD.encode()):
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(COOKIE, _token(), httponly=True, samesite="lax", max_age=30 * 24 * 3600)
        return response
    return HTMLResponse(LOGIN_PAGE.replace("__ERROR__", '<p class="err">Wrong password.</p>'), status_code=401)


# ---------- page ----------

@app.get("/")
def index():
    return FileResponse(HERE / "web" / "index.html")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(HERE / "web" / "assets" / "favicon.png", media_type="image/png")


@app.get("/healthz")
def healthz():
    return {"ok": True}


QUESTION_RE = re.compile(r'Question:\s*(.*?)\s*\nIs "(.*)"', re.S)


def load_examples(path):
    """Starter questions: model records (one per line, the training-data format) plus their display text."""
    if not path.exists():
        return []
    examples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        q = record["questions"]["question"]
        header, _, passage = record["state"].partition("Context:")
        first = header.split("\n", 1)[0]
        m = QUESTION_RE.search(q["instructions"])
        # shown on the card: the question as the model reads it, candidate answer at the end
        shown = re.sub(r"^\s*Question:\s*", "", q["instructions"]).replace("\n", " ").strip()
        examples.append({
            "label": first.split("scenario:", 1)[1].strip() if "scenario:" in first else "Example",
            "passage": passage.strip(),
            "question": shown,
            "answer": m.group(2) if m else "",
            # sent to the model unchanged when the example is clicked
            "request": {"state": record["state"], "instructions": q["instructions"],
                        "criteria": q.get("criteria", CRITERIA)},
        })
    return examples


EXAMPLES = load_examples(EXAMPLES_FILE)


@app.get("/api/config")
def config():
    shown = [{k: e[k] for k in ("label", "question")} for e in EXAMPLES]  # passage and answer stay on the server
    return {"threshold": THRESHOLD, "model_configured": bool(MODEL_URL), "examples": shown}


# ---------- agent ----------

class AgentRequest(BaseModel):
    passage: str = Field(default="", max_length=20000)
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(default="", max_length=500)  # required unless `example` is given
    example: int | None = None  # index of a starter example: send its original record


def _pct(p):
    return f"{p * 100:.1f}%"


def explain(probs, threshold=THRESHOLD):
    """Turn the model's probabilities into the response card the page renders."""
    choice, confidence = decide(probs[TRUE], probs[FALSE], threshold)
    top = max(probs, key=probs.get)
    options = [{"key": k, "label": CRITERIA[k], "p": probs[k]} for k in (TRUE, FALSE, IDK)]
    if choice is not None:
        text = ("True. The passage supports this answer." if choice == TRUE
                else "False. The passage does not support this answer.")
        factors = [
            {"ok": True, "t": f"The model judged the answer {CRITERIA[choice].lower()} with {_pct(confidence)} probability"},
            {"ok": True, "t": f"Above the {_pct(threshold)} answer threshold"},
            {"ok": True, "t": f"Chance the passage lacks the information: {_pct(probs[IDK])}"},
        ]
        return {"kind": "answer", "verdict": CRITERIA[choice], "confidence": confidence,
                "text": text, "reason": None, "options": options, "factors": factors}

    if top == IDK:
        reason = "The model judged that the passage does not contain enough information to verify this answer."
    else:
        reason = (f"The model leaned {CRITERIA[top]} ({_pct(confidence)}), "
                  f"but that is below the {_pct(threshold)} answer threshold.")
    factors = [
        {"ok": False, "t": f"Best answer ({CRITERIA[TRUE if probs[TRUE] >= probs[FALSE] else FALSE]}) "
                           f"only {_pct(confidence)}, below the {_pct(threshold)} threshold"},
        {"ok": False, "t": f"Chance the passage lacks the information: {_pct(probs[IDK])}"},
    ]
    return {"kind": "abstain", "verdict": "I don't know", "confidence": confidence,
            "text": "There is not enough reliable information in the passage to answer this confidently.",
            "reason": reason, "options": options, "factors": factors}


@app.post("/api/agent")
def agent(req: AgentRequest):
    if not MODEL_URL:
        raise HTTPException(503, "MODEL_URL is not set")
    try:
        if req.example is not None and 0 <= req.example < len(EXAMPLES):
            payload = EXAMPLES[req.example]["request"]
        elif req.answer.strip():
            payload = build_request(req.passage, req.question, req.answer)
        else:
            raise HTTPException(422, "A candidate answer is required")
        r = requests.post(MODEL_URL, json=payload, timeout=300)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        raise HTTPException(502, f"Could not reach the model: {e}")
    if "error" in data or "probabilities" not in data:
        raise HTTPException(502, f"The model returned an error: {data.get('error', 'no probabilities')}")
    probs = {k: float(data["probabilities"].get(k, 0.0)) for k in (TRUE, FALSE, IDK)}
    return explain(probs)


# ---------- evaluation ----------

@app.get("/api/eval")
def evaluation():
    if not EVAL_FILE.exists():
        return {"available": False}
    return {"available": True, **json.loads(EVAL_FILE.read_text())}


# ---------- dataset map ----------

def _umap_file(name, media_type):
    path = UMAP_DIR / name
    if not path.is_file():
        raise HTTPException(404, f"Dataset map file not found: {name}")
    return FileResponse(path, media_type=media_type)


@app.get("/umap/umap-scatter.js")
def umap_script():
    return _umap_file("umap-scatter.js", "text/javascript")


@app.get("/umap/points.json")
def umap_points():
    return _umap_file("points.json", "application/json")


# ---------- feedback ----------

class Feedback(BaseModel):
    passage: str = Field(default="", max_length=20000)
    question: str = Field(max_length=2000)
    answer: str = Field(default="", max_length=500)
    example: int | None = None  # starter example the feedback is about, if any
    decision: str = Field(max_length=40)
    confidence: float
    feedback: str = Field(pattern="^(correct|incorrect|should-yes|should-no)$")


@app.post("/api/feedback")
def feedback(item: Feedback):
    record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **item.model_dump()}
    with _feedback_lock:
        FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if FEEDBACK_VOLUME:  # on Modal: persist the write to the volume right away
            import modal
            modal.Volume.from_name(FEEDBACK_VOLUME).commit()
    return {"ok": True}
