"""Text extraction for multipart attachments (the service-side path)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree

from fastapi import UploadFile
from pypdf import PdfReader


TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".xml"}


async def extract_attachment_text(upload: UploadFile) -> str:
    """Extract human-readable text from one uploaded document.

    This implements path B: files are read inside the service and only their
    extracted text is passed to the estimation prompt. Binary formats are
    intentionally limited to PDF and DOCX for this exercise.
    """
    filename = upload.filename or "attachment"
    suffix = PurePosixPath(filename).suffix.lower()
    data = await upload.read()

    if suffix in TEXT_SUFFIXES:
        text = data.decode("utf-8-sig")
        if suffix == ".json":
            try:
                return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                return text
        return text

    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()

    if suffix == ".docx":
        return _extract_docx_text(data)

    raise ValueError(f"Unsupported attachment type: {suffix or 'unknown'}")


def _extract_docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        document = ElementTree.fromstring(archive.read("word/document.xml"))
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in document.findall(".//w:p", namespace):
        words = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        if words:
            paragraphs.append("".join(words))
    return "\n".join(paragraphs).strip()
