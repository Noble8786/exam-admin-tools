"""
Mapping File Converter – core logic.
Converts source mapping files into the required template format.
"""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


TARGET_CO_COLUMNS = ["CO1", "CO2", "CO3", "CO4", "CO5"]


# ---------------------------------------------------------------------------
# Permanent Template storage
# ---------------------------------------------------------------------------
def _templates_folder() -> Path:
    folder = Path.home() / ".exam_admin_tools" / "mapping_templates"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def list_saved_templates() -> List[str]:
    """Return list of saved template file names."""
    folder = _templates_folder()
    return sorted([p.name for p in folder.glob("*.xlsx")] + [p.name for p in folder.glob("*.xlsm")])


def save_template(filename: str, data: bytes) -> Path:
    """Save or replace a template file."""
    path = _templates_folder() / filename
    path.write_bytes(data)
    return path


def delete_template(filename: str) -> bool:
    """Delete a saved template. Returns True if deleted."""
    path = _templates_folder() / filename
    if path.exists():
        path.unlink()
        return True
    return False


def get_templates_dir() -> Path:
    """Return the permanent templates directory."""
    return _templates_folder()


def extract_metadata(df_source_full: pd.DataFrame) -> Tuple[str, int, int, pd.DataFrame]:
    """
    Extracts Course Code, Max Marks, Total Questions and the cleaned data rows.
    """
    # Find the metadata row that contains 'QP Code'
    mask = df_source_full.iloc[:, 0].astype(str).str.contains("QP Code", na=False)
    if not mask.any():
        raise ValueError("Could not find 'QP Code' row in the source file.")

    metadata_row = df_source_full[mask].iloc[0]

    # Max mark is the 7th item (index 6)
    try:
        max_mark = int(float(str(metadata_row.iloc[6]).strip()))
    except Exception:
        raise ValueError("Could not read Max Marks from the metadata row.")

    # Course code is the 2nd item (index 1)
    course_code_raw = str(metadata_row.iloc[1]).strip()
    course_code = course_code_raw.split(" ")[0] if course_code_raw else ""
    if not course_code:
        raise ValueError("Could not extract Course Code.")

    # Identify the start of the actual data (Qn.No header)
    qn_mask = df_source_full.iloc[:, 0].astype(str).str.strip() == "Qn.No"
    if not qn_mask.any():
        raise ValueError("Could not find 'Qn.No' header row.")

    data_start_row_index = qn_mask.idxmax()
    df_data = df_source_full.iloc[data_start_row_index + 1 :].copy()

    # Extract Total Questions (largest number in Qn.No column)
    qns_col = df_data.iloc[:, 0].astype(str)
    all_qns_numbers = []
    for qn in qns_col:
        m = re.search(r"(\d+)", qn)
        if m:
            all_qns_numbers.append(int(m.group(1)))

    total_qns = max(all_qns_numbers) if all_qns_numbers else 0
    if total_qns == 0:
        raise ValueError("Could not determine Total Questions.")

    # Rename columns for easy access
    n_cols = df_data.shape[1]
    new_cols = ["Qn.No", "Question ID", "Max.Marks"] + [
        f"CO_Source_{i}" for i in range(max(0, n_cols - 3))
    ]
    # Pad or trim to match
    if len(new_cols) < n_cols:
        new_cols += [f"Extra_{i}" for i in range(len(new_cols), n_cols)]
    df_data.columns = new_cols[:n_cols]

    # Clean trailing empty rows
    df_data = df_data[df_data["Qn.No"].astype(str).str.strip().str.lower() != "nan"]
    df_data = df_data[df_data["Qn.No"].astype(str).str.strip() != ""]

    return course_code, max_mark, total_qns, df_data


def load_template_data(
    total_qns: int,
    max_mark: int,
    template_dir: Path,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Selects and loads the correct target template file.
    Template naming convention: "{total_qns} Qns {max_mark} Marks.xlsx"
    """
    template_name = f"{total_qns} Qns {max_mark} Marks.xlsx"
    template_path = template_dir / template_name

    if not template_path.exists():
        return None, f"Template file not found: {template_name}"

    df_template = pd.read_excel(template_path, header=0, sheet_name=0, na_filter=False)

    for col in TARGET_CO_COLUMNS:
        if col not in df_template.columns:
            df_template[col] = ""

    # Clear existing CO data
    df_template[TARGET_CO_COLUMNS] = ""

    return df_template, None


def transform_and_verify(
    df_source: pd.DataFrame,
    df_template: pd.DataFrame,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Performs Mark Verification, Row Insertion, and CO Copy.
    """
    source_co_cols = [col for col in df_source.columns if col.startswith("CO_Source_")]

    if len(source_co_cols) < len(TARGET_CO_COLUMNS):
        # Pad missing CO columns
        for i in range(len(source_co_cols), len(TARGET_CO_COLUMNS)):
            col_name = f"CO_Source_{i}"
            df_source[col_name] = ""
            source_co_cols.append(col_name)

    transformed_rows = []
    template_row_index = 0

    for _, source_row in df_source.iterrows():
        qn_id = str(source_row["Qn.No"]).strip()
        m_num = re.search(r"(\d+)", qn_id)
        if not m_num:
            continue
        main_qn_num = m_num.group(1)
        sub_qn_char = re.search(r"[a-zA-Z]", qn_id)

        # 1. Row Insertion Logic – insert main question header if needed
        if sub_qn_char and (
            not transformed_rows or str(transformed_rows[-1].get("Qn.Num", "")) != main_qn_num
        ):
            if template_row_index >= len(df_template):
                return None, "Template verification failed: Template has too few rows."
            header_row = df_template.iloc[template_row_index].copy()
            header_row["Qn.Num"] = main_qn_num
            transformed_rows.append(header_row)
            template_row_index += 1

        # 2. Mark Verification and CO Copy
        if template_row_index >= len(df_template):
            return None, "Template verification failed: Template has too few rows for the sub-questions."

        current_template_row = df_template.iloc[template_row_index].copy()

        source_mark = pd.to_numeric(source_row["Max.Marks"], errors="coerce")
        template_mark = pd.to_numeric(current_template_row.get("QUESTION MARK", None), errors="coerce")

        if pd.isna(source_mark) or pd.isna(template_mark) or source_mark != template_mark:
            return (
                None,
                f"Questions Mark not Matched: Source Qn. {qn_id} (Mark {source_mark}) "
                f"does not match Template Qn. {current_template_row.get('QUESTIONS', '')} "
                f"(Mark {template_mark}).",
            )

        # CO Copy
        for j, co_col in enumerate(TARGET_CO_COLUMNS):
            current_template_row[co_col] = source_row[source_co_cols[j]]

        current_template_row["Qn.Num"] = main_qn_num
        transformed_rows.append(current_template_row)
        template_row_index += 1

    df_output = pd.DataFrame(transformed_rows)
    df_output.drop(columns=["Qn.Num"], inplace=True, errors="ignore")

    return df_output, None


def process_single_file(
    source_path: Path,
    template_dir: Path,
    output_dir: Path,
) -> dict:
    """
    Process one source file. Returns a result dict.
    """
    file_name = source_path.name
    try:
        df_source_full = pd.read_excel(
            source_path, header=None, sheet_name=0, na_filter=False
        )
        course_code, max_mark, total_qns, df_source_data = extract_metadata(df_source_full)

        df_template, error = load_template_data(total_qns, max_mark, template_dir)
        if error:
            return {
                "file": file_name,
                "status": "FAILED",
                "message": error,
                "course_code": course_code,
                "total_qns": total_qns,
                "max_mark": max_mark,
            }

        df_transformed, error = transform_and_verify(df_source_data, df_template)
        if error:
            return {
                "file": file_name,
                "status": "FAILED",
                "message": error,
                "course_code": course_code,
                "total_qns": total_qns,
                "max_mark": max_mark,
            }

        output_file_name = f"{course_code}.xlsx"
        output_path = output_dir / output_file_name
        df_transformed.to_excel(output_path, index=False, engine="openpyxl")

        return {
            "file": file_name,
            "status": "SUCCESS",
            "message": f"Transformed to {output_file_name}",
            "course_code": course_code,
            "total_qns": total_qns,
            "max_mark": max_mark,
            "output_file": str(output_path),
            "output_name": output_file_name,
        }

    except Exception as e:
        return {
            "file": file_name,
            "status": "FAILED",
            "message": str(e),
            "course_code": "",
            "total_qns": "",
            "max_mark": "",
        }


def process_mapping_files(
    source_files: List[Path],
    template_files: List[Path] | None,
    output_dir: Path,
    use_saved_templates: bool = True,
) -> dict:
    """
    Main entry point used by the Streamlit page.
    - source_files: list of uploaded source Excel paths
    - template_files: optional list of newly uploaded template paths
    - output_dir: where to write the results
    - use_saved_templates: if True, also use permanently saved templates
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build the template directory to use
    template_dir = output_dir / "_templates"
    template_dir.mkdir(exist_ok=True)

    # 1. Copy permanently saved templates
    if use_saved_templates:
        saved_dir = get_templates_dir()
        for p in saved_dir.glob("*.xlsx"):
            (template_dir / p.name).write_bytes(p.read_bytes())
        for p in saved_dir.glob("*.xlsm"):
            (template_dir / p.name).write_bytes(p.read_bytes())

    # 2. Overlay any newly uploaded templates (they take priority)
    if template_files:
        for t in template_files:
            dest = template_dir / Path(t).name
            dest.write_bytes(Path(t).read_bytes())

    results = []
    success_files = []

    for src in source_files:
        result = process_single_file(Path(src), template_dir, output_dir)
        results.append(result)
        if result["status"] == "SUCCESS":
            success_files.append(result["output_file"])

    # Create ZIP of successful outputs
    zip_path = output_dir / "Mapping_Converted_Files.zip"
    if success_files:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in success_files:
                zf.write(f, arcname=Path(f).name)

    return {
        "results": results,
        "success_count": sum(1 for r in results if r["status"] == "SUCCESS"),
        "failed_count": sum(1 for r in results if r["status"] == "FAILED"),
        "zip_path": str(zip_path) if success_files else None,
        "total": len(results),
        "templates_used": list_saved_templates() if use_saved_templates else [],
    }
