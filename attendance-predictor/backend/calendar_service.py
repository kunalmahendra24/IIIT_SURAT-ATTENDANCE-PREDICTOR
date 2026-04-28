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
- Extract EVERY event you can find. Do not be conservative.
- Prefer specific types (exam/holiday/break/fest) over 'other', but use 'other' if unsure.
- affects_attendance should be true for holidays, breaks, exams, fests; false for purely administrative events.
- If a date range is given (e.g. '20-22 Oct'), use date + end_date.
- Resolve year from the academic calendar header. If the calendar spans 2025-2026 and the month is Aug-Dec, use 2025; if Jan-Jul, use 2026.
- If you genuinely cannot find any events, return an empty events list — but try hard first.
"""


_MODEL_CHAIN = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
)


def _alnum_ratio(s: str) -> float:
    if not s:
        return 0.0
    alnum = sum(1 for ch in s if ch.isalnum())
    return alnum / max(1, len(s))


def _ensure_api_key() -> None:
    if not (os.getenv("GOOGLE_API_KEY") or "").strip():
        raise RuntimeError("GOOGLE_API_KEY is not set")
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


def _build_model(name: str, temperature: float):
    return genai.GenerativeModel(
        name,
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


def _gemini_call_with_fallback(content_parts: list[Any]) -> tuple[str, str, str | None]:
    """
    Try each model in the chain until one returns parseable JSON with events.

    Returns (model_used, raw_text, error_message_or_none).
    """
    last_error: str | None = None
    last_raw = ""
    last_model = _MODEL_CHAIN[0]

    for model_name in _MODEL_CHAIN:
        last_model = model_name
        try:
            model = _build_model(model_name, temperature=0.1)
            response = model.generate_content(content_parts)
            raw = getattr(response, "text", None) or ""
            last_raw = raw
            try:
                parsed = json.loads(raw)
            except Exception as je:
                last_error = f"{model_name}: invalid JSON ({je})"
                continue
            events = (parsed.get("events") if isinstance(parsed, dict) else None) or []
            if isinstance(events, list) and len(events) > 0:
                return model_name, raw, None
            last_error = f"{model_name}: returned 0 events"
        except Exception as e:
            last_error = f"{model_name}: {e}"
            continue

    return last_model, last_raw, last_error


def _validate_and_clean(extracted: dict) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    events_in = extracted.get("events", [])
    if not isinstance(events_in, list):
        events_in = []

    kept: list[dict[str, Any]] = []
    drop_counts: dict[str, int] = {
        "not_dict": 0,
        "missing_name": 0,
        "invalid_date": 0,
        "invalid_end_date_kept": 0,
        "end_before_start": 0,
        "duplicate": 0,
    }

    def norm_key(d: str, name: str) -> tuple[str, str]:
        return (d, (name or "").strip().lower())

    seen: set[tuple[str, str]] = set()

    for ev in events_in:
        if not isinstance(ev, dict):
            drop_counts["not_dict"] += 1
            continue
        raw_date = ev.get("date")
        raw_end = ev.get("end_date")
        name = str(ev.get("name") or "").strip()
        if not name:
            drop_counts["missing_name"] += 1
            continue
        ts = pd.to_datetime(raw_date, errors="coerce")
        if pd.isna(ts):
            drop_counts["invalid_date"] += 1
            continue
        ts = pd.Timestamp(ts).normalize()

        end_ts = None
        if raw_end not in (None, ""):
            ets = pd.to_datetime(raw_end, errors="coerce")
            if pd.isna(ets):
                drop_counts["invalid_end_date_kept"] += 1
                end_ts = None
            else:
                end_ts = pd.Timestamp(ets).normalize()
                if end_ts < ts:
                    drop_counts["end_before_start"] += 1
                    end_ts = None

        key = norm_key(ts.strftime("%Y-%m-%d"), name)
        if key in seen:
            drop_counts["duplicate"] += 1
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
        total_dropped = sum(v for k, v in drop_counts.items() if k != "invalid_end_date_kept")
        if total_dropped:
            for reason, count in drop_counts.items():
                if count > 0:
                    warnings.append(f"Dropped {count} event(s): {reason}")
        removed_ratio = total_dropped / max(1, len(events_in))
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
    Extract academic calendar events from a PDF using Gemini.

    Strategy:
    1. Try pdfplumber to get text. If text is decent, send (text + prompt) to Gemini.
    2. Otherwise (or if text path returns 0 events), send the PDF bytes directly to Gemini
       with mime_type=application/pdf — works on Vercel (no poppler needed).
    3. Walk a model fallback chain until one returns events.

    Returns dict: {academic_year, semester, events, warnings?, path?, model_used?, model_event_count?}
    Does NOT save to disk.
    """
    _ensure_api_key()

    warnings: list[str] = []
    diagnostics: dict[str, Any] = {}

    text = ""
    try:
        text = _extract_text_pdfplumber(pdf_bytes)
    except Exception as e:
        warnings.append(f"pdfplumber extraction failed; falling back to PDF input ({e})")
        text = ""

    text_quality_ok = len(text) >= 100 and _alnum_ratio(text) >= 0.3

    extracted: dict[str, Any] = {}
    raw_text_used = ""
    path_used = ""
    model_used = ""

    if text_quality_ok:
        path_used = "text"
        model_used, raw_text_used, err = _gemini_call_with_fallback([_SCHEMA_PROMPT, text])
        if err:
            warnings.append(f"Text path: {err}")
        try:
            extracted = json.loads(raw_text_used) if raw_text_used else {}
        except Exception:
            extracted = {}

    if not extracted.get("events"):
        path_used = "pdf"
        warnings.append("Sending PDF directly to Gemini (image/scanned-friendly).")
        pdf_part = {"mime_type": "application/pdf", "data": pdf_bytes}
        model_used, raw_text_used, err = _gemini_call_with_fallback([_SCHEMA_PROMPT, pdf_part])
        if err:
            warnings.append(f"PDF path: {err}")
        try:
            extracted = json.loads(raw_text_used) if raw_text_used else {}
        except Exception:
            extracted = {}

    diagnostics["path"] = path_used
    diagnostics["model_used"] = model_used
    model_events = (extracted.get("events") if isinstance(extracted, dict) else None) or []
    diagnostics["model_event_count"] = len(model_events) if isinstance(model_events, list) else 0

    if diagnostics["model_event_count"] == 0 and raw_text_used:
        preview = raw_text_used.strip().replace("\n", " ")
        if len(preview) > 400:
            preview = preview[:400] + "..."
        warnings.append(f"Model returned 0 events. Raw preview: {preview}")

    cleaned, val_warnings = _validate_and_clean(extracted if isinstance(extracted, dict) else {})
    diagnostics["kept_event_count"] = len(cleaned.get("events", []))
    warnings.extend(val_warnings)

    summary = (
        f"Path: {diagnostics['path']} | Model: {diagnostics['model_used']} | "
        f"Returned: {diagnostics['model_event_count']} | Kept: {diagnostics['kept_event_count']}"
    )
    warnings.insert(0, summary)

    cleaned.update(diagnostics)
    cleaned["warnings"] = warnings
    return cleaned


def validate_calendar_payload(payload: dict) -> tuple[dict, list[str]]:
    """
    Validate a calendar_events.json-shaped object (at least academic_year/semester/events).
    Returns (cleaned_payload, warnings).
    """
    cleaned, warnings = _validate_and_clean(payload if isinstance(payload, dict) else {})
    return cleaned, warnings
