"""
Appointment Letter Generation – core logic.
Currently supports: Question Bank Setting appointment orders.
"""

from __future__ import annotations

import os
import re
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ---------------------------------------------------------------------------
# PDF Styles (created once)
# ---------------------------------------------------------------------------
_styles = getSampleStyleSheet()

title_style = _styles["Heading1"]
title_style.fontName = "Helvetica-Bold"
title_style.fontSize = 16
title_style.leading = 16
title_style.spaceBefore = 0
title_style.spaceAfter = 6
title_style.alignment = TA_CENTER

normal_style = _styles["BodyText"]
normal_style.fontSize = 12
normal_style.leading = 12
normal_style.spaceBefore = 0
normal_style.spaceAfter = 0

small_style = _styles["BodyText"]
small_style.fontSize = 10
small_style.leading = 10
small_style.spaceBefore = 0
small_style.spaceAfter = 0
small_style.alignment = TA_JUSTIFY

right_style = deepcopy(normal_style)
right_style.alignment = TA_RIGHT


RESPONSIBILITIES = """
<b>Responsibilities:</b><br/><br/>
<b>Question Submission:</b> Each teacher is requested to prepare and submit
questions that cover all topics/COs as outlined in the syllabus/course file.
The questions and blueprint should adhere to the guidelines provided in the
syllabus/regulations/exam policy documents. Please ensure that the questions
are clear, concise and based on different difficulty levels. Answers should be
provided in the case of multiple choice question banks.<br/><br/>
<b>Quantity:</b> Upload the maximum possible number
(5 times the required question) of standard questions.<br/><br/>
<b>Format:</b> Questions must be uploaded using the prescribed format available
in the Question Bank Portal. For bulk upload, the Excel template may be
downloaded from the portal. Alternatively, questions may be entered directly
into the software. Ensure that every question is mapped to the corresponding
CO.<br/><br/>
<b>Confidentiality:</b> The confidentiality of the Question Bank must be
maintained at all times. Questions should never be shared with students.<br/><br/>
<b>Deadline:</b> Please ensure that all questions are uploaded on or before
the deadline mentioned in this appointment order.<br/><br/>
<b>Authenticity:</b> Follow the curriculum approved by BOS.<br/><br/>
<b>Collaboration:</b> Teachers assigned to the same course may work
collaboratively to ensure the quality and standard of the Question Bank.<br/><br/>
Thank you for your cooperation.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_teacher(raw) -> tuple[str, str]:
    """
    Return (clean_name, email).
    Email is extracted from parentheses if present.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "", ""
    text = str(raw).strip()
    if text.lower() in {"", "nan", "none"}:
        return "", ""

    email = ""
    name = text
    # Extract email from parentheses: "Name (email@domain.com)"
    match = re.search(r"\(([^)]+@[^)]+)\)", text)
    if match:
        email = match.group(1).strip()
        name = text[: match.start()].strip()
    else:
        # Sometimes only the email is present
        if "@" in text and " " not in text:
            email = text
            name = ""

    return name, email


def _extract_semester(excel_filename: str) -> str:
    match = re.search(r"S(\d+)", excel_filename.upper())
    return f"S{match.group(1)}" if match else ""


def _add_assignment(
    teachers: Dict[str, dict],
    raw_teacher,
    semester: str,
    course_code: str,
    course_name: str,
    role: str,
) -> None:
    name, email = _parse_teacher(raw_teacher)
    if not name:
        return
    if name not in teachers:
        teachers[name] = {"email": email, "assignments": []}
    # Keep the first non-empty email we find
    if email and not teachers[name]["email"]:
        teachers[name]["email"] = email
    assignment = (semester, course_code.strip(), course_name.strip(), role)
    if assignment not in teachers[name]["assignments"]:
        teachers[name]["assignments"].append(assignment)


def build_teacher_database(df: pd.DataFrame, semester: str) -> Dict[str, dict]:
    """
    Expected columns (0-based):
      0 = Course Code
      1 = Course Name
      2 = Chief Examiner
      3 = Examiner 1
      4 = Examiner 2
      5 = Examiner 3

    Returns: { teacher_name: {"email": str, "assignments": [(sem, code, name, role), ...]} }
    """
    teachers: Dict[str, dict] = {}
    for _, row in df.iterrows():
        course_code = str(row.iloc[0]).strip() if not pd.isna(row.iloc[0]) else ""
        course_name = str(row.iloc[1]).strip() if not pd.isna(row.iloc[1]) else ""
        if not course_code:
            continue
        _add_assignment(teachers, row.iloc[2], semester, course_code, course_name, "Chief Examiner")
        _add_assignment(teachers, row.iloc[3], semester, course_code, course_name, "Examiner")
        _add_assignment(teachers, row.iloc[4], semester, course_code, course_name, "Examiner")
        _add_assignment(teachers, row.iloc[5], semester, course_code, course_name, "Examiner")
    return dict(sorted(teachers.items()))


# ---------------------------------------------------------------------------
# Persistent counter (remembers last number across days)
# ---------------------------------------------------------------------------
def _counter_file_path() -> Path:
    """Store the counter in the user's home folder so it survives app updates."""
    folder = Path.home() / ".exam_admin_tools"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "qb_appointment_counter.txt"


def get_next_appointment_number() -> int:
    """Return the next number that should be used (starts from 1 if file missing)."""
    path = _counter_file_path()
    if not path.exists():
        return 1
    try:
        value = int(path.read_text(encoding="utf-8").strip())
        return max(1, value + 1)
    except (ValueError, OSError):
        return 1


def save_last_appointment_number(last_number: int) -> None:
    """Save the highest number that was just used."""
    path = _counter_file_path()
    path.write_text(str(last_number), encoding="utf-8")


def reset_appointment_counter() -> None:
    """Reset so the next run starts from 0001."""
    path = _counter_file_path()
    if path.exists():
        path.unlink()


def generate_appointment_numbers(
    teachers: Dict[str, dict],
    prefix: str,
    year: int,
    start_number: int = 1,
) -> Dict[str, str]:
    """Generate continuous appointment numbers starting from start_number."""
    numbers = {}
    current = start_number
    for teacher in teachers:
        numbers[teacher] = f"{prefix}/{year}/QB/{current:04d}"
        current += 1
    return numbers


# ---------------------------------------------------------------------------
# Persistent Logo & Signature storage
# ---------------------------------------------------------------------------
def _assets_folder() -> Path:
    folder = Path.home() / ".exam_admin_tools" / "assets"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_saved_logo_path() -> Path | None:
    path = _assets_folder() / "logo.png"
    return path if path.exists() else None


def get_saved_signature_path() -> Path | None:
    path = _assets_folder() / "signature.png"
    return path if path.exists() else None


def save_logo(uploaded_bytes: bytes, filename: str = "logo.png") -> Path:
    path = _assets_folder() / "logo.png"
    path.write_bytes(uploaded_bytes)
    return path


def save_signature(uploaded_bytes: bytes, filename: str = "signature.png") -> Path:
    path = _assets_folder() / "signature.png"
    path.write_bytes(uploaded_bytes)
    return path


def clear_logo() -> None:
    path = _assets_folder() / "logo.png"
    if path.exists():
        path.unlink()


def clear_signature() -> None:
    path = _assets_folder() / "signature.png"
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# PDF creation
# ---------------------------------------------------------------------------
def create_question_bank_pdf(
    teacher_name: str,
    assignments: List[Tuple],
    appointment_no: str,
    output_path: str,
    *,
    deadline: str,
    portal_link: str,
    signatory: str,
    logo_path: str | None = None,
    signature_path: str | None = None,
) -> None:
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch,
    )
    story = []

    # Logo
    if logo_path and os.path.exists(logo_path):
        logo = Image(logo_path)
        logo.drawHeight = 0.787402 * inch
        logo.drawWidth = 4.72441 * inch
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 0.05 * inch))

    # Title
    story.append(Paragraph("<b>Appointment Order</b>", title_style))
    story.append(Spacer(1, 0.15 * inch))

    # Order number & date
    today = datetime.today().strftime("%d %B %Y")
    available_width = doc.width
    header = Table(
        [
            [
                Paragraph(f"<b>No.</b> {appointment_no}", normal_style),
                Paragraph(f"<b>Date :</b> {today}", right_style),
            ]
        ],
        colWidths=[available_width - 2.0 * inch, 2.02 * inch],
    )
    header.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 0.18 * inch))

    # Subject
    story.append(
        Paragraph("<b>Sub:</b> Question Bank Setting - Appointment reg.", normal_style)
    )
    story.append(Spacer(1, 0.15 * inch))

    # Salutation
    story.append(Paragraph(f"Dear <b>{teacher_name}</b>,", normal_style))
    story.append(Spacer(1, 0.12 * inch))
    story.append(
        Paragraph(
            "I am pleased to appoint you as Question Bank Setter "
            "for the following course(s) as part of the upcoming "
            "semester examinations.",
            normal_style,
        )
    )
    story.append(Spacer(1, 0.08 * inch))
    story.append(Paragraph("<b>Course Details</b>", normal_style))
    story.append(Spacer(1, 0.08 * inch))

    # Course table
    table_data = [["Semester", "Course Code", "Course Name", "Assigned As"]]
    for row in assignments:
        table_data.append(
            [row[0], row[1], Paragraph(row[2], small_style), row[3]]
        )

    course_table = Table(
        table_data,
        colWidths=[0.8 * inch, 1.3 * inch, 3.5 * inch, 1.2 * inch],
    )
    course_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
            ]
        )
    )
    story.append(course_table)
    story.append(Spacer(1, 0.18 * inch))

    # Deadline & link
    story.append(Paragraph(f"<b>Deadline :</b> {deadline}", normal_style))
    story.append(Spacer(1, 0.08 * inch))
    story.append(Paragraph(portal_link, normal_style))
    story.append(Spacer(1, 0.15 * inch))

    # Responsibilities
    story.append(Paragraph(RESPONSIBILITIES, small_style))
    story.append(Spacer(1, 0.18 * inch))

    # Signature
    story.append(Paragraph("Yours sincerely,", normal_style))
    story.append(Spacer(1, 0.30 * inch))

    if signature_path and os.path.exists(signature_path):
        sign = Image(signature_path)
        sign.drawHeight = 0.92 * inch
        sign.drawWidth = 2.5 * inch
        sign.hAlign = "LEFT"
        story.append(sign)

    story.append(Paragraph(f"<b>{signatory}</b>", normal_style))

    doc.build(story)


# ---------------------------------------------------------------------------
# Main generator (used by Streamlit)
# ---------------------------------------------------------------------------
def generate_question_bank_appointments(
    excel_path: str,
    output_dir: str,
    *,
    prefix: str = "SBCE",
    year: int | None = None,
    deadline: str = "31 August 2026",
    portal_link: str = "https://qnsmarti.qbanksbcollege.in",
    signatory: str = "Controller of Examinations",
    max_rows_per_page: int = 12,
    logo_path: str | None = None,
    signature_path: str | None = None,
    start_number: int | None = None,
) -> dict:
    """
    Returns a summary dict and creates PDFs + a ZIP in output_dir.
    Appointment numbers continue automatically from the last used number.
    """
    if year is None:
        year = datetime.today().year

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = output_dir / "pdfs"
    pdf_dir.mkdir(exist_ok=True)

    # Read Excel
    df = pd.read_excel(excel_path)
    df = df.fillna("")

    excel_name = Path(excel_path).stem
    semester = _extract_semester(excel_name)

    teachers = build_teacher_database(df, semester)

    # Automatic continuous numbering
    if start_number is None:
        start_number = get_next_appointment_number()

    appointment_numbers = generate_appointment_numbers(
        teachers, prefix, year, start_number=start_number
    )

    # Highest number that will be used in this batch
    last_number_used = start_number + len(teachers) - 1 if teachers else start_number - 1

    generated = 0
    skipped = []
    pdf_files = []
    # List of successfully generated items for emailing later
    # each item: {"name": str, "email": str, "pdf_path": str, "appt_no": str}
    generated_items = []

    for teacher_name, info in teachers.items():
        assignments = sorted(info["assignments"], key=lambda x: x[1])  # by course code
        appt_no = appointment_numbers[teacher_name]
        email = info.get("email", "")

        if len(assignments) > max_rows_per_page:
            skipped.append(
                {
                    "Teacher Name": teacher_name,
                    "Email": email,
                    "No. of Courses": len(assignments),
                    "Appointment No": appt_no,
                }
            )
            continue

        safe_name = teacher_name.replace("/", "-").replace("\\", "-")
        pdf_path = pdf_dir / f"{safe_name}.pdf"
        create_question_bank_pdf(
            teacher_name=teacher_name,
            assignments=assignments,
            appointment_no=appt_no,
            output_path=str(pdf_path),
            deadline=deadline,
            portal_link=portal_link,
            signatory=signatory,
            logo_path=logo_path,
            signature_path=signature_path,
        )
        pdf_files.append(pdf_path)
        generated_items.append(
            {
                "name": teacher_name,
                "email": email,
                "pdf_path": str(pdf_path),
                "appt_no": appt_no,
            }
        )
        generated += 1

    # Create ZIP of all PDFs
    zip_path = output_dir / "Appointment_Orders.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf in pdf_files:
            zf.write(pdf, arcname=pdf.name)

    # Skipped log
    skipped_df = pd.DataFrame(skipped) if skipped else pd.DataFrame(
        columns=["Teacher Name", "Email", "No. of Courses", "Appointment No"]
    )
    if skipped:
        skipped_df.to_excel(output_dir / "Teachers_Exceeding_One_Page.xlsx", index=False)

    # Save the last used number so the next run continues automatically
    if teachers:
        save_last_appointment_number(last_number_used)

    return {
        "total_teachers": len(teachers),
        "generated": generated,
        "skipped": len(skipped),
        "skipped_df": skipped_df,
        "zip_path": str(zip_path),
        "semester": semester,
        "appointment_numbers": appointment_numbers,
        "start_number": start_number,
        "last_number": last_number_used if teachers else None,
        "next_number": last_number_used + 1 if teachers else start_number,
        "generated_items": generated_items,  # for emailing
        "pdf_dir": str(pdf_dir),
    }


# ---------------------------------------------------------------------------
# Email sending (Gmail)
# ---------------------------------------------------------------------------
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


def send_appointment_emails(
    items: list[dict],
    *,
    sender_email: str,
    app_password: str,
    subject_template: str = "Appointment Order – Question Bank Setting ({appt_no})",
    body_template: str = (
        "Dear {name},\n\n"
        "Please find attached your Appointment Order for Question Bank Setting.\n\n"
        "Appointment No: {appt_no}\n\n"
        "Kindly go through the order carefully and complete the work before the deadline.\n\n"
        "Regards,\n"
        "Controller of Examinations"
    ),
) -> dict:
    """
    Send each PDF to the teacher's email.
    Returns summary: {"sent": int, "failed": list of {name, email, error}}
    """
    sent = 0
    failed = []

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, app_password)
    except Exception as e:
        return {
            "sent": 0,
            "failed": [{"name": "", "email": "", "error": f"Login failed: {e}"}],
        }

    for item in items:
        name = item["name"]
        email = item.get("email", "").strip()
        pdf_path = item["pdf_path"]
        appt_no = item["appt_no"]

        if not email:
            failed.append({"name": name, "email": "", "error": "No email address found"})
            continue

        try:
            msg = MIMEMultipart()
            msg["From"] = sender_email
            msg["To"] = email
            msg["Subject"] = subject_template.format(name=name, appt_no=appt_no)

            body = body_template.format(name=name, appt_no=appt_no)
            msg.attach(MIMEText(body, "plain"))

            with open(pdf_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=Path(pdf_path).name)
            part["Content-Disposition"] = f'attachment; filename="{Path(pdf_path).name}"'
            msg.attach(part)

            server.send_message(msg)
            sent += 1
        except Exception as e:
            failed.append({"name": name, "email": email, "error": str(e)})

    try:
        server.quit()
    except Exception:
        pass

    return {"sent": sent, "failed": failed}
