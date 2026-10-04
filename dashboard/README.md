# My LLM App: Chat + Fine-tuning Dashboard

A simple Python app (Streamlit) with two pages:
- **Chat**: a ChatGPT-style chat with your model (switch between base and fine-tuned).
- **Dashboard**: training loss curves and before/after fine-tuning results.

## 1. Run it on your computer
Install Python 3.10 or newer, then in this folder run:
```bash
pip install -r requirements.txt
streamlit run app.py
```
Your browser opens at http://localhost:8501. Until you connect a real model, the chat uses a **demo model**.

## 2. Connect to Modal (exact steps)

**A. Create a Modal account**
1. Go to https://modal.com and sign up (you can use GitHub or Google).

**B. Open a terminal inside the project folder**
- Windows: open the `llm-chat-dashboard` folder in File Explorer, click the address bar, type `cmd`, press Enter.
- Mac: right-click the `llm-chat-dashboard` folder in Finder > Services > "New Terminal at Folder".

**C. Install Modal and log in** (paste each line into the terminal, then press Enter)
```bash
pip install modal
modal setup
```
A browser window opens. Click to approve it. The terminal then says it is logged in.

**D. Create your secret on the Modal website**
1. On modal.com, click **Secrets** (left menu), then **Create new secret**, then **Custom**.
2. Add a key `MODEL_API_KEY` with a value you make up (a password, e.g. `leila-secret-123`).
3. (Only if your Hugging Face model is private) click "Add another" and add `HF_TOKEN` = your token from https://huggingface.co/settings/tokens
4. Name the secret exactly `llm-secrets` and click **Create**.

**E. Deploy the model**
```bash
modal deploy modal_app.py
```
Wait for it to finish (the first time takes a few minutes). It prints a web address like
`https://YOURNAME--my-llm-serve.modal.run`. Copy it.

By default this runs the public model `Qwen/Qwen2.5-1.5B-Instruct`. After fine-tuning, open `modal_app.py`,
set `BASE_MODEL` to your original model and `LORA_ADAPTER` to your adapter on Hugging Face, then run `modal deploy modal_app.py` again.

**F. Check that it works** (optional; replace the address and password with yours)
```bash
curl https://YOURNAME--my-llm-serve.modal.run/v1/models -H "Authorization: Bearer leila-secret-123"
```
The first time can take 1-3 minutes while the model starts. A reply listing `base` and `finetuned` means it works.

## 3. Connect the app to Modal
1. In the project folder, make a copy of `.env.example` and name the copy `.env`.
2. Open `.env` in a text editor (Notepad / TextEdit) and fill in the address from step E **with `/v1` added at the end**, plus your password:
```
MODEL_BASE_URL=https://YOURNAME--my-llm-serve.modal.run/v1
MODEL_API_KEY=leila-secret-123
```
3. Save the file. In the terminal, stop the app (Ctrl+C) if it is running, then start it again:
```bash
streamlit run app.py
```
The blue "Demo mode" box is gone, and the chat now uses your model on Modal.

Costs: Modal only charges while the model is running. It shuts down by itself after 15 minutes without use.
The first message after that takes 1-3 minutes while it starts again.

## 4. Show your real training results
- **Loss curves**: add `DashboardLogger` from `metrics/hf_callback.py` to your trainer. It writes `metrics/training_log.json`.
- **Before/after scores**: edit `metrics/eval_results.json` with your own numbers and example answers.

## Files
| File | What it does |
|---|---|
| `app.py` | Starts the app and the page menu |
| `pages/chat.py` | Chat page |
| `pages/dashboard.py` | Dashboard page |
| `model_client.py` | Connects to the model (or the demo model) |
| `modal_app.py` | Runs your model on Modal |
| `metrics/` | Training and evaluation data shown in the dashboard |
