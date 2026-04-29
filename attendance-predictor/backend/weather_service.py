"""
Fetch weather data via the Open-Meteo API (free, no API key required).

Historical archive  : https://archive-api.open-meteo.com/v1/archive
Forecast (≤ 16 days): https://api.open-meteo.com/v1/forecast

Default location: Surat, Gujarat  (21.1702 °N, 72.8311 °E)

Override with env vars LOCATION_LAT / LOCATION_LON / LOCATION_NAME,
or by persisting location_settings.json next to this file (via /api/settings/location).
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

import requests

BACKEND_DIR            = Path(__file__).resolve().parent
WEATHER_CACHE_PATH     = BACKEND_DIR / "weather_cache.json"
LOCATION_SETTINGS_PATH = BACKEND_DIR / "location_settings.json"

DEFAULT_LAT  = 21.1702   # Surat, Gujarat
DEFAULT_LON  = 72.8311
DEFAULT_NAME = "Surat, Gujarat"

HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL   = "https://api.open-meteo.com/v1/forecast"
DAILY_VARS     = "temperature_2m_max,precipitation_sum,weather_code"
TIMEZONE       = "Asia/Kolkata"

# WMO weather code → (description, icon)
_WMO_MAP: list[tuple[tuple[int, int] | tuple[int, None], str, str]] = [
    ((0,   0),   "Clear sky",      "clear"),
    ((1,   3),   "Partly cloudy",  "cloudy"),
    ((45,  48),  "Foggy",          "fog"),
    ((51,  67),  "Drizzle / Rain", "rain"),
    ((71,  77),  "Snowfall",       "snow"),
    ((80,  82),  "Rain showers",   "rain"),
    ((85,  86),  "Snow showers",   "snow"),
    ((95,  99),  "Thunderstorm",   "storm"),
]


def _wmo_label(code: int | None) -> tuple[str, str]:
    """Return (description, icon_key) for a WMO weather code."""
    if code is None:
        return "Unknown", "cloudy"
    for (lo, hi), desc, icon in _WMO_MAP:
        if lo <= code <= hi:
            return desc, icon
    return "Unknown", "cloudy"


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

_WEATHER_CACHE: dict[str, dict] = {}
_cache_loaded = False


def _load_cache() -> None:
    global _WEATHER_CACHE, _cache_loaded
    if _cache_loaded:
        return
    if WEATHER_CACHE_PATH.exists():
        try:
            _WEATHER_CACHE = json.loads(WEATHER_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _WEATHER_CACHE = {}
    _cache_loaded = True


def _save_cache() -> None:
    try:
        WEATHER_CACHE_PATH.write_text(
            json.dumps(_WEATHER_CACHE, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _cache_key(date_str: str, lat: float, lon: float) -> str:
    return f"{date_str}|{lat:.4f}|{lon:.4f}"


# ---------------------------------------------------------------------------
# Location helpers
# ---------------------------------------------------------------------------

def get_location() -> tuple[float, float, str]:
    """Return (lat, lon, name) from location_settings.json → env → defaults."""
    if LOCATION_SETTINGS_PATH.exists():
        try:
            data = json.loads(LOCATION_SETTINGS_PATH.read_text(encoding="utf-8"))
            lat  = float(data.get("lat",  DEFAULT_LAT))
            lon  = float(data.get("lon",  DEFAULT_LON))
            name = str(data.get("name",   DEFAULT_NAME))
            return lat, lon, name
        except Exception:
            pass
    lat  = float(os.getenv("LOCATION_LAT",  str(DEFAULT_LAT)))
    lon  = float(os.getenv("LOCATION_LON",  str(DEFAULT_LON)))
    name = str(os.getenv("LOCATION_NAME", DEFAULT_NAME))
    return lat, lon, name


def save_location(lat: float, lon: float, name: str) -> None:
    """Persist location to location_settings.json and invalidate cache."""
    LOCATION_SETTINGS_PATH.write_text(
        json.dumps({"lat": lat, "lon": lon, "name": name}, indent=2),
        encoding="utf-8",
    )
    invalidate_weather_cache()


def invalidate_weather_cache() -> None:
    """Drop all in-memory weather cache entries (call after changing location)."""
    global _WEATHER_CACHE, _cache_loaded
    _WEATHER_CACHE = {}
    _cache_loaded  = False
    if WEATHER_CACHE_PATH.exists():
        try:
            WEATHER_CACHE_PATH.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _parse_response(data: dict) -> dict[str, dict]:
    daily  = data.get("daily", {})
    dates  = daily.get("time", [])
    tmax   = daily.get("temperature_2m_max",  [])
    precip = daily.get("precipitation_sum",   [])
    codes  = daily.get("weather_code",        [])
    out: dict[str, dict] = {}
    for i, d in enumerate(dates):
        t  = tmax[i]   if i < len(tmax)   else None
        p  = precip[i] if i < len(precip) else None
        wc = codes[i]  if i < len(codes)  else None
        desc, icon = _wmo_label(wc)
        out[str(d)] = {
            "temp_max":           float(t)   if t  is not None else None,
            "precipitation":      float(p)   if p  is not None else None,
            "weather_code":       int(wc)    if wc is not None else None,
            "description":        desc,
            "icon":               icon,
            "is_rainy":           int((p or 0.0) > 1.0),
            "is_extreme_weather": int(wc is not None and wc >= 80),
        }
    return out


def _fetch_historical(start: str, end: str, lat: float, lon: float) -> dict[str, dict]:
    params = {
        "latitude":   lat, "longitude":  lon,
        "start_date": start, "end_date": end,
        "daily":      DAILY_VARS,
        "timezone":   TIMEZONE,
    }
    try:
        r = requests.get(HISTORICAL_URL, params=params, timeout=30)
        r.raise_for_status()
        return _parse_response(r.json())
    except Exception as e:
        print(f"[weather] historical fetch failed for {start}–{end}: {e}")
        return {}


def _fetch_forecast(lat: float, lon: float, days: int = 16) -> dict[str, dict]:
    params = {
        "latitude":      lat, "longitude":   lon,
        "forecast_days": min(days, 16),
        "daily":         DAILY_VARS,
        "timezone":      TIMEZONE,
    }
    try:
        r = requests.get(FORECAST_URL, params=params, timeout=15)
        r.raise_for_status()
        return _parse_response(r.json())
    except Exception as e:
        print(f"[weather] forecast fetch failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _neutral() -> dict:
    """Neutral fallback when data is unavailable (no rain, typical temp)."""
    return {
        "temp_max":           28.0,
        "precipitation":       0.0,
        "weather_code":          1,
        "description":         "Partly cloudy",
        "icon":                "cloudy",
        "is_rainy":              0,
        "is_extreme_weather":    0,
    }


def _climatology(date_str: str, lat: float, lon: float) -> dict:
    """
    For dates beyond the 16-day forecast horizon use the same calendar date
    from the previous year as a seasonal proxy.
    """
    try:
        target = date.fromisoformat(date_str)
        proxy  = target.replace(year=target.year - 1).isoformat()
        ck     = _cache_key(proxy, lat, lon)
        _load_cache()
        if ck in _WEATHER_CACHE:
            return _WEATHER_CACHE[ck]
        fetched = _fetch_historical(proxy, proxy, lat, lon)
        if fetched:
            w = next(iter(fetched.values()))
            _WEATHER_CACHE[ck] = w
            _save_cache()
            return w
    except Exception:
        pass
    return _neutral()


def get_weather_for_date(
    date_str: str,
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    """
    Return weather feature dict for a single date.
    Keys: temp_max, precipitation, weather_code, description, icon,
          is_rainy (0/1), is_extreme_weather (0/1).
    Falls back gracefully if the API is unreachable.
    """
    _load_cache()
    if lat is None or lon is None:
        lat, lon, _ = get_location()

    ck = _cache_key(date_str, lat, lon)
    if ck in _WEATHER_CACHE:
        return _WEATHER_CACHE[ck]

    today     = date.today()
    target    = date.fromisoformat(date_str)
    days_diff = (target - today).days

    if days_diff <= 0:
        fetched = _fetch_historical(date_str, date_str, lat, lon)
    elif days_diff <= 16:
        fetched = _fetch_forecast(lat, lon, days=days_diff + 2)
    else:
        return _climatology(date_str, lat, lon)

    for d, w in fetched.items():
        _WEATHER_CACHE[_cache_key(d, lat, lon)] = w
    _save_cache()
    return _WEATHER_CACHE.get(ck, _neutral())


def get_weather_for_range(
    start_date: str,
    end_date: str,
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, dict]:
    """
    Batch-fetch weather for a date range — efficient for training pipelines.
    Returns {date_str: weather_dict, ...}.
    """
    _load_cache()
    if lat is None or lon is None:
        lat, lon, _ = get_location()

    s     = date.fromisoformat(start_date)
    e     = date.fromisoformat(end_date)
    today = date.today()

    missing_hist: list[str] = []
    missing_fore: list[str] = []
    result: dict[str, dict] = {}

    cur = s
    while cur <= e:
        ds = cur.isoformat()
        ck = _cache_key(ds, lat, lon)
        if ck in _WEATHER_CACHE:
            result[ds] = _WEATHER_CACHE[ck]
        else:
            dd = (cur - today).days
            if dd <= 0:
                missing_hist.append(ds)
            elif dd <= 16:
                missing_fore.append(ds)
            else:
                result[ds] = _climatology(ds, lat, lon)
        cur += timedelta(days=1)

    if missing_hist:
        fetched = _fetch_historical(min(missing_hist), max(missing_hist), lat, lon)
        for d, w in fetched.items():
            _WEATHER_CACHE[_cache_key(d, lat, lon)] = w
            result[d] = w

    if missing_fore:
        max_ahead = (date.fromisoformat(max(missing_fore)) - today).days + 1
        fetched = _fetch_forecast(lat, lon, days=min(max_ahead, 16))
        for d, w in fetched.items():
            _WEATHER_CACHE[_cache_key(d, lat, lon)] = w
            result[d] = w

    _save_cache()
    return result
