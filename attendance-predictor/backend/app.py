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

from prediction_service import (
    DAY_NAMES,
    adjust_prediction_for_calendar,
    build_feature_row,
    load_artifacts,
    predict_for_date,
    tree_predictions,
    _historical_series,
)

load_dotenv(Path(__file__).resolve().parent / ".env")

BACKEND_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = BACKEND_DIR / "email_settings.json"
NOTIFICATION_LOG_PATH = BACKEND_DIR / "notification_log.json"

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


def _maybe_start_scheduler():
    if os.getenv("RUN_EMAIL_SCHEDULER", "").lower() not in ("1", "true", "yes"):
        return
    from email_scheduler import start_scheduler_background

    start_scheduler_background()


if __name__ == "__main__":
    _maybe_start_scheduler()
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
