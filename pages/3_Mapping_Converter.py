"""
Mapping File Converter – Streamlit page.
"""

import tempfile
from pathlib import Path

import streamlit as st
import pandas as pd

from utils.theme import apply_theme, show_sidebar_branding
from utils.auth import require_feature
from core.mapping_converter import (
    process_mapping_files,
    list_saved_templates,
    save_template,
    delete_template,
)

st.set_page_config(page_title="Mapping Converter", page_icon="🔄", layout="wide")

apply_theme()
require_feature("mapping_converter")
show_sidebar_branding()

st.title("🔄 Mapping File Converter")
st.markdown(
    """
    Convert source mapping files (`*Upload_Mapping*.xlsx`) into the required template format.
    
    **How it works:**
    1. Upload / manage your **Template** files once (they are saved permanently)
    2. Upload one or more **Source** files
    3. Click **Convert**
    4. Download the successful output files as a ZIP
    """
)

st.divider()

# ------------------------------------------------------------------
# Permanent Template Library
# ------------------------------------------------------------------
st.subheader("Template Library (saved permanently)")

saved = list_saved_templates()

if saved:
    st.success(f"{len(saved)} template(s) currently saved:")
    for name in saved:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"• `{name}`")
        with col2:
            if st.button("Delete", key=f"del_{name}"):
                delete_template(name)
                st.rerun()
else:
    st.warning("No templates saved yet. Please upload them below.")

new_templates = st.file_uploader(
    "Upload / Add Template file(s) (e.g. '12 Qns 60 Marks.xlsx')",
    type=["xlsx", "xlsm"],
    accept_multiple_files=True,
    key="new_templates",
)

if new_templates:
    for f in new_templates:
        save_template(f.name, f.getbuffer())
    st.success(f"Saved {len(new_templates)} template(s).")
    st.rerun()

st.caption("Templates are stored permanently. You only need to upload them once. You can add or delete them anytime.")

st.divider()

# ------------------------------------------------------------------
# Source file upload
# ------------------------------------------------------------------
st.subheader("Source Files")

source_files = st.file_uploader(
    "Upload Source Excel file(s)",
    type=["xlsx", "xlsm"],
    accept_multiple_files=True,
    key="sources",
    help="These are the files that contain 'Upload_Mapping' in the name.",
)

st.divider()

# ------------------------------------------------------------------
# Convert button
# ------------------------------------------------------------------
run_btn = st.button("🚀 Convert Mapping Files", type="primary", use_container_width=True)

if run_btn:
    if not source_files:
        st.error("Please upload at least one Source file.")
        st.stop()

    if not list_saved_templates():
        st.error("No templates are saved. Please upload at least one template first.")
        st.stop()

    with st.spinner("Processing files… please wait."):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # Save uploaded source files
            source_paths = []
            for f in source_files:
                p = tmp / f.name
                p.write_bytes(f.getbuffer())
                source_paths.append(p)

            output_dir = tmp / "output"

            try:
                result = process_mapping_files(
                    source_files=source_paths,
                    template_files=None,          # use permanent templates
                    output_dir=output_dir,
                    use_saved_templates=True,
                )
            except Exception as exc:
                st.error(f"An unexpected error occurred:\n\n{exc}")
                st.stop()

            # Read ZIP if available
            zip_bytes = None
            if result["zip_path"] and Path(result["zip_path"]).exists():
                with open(result["zip_path"], "rb") as f:
                    zip_bytes = f.read()

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    st.success("Processing completed!")

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Files", result["total"])
    m2.metric("Successful", result["success_count"])
    m3.metric("Failed", result["failed_count"])

    if zip_bytes:
        st.download_button(
            label="⬇️ Download Converted Files (ZIP)",
            data=zip_bytes,
            file_name="Mapping_Converted_Files.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True,
        )
    else:
        st.warning("No files were converted successfully, so there is nothing to download.")

    # Detailed results table
    st.subheader("Detailed Results")
    df_results = pd.DataFrame(result["results"])
    cols = ["file", "status", "course_code", "total_qns", "max_mark", "message"]
    df_results = df_results[[c for c in cols if c in df_results.columns]]
    st.dataframe(df_results, use_container_width=True, hide_index=True)

    # Show failed ones more prominently
    failed = [r for r in result["results"] if r["status"] == "FAILED"]
    if failed:
        st.error("Some files failed. See details below:")
        for r in failed:
            st.write(f"**{r['file']}** → {r['message']}")
