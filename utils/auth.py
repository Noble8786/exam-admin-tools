"""
Username + password login, roles, and page access control.
"""

from __future__ import annotations

import streamlit as st

from core.users_db import (
    User,
    authenticate,
    change_own_password,
    init_db,
    user_has_feature,
)


def _load_user_from_session() -> User | None:
    data = st.session_state.get("user")
    if not data:
        return None
    return User(
        id=data["id"],
        username=data["username"],
        full_name=data["full_name"],
        is_admin=data["is_admin"],
        is_active=data["is_active"],
        must_change_password=data["must_change_password"],
        permissions=data["permissions"],
    )


def _save_user_to_session(user: User) -> None:
    st.session_state["authenticated"] = True
    st.session_state["user"] = {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "permissions": user.permissions,
    }


def current_user() -> User | None:
    if not st.session_state.get("authenticated"):
        return None
    return _load_user_from_session()


def require_login() -> User:
    """
    Show login form if needed. Returns the logged-in user.
    Also forces password change when admin reset the password.
    """
    init_db()

    user = current_user()
    if user is None:
        st.markdown("## 🔒 Exam & Admin Tools")
        st.caption("Sign in with your username and password")

        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", type="primary")

            if submitted:
                user = authenticate(username, password)
                if user is None:
                    st.error("Invalid username or password, or account is disabled.")
                else:
                    _save_user_to_session(user)
                    st.rerun()

        st.stop()

    # Forced password change
    if user.must_change_password:
        st.warning("You must change your password before continuing.")
        with st.form("force_change_password"):
            current_pw = st.text_input("Current password", type="password")
            new_pw = st.text_input("New password", type="password")
            new_pw2 = st.text_input("Confirm new password", type="password")
            if st.form_submit_button("Change password", type="primary"):
                if new_pw != new_pw2:
                    st.error("New passwords do not match.")
                else:
                    ok, msg = change_own_password(user.id, current_pw, new_pw)
                    if ok:
                        user.must_change_password = False
                        _save_user_to_session(user)
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        st.stop()

    return user


def require_feature(feature_key: str) -> User:
    """Login + check permission for a feature page."""
    user = require_login()
    if not user_has_feature(user, feature_key):
        st.error("You do not have permission to access this tool.")
        st.info("Contact the administrator if you need access.")
        st.stop()
    return user


def show_logout_button() -> None:
    user = current_user()
    if not user:
        return
    with st.sidebar:
        label = user.full_name or user.username
        st.caption(f"Signed in as **{label}**")
        if user.is_admin:
            st.caption("Role: Administrator")
        if st.button("Log out"):
            for key in ("authenticated", "user"):
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()


def show_change_password_sidebar() -> None:
    """Small expander so any user can change their password."""
    user = current_user()
    if not user:
        return
    with st.sidebar:
        with st.expander("Change my password"):
            with st.form("sidebar_change_pw"):
                cur = st.text_input("Current password", type="password", key="cp_cur")
                new = st.text_input("New password", type="password", key="cp_new")
                new2 = st.text_input("Confirm new password", type="password", key="cp_new2")
                if st.form_submit_button("Update password"):
                    if new != new2:
                        st.error("Passwords do not match.")
                    else:
                        ok, msg = change_own_password(user.id, cur, new)
                        if ok:
                            user.must_change_password = False
                            _save_user_to_session(user)
                            st.success(msg)
                        else:
                            st.error(msg)
