"""
Calendar extraction + validation utilities for admin calendar uploads.

This module does NOT write to disk; saving is handled by /api/calendar/save.
"""

from __future__ import annotations

import json
import os
from io import BytesIO
from typing import Any

import pandas as pd
import google.generativeai as genai


_SCHEMA_PROMPT = """You are extracting events from an academic calendar for IIIT Surat.
Return ONLY valid JSON matching this exact schema. No preamble,
no markdown fences, no commentary:
{
  "events": [
    {
      "date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD" or null,
      "name": "string",
      "type": "exam" | "holiday" | "break" | "fest" | "class_resumes" | "other",
      "affects_attendance": true or false,
      "source_text": "original text from the calendar"
    }
  ],
  "academic_year": "YYYY-YYYY",
  "semester": "Odd" or "Even"
}

Rules:
- Prefer specific types (exam/holiday/break/fest) over 'other'
- affects_attendance should be true for holidays, breaks, exams,
  fests; false for purely administrative events
- If a date range is given (e.g. '20-22 Oct'), use date + end_date
- Skip events you are not confident about
"""


def _alnum_ratio(s: str) -> float:
    if not s:
        return 0.0
    alnum = sum(1 for ch in s if ch.isalnum())
    return alnum / max(1, len(s))


def _gemini_model(temperature: float):
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        "gemini-2.5-flash",
        generation_config={
            "response_mime_type": "application/json",
            "temperature": float(temperature),
        },
    )


def _extract_text_pdfplumber(pdf_bytes: bytes) -> str:
    import pdfplumber  # type: ignore

    out = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages[:10]:
            try:
                out.append(page.extract_text() or "")
            except Exception:
                out.append("")
    return "\n".join(out).strip()


def _images_from_pdf(pdf_bytes: bytes):
    # pdf2image requires poppler installed; handle errors upstream.
    from pdf2image import convert_from_bytes  # type: ignore

    # Returns PIL Images.
    return convert_from_bytes(pdf_bytes, dpi=150, first_page=1, last_page=10)


def _validate_and_clean(extracted: dict) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    events_in = extracted.get("events", [])
    if not isinstance(events_in, list):
        events_in = []

    kept: list[dict[str, Any]] = []
    dropped = 0

    def norm_key(d: str, name: str) -> tuple[str, str]:
        return (d, (name or "").strip().lower())

    seen: set[tuple[str, str]] = set()

    for ev in events_in:
        if not isinstance(ev, dict):
            dropped += 1
            continue
        raw_date = ev.get("date")
        raw_end = ev.get("end_date")
        name = str(ev.get("name") or "").strip()
        if not name:
            dropped += 1
            continue
        ts = pd.to_datetime(raw_date, errors="coerce")
        if pd.isna(ts):
            dropped += 1
            continue
        ts = pd.Timestamp(ts).normalize()

        end_ts = None
        if raw_end not in (None, ""):
            ets = pd.to_datetime(raw_end, errors="coerce")
            if pd.isna(ets):
                dropped += 1
                continue
            end_ts = pd.Timestamp(ets).normalize()
            if end_ts < ts:
                dropped += 1
                continue

        key = norm_key(ts.strftime("%Y-%m-%d"), name)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)

        kept.append(
            {
                "date": ts.strftime("%Y-%m-%d"),
                "end_date": end_ts.strftime("%Y-%m-%d") if end_ts is not None else None,
                "name": name,
                "type": str(ev.get("type") or "other"),
                "affects_attendance": bool(ev.get("affects_attendance", False)),
                "source_text": str(ev.get("source_text") or "").strip(),
            }
        )

    if events_in:
        removed_ratio = dropped / max(1, len(events_in))
        if removed_ratio > 0.5:
            warnings.append("Validation removed more than 50% of extracted events; review carefully.")

    out = {
        "academic_year": str(extracted.get("academic_year") or "").strip(),
        "semester": str(extracted.get("semester") or "").strip(),
        "events": kept,
    }
    return out, warnings


def extract_events_from_pdf(pdf_bytes: bytes) -> dict:
    """
    Extract academic calendar events from a PDF, using:
    - pdfplumber text extraction first
    - Gemini vision fallback for scanned/image PDFs

    Returns a dict: {academic_year, semester, events, warnings?}
    Does NOT save to disk.
    """
    warnings: list[str] = []
    if not (os.getenv("GOOGLE_API_KEY") or "").strip():
        raise RuntimeError("GOOGLE_API_KEY is not set")

    text = ""
    try:
        text = _extract_text_pdfplumber(pdf_bytes)
    except Exception as e:
        warnings.append(f"pdfplumber extraction failed; trying vision fallback ({e})")
        text = ""

    use_vision = (len(text) < 100) or (_alnum_ratio(text) < 0.3)
    if use_vision:
        warnings.append("Low-quality PDF text detected; using vision extraction.")
        try:
            imgs = _images_from_pdf(pdf_bytes)
        except Exception as e:
            raise RuntimeError(f"Vision fallback unavailable (pdf2image/poppler error): {e}") from e

        model = _gemini_model(temperature=0.1)
        content_parts: list[Any] = [_SCHEMA_PROMPT]
        for img in list(imgs)[:10]:
            content_parts.append(img)  # google-generativeai accepts PIL.Image
        response = model.generate_content(content_parts)
        raw_text = getattr(response, "text", None) or ""
        extracted = json.loads(raw_text)
    else:
        model = _gemini_model(temperature=0.1)
        prompt = _SCHEMA_PROMPT
        response = model.generate_content([prompt, text])
        raw_text = getattr(response, "text", None) or ""
        extracted = json.loads(raw_text)

    cleaned, val_warnings = _validate_and_clean(extracted if isinstance(extracted, dict) else {})
    warnings.extend(val_warnings)
    if warnings:
        cleaned["warnings"] = warnings
    return cleaned


def validate_calendar_payload(payload: dict) -> tuple[dict, list[str]]:
    """
    Validate a calendar_events.json-shaped object (at least academic_year/semester/events).
    Returns (cleaned_payload, warnings).
    """
    cleaned, warnings = _validate_and_clean(payload if isinstance(payload, dict) else {})
    return cleaned, warnings

