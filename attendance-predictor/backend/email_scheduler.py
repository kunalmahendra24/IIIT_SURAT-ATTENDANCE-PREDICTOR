"""
Daily email notifications via APScheduler.
Run standalone: python email_scheduler.py
Or set RUN_EMAIL_SCHEDULER=1 when starting app.py to embed the scheduler.
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

BACKEND_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = BACKEND_DIR / "email_settings.json"
NOTIFICATION_LOG_PATH = BACKEND_DIR / "notification_log.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("email_scheduler")


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


def append_notification_log(entry: dict) -> None:
    log = []
    if NOTIFICATION_LOG_PATH.exists():
        try:
            log = json.loads(NOTIFICATION_LOG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log = []
    log.append(entry)
    NOTIFICATION_LOG_PATH.write_text(
        json.dumps(log[-200:], indent=2), encoding="utf-8"
    )


def send_forecast_email(to_email: str, payload: dict, predicted: int) -> None:
    settings = load_settings()
    smtp_host = settings.get("smtp_host") or os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(settings.get("smtp_port") or 587)
    login_user = settings.get("sender_email") or os.getenv("SENDER_EMAIL")
    password = settings.get("sender_password") or os.getenv("SENDER_PASSWORD")
    mail_from = (
        (settings.get("mail_from") or "").strip()
        or os.getenv("SMTP_FROM_EMAIL", "").strip()
        or login_user
    )
    if not login_user or not password:
        raise RuntimeError("SMTP sender_email (login) and sender_password must be configured")

    d = payload["date"]
    dow = payload["day_of_week"]
    subj = f"📊 Attendance Forecast for {d} — {dow}"
    lo = payload["confidence_range"]["low"]
    hi = payload["confidence_range"]["high"]
    hist_avg = payload.get("historical_avg", 0)
    meals = int((predicted * 1.05) + 0.999)
    buses = max(1, (predicted + 29) // 30)
    rooms = max(1, (predicted + 24) // 25)

    html = f"""
    <html><body style="font-family:Segoe UI,Arial,sans-serif;color:#1B3A5C;">
    <h2>Attendance forecast</h2>
    <p><strong>Date:</strong> {d} ({dow})</p>
    <p><strong>Predicted attendance:</strong> {predicted}</p>
    <p><strong>Expected range:</strong> {lo} – {hi}</p>
    <p><strong>Historical avg (same weekday):</strong> {hist_avg}</p>
    <h3>Resource planning</h3>
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;">
      <tr style="background:#1B3A5C;color:#fff;"><th>Resource</th><th>Suggested capacity</th><th>Based on</th></tr>
      <tr><td>Canteen meals</td><td>{meals}</td><td>Predicted + 5%</td></tr>
      <tr><td>Transport</td><td>{buses} buses</td><td>~30 per bus</td></tr>
      <tr><td>Classrooms</td><td>{rooms}</td><td>~25 per room</td></tr>
    </table>
    <p style="margin-top:24px;color:#666;font-size:13px;">This is an automated prediction. Actual attendance may vary.</p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subj
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(login_user, password)
        server.sendmail(mail_from, [to_email], msg.as_string())

    logger.info("Sent forecast email to %s at %s", to_email, datetime.utcnow().isoformat())


def run_daily_job():
    from prediction_service import predict_for_date

    settings = load_settings()
    if not settings.get("enabled"):
        logger.info("Notifications disabled; skipping job")
        return
    to_email = settings.get("staff_email")
    if not to_email:
        logger.warning("No staff_email configured")
        return
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        payload, pred = predict_for_date(tomorrow)
        send_forecast_email(to_email, payload, pred)
        append_notification_log(
            {"sent_at": datetime.utcnow().isoformat() + "Z", "to": to_email, "scheduled": True}
        )
    except Exception:
        logger.exception("Daily notification failed")


def parse_send_time(s: str) -> tuple[int, int]:
    parts = (s or "18:00").strip().split(":")
    h = int(parts[0]) if parts else 18
    m = int(parts[1]) if len(parts) > 1 else 0
    return h, m


_scheduler: BackgroundScheduler | None = None


def start_scheduler_background():
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    settings = load_settings()
    h, m = parse_send_time(settings.get("send_time", "18:00"))
    sched = BackgroundScheduler()
    sched.add_job(run_daily_job, "cron", hour=h, minute=m, id="daily_attendance_email")
    sched.start()
    _scheduler = sched
    logger.info("Background scheduler started; daily job at %02d:%02d", h, m)
    return sched


if __name__ == "__main__":
    from apscheduler.schedulers.blocking import BlockingScheduler

    settings = load_settings()
    h, m = parse_send_time(settings.get("send_time", "18:00"))
    sched = BlockingScheduler()
    sched.add_job(run_daily_job, "cron", hour=h, minute=m)
    logger.info("Blocking scheduler running; job at %02d:%02d (Ctrl+C to stop)", h, m)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        pass
