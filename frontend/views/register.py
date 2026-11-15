import streamlit as st

from components.layout import page_header, show_error
from lib import auth
from lib.api_client import ApiError

page_header("Create account", "Passwords need at least 12 characters.")
with st.form("register"):
    name = st.text_input("Display name")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm = st.text_input("Confirm password", type="password")
    submitted = st.form_submit_button("Create account", type="primary")
if submitted:
    if password != confirm:
        st.error("Passwords do not match.")
    else:
        try:
            auth.register(email, password, name)
            auth.login(email, password)
            st.rerun()
        except ApiError as exc:
            show_error(exc)
