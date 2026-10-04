import streamlit as st

from model_client import MODEL_NAMES, is_demo_mode, stream_reply

st.title("💬 Chat")

with st.sidebar:
    model_label = st.radio("Model", list(MODEL_NAMES), index=1)
    temperature = st.slider("Creativity (temperature)", 0.0, 1.5, 0.7, 0.1)
    system_prompt = st.text_area("System prompt", "You are a helpful assistant.")
    if st.button("🗑️ New chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

if is_demo_mode():
    st.info("Demo mode: no real model connected yet. See README to connect your Modal model.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask me anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    history = [{"role": "system", "content": system_prompt}] + st.session_state.messages
    with st.chat_message("assistant"):
        try:
            answer = st.write_stream(stream_reply(history, model_label, temperature))
        except Exception as e:
            answer = f"⚠️ Could not reach the model: {e}"
            st.error(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})
