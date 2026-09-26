"""
Admin-only: create users, assign tool access, reset passwords.
"""

from __future__ import annotations

import streamlit as st

from core.users_db import (
    FEATURES,
    create_user,
    delete_user,
    list_users,
    reset_password,
    update_user_permissions,
)
from utils.auth import require_feature
from utils.theme import apply_theme, show_sidebar_branding

st.set_page_config(page_title="User Management", page_icon="👤", layout="wide")

apply_theme()
admin = require_feature("user_management")
show_sidebar_branding()

st.title("👤 User Management")
st.caption("Admin only — create users, assign tools, reset passwords.")

# ------------------------------------------------------------------
# Create user
# ------------------------------------------------------------------
st.subheader("Create new user")

with st.form("create_user_form"):
    c1, c2 = st.columns(2)
    with c1:
        new_username = st.text_input("Username")
        new_full_name = st.text_input("Full name")
        new_password = st.text_input("Temporary password", type="password")
    with c2:
        is_admin = st.checkbox("Administrator (full access)")
        st.markdown("**Tools this user can access**")
        perm_exam = st.checkbox("Exam Grouping", value=True)
        perm_appt = st.checkbox("Appointment Letters", value=False)
        perm_map = st.checkbox("Mapping Converter", value=False)

    if st.form_submit_button("Create user", type="primary"):
        perms = []
        if perm_exam:
            perms.append("exam_grouping")
        if perm_appt:
            perms.append("appointment_letters")
        if perm_map:
            perms.append("mapping_converter")
        if is_admin:
            perms = list(FEATURES.keys())

        ok, msg = create_user(
            username=new_username,
            full_name=new_full_name,
            password=new_password,
            is_admin=is_admin,
            permissions=perms,
            must_change_password=True,
        )
        if ok:
            st.success(msg + " User must change password on first login.")
            st.rerun()
        else:
            st.error(msg)

st.divider()

# ------------------------------------------------------------------
# Existing users
# ------------------------------------------------------------------
st.subheader("Existing users")

users = list_users()
if not users:
    st.info("No users found.")
else:
    for u in users:
        with st.expander(f"{u.username}  —  {u.full_name or '(no name)'}{'  [ADMIN]' if u.is_admin else ''}"):
            st.write(f"**Active:** {'Yes' if u.is_active else 'No'}")
            st.write(
                "**Tools:** "
                + (", ".join(FEATURES.get(p, p) for p in u.permissions) if u.permissions else "None")
            )

            st.markdown("#### Edit access")
            full_name = st.text_input("Full name", value=u.full_name, key=f"fn_{u.id}")
            is_admin_e = st.checkbox("Administrator", value=u.is_admin, key=f"adm_{u.id}")
            is_active_e = st.checkbox("Active", value=u.is_active, key=f"act_{u.id}")
            pe = st.checkbox("Exam Grouping", value="exam_grouping" in u.permissions, key=f"pe_{u.id}")
            pa = st.checkbox("Appointment Letters", value="appointment_letters" in u.permissions, key=f"pa_{u.id}")
            pm = st.checkbox("Mapping Converter", value="mapping_converter" in u.permissions, key=f"pm_{u.id}")

            if st.button("Save changes", key=f"save_{u.id}"):
                perms = []
                if pe:
                    perms.append("exam_grouping")
                if pa:
                    perms.append("appointment_letters")
                if pm:
                    perms.append("mapping_converter")
                ok, msg = update_user_permissions(
                    user_id=u.id,
                    is_admin=is_admin_e,
                    permissions=perms,
                    is_active=is_active_e,
                    full_name=full_name,
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            st.markdown("#### Reset password")
            new_pw = st.text_input("New temporary password", type="password", key=f"rpw_{u.id}")
            if st.button("Reset password", key=f"reset_{u.id}"):
                ok, msg = reset_password(u.id, new_pw, force_change=True)
                if ok:
                    st.success(msg + " User must change it on next login.")
                else:
                    st.error(msg)

            st.markdown("#### Delete user")
            if st.button("Delete this user", key=f"del_{u.id}"):
                ok, msg = delete_user(u.id, acting_admin_id=admin.id)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
