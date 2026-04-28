from __future__ import annotations

import csv
import io
from pathlib import Path

from docx import Document
from pypdf import PdfReader


UPLOAD_ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".pdf", ".docx"}


def extract_text_from_upload(filename: str, raw: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext in {".txt", ".md"}:
        return raw.decode("utf-8", errors="ignore")
    if ext == ".csv":
        return _extract_csv(raw)
    if ext == ".pdf":
        return _extract_pdf(raw)
    if ext == ".docx":
        return _extract_docx(raw)
    raise ValueError("Unsupported file extension")


def _extract_csv(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = [", ".join(cell.strip() for cell in row) for row in reader]
    return "\n".join(rows)


def _extract_pdf(raw: bytes) -> str:
    reader = PdfReader(io.BytesIO(raw))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages)


def _extract_docx(raw: bytes) -> str:
    doc = Document(io.BytesIO(raw))
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(lines)
