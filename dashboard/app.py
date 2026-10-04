import streamlit as st

st.set_page_config(page_title="My LLM App", page_icon="🤖", layout="wide")

pages = [
    st.Page("pages/chat.py", title="Chat", icon="💬", default=True),
    st.Page("pages/dashboard.py", title="Dashboard", icon="📊"),
]
st.navigation(pages).run()
