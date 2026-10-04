# Candor: uncertainty-aware agent + evaluation dashboard

A web app with two pages:
- **Agent**: give a passage, a question and a candidate answer. The live KEV model says whether the answer is
  right, or "I don't know" when the passage can't settle it.
- **Dashboard**: KEV's real evaluation results: accuracy, abstention, calibration, accuracy vs coverage,
  base vs fine-tuned, and example questions.

## 1. Run it on your computer
Install Python 3.10 or newer, then in this folder:
```bash
pip install -r requirements.txt
cp .env.example .env          # then set KEV_MODEL_URL (and DASHBOARD_PASSWORD if you want a login)
uvicorn server:app --reload
```
Open http://localhost:8000.

## 2. How the agent decides
KEV scores the candidate answer against the passage with three options: **True**, **False** and
**There is not enough information**. Candor answers with the more likely of True/False when that
probability is at least **60%**, and otherwise says "I don't know" (change it with `CANDOR_THRESHOLD`).
The rule lives in `decision.py` and is used for both the live agent and the dashboard numbers.

KEV needs a passage: it was trained to say "not enough information" when the passage is missing.
The first request after KEV has been idle takes about a minute while it starts on Modal.

## 3. Show real evaluation results
The dashboard reads `data/eval.json`. Until it exists, the page says "No evaluation results yet".

1. **Pull the KEV run** that the live endpoint serves. The runs are on the Modal volume `kev-finetune-runs`
   in the `ili3p-ox3` workspace, so this needs someone with access to that workspace. From the repo root:
   ```bash
   modal run skills/kev-finetune/scripts/kev_modal.py::pull --name <run>
   ```
   This writes `runs/<run>/` (`result.json`, `development/rows.json`, `baseline/development/rows.json`, ...).
2. **Build the dashboard data**, from this folder:
   ```bash
   python build_eval.py --run ../runs/<run> --data ../data/development.jsonl
   ```
   `--data` must be the development file the run was scored on. The script stops with an error if
   the questions don't match.
3. Restart the app (or redeploy, section 4).

`build_eval.py` also refreshes `data/examples.json`, the starter questions on the Agent page.

## 4. Put it online (Modal)
The app runs on Modal behind the password, at `https://<workspace>--my-llm-dashboard-dashboard.modal.run`.

1. Store the settings in a Modal secret (from `.env`; add `--force` to update an existing one):
   ```bash
   modal secret create dashboard-secrets --from-dotenv .env
   ```
2. Deploy:
   ```bash
   modal deploy modal_dashboard.py
   ```
Your `.env` file is never uploaded. Feedback (👍/👎 on agent answers) is saved to the Modal volume
`candor-feedback` as `feedback.jsonl`. Locally it goes to `feedback/feedback.jsonl`.

## Files
| File | What it does |
|---|---|
| `server.py` | Backend: login, page, `/api/agent`, `/api/eval`, `/api/feedback` |
| `web/index.html` | The Candor page (design from `candor-prototype.html`, wired to the backend) |
| `decision.py` | When to answer and when to say "I don't know" |
| `build_eval.py` | Turns a pulled KEV run into `data/eval.json`, and picks `data/examples.json` |
| `data/` | Dashboard data and Agent starter questions |
| `modal_dashboard.py` | Runs the app on Modal |
| `modal_app.py` | Qwen chat model server from the old dashboard (not used by Candor) |
| `candor-prototype.html` | The original mock-data template, kept for reference |
