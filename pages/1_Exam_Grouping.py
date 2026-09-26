"""
Exam Grouping feature page.
"""

import os
import tempfile
from pathlib import Path

import streamlit as st
import pandas as pd

from core.exam_grouping import generate_exam_groups
from utils.theme import apply_theme, show_sidebar_branding
from utils.auth import require_feature

st.set_page_config(page_title="Exam Grouping", page_icon="📚", layout="wide")

apply_theme()
require_feature("exam_grouping")
show_sidebar_branding()

st.title("📚 Exam Grouping")
st.markdown(
    """
    Upload **Regular** and (optionally) **Improvement / Supplementary** student Excel files.  
    The tool will standardise the data, detect Theory vs Practical papers, build conflict graphs,  
    and produce a fully formatted Excel workbook with conflict-free exam groups.
    """
)

# ------------------------------------------------------------------
# File uploaders
# ------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("Regular Students")
    regular_files = st.file_uploader(
        "Upload Regular Excel file(s)",
        type=["xlsx", "xlsm", "xls"],
        accept_multiple_files=True,
        key="regular",
        help="You can select multiple files.",
    )

with col2:
    st.subheader("Improvement / Supplementary")
    supp_files = st.file_uploader(
        "Upload Improvement / Supplementary Excel file(s) (optional)",
        type=["xlsx", "xlsm", "xls"],
        accept_multiple_files=True,
        key="supp",
        help="Leave empty if there are no supplementary files.",
    )

st.divider()

# ------------------------------------------------------------------
# Run button
# ------------------------------------------------------------------
run_btn = st.button("🚀 Generate Exam Groups", type="primary", use_container_width=True)

if run_btn:
    if not regular_files and not supp_files:
        st.error("Please upload at least one Excel file.")
        st.stop()

    with st.spinner("Processing files… this may take a moment for large workbooks."):
        # Save uploaded files to a temporary directory so pandas can read them
        with tempfile.TemporaryDirectory() as tmpdir:
            regular_paths = []
            for f in regular_files or []:
                path = Path(tmpdir) / f.name
                path.write_bytes(f.getbuffer())
                regular_paths.append(str(path))

            supp_paths = []
            for f in supp_files or []:
                path = Path(tmpdir) / f.name
                path.write_bytes(f.getbuffer())
                supp_paths.append(str(path))

            output_path = str(Path(tmpdir) / "final_output.xlsx")

            try:
                result = generate_exam_groups(regular_paths, supp_paths, output_path)
            except Exception as exc:
                st.error(f"An error occurred while processing the files:\n\n{exc}")
                st.stop()

            # Read the generated workbook into memory for download
            with open(output_path, "rb") as f:
                excel_bytes = f.read()

    # ------------------------------------------------------------------
    # Success summary
    # ------------------------------------------------------------------
    st.success("✅ Grouping completed successfully!")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Unique Students", f"{result['unique_students']:,}")
    m2.metric("Theory Papers / Groups", f"{result['theory_papers']:,} / {result['theory_groups']:,}")
    m3.metric("Practical Papers / Groups", f"{result['practical_papers']:,} / {result['practical_groups']:,}")
    m4.metric("Warnings", f"{result['warnings']:,}")

    st.download_button(
        label="⬇️ Download Final Grouping Workbook (.xlsx)",
        data=excel_bytes,
        file_name="final_output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )

    # ------------------------------------------------------------------
    # Optional previews
    # ------------------------------------------------------------------
    with st.expander("📊 Overview", expanded=True):
        st.dataframe(result["overview"], use_container_width=True, hide_index=True)

    with st.expander("📋 Group Summary"):
        if not result["group_summary"].empty:
            st.dataframe(result["group_summary"], use_container_width=True, hide_index=True)
        else:
            st.info("No groups generated.")

    with st.expander("📚 Course Summary"):
        if not result["course_summary"].empty:
            st.dataframe(result["course_summary"], use_container_width=True, hide_index=True)
        else:
            st.info("No course summary available.")

    with st.expander("⚠️ Warnings"):
        if not result["warnings_df"].empty:
            st.dataframe(result["warnings_df"], use_container_width=True, hide_index=True)
        else:
            st.success("No warnings.")

    with st.expander("Theory Groups (preview)"):
        if not result["theory_groups_df"].empty:
            st.dataframe(result["theory_groups_df"], use_container_width=True, hide_index=True)
        else:
            st.info("No theory papers.")

    with st.expander("Practical Groups (preview)"):
        if not result["practical_groups_df"].empty:
            st.dataframe(result["practical_groups_df"], use_container_width=True, hide_index=True)
        else:
            st.info("No practical papers.")
