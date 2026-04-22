"""
Best-days recommendation logic for ranking dates in a range.

This is intentionally ranking-focused: predicted absolute headcount can be noisy
on mixed-scale datasets, so reasons are phrased relatively and the API includes
an explicit disclaimer.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
import google.generativeai as genai

from calendar_features import compute_calendar_features, get_cached_events
from prediction_service import DAY_NAMES, adjust_prediction_for_calendar, build_feature_row, load_artifacts, tree_predictions

def _normalize01(values: list[float]) -> list[float]:
    if not values:
        return []
    vmin = min(values)
    vmax = max(values)
    if vmax == vmin:
        return [0.5 for _ in values]
    return [(v - vmin) / (vmax - vmin) for v in values]


def _confidence_tightness(widths: list[float]) -> list[float]:
    """Higher is better (tighter band)."""
    if not widths:
        return []
    wmin = min(widths)
    wmax = max(widths)
    if wmax == wmin:
        return [0.5 for _ in widths]
    return [(wmax - w) / (wmax - wmin) for w in widths]


def _calendar_score(cal: dict[str, int]) -> float:
    """
    Calendar score in [0,1]. Penalize proximity to holidays/exams.
    Uses the same proximity signals as calendar_features.py.
    """
    d_h = int(cal.get("days_to_nearest_holiday", 30))
    d_e = int(cal.get("days_to_next_exam", 60))
    is_holiday = int(cal.get("is_holiday", 0))
    is_exam = int(cal.get("is_exam_day", 0))
    is_break = int(cal.get("is_break", 0))

    if is_holiday or is_exam:
        return 0.0
    if is_break:
        # Break days are generally not ideal for events; keep low but not zero.
        return 0.15

    # Within 7 days of a holiday, start penalizing.
    holiday_prox = max(0.0, (7.0 - float(min(d_h, 7))) / 7.0)
    # Within 10 days of an exam, start penalizing.
    exam_prox = max(0.0, (10.0 - float(min(d_e, 10))) / 10.0)
    penalty = min(1.0, 0.6 * holiday_prox + 0.4 * exam_prox)
    return float(max(0.0, 1.0 - penalty))


@dataclass(frozen=True)
class _Candidate:
    ts: pd.Timestamp
    predicted: int
    low: int
    high: int
    calendar: dict[str, int]
    dow: int
    score: float = 0.0
    reasons: list[str] | None = None
    warnings: list[str] | None = None


def _build_avoid_dates(
    start_ts: pd.Timestamp, end_ts: pd.Timestamp, events: list[dict]
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    cur = start_ts.normalize()
    while cur <= end_ts.normalize():
        cal = compute_calendar_features(cur, events)
        is_h = int(cal.get("is_holiday", 0)) == 1
        is_e = int(cal.get("is_exam_day", 0)) == 1
        prev = cur - timedelta(days=1)
        nxt = cur + timedelta(days=1)
        prev_cal = compute_calendar_features(prev, events)
        next_cal = compute_calendar_features(nxt, events)
        adj_to_h = int(prev_cal.get("is_holiday", 0)) == 1 or int(next_cal.get("is_holiday", 0)) == 1
        adj_to_e = int(prev_cal.get("is_exam_day", 0)) == 1 or int(next_cal.get("is_exam_day", 0)) == 1

        if is_h:
            out.append({"date": cur.strftime("%Y-%m-%d"), "reason": "Holiday"})
        elif is_e:
            out.append({"date": cur.strftime("%Y-%m-%d"), "reason": "Exam day"})
        elif adj_to_e:
            # Prefer specific direction for adjacent exam day.
            if int(prev_cal.get("is_exam_day", 0)) == 1:
                out.append({"date": cur.strftime("%Y-%m-%d"), "reason": "Day after exam"})
            else:
                out.append({"date": cur.strftime("%Y-%m-%d"), "reason": "Day before exam"})
        elif adj_to_h:
            if int(prev_cal.get("is_holiday", 0)) == 1:
                out.append({"date": cur.strftime("%Y-%m-%d"), "reason": "Day after holiday"})
            else:
                out.append({"date": cur.strftime("%Y-%m-%d"), "reason": "Day before holiday"})

        cur = cur + timedelta(days=1)

    # de-dupe by date, keep first reason
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in out:
        d = item["date"]
        if d in seen:
            continue
        seen.add(d)
        deduped.append(item)
    return deduped


def _rule_based_reasons(
    c: _Candidate,
    attendance_norm: float,
    dow_norm: float,
    cal_score: float,
    conf_score: float,
) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []

    if attendance_norm >= 0.85:
        reasons.append("Among the strongest predicted days in this range")
    elif attendance_norm >= 0.65:
        reasons.append("Predicted to be stronger than many nearby dates")

    if dow_norm >= 0.75 and c.dow not in (5, 6):
        reasons.append(f"{DAY_NAMES[c.dow]}s typically run higher in your history")

    if cal_score >= 0.8:
        reasons.append("No nearby holidays or exams expected to disrupt turnout")
    elif cal_score <= 0.35:
        warnings.append("Close to holidays/exams; turnout may be less consistent")

    if conf_score >= 0.75:
        reasons.append("Tighter model spread than most days in the window")
    elif conf_score <= 0.25:
        warnings.append("Wider model spread than most days in the window")

    if int(c.calendar.get("is_sandwich_day", 0)) == 1:
        warnings.append("Sandwich day; attendance patterns can be unpredictable")
    if int(c.calendar.get("is_post_break_monday", 0)) == 1:
        warnings.append("Post-break Monday; turnout can be volatile")

    if not reasons:
        reasons.append("Solid balance of predicted turnout and calendar conditions")

    # Keep reasons short-ish; endpoint later enforces LLM rewrite constraints if enabled.
    return reasons[:4], warnings[:3]


def _rewrite_reasons_with_gemini(
    recommendations: list[dict[str, Any]],
    event_type: str,
) -> dict[str, Any] | None:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None

    try:
        payload = {
            "event_type": event_type,
            "recommendations": [
                {
                    "date": r.get("date"),
                    "day_of_week": r.get("day_of_week"),
                    "reasons": r.get("reasons", []),
                    "warnings": r.get("warnings", []),
                }
                for r in recommendations
            ],
        }
        prompt = (
            "You rewrite reasons for a 'best days' recommender.\n"
            "Rules:\n"
            "- Use ONLY relative phrasing; do NOT promise exact headcounts.\n"
            "- Keep each reason under 15 words.\n"
            "- Return ONLY valid JSON. No preamble. No markdown fences.\n"
            "- Output schema: {\"recommendations\":[{\"date\":\"YYYY-MM-DD\",\"reasons\":[...],\"warnings\":[...]}]}.\n"
            f"- Event type: {event_type}\n\n"
            f"Input JSON:\n{json.dumps(payload, ensure_ascii=False)}\n"
        )
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.3,
            },
        )
        response = model.generate_content(prompt)
        raw_text = getattr(response, "text", None) or ""
        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict):
            return None
        return parsed
    except Exception:
        # Never fail the endpoint due to LLM issues.
        return None


def _maybe_rewrite_reasons_with_gemini(
    recommendations: list[dict[str, Any]],
    event_type: str,
) -> list[dict[str, Any]]:
    parsed = _rewrite_reasons_with_gemini(recommendations, event_type=event_type)
    if not parsed:
        return recommendations
    rewritten = {
        item.get("date"): item
        for item in parsed.get("recommendations", [])
        if isinstance(item, dict)
    }
    if not rewritten:
        return recommendations

    out: list[dict[str, Any]] = []
    for r in recommendations:
        d = r.get("date")
        if d in rewritten:
            rr = rewritten[d]
            reasons = rr.get("reasons")
            warnings = rr.get("warnings")
            if isinstance(reasons, list) and all(isinstance(x, str) for x in reasons):
                r["reasons"] = reasons[:5]
            if isinstance(warnings, list) and all(isinstance(x, str) for x in warnings):
                r["warnings"] = warnings[:5]
        out.append(r)
    return out


def find_best_days(
    start: str,
    end: str,
    top_n: int = 3,
    min_attendance: int | None = None,
    event_type: str = "event",
    include_saturdays: bool = False,
) -> dict[str, Any]:
    s = pd.to_datetime(start).normalize()
    e = pd.to_datetime(end).normalize()
    if e < s:
        raise ValueError("end must be >= start")

    model, feature_names, meta, historical = load_artifacts()
    if model is None or historical is None or feature_names is None:
        raise RuntimeError("Model not trained. Run train_model.py first.")

    hist = historical.copy()
    hist["date"] = pd.to_datetime(hist["date"]).dt.normalize()
    hist["dow"] = hist["date"].dt.dayofweek
    dow_mean = hist.groupby("dow")["attendance"].mean().to_dict()

    # Candidate generation + sequential extension (like /api/predict-range).
    events = get_cached_events()
    series = hist.sort_values("date").drop_duplicates("date", keep="last").set_index("date")["attendance"]
    extended = series.copy()

    candidates: list[_Candidate] = []
    cur = s
    while cur <= e:
        d = cur.normalize()
        dow = int(d.dayofweek)

        # Skip Sunday always; skip Saturday unless explicitly included.
        if dow == 6:
            cur = cur + timedelta(days=1)
            continue
        if dow == 5 and not include_saturdays:
            cur = cur + timedelta(days=1)
            continue

        row = build_feature_row(d, extended, meta)
        X = row[feature_names].values.astype(float).reshape(1, -1)
        trees = tree_predictions(model, X)
        mean_pred = float(trees.mean())
        low = float(np.percentile(trees, 10))
        high = float(np.percentile(trees, 90))
        mean_pred, low, high = adjust_prediction_for_calendar(d, row, mean_pred, low, high, extended)

        pred_int = int(round(mean_pred))
        low_i = int(round(low))
        high_i = int(round(high))

        cal = compute_calendar_features(d, events)
        candidates.append(
            _Candidate(
                ts=d,
                predicted=pred_int,
                low=low_i,
                high=high_i,
                calendar=cal,
                dow=dow,
            )
        )

        # Extend for future lag/rolling features.
        extended = extended.copy()
        extended.loc[d] = float(pred_int)
        extended = extended.sort_index()
        cur = cur + timedelta(days=1)

    if not candidates:
        return {
            "recommendations": [],
            "avoid_dates": _build_avoid_dates(s, e, events),
            "range": {"start": s.strftime("%Y-%m-%d"), "end": e.strftime("%Y-%m-%d")},
            "disclaimer": "Ranking reflects relative strength of days; absolute predicted counts have limited precision on the current dataset.",
        }

    # Component scores (normalized across the generated range).
    preds = [float(c.predicted) for c in candidates]
    attendance_scores = _normalize01(preds)

    dow_vals = [float(dow_mean.get(c.dow, float(hist["attendance"].mean()))) for c in candidates]
    dow_scores = _normalize01(dow_vals)

    cal_scores = [float(_calendar_score(c.calendar)) for c in candidates]

    widths = [float(max(0, c.high - c.low)) for c in candidates]
    conf_scores = _confidence_tightness(widths)

    # Weighted total (ranking-focused).
    total_scores: list[float] = []
    for i in range(len(candidates)):
        total = (
            0.50 * float(attendance_scores[i])
            + 0.20 * float(dow_scores[i])
            + 0.20 * float(cal_scores[i])
            + 0.10 * float(conf_scores[i])
        )
        total_scores.append(float(total))

    # Attach reasons/warnings and produce response dicts.
    last_hist_date = None
    try:
        if meta and meta.get("last_historical_date"):
            last_hist_date = pd.to_datetime(meta["last_historical_date"]).normalize()
    except Exception:
        last_hist_date = None

    recs: list[dict[str, Any]] = []
    for i, c in enumerate(candidates):
        reasons, warnings = _rule_based_reasons(
            c=c,
            attendance_norm=float(attendance_scores[i]),
            dow_norm=float(dow_scores[i]),
            cal_score=float(cal_scores[i]),
            conf_score=float(conf_scores[i]),
        )

        if last_hist_date is not None:
            days_ahead = int((c.ts.date() - last_hist_date.date()).days)
            if days_ahead > 90:
                warnings = list(warnings) + ["Far beyond training history; ranking may be less stable"]

        recs.append(
            {
                "date": c.ts.strftime("%Y-%m-%d"),
                "day_of_week": DAY_NAMES[c.dow],
                "predicted_attendance": int(c.predicted),
                "confidence_range": {"low": int(c.low), "high": int(c.high)},
                "score": float(total_scores[i]),
                "reasons": reasons,
                "warnings": warnings,
            }
        )

    # Apply min_attendance filter at the end.
    if min_attendance is not None:
        recs = [r for r in recs if int(r.get("predicted_attendance", 0)) >= int(min_attendance)]

    recs = sorted(recs, key=lambda r: float(r.get("score", 0.0)), reverse=True)
    recs = recs[: max(1, int(top_n))]
    for idx, r in enumerate(recs, start=1):
        r["rank"] = idx
        # round for readability
        r["score"] = float(round(float(r["score"]), 4))

    # Optional LLM rewrite (never fatal).
    recs = _maybe_rewrite_reasons_with_gemini(recs, event_type=event_type)

    return {
        "recommendations": recs,
        "avoid_dates": _build_avoid_dates(s, e, events),
        "range": {"start": s.strftime("%Y-%m-%d"), "end": e.strftime("%Y-%m-%d")},
        "disclaimer": "Ranking reflects relative strength of days; absolute predicted counts have limited precision on the current dataset.",
    }

