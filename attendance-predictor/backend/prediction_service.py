"""
Shared ML loading, feature building, and prediction (used by Flask API and email scheduler).
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from calendar_features import compute_calendar_features, get_cached_events
from weather_service import get_weather_for_date

BACKEND_DIR = Path(__file__).resolve().parent
MODEL_DIR = BACKEND_DIR / "model"
MODEL_PATH = MODEL_DIR / "attendance_model.pkl"
FEATURE_COLS_PATH = MODEL_DIR / "feature_columns.pkl"
META_PATH = MODEL_DIR / "training_meta.pkl"
HISTORICAL_PATH = MODEL_DIR / "historical_daily.pkl"

DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

_artifacts_cache: tuple | None = None


def _get_cached_artifacts():
    global _artifacts_cache
    if _artifacts_cache is None:
        _artifacts_cache = load_artifacts()
    return _artifacts_cache


def reload_artifacts() -> None:
    global _artifacts_cache
    _artifacts_cache = None


def load_artifacts():
    if not MODEL_PATH.exists():
        return None, None, None, None
    model = joblib.load(MODEL_PATH)
    feature_names = joblib.load(FEATURE_COLS_PATH)
    meta = joblib.load(META_PATH) if META_PATH.exists() else {}
    historical = joblib.load(HISTORICAL_PATH) if HISTORICAL_PATH.exists() else None
    return model, feature_names, meta, historical


def _historical_series(historical: pd.DataFrame) -> pd.Series:
    s = historical.copy()
    s["date"] = pd.to_datetime(s["date"]).dt.normalize()
    s = s.sort_values("date").drop_duplicates("date", keep="last")
    return s.set_index("date")["attendance"]


def build_feature_row(
    target: pd.Timestamp,
    series: pd.Series,
    meta: dict,
) -> pd.Series:
    fb = meta.get("fallbacks", {})
    hist_mean = float(fb.get("historical_mean", series.mean() if len(series) else 0))
    last_date = series.index.max() if len(series) else None

    d = pd.Timestamp(target).normalize()
    prev = d - timedelta(days=1)
    week_ago = d - timedelta(days=7)

    def get_val(ts: pd.Timestamp) -> float:
        ts = ts.normalize()
        if ts in series.index:
            return float(series.loc[ts])
        return hist_mean

    lag_1 = get_val(prev)
    lag_7 = get_val(week_ago)

    sub = series[series.index < d]
    if len(sub) >= 7:
        rolling_7 = float(sub.tail(7).mean())
    else:
        rolling_7 = float(fb.get("rolling_7_fallback", hist_mean))
    if len(sub) >= 30:
        rolling_30 = float(sub.tail(30).mean())
    else:
        rolling_30 = float(fb.get("rolling_30_fallback", hist_mean))

    if last_date is not None and d > last_date:
        lag_1 = float(series.iloc[-1]) if len(series) else hist_mean
        if len(series) >= 7:
            rolling_7 = float(series.tail(7).mean())
        if len(series) >= 30:
            rolling_30 = float(series.tail(30).mean())
        elif len(series):
            rolling_30 = float(series.mean())

    dt = d
    last_dom = (dt + pd.offsets.MonthEnd(0)).day
    row = {
        "day_of_week": int(dt.dayofweek),
        "day_of_month": int(dt.day),
        "month": int(dt.month),
        "week_of_year": int(dt.isocalendar()[1]),
        "is_weekend": int(dt.dayofweek >= 5),
        "is_monday": int(dt.dayofweek == 0),
        "is_friday": int(dt.dayofweek == 4),
        "quarter": int((dt.month - 1) // 3 + 1),
        "day_of_year": int(dt.dayofyear),
        "is_month_start": int(dt.day <= 3),
        "is_month_end": int(dt.day >= last_dom - 2),
        "lag_1": lag_1,
        "lag_7": lag_7,
        "rolling_mean_7": rolling_7,
        "rolling_mean_30": rolling_30,
    }
    row.update(compute_calendar_features(dt, get_cached_events()))

    # Weather features — loaded from cache or live API; safe fallback built-in.
    weather = get_weather_for_date(dt.strftime("%Y-%m-%d"))
    row["temp_max"]           = float(weather.get("temp_max")           or 28.0)
    row["precipitation"]      = float(weather.get("precipitation")      or 0.0)
    row["is_rainy"]           = int(weather.get("is_rainy")             or 0)
    row["is_extreme_weather"] = int(weather.get("is_extreme_weather")   or 0)

    return pd.Series(row)


def tree_predictions(model, X: np.ndarray) -> np.ndarray:
    return np.array([t.predict(X)[0] for t in model.estimators_])


def adjust_prediction_for_calendar(
    target: pd.Timestamp,
    row: pd.Series,
    mean_pred: float,
    low: float,
    high: float,
    series: pd.Series,
) -> tuple[float, float, float]:
    """
    Hard rules applied after the forest prediction:
      - Sunday                → 0  (no classes)
      - Calendar holiday/break → 0  (institution closed)
      - Extreme weather day    → dampen by up to 40 %
      - Saturday               → cap at 15 % of historical mean
    """
    d = pd.Timestamp(target).normalize()

    # Sunday — always zero
    if d.dayofweek == 6:
        return 0.0, 0.0, 0.0

    # Calendar holiday or break day — always zero
    if int(row.get("is_holiday", 0)) == 1 or int(row.get("is_break", 0)) == 1:
        return 0.0, 0.0, 0.0

    # Extreme weather (heavy storms / flooding)
    if int(row.get("is_extreme_weather", 0)) == 1:
        factor = 0.60
        mean_pred = mean_pred * factor
        low       = low       * factor
        high      = high      * factor

    # Saturday — classes may run but at much lower turnout
    if int(row.get("is_weekend", 0)) == 1:
        cap = max(5.0, float(series.mean()) * 0.15 if len(series) else 5.0)
        mean_pred = min(mean_pred, cap)
        low       = min(low,  mean_pred)
        high      = min(high, mean_pred * 1.5)

    return mean_pred, low, high


def predict_for_date(target_str: str) -> tuple[dict, int]:
    model, feature_names, meta, historical = _get_cached_artifacts()
    if model is None or historical is None:
        raise RuntimeError("Model not trained. Run train_model.py first.")

    target = pd.to_datetime(target_str).normalize()
    series = _historical_series(historical)
    row = build_feature_row(target, series, meta)
    X = row[feature_names].values.astype(np.float64).reshape(1, -1)

    trees = tree_predictions(model, X)
    mean_pred = float(np.mean(trees))
    low = float(np.percentile(trees, 10))
    high = float(np.percentile(trees, 90))
    mean_pred, low, high = adjust_prediction_for_calendar(
        target, row, mean_pred, low, high, series
    )

    pred_int = int(round(mean_pred))
    low_i = int(round(low))
    high_i = int(round(high))

    hist = historical.copy()
    hist["date"] = pd.to_datetime(hist["date"])
    hist["dow"] = hist["date"].dt.dayofweek
    same_dow = hist[hist["dow"] == target.dayofweek]["attendance"]
    historical_avg = float(same_dow.mean()) if len(same_dow) else float(hist["attendance"].mean())

    last_hist = series.index.max() if len(series) else None

    # Weather summary for UI display
    weather_data = get_weather_for_date(target.strftime("%Y-%m-%d"))

    out = {
        "date": target.strftime("%Y-%m-%d"),
        "predicted_attendance": pred_int,
        "confidence_range": {"low": low_i, "high": high_i},
        "day_of_week": DAY_NAMES[target.dayofweek],
        "is_weekend": bool(target.dayofweek >= 5),
        "is_holiday": bool(int(row.get("is_holiday", 0)) == 1),
        "is_break": bool(int(row.get("is_break", 0)) == 1),
        "historical_avg": round(historical_avg),
        "weather": {
            "temp_max":      weather_data.get("temp_max"),
            "precipitation": weather_data.get("precipitation"),
            "description":   weather_data.get("description", ""),
            "icon":          weather_data.get("icon", "cloudy"),
            "is_rainy":      bool(weather_data.get("is_rainy", 0)),
            "is_extreme":    bool(weather_data.get("is_extreme_weather", 0)),
        },
    }
    if last_hist is not None:
        days_ahead = (target.date() - last_hist.date()).days
        if days_ahead > 90:
            out["warning"] = "Date is far beyond training data; accuracy may be reduced."
    return out, pred_int
