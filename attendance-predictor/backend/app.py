"""
Flask API for attendance predictions, model metadata, and email settings.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

from calendar_features import reload_calendar
from calendar_service import extract_events_from_pdf, validate_calendar_payload
from recommendation_service import find_best_days
from retrain_service import restore_artifacts, retrain_with_safety_net
from weather_service import (
    get_location,
    get_weather_for_date,
    invalidate_weather_cache,
    save_location,
)
from prediction_service import (
    DAY_NAMES,
    adjust_prediction_for_calendar,
    build_feature_row,
    load_artifacts,
    predict_for_date,
    reload_artifacts,
    tree_predictions,
    _historical_series,
)

load_dotenv(Path(__file__).resolve().parent / ".env")

BACKEND_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = BACKEND_DIR / "email_settings.json"
NOTIFICATION_LOG_PATH = BACKEND_DIR / "notification_log.json"
CALENDAR_PATH = BACKEND_DIR / "calendar_events.json"
CALENDAR_PREV_PATH = BACKEND_DIR / "calendar_events.prev.json"

app = Flask(__name__)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "http://localhost:5173",
                "http://localhost:5174",
                "http://localhost:5175",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
                "http://127.0.0.1:5175",
            ]
        }
    },
    supports_credentials=True,
)


def _default_settings() -> dict:
    return {
        "staff_email": os.getenv("STAFF_EMAIL", ""),
        "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "sender_email": os.getenv("SENDER_EMAIL", ""),
        "sender_password": os.getenv("SENDER_PASSWORD", ""),
        "mail_from": os.getenv("SMTP_FROM_EMAIL", ""),
        "enabled": False,
        "send_time": os.getenv("NOTIFICATION_TIME", "18:00"),
    }


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            base = _default_settings()
            base.update({k: v for k, v in data.items() if v is not None})
            return base
        except (json.JSONDecodeError, OSError):
            pass
    return _default_settings()


def save_settings(data: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_notification_log(entry: dict) -> None:
    log = []
    if NOTIFICATION_LOG_PATH.exists():
        try:
            log = json.loads(NOTIFICATION_LOG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log = []
    log.append(entry)
    NOTIFICATION_LOG_PATH.write_text(json.dumps(log[-200:], indent=2), encoding="utf-8")


def get_last_notification_time() -> str | None:
    if not NOTIFICATION_LOG_PATH.exists():
        return None
    try:
        log = json.loads(NOTIFICATION_LOG_PATH.read_text(encoding="utf-8"))
        if log:
            return log[-1].get("sent_at")
    except (json.JSONDecodeError, OSError):
        pass
    return None


@app.route("/api/predict", methods=["GET"])
def api_predict():
    d = request.args.get("date")
    if not d:
        return jsonify({"error": "Missing date query parameter (YYYY-MM-DD)"}), 400
    try:
        payload, _ = predict_for_date(d)
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/predict-range", methods=["GET"])
def api_predict_range():
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        return jsonify({"error": "Missing start or end (YYYY-MM-DD)"}), 400
    try:
        s = pd.to_datetime(start).normalize()
        e = pd.to_datetime(end).normalize()
        if e < s:
            return jsonify({"error": "end must be >= start"}), 400
        model, feature_names, meta, historical = load_artifacts()
        if model is None or historical is None:
            return jsonify({"error": "Model not found"}), 503
        series = _historical_series(historical)
        extended = series.copy()
        out = []
        cur = s
        while cur <= e:
            row = build_feature_row(cur, extended, meta)
            X = row[feature_names].values.astype(float).reshape(1, -1)
            trees = tree_predictions(model, X)
            mean_pred = float(trees.mean())
            low = float(np.percentile(trees, 10))
            high = float(np.percentile(trees, 90))
            mean_pred, low, high = adjust_prediction_for_calendar(
                cur, row, mean_pred, low, high, extended
            )
            pred_int = int(round(mean_pred))
            low_i = int(round(low))
            high_i = int(round(high))
            out.append(
                {
                    "date": cur.strftime("%Y-%m-%d"),
                    "predicted_attendance": pred_int,
                    "confidence_range": {"low": low_i, "high": high_i},
                    "day_of_week": DAY_NAMES[cur.dayofweek],
                }
            )
            extended = extended.copy()
            extended.loc[cur.normalize()] = float(pred_int)
            extended = extended.sort_index()
            cur = cur + timedelta(days=1)
        return jsonify({"predictions": out})
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500


@app.route("/api/historical", methods=["GET"])
def api_historical():
    _, _, _, historical = load_artifacts()
    if historical is None:
        return jsonify({"error": "No historical data"}), 503
    df = historical.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    records = df.to_dict(orient="records")
    return jsonify({"data": records})


@app.route("/api/model-info", methods=["GET"])
def api_model_info():
    _, feature_names, meta, _hist = load_artifacts()
    if not meta:
        return jsonify({"error": "No training metadata"}), 503
    return jsonify(
        {
            "trained_at": meta.get("trained_at"),
            "n_records": meta.get("n_records"),
            "metrics": meta.get("metrics"),
            "feature_importances": meta.get("feature_importances"),
            "feature_columns": feature_names,
            "attendance_summary": meta.get("attendance_summary"),
            "last_historical_date": meta.get("last_historical_date"),
        }
    )


@app.route("/api/send-notification", methods=["POST"])
def api_send_notification():
    from email_scheduler import send_forecast_email

    body = request.get_json(silent=True) or {}
    email = body.get("staff_email") or load_settings().get("staff_email")
    if not email:
        return jsonify({"error": "staff_email required in body or settings"}), 400
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        payload, pred = predict_for_date(tomorrow)
        send_forecast_email(email, payload, pred)
        append_notification_log({"sent_at": datetime.utcnow().isoformat() + "Z", "to": email})
        return jsonify({"ok": True, "message": f"Notification sent to {email}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/email", methods=["POST"])
def api_settings_email():
    body = request.get_json(silent=True) or {}
    current = load_settings()
    for key in (
        "staff_email",
        "smtp_host",
        "smtp_port",
        "sender_email",
        "sender_password",
        "mail_from",
        "enabled",
        "send_time",
    ):
        if key in body:
            current[key] = body[key]
    if "smtp_port" in body:
        current["smtp_port"] = int(current["smtp_port"])
    save_settings(current)
    safe = {k: v for k, v in current.items() if k != "sender_password"}
    safe["sender_password_set"] = bool(current.get("sender_password"))
    return jsonify(safe)


@app.route("/api/settings/email", methods=["GET"])
def api_get_settings():
    current = load_settings()
    safe = {k: v for k, v in current.items() if k != "sender_password"}
    safe["sender_password_set"] = bool(current.get("sender_password"))
    safe["last_notification_at"] = get_last_notification_time()
    return jsonify(safe)


@app.route("/api/calendar/events", methods=["GET"])
def api_calendar_events():
    if not CALENDAR_PATH.exists():
        return jsonify(
            {
                "academic_year": "",
                "semester": "",
                "events": [],
                "last_updated": None,
                "updated_by": None,
            }
        )
    try:
        data = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/calendar/upload", methods=["POST"])
def api_calendar_upload():
    # Max 10 MB
    if request.content_length is not None and request.content_length > 10 * 1024 * 1024:
        return jsonify({"error": "File too large (max 10MB)"}), 413

    if "pdf" not in request.files:
        return jsonify({"error": 'Missing multipart file field "pdf"'}), 400
    f = request.files["pdf"]
    pdf_bytes = f.read()
    if not pdf_bytes:
        return jsonify({"error": "Empty file"}), 400
    if len(pdf_bytes) > 10 * 1024 * 1024:
        return jsonify({"error": "File too large (max 10MB)"}), 413

    try:
        extracted = extract_events_from_pdf(pdf_bytes)
        warnings = extracted.pop("warnings", []) if isinstance(extracted, dict) else []
        return jsonify({**extracted, "warnings": warnings})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/calendar/save", methods=["POST"])
def api_calendar_save():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Invalid JSON body"}), 400

    cleaned, warnings = validate_calendar_payload(body)

    # Preserve the original schema fields if present (academic_year/semester already in cleaned).
    saved = {
        "academic_year": cleaned.get("academic_year", ""),
        "semester": cleaned.get("semester", ""),
        "events": cleaned.get("events", []),
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "updated_by": "dashboard",
    }

    try:
        if CALENDAR_PATH.exists():
            CALENDAR_PREV_PATH.write_text(CALENDAR_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        CALENDAR_PATH.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")

        # Hot reload cached calendar data for feature computation & recommendations.
        reload_calendar()

        return jsonify({**saved, "warnings": warnings})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/calendar/retrain", methods=["POST"])
def api_calendar_retrain():
    try:
        out = retrain_with_safety_net()
        # Match requested response shape (only include selected metric keys)
        def pick(m: dict) -> dict:
            return {k: m.get(k) for k in ("mae", "mdape", "wmape", "r2") if k in m}

        resp = {
            "status": out.get("status"),
            "old_metrics": pick(out.get("old_metrics") or {}),
            "new_metrics": pick(out.get("new_metrics") or {}),
            "improvement": out.get("improvement") or {},
            "trained_at": out.get("trained_at"),
        }
        if out.get("status") == "reverted":
            resp["reverted_reason"] = out.get("reverted_reason", "Model reverted")
        return jsonify(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/calendar/rollback", methods=["POST"])
def api_calendar_rollback():
    try:
        # Restore model artifacts
        restore_artifacts()
    except FileNotFoundError as fe:
        return jsonify({"error": str(fe)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    calendar_restored = False
    try:
        if CALENDAR_PREV_PATH.exists():
            CALENDAR_PATH.write_text(CALENDAR_PREV_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            calendar_restored = True
    except Exception:
        calendar_restored = False

    # Hot reload caches
    reload_artifacts()
    reload_calendar()

    restored_at = datetime.utcnow().isoformat() + "Z"
    # Report restored metrics (best-effort)
    restored_metrics = {}
    try:
        _m, _f, meta, _h = load_artifacts()
        if meta and isinstance(meta, dict):
            mm = meta.get("metrics", {}) or {}
            restored_metrics = {k: mm.get(k) for k in ("mae", "mdape", "wmape", "r2") if k in mm}
    except Exception:
        restored_metrics = {}

    return jsonify(
        {
            "status": "ok",
            "restored_metrics": restored_metrics,
            "calendar_restored": calendar_restored,
            "restored_at": restored_at,
        }
    )


@app.route("/api/best-days", methods=["GET"])
def api_best_days():
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        return jsonify({"error": "Missing start or end (YYYY-MM-DD)"}), 400

    top_n = request.args.get("top_n", "3")
    min_attendance = request.args.get("min_attendance")
    event_type = request.args.get("event_type", "event")
    include_saturdays = request.args.get("include_saturdays", "false")

    try:
        top_n_i = int(top_n)
        top_n_i = max(1, min(15, top_n_i))
    except Exception:
        top_n_i = 3

    min_att_i: int | None
    try:
        min_att_i = int(min_attendance) if min_attendance not in (None, "") else None
    except Exception:
        min_att_i = None

    include_sat = str(include_saturdays).lower() in ("1", "true", "yes", "on")

    try:
        out = find_best_days(
            start=start,
            end=end,
            top_n=top_n_i,
            min_attendance=min_att_i,
            event_type=event_type,
            include_saturdays=include_sat,
        )
        return jsonify(out)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/location", methods=["GET"])
def api_get_location():
    lat, lon, name = get_location()
    return jsonify({"lat": lat, "lon": lon, "name": name})


@app.route("/api/settings/location", methods=["POST"])
def api_set_location():
    body = request.get_json(silent=True) or {}
    try:
        lat  = float(body.get("lat",  0))
        lon  = float(body.get("lon",  0))
        name = str(body.get("name", "")).strip()
    except (TypeError, ValueError) as e:
        return jsonify({"error": f"Invalid lat/lon: {e}"}), 400

    if not (-90 <= lat <= 90):
        return jsonify({"error": "lat must be between -90 and 90"}), 400
    if not (-180 <= lon <= 180):
        return jsonify({"error": "lon must be between -180 and 180"}), 400
    if not name:
        return jsonify({"error": "name is required"}), 400

    save_location(lat, lon, name)
    return jsonify({"ok": True, "lat": lat, "lon": lon, "name": name})


@app.route("/api/weather/today", methods=["GET"])
def api_weather_today():
    from datetime import date as _date
    d = request.args.get("date") or _date.today().isoformat()
    lat, lon, name = get_location()
    try:
        w = get_weather_for_date(d, lat=lat, lon=lon)
        return jsonify({**w, "location": name, "date": d})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _maybe_start_scheduler():
    if os.getenv("RUN_EMAIL_SCHEDULER", "").lower() not in ("1", "true", "yes"):
        return
    from email_scheduler import start_scheduler_background

    start_scheduler_background()


if __name__ == "__main__":
    _maybe_start_scheduler()
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
