"""Streamlit entrypoint: navigation depends on whether (and as whom) the user is signed in."""

import streamlit as st

from components.layout import sidebar
from lib import auth
from lib.permissions import can_view_evaluation

st.set_page_config(page_title="GitHub Code Intelligence", page_icon="🔍", layout="wide")

user = auth.current_user()
if user is None:
    pages = [
        st.Page("views/login.py", title="Sign in", icon="🔑", url_path="login", default=True),
        st.Page("views/register.py", title="Create account", icon="📝", url_path="register"),
    ]
else:
    pages = {
        "Workspace": [
            st.Page("views/dashboard.py", title="Dashboard", icon="🏠", url_path="dashboard", default=True),
            st.Page("views/github.py", title="GitHub", icon="🔗", url_path="github"),
            st.Page("views/repository.py", title="Repository", icon="📂", url_path="repository"),
            st.Page("views/review.py", title="Review & propose", icon="🧪", url_path="review"),
            st.Page("views/approvals.py", title="Approvals", icon="✅", url_path="approvals"),
            st.Page("views/history.py", title="History", icon="🕘", url_path="history"),
        ]
    }
    if can_view_evaluation(user):
        pages["Evaluation"] = [
            st.Page("views/recruiter/overview.py", title="Overview", icon="📊", url_path="recruiter-overview"),
            st.Page("views/recruiter/runs.py", title="Runs", icon="🏃", url_path="recruiter-runs"),
            st.Page("views/recruiter/quality.py", title="Quality", icon="🎯", url_path="recruiter-quality"),
            st.Page("views/recruiter/safety.py", title="Safety", icon="🛡️", url_path="recruiter-safety"),
            st.Page("views/recruiter/failures.py", title="Failures", icon="🧯", url_path="recruiter-failures"),
            st.Page("views/recruiter/model_comparison.py", title="Model comparison", icon="⚖️", url_path="recruiter-models"),
        ]
    sidebar(user)

st.navigation(pages).run()
