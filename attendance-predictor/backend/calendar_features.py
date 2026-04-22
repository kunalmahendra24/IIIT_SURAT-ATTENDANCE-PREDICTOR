from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent
CALENDAR_EVENTS_PATH = BACKEND_DIR / "calendar_events.json"

# Cached calendar events; keep in-memory so we can hot-reload on admin save.
_EVENTS_CACHE: list[dict] | None = None


def _read_calendar_file() -> dict:
    if not CALENDAR_EVENTS_PATH.exists():
        return {}
    try:
        return json.loads(CALENDAR_EVENTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def get_cached_events() -> list[dict]:
    """Return cached calendar events (loaded from calendar_events.json on first access)."""
    global _EVENTS_CACHE
    if _EVENTS_CACHE is None:
        data = _read_calendar_file()
        events = data.get("events", [])
        _EVENTS_CACHE = events if isinstance(events, list) else []
    return _EVENTS_CACHE


def reload_calendar() -> None:
    """Reload calendar_events.json into the module-level cache."""
    global _EVENTS_CACHE
    data = _read_calendar_file()
    events = data.get("events", [])
    _EVENTS_CACHE = events if isinstance(events, list) else []


@dataclass(frozen=True)
class _ExpandedCalendar:
    holiday_dates: set[pd.Timestamp]
    exam_dates: set[pd.Timestamp]
    break_dates: set[pd.Timestamp]
    fest_dates: set[pd.Timestamp]
    break_ranges: list[tuple[pd.Timestamp, pd.Timestamp]]


def _to_ts(d: Any) -> pd.Timestamp | None:
    if d is None:
        return None
    try:
        ts = pd.to_datetime(d, errors="coerce")
    except Exception:
        return None
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts).normalize()


def _expand_dates(start: pd.Timestamp, end: pd.Timestamp) -> Iterable[pd.Timestamp]:
    cur = start.normalize()
    end = end.normalize()
    while cur <= end:
        yield cur
        cur = cur + timedelta(days=1)


_FEST_TOKENS = (
    "diwali",
    "holi",
    "navratri",
    "dussehra",
    "dussera",
    "eid",
    "christmas",
    "independence",
    "republic",
    "gandhi",
)


def _is_fest_like(name: str) -> bool:
    s = (name or "").strip().lower()
    return any(tok in s for tok in _FEST_TOKENS)


def _expand_events(events: list[dict]) -> _ExpandedCalendar:
    holiday_dates: set[pd.Timestamp] = set()
    exam_dates: set[pd.Timestamp] = set()
    break_dates: set[pd.Timestamp] = set()
    fest_dates: set[pd.Timestamp] = set()
    break_ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        if ev.get("affects_attendance") is False:
            continue

        ev_type = str(ev.get("type") or "").strip().lower()
        name = str(ev.get("name") or "")
        start = _to_ts(ev.get("date"))
        if start is None:
            continue
        end = _to_ts(ev.get("end_date")) or start
        if end < start:
            start, end = end, start

        is_range = end != start
        dates = list(_expand_dates(start, end))

        if ev_type == "exam":
            exam_dates.update(dates)
            continue

        if ev_type in ("holiday", "break", "vacation"):
            holiday_dates.update(dates)
            if is_range:
                break_dates.update(dates)
                break_ranges.append((start, end))
            elif _is_fest_like(name):
                fest_dates.add(start)
            continue

        # Unknown type: ignore (keeps behavior predictable)

    return _ExpandedCalendar(
        holiday_dates=holiday_dates,
        exam_dates=exam_dates,
        break_dates=break_dates,
        fest_dates=fest_dates,
        break_ranges=sorted(break_ranges, key=lambda x: (x[0], x[1])),
    )


def compute_calendar_features(target_date: pd.Timestamp, events: list[dict]) -> dict[str, int]:
    """
    Compute academic-calendar-aware features for a single target date.

    Inputs:
    - target_date: the date being predicted/trained on (normalized to a calendar day).
    - events: list of dicts loaded from `calendar_events.json` (each may be single-day
      or a date range via `end_date`).

    The function expands all ranges internally into individual dates and returns 9
    integer features:
    - is_holiday (0/1)
    - is_exam_day (0/1)
    - is_break (0/1)
    - is_fest_day (0/1)
    - days_to_nearest_holiday (int, capped at 30)
    - days_after_holiday (int, capped at 30)
    - days_to_next_exam (int, capped at 60)
    - is_sandwich_day (0/1)
    - is_post_break_monday (0/1)
    """
    d = pd.Timestamp(target_date).normalize()
    cal = _expand_events(events)

    is_holiday = int(d in cal.holiday_dates)
    is_exam_day = int(d in cal.exam_dates)
    is_break = int(d in cal.break_dates)
    is_fest_day = int(d in cal.fest_dates)

    # Nearest holiday distance (absolute days)
    if cal.holiday_dates:
        nearest = min(abs((d - hd).days) for hd in cal.holiday_dates)
        days_to_nearest_holiday = int(min(nearest, 30))
    else:
        days_to_nearest_holiday = 30

    # Days after most recent holiday (0 if holiday itself)
    if cal.holiday_dates:
        past = [hd for hd in cal.holiday_dates if hd <= d]
        if past:
            recent = max(past)
            days_after_holiday = int(min((d - recent).days, 30))
        else:
            days_after_holiday = 30
    else:
        days_after_holiday = 30

    # Days to next exam day (0 if exam day)
    if cal.exam_dates:
        future = [ed for ed in cal.exam_dates if ed >= d]
        if future:
            nxt = min(future)
            days_to_next_exam = int(min((nxt - d).days, 60))
        else:
            days_to_next_exam = 60
    else:
        days_to_next_exam = 60

    # Sandwich day: weekday that is wedged between two "off" days.
    # Off-day definition: weekend OR holiday (includes break days).
    def is_off(ts: pd.Timestamp) -> bool:
        ts = ts.normalize()
        return (ts.dayofweek >= 5) or (ts in cal.holiday_dates)

    prev_d = d - timedelta(days=1)
    next_d = d + timedelta(days=1)
    is_weekday = d.dayofweek < 5
    is_sandwich_day = int(is_weekday and (not is_off(d)) and is_off(prev_d) and is_off(next_d))

    # Post-break Monday: Monday immediately after a multi-day break range.
    is_post_break_monday = 0
    if d.dayofweek == 0 and cal.break_ranges:
        yesterday = d - timedelta(days=1)
        for start, end in cal.break_ranges:
            if (end - start).days >= 1 and start <= yesterday <= end and d not in cal.break_dates:
                is_post_break_monday = 1
                break

    return {
        "is_holiday": int(is_holiday),
        "is_exam_day": int(is_exam_day),
        "is_break": int(is_break),
        "is_fest_day": int(is_fest_day),
        "days_to_nearest_holiday": int(days_to_nearest_holiday),
        "days_after_holiday": int(days_after_holiday),
        "days_to_next_exam": int(days_to_next_exam),
        "is_sandwich_day": int(is_sandwich_day),
        "is_post_break_monday": int(is_post_break_monday),
    }

