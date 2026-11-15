import streamlit as st

from components.layout import page_header, show_error
from lib import auth
from lib.api_client import ApiError

page_header("Sign in", "GitHub Code Intelligence")
with st.form("login"):
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    submitted = st.form_submit_button("Sign in", type="primary")
if submitted:
    try:
        auth.login(email, password)
        st.rerun()
    except ApiError as exc:
        show_error(exc)
