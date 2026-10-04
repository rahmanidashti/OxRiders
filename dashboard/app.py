import streamlit as st

from auth import require_password

st.set_page_config(page_title="My LLM App", page_icon="🤖", layout="wide")
require_password()

pages = [
    st.Page("pages/chat.py", title="Chat", icon="💬", default=True),
    st.Page("pages/verify.py", title="Verify", icon="✅"),
    st.Page("pages/dashboard.py", title="Dashboard", icon="📊"),
]
st.navigation(pages).run()
