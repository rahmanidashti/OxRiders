# OxRiders: uncertainty-aware agent + evaluation dashboard

A web app with two pages:
- **Agent**: give a passage, a question and a candidate answer. The live model says whether the answer is
  right, or "I don't know" when the passage can't settle it.
- **Dashboard**: the model's evaluation results from `data/dashboard_data.json`: accuracy, abstention, calibration,
  accuracy vs coverage, baseline vs fine-tuned, and example questions.

## 1. Run it on your computer
Install Python 3.10 or newer, then in this folder:
```bash
pip install -r requirements.txt
cp .env.example .env          # then set MODEL_URL (and DASHBOARD_PASSWORD if you want a login)
uvicorn server:app --reload
```
Open http://localhost:8000.

## 2. How the agent decides
The model scores the candidate answer against the passage with three options: **True**, **False** and
**There is not enough information**. The agent answers with the more likely of True/False when that
probability is at least **60%**, and otherwise says "I don't know" (change it with `OXRIDERS_THRESHOLD`).
The rule lives in `decision.py`.

The model needs a passage: it was trained to say "not enough information" when the passage is missing.
The first request after the model has been idle takes about a minute while it starts on Modal.

## 3. Dashboard and example data
Both live in `data/`:

- **`data/dashboard_data.json`**: the evaluation results the Dashboard page shows. Keys:
  `KPIS` and `MINIS` (`label`, `value`, optional `sub`, `lead`, `tip`), `ACC_COV` (`[threshold, coverage %, accuracy %]`),
  `CALIB` (`[predicted confidence, observed accuracy]`), `MATRIX` (`answeredShould`, `answeredShouldNot`,
  `abstainedShould`, `abstainedShouldNot`), `DIST` (`label`, `value`, `color`), `MODELS` (`name`, `acc`, `unsup`, `abst`,
  `cal`, `hl` for the final model) and `EVALS` (`q`, `exp`, `dec`, `conf`, `ok`, `cat`, `why`, `ref`, `out`).
  In this file an *answer* is the model's top option (including "Not enough information"); the agent abstains when its
  confidence is below the threshold, and *should* abstain when its top option is wrong.
  Calibration points below 33% confidence are not drawn: with three options the model's top probability is never that low.
- **`data/examples.jsonl`**: the Agent page's starter questions, one model record per line (same format as
  `data/development.jsonl`). Clicking one sends that record to the model unchanged.

Replace either file and restart the app (or redeploy, section 4) to update the page.

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
`oxriders-feedback` as `feedback.jsonl`. Locally it goes to `feedback/feedback.jsonl`.

## Files
| File | What it does |
|---|---|
| `server.py` | Backend: login, page, `/api/agent`, `/api/eval`, `/api/feedback` |
| `web/index.html` | The OxRiders page (design from `candor-prototype.html`, wired to the backend) |
| `web/assets/` | Logo images made from `logo.jpeg` (sidebar, Agent page, login, browser tab) |
| `decision.py` | When to answer and when to say "I don't know" |
| `data/` | `dashboard_data.json` (Dashboard) and `examples.jsonl` (Agent starter questions) |
| `modal_dashboard.py` | Runs the app on Modal |
| `modal_app.py` | Qwen chat model server from the old dashboard (not used by the OxRiders dashboard) |
| `candor-prototype.html` | The original mock-data template, kept for reference |
| `logo.jpeg` | The OxRiders logo (source for `web/assets/`) |
