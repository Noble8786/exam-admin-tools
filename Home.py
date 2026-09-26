"""
Main entry point – Home page.
Run with:  streamlit run Home.py
"""

import streamlit as st

from utils.theme import apply_theme, show_sidebar_branding
from utils.auth import require_login, current_user
from core.users_db import FEATURES, user_has_feature

st.set_page_config(
    page_title="Exam & Admin Tools",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()
require_login()
show_sidebar_branding()

user = current_user()

st.title("🏠 Home")
st.markdown(
    """
    Welcome to the **Exam & Admin Tools** internal toolkit.

    Use the **sidebar** on the left to open the tools assigned to you.
    """
)

rows = []
if user and user_has_feature(user, "exam_grouping"):
    rows.append(("**Exam Grouping**", "Combine student Excel files and generate conflict-free exam groups"))
if user and user_has_feature(user, "appointment_letters"):
    rows.append(("**Appointment Letters**", "Generate Question Bank appointment orders (PDF) and email them"))
if user and user_has_feature(user, "mapping_converter"):
    rows.append(("**Mapping Converter**", "Convert source mapping files into the required template format"))
if user and user_has_feature(user, "user_management"):
    rows.append(("**User Management**", "Create users, assign tools, reset passwords (Admin)"))

if rows:
    table = "| Feature | Description |\n|---------|-------------|\n"
    for a, b in rows:
        table += f"| {a} | {b} |\n"
    st.markdown(table)
else:
    st.warning("No tools are assigned to your account. Contact the administrator.")

st.info("Select a feature from the sidebar to get started.")

st.markdown("---")
st.caption("St. Berchmans College (Autonomous) · Internal use only")
