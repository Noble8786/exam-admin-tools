"""
Shared theme and sidebar branding for all pages.
College colours:
  Blue   #007CC2
  Maroon #8F2925
  Gold   #F3AC02
  Brown  #8F652B
  Green  #2BA550
"""

from pathlib import Path

import streamlit as st

from utils.auth import show_logout_button, show_change_password_sidebar


def apply_theme() -> None:
    """Inject CSS so sidebar and main area look consistent on every page."""
    st.markdown(
        """
        <style>
        /* ---------- Sidebar ---------- */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #007CC2 0%, #005A8F 100%);
        }
        [data-testid="stSidebar"] * {
            color: #FFFFFF !important;
        }
        [data-testid="stSidebar"] a {
            color: #FFFFFF !important;
        }
        [data-testid="stSidebar"] .stMarkdown p,
        [data-testid="stSidebar"] .stCaption {
            color: #E8F4FC !important;
        }
        /* Active menu item – gold accent */
        [data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-selected="true"] {
            background-color: rgba(243, 172, 2, 0.25);
            border-left: 4px solid #F3AC02;
        }
        /* Hover */
        [data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover {
            background-color: rgba(255, 255, 255, 0.12);
        }

        /* ---------- Main area ---------- */
        .stApp {
            background-color: #F5F9FC;
        }

        /* Primary buttons – college blue */
        .stButton > button[kind="primary"] {
            background-color: #007CC2;
            border-color: #007CC2;
            color: white;
        }
        .stButton > button[kind="primary"]:hover {
            background-color: #005A8F;
            border-color: #005A8F;
            color: white;
        }

        /* Metrics */
        div[data-testid="stMetricValue"] {
            color: #007CC2;
        }

        /* Success green accent */
        .stSuccess {
            border-left-color: #2BA550 !important;
        }

        /* Warning / gold */
        .stWarning {
            border-left-color: #F3AC02 !important;
        }

        /* Error / maroon */
        .stError {
            border-left-color: #8F2925 !important;
        }

        .stAlert {
            border-radius: 8px;
        }

        /* Keep logo compact */
        [data-testid="stSidebar"] img {
            max-width: 160px !important;
            height: auto !important;
            margin: 0.4rem auto 0.6rem auto;
            display: block;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_sidebar_branding() -> None:
    """
    Show college logo at the TOP of the sidebar, then a short caption.
    Looks for logo in several common places.
    """
    logo_candidates = [
        Path("assets/logo.png"),
        Path("logo.png"),
        Path.home() / ".exam_admin_tools" / "assets" / "logo.png",
    ]
    logo_path = next((p for p in logo_candidates if p.exists()), None)

    with st.sidebar:
        if logo_path:
            st.image(str(logo_path), width=150)
        else:
            st.markdown("### Exam & Admin Tools")
        st.caption("St. Berchmans College")
        st.markdown("---")
    show_logout_button()
    show_change_password_sidebar()
