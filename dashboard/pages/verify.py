import pandas as pd
import plotly.express as px
import streamlit as st

from model_client import KEV_MODEL_URL, predict

st.title("✅ Verify")
st.caption("Give the model a finding and a question; it picks one of the answer options.")

if not KEV_MODEL_URL:
    st.info("No verify model connected. Set `KEV_MODEL_URL` in `.env` (see README).")

state = st.text_area(
    "State (the finding or context)",
    "Biomedical finding: Active OR genes increased contacts by 2.7-fold in mouse olfactory neurons.",
)
instructions = st.text_area(
    "Instructions (the question)",
    "Question: By what factor did active OR genes increase contacts in mouse olfactory neurons?\n"
    'Is "2.7 fold" the correct answer?',
)

st.markdown("**Answer options**")
options = st.data_editor(
    pd.DataFrame({
        "letter": ["A", "B", "C"],
        "meaning": ["True", "False", "There is not enough information"],
    }),
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
)

if st.button("Predict", type="primary", disabled=not KEV_MODEL_URL):
    criteria = {
        str(row.letter).strip(): str(row.meaning).strip()
        for row in options.dropna().itertuples()
        if str(row.letter).strip()
    }
    with st.spinner("Asking the model... the first call can take about a minute while it starts."):
        try:
            result = predict(state, instructions, criteria)
        except Exception as e:
            st.error(f"⚠️ Could not reach the model: {e}")
            st.stop()

    left, right = st.columns(2)
    left.metric("Prediction", f"{result['prediction']}: {result['label_meaning']}")
    right.metric("Confidence", f"{result['confidence']:.1%}")

    probs = pd.DataFrame(
        [{"option": f"{k}: {criteria.get(k, '')}", "probability": v}
         for k, v in result["probabilities"].items()]
    )
    fig = px.bar(probs, x="probability", y="option", orientation="h", text_auto=".1%",
                 range_x=[0, 1])
    fig.update_layout(yaxis_title=None)
    st.plotly_chart(fig, width="stretch")

    with st.expander("Raw response"):
        st.json(result)
