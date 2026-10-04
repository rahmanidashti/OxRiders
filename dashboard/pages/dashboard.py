import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

METRICS_DIR = Path(__file__).resolve().parent.parent / "metrics"

st.title("📊 Fine-tuning Dashboard")


@st.cache_data
def load_json(name: str):
    return json.loads((METRICS_DIR / name).read_text())


training = pd.DataFrame(load_json("training_log.json"))
evals = load_json("eval_results.json")
metrics = evals["metrics"]

st.caption(evals.get("note", ""))

# Summary cards
cols = st.columns(len(metrics))
for col, m in zip(cols, metrics):
    delta = m["finetuned"] - m["base"]
    col.metric(
        m["name"],
        f"{m['finetuned']:g}",
        f"{delta:+.2f} vs base",
        delta_color="normal" if m.get("higher_is_better", True) else "inverse",
    )

st.divider()

# Loss curves
left, right = st.columns(2)
with left:
    st.subheader("Loss during training")
    loss_df = training.melt(
        id_vars="step", value_vars=["train_loss", "eval_loss"], var_name="type", value_name="loss"
    ).dropna()
    fig = px.line(loss_df, x="step", y="loss", color="type", markers=False)
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader("Learning rate")
    st.plotly_chart(px.line(training, x="step", y="learning_rate"), use_container_width=True)

# Before vs after
st.subheader("Before vs after fine-tuning")
bar_df = pd.DataFrame(
    [{"metric": m["name"], "model": "Base", "score": m["base"]} for m in metrics]
    + [{"metric": m["name"], "model": "Fine-tuned", "score": m["finetuned"]} for m in metrics]
)
fig = px.bar(bar_df, x="metric", y="score", color="model", barmode="group", text_auto=True)
st.plotly_chart(fig, use_container_width=True)

# Example answers
st.subheader("Example answers")
for ex in evals.get("examples", []):
    with st.expander(ex["prompt"]):
        a, b = st.columns(2)
        a.markdown("**Base model**")
        a.write(ex["base"])
        b.markdown("**Fine-tuned model**")
        b.write(ex["finetuned"])
