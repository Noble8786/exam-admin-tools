"""
Appointment Letter Generation – Streamlit page.
Currently supports Question Bank Setting appointment orders.
"""

import io
import shutil
import tempfile
from pathlib import Path

import streamlit as st
import pandas as pd

from utils.theme import apply_theme, show_sidebar_branding
from utils.auth import require_feature
from core.appointment_letters import (
    generate_question_bank_appointments,
    get_next_appointment_number,
    reset_appointment_counter,
    get_saved_logo_path,
    get_saved_signature_path,
    save_logo,
    save_signature,
    clear_logo,
    clear_signature,
    send_appointment_emails,
)

st.set_page_config(page_title="Appointment Letters", page_icon="📝", layout="wide")

apply_theme()
require_feature("appointment_letters")
show_sidebar_branding()

st.title("📝 Appointment Letter Generation")
st.markdown(
    """
    Generate **Question Bank Setting** appointment orders as individual PDFs.
    Other letter types (Chairman, Paper Valuation, etc.) will be added later.
    """
)

# ------------------------------------------------------------------
# Letter type selector (ready for future expansion)
# ------------------------------------------------------------------
letter_type = st.selectbox(
    "Select Appointment Type",
    options=["Question Bank Setting"],
    help="More types (Chairman, Paper Valuation …) will appear here later.",
)

st.divider()

# ------------------------------------------------------------------
# Automatic continuous numbering
# ------------------------------------------------------------------
st.subheader("Appointment Numbering (Automatic)")

next_num = get_next_appointment_number()
col_num, col_reset = st.columns([3, 1])
with col_num:
    st.info(f"**Next appointment number will start from:** `{next_num:04d}`")
with col_reset:
    if st.button("Reset Counter to 0001", help="Only use this if you want to start numbering from 1 again"):
        reset_appointment_counter()
        st.rerun()

st.caption("Numbers continue automatically across different Excel files and different days.")

st.divider()

# ------------------------------------------------------------------
# Logo & Signature management (persistent)
# ------------------------------------------------------------------
st.subheader("Logo & Signature (saved permanently)")

logo_path = get_saved_logo_path()
sign_path = get_saved_signature_path()

col_l, col_s = st.columns(2)

with col_l:
    if logo_path:
        st.success("Logo is saved")
        st.image(str(logo_path), width=250)
        if st.button("Remove Logo"):
            clear_logo()
            st.rerun()
    else:
        st.warning("No logo saved yet")
    new_logo = st.file_uploader("Upload / Replace Logo", type=["png", "jpg", "jpeg"], key="logo_up")
    if new_logo is not None:
        save_logo(new_logo.getbuffer())
        st.success("Logo saved!")
        st.rerun()

with col_s:
    if sign_path:
        st.success("Signature is saved")
        st.image(str(sign_path), width=200)
        if st.button("Remove Signature"):
            clear_signature()
            st.rerun()
    else:
        st.warning("No signature saved yet")
    new_sign = st.file_uploader("Upload / Replace Signature", type=["png", "jpg", "jpeg"], key="sign_up")
    if new_sign is not None:
        save_signature(new_sign.getbuffer())
        st.success("Signature saved!")
        st.rerun()

st.caption("Upload once. They will be used automatically every time. You can replace them whenever the Controller changes.")

st.divider()

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
st.subheader("Settings")

col1, col2, col3 = st.columns(3)
with col1:
    prefix = st.text_input("Appointment Prefix", value="SBCE")
with col2:
    year = st.number_input("Year", min_value=2020, max_value=2035, value=2026)
with col3:
    deadline = st.text_input("Deadline", value="31 August 2026")

col4, col5 = st.columns(2)
with col4:
    portal_link = st.text_input(
        "Question Bank Portal Link",
        value="https://qnsmarti.qbanksbcollege.in",
    )
with col5:
    signatory = st.text_input("Signatory", value="Controller of Examinations")

max_rows = st.slider(
    "Max courses per PDF (one-page limit)",
    min_value=5,
    max_value=20,
    value=12,
    help="Teachers with more courses than this will be skipped and listed in a log.",
)

st.divider()

# ------------------------------------------------------------------
# File upload
# ------------------------------------------------------------------
st.subheader("Upload Excel File")

excel_file = st.file_uploader(
    "Excel file (Course Code | Course Name | Chief Examiner | Examiner 1 | Examiner 2 | Examiner 3)",
    type=["xlsx", "xlsm", "xls"],
    key="excel",
)

st.divider()

# ------------------------------------------------------------------
# Generate button
# ------------------------------------------------------------------
run_btn = st.button("🚀 Generate Appointment Orders", type="primary", use_container_width=True)

if run_btn:
    if excel_file is None:
        st.error("Please upload an Excel file.")
        st.stop()

    with st.spinner("Generating appointment orders… please wait."):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            excel_path = tmp / excel_file.name
            excel_path.write_bytes(excel_file.getbuffer())

            # Use saved logo / signature if available
            logo_path = get_saved_logo_path()
            signature_path = get_saved_signature_path()

            output_dir = tmp / "output"

            try:
                result = generate_question_bank_appointments(
                    excel_path=str(excel_path),
                    output_dir=str(output_dir),
                    prefix=prefix,
                    year=int(year),
                    deadline=deadline,
                    portal_link=portal_link,
                    signatory=signatory,
                    max_rows_per_page=max_rows,
                    logo_path=str(logo_path) if logo_path else None,
                    signature_path=str(signature_path) if signature_path else None,
                )
            except Exception as exc:
                st.error(f"An error occurred:\n\n{exc}")
                st.stop()

            with open(result["zip_path"], "rb") as f:
                zip_bytes = f.read()

            # Keep generated items so we can email them later
            # Copy PDFs out of the temporary directory
            pdf_storage = Path.home() / ".exam_admin_tools" / "last_pdfs"
            if pdf_storage.exists():
                shutil.rmtree(pdf_storage)
            pdf_storage.mkdir(parents=True, exist_ok=True)
            for item in result["generated_items"]:
                src = Path(item["pdf_path"])
                dst = pdf_storage / src.name
                dst.write_bytes(src.read_bytes())
                item["pdf_path"] = str(dst)

            st.session_state["last_result"] = result
            st.session_state["last_zip_bytes"] = zip_bytes

    # ------------------------------------------------------------------
    # Success UI
    # ------------------------------------------------------------------
    st.success("✅ Appointment orders generated successfully!")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Teachers", f"{result['total_teachers']:,}")
    m2.metric("PDFs Generated", f"{result['generated']:,}")
    m3.metric("Skipped", f"{result['skipped']:,}")
    if result.get("last_number"):
        m4.metric(
            "Numbers Used",
            f"{result['start_number']:04d} → {result['last_number']:04d}",
        )
    else:
        m4.metric("Numbers Used", "—")

    st.info(f"Next run will automatically start from **{result['next_number']:04d}**")

    if result["semester"]:
        st.info(f"Detected Semester: **{result['semester']}**")

    st.download_button(
        label="⬇️ Download All Appointment Orders (ZIP)",
        data=zip_bytes,
        file_name="Appointment_Orders.zip",
        mime="application/zip",
        type="primary",
        use_container_width=True,
    )

    skipped_df = result["skipped_df"]
    if not skipped_df.empty:
        st.warning("Some teachers were skipped because they have too many courses for a single page.")
        st.dataframe(skipped_df, use_container_width=True, hide_index=True)
        buffer = io.BytesIO()
        skipped_df.to_excel(buffer, index=False)
        st.download_button(
            label="⬇️ Download Skipped Teachers Log (.xlsx)",
            data=buffer.getvalue(),
            file_name="Teachers_Exceeding_One_Page.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.success("No teachers were skipped.")

# ------------------------------------------------------------------
# Email section (appears after generation)
# ------------------------------------------------------------------
if "last_result" in st.session_state:
    st.divider()
    st.subheader("📧 Send Appointment Orders by Email")

    result = st.session_state["last_result"]
    items = result.get("generated_items", [])

    with_email = [i for i in items if i.get("email")]
    without_email = [i for i in items if not i.get("email")]

    st.write(
        f"Teachers with email: **{len(with_email)}** &nbsp;&nbsp;|&nbsp;&nbsp; "
        f"Without email: **{len(without_email)}**"
    )

    if without_email:
        with st.expander("Teachers without email address"):
            st.dataframe(
                pd.DataFrame(
                    [{"Name": i["name"], "Appointment No": i["appt_no"]} for i in without_email]
                ),
                use_container_width=True,
                hide_index=True,
            )

    sender_email = st.text_input(
        "Sender Email (Controller of Examinations)", value="", key="sender"
    )
    app_password = st.text_input(
        "Gmail App Password",
        type="password",
        help="Use a Google App Password (not your normal password).",
        key="app_pw",
    )

    with st.expander("How to create a Gmail App Password"):
        st.markdown(
            """
            1. Go to [Google Account → Security](https://myaccount.google.com/security)
            2. Enable **2-Step Verification** if not already enabled
            3. Search for **App passwords**
            4. Create a new App Password for “Mail”
            5. Copy the 16-character password and paste it above
            """
        )

    if st.button("📨 Send PDFs to Teachers", type="primary"):
        if not sender_email or not app_password:
            st.error("Please enter both Sender Email and App Password.")
        elif not with_email:
            st.error("No teachers have email addresses to send to.")
        else:
            with st.spinner(f"Sending emails to {len(with_email)} teachers…"):
                email_result = send_appointment_emails(
                    with_email,
                    sender_email=sender_email,
                    app_password=app_password,
                )
            st.success(f"Successfully sent: **{email_result['sent']}**")
            if email_result["failed"]:
                st.error(f"Failed: **{len(email_result['failed'])}**")
                st.dataframe(
                    pd.DataFrame(email_result["failed"]),
                    use_container_width=True,
                    hide_index=True,
                )
