"""Simple password screen. Active only when DASHBOARD_PASSWORD is set."""
import hmac
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def require_password() -> None:
    """Stop the page until the user enters DASHBOARD_PASSWORD (once per browser session)."""
    password = os.getenv("DASHBOARD_PASSWORD", "")
    if not password or st.session_state.get("authenticated"):
        return

    st.title("🔒 My LLM App")
    with st.form("login"):
        entered = st.text_input("Password", type="password")
        if st.form_submit_button("Log in", type="primary"):
            if hmac.compare_digest(entered.encode(), password.encode()):
                st.session_state.authenticated = True
                st.rerun()
            st.error("Wrong password.")
    st.stop()
