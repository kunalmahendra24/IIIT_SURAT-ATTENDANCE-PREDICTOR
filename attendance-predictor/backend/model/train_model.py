"""
Train Random Forest attendance predictor from CSV / Excel files in ../data/.
Supports .csv, .xlsx (openpyxl), and .xls where pandas can read them.

Layouts:
- Long tables: date column + present count (or % + total).
- IIIT-style Excel: month row + day row + P/A grid (all sheets scanned).
- Snapshot-only Excel: student rows with attendance % or session counts and no dates —
  one synthetic mid-semester date per file (spread by path hash) so rollups still train.
Saves model, feature columns, training metadata, and historical daily series.

New in this version:
- Holiday/break dates from calendar_events.json are injected as synthetic 0-attendance
  rows so the model learns the holiday → 0 pattern directly.
- Weather features (temperature, precipitation, rain flags) are added using the
  Open-Meteo free API via weather_service.py.
"""
from __future__ import annotations

import json
import re
import sys
import zlib
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

DATA_DIR    = Path(__file__).resolve().parent.parent / "data"
BACKEND_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR   = Path(__file__).resolve().parent
MODEL_PATH        = MODEL_DIR / "attendance_model.pkl"
FEATURE_COLS_PATH = MODEL_DIR / "feature_columns.pkl"
META_PATH         = MODEL_DIR / "training_meta.pkl"
HISTORICAL_PATH   = MODEL_DIR / "historical_daily.pkl"

# Allow importing backend modules when running `python model/train_model.py`
sys.path.insert(0, str(BACKEND_DIR))
from calendar_features import compute_calendar_features  # noqa: E402
from weather_service import get_weather_for_range         # noqa: E402

CALENDAR_EVENTS_PATH = BACKEND_DIR / "calendar_events.json"

# Feature columns used by the model (order matters — must match inference)
FEATURE_NAMES = [
    # Time
    "day_of_week",
    "day_of_month",
    "month",
    "week_of_year",
    "is_weekend",
    "is_monday",
    "is_friday",
    "quarter",
    "day_of_year",
    "is_month_start",
    "is_month_end",
    # Lagged attendance
    "lag_1",
    "lag_7",
    "rolling_mean_7",
    "rolling_mean_30",
    # Calendar
    "is_holiday",
    "is_exam_day",
    "is_break",
    "is_fest_day",
    "days_to_nearest_holiday",
    "days_after_holiday",
    "days_to_next_exam",
    "is_sandwich_day",
    "is_post_break_monday",
    # Weather (new)
    "temp_max",
    "precipitation",
    "is_rainy",
    "is_extreme_weather",
]


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------

def load_calendar_events() -> list[dict]:
    if not CALENDAR_EVENTS_PATH.exists():
        return []
    try:
        data = json.loads(CALENDAR_EVENTS_PATH.read_text(encoding="utf-8"))
        events = data.get("events", [])
        return events if isinstance(events, list) else []
    except (json.JSONDecodeError, OSError, AttributeError):
        return []


def _holiday_dates_from_calendar(events: list[dict]) -> set[pd.Timestamp]:
    """Return all dates tagged as holiday / break / vacation."""
    from calendar_features import _expand_events  # local import to avoid circular
    cal = _expand_events(events)
    return cal.holiday_dates | cal.break_dates


# ---------------------------------------------------------------------------
# Data parsing helpers (unchanged from original)
# ---------------------------------------------------------------------------

def _normalize_col(name: str) -> str:
    return re.sub(r"\s+", "_", str(name).strip().lower())


def _guess_date_column(df: pd.DataFrame) -> str | None:
    candidates = []
    for c in df.columns:
        n = _normalize_col(c)
        if any(
            x in n
            for x in ("date", "day", "attendance_date", "record_date", "timestamp")
        ):
            candidates.append(c)
    for c in df.columns:
        if c not in candidates and pd.api.types.is_datetime64_any_dtype(df[c]):
            candidates.append(c)
    if candidates:
        return candidates[0]
    for c in df.columns:
        if "date" in _normalize_col(c):
            return c
    return None


def _guess_present_column(df: pd.DataFrame) -> str | None:
    skip = set()
    dc = _guess_date_column(df)
    if dc:
        skip.add(dc)
    best = None
    best_score = -1
    for c in df.columns:
        if c in skip:
            continue
        n = _normalize_col(c)
        if any(
            kw in n
            for kw in (
                "present",
                "attended",
                "attendance_count",
                "count",
                "students_present",
                "num_present",
                "attendence",
            )
        ):
            return c
        if n == "attendance" or (n.startswith("attendance_") and "percent" not in n and "%" not in n):
            return c
        if df[c].dtype in (np.float64, np.int64, "float64", "int64", "Int64"):
            non_null = df[c].notna().sum()
            if non_null > best_score:
                best_score = non_null
                best = c
    return best


def _guess_total_column(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        n = _normalize_col(c)
        if any(kw in n for kw in ("total_students", "total", "enrolled", "capacity")):
            return c
    return None


def _guess_percent_column(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        n = _normalize_col(c)
        if any(x in n for x in ("percent", "percentage", "pct", "%")) or (
            "attend" in n and "%" in str(c)
        ):
            ser = pd.to_numeric(df[c], errors="coerce").dropna()
            if not len(ser):
                continue
            ok = ser.between(0, 100, inclusive="both")
            if len(ser) >= 3:
                if ok.mean() > 0.7:
                    return c
            elif bool(ok.all()):
                return c
    return None


def _parse_dates(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
    mask = parsed.isna()
    if mask.any():
        parsed2 = pd.to_datetime(series[mask], errors="coerce", dayfirst=False)
        parsed = parsed.fillna(parsed2)
    return parsed


_MONTH_TOKEN_TO_NUM: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_SR_NO_RE = re.compile(
    r"^(sr\.?\s*no\.?|s\.?\s*n\.?|serial\s*no\.?|sl\.?\s*no\.?)$", re.I,
)


def _cell_str(v: object) -> str:
    if pd.isna(v):
        return ""
    return str(v).strip()


def _month_from_cell(v: object) -> int | None:
    s = _cell_str(v).lower().rstrip(".")
    if not s:
        return None
    return _MONTH_TOKEN_TO_NUM.get(s)


def _day_from_cell(v: object) -> int | None:
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 1 <= float(v) <= 31 and float(v) == int(float(v)):
            return int(v)
    s = _cell_str(v).strip()
    m = re.match(r"^(\d{1,2})\s*(?:st|nd|rd|th)?\.?$", s, re.I)
    if m:
        d = int(m.group(1))
        if 1 <= d <= 31:
            return d
    if s.isdigit():
        d = int(s)
        if 1 <= d <= 31:
            return d
    return None


def _parse_academic_year_start(raw: pd.DataFrame) -> int | None:
    pat = re.compile(r"(20\d{2})\s*[-/]\s*(20\d{2})")
    for r in range(min(15, len(raw))):
        for c in range(min(8, raw.shape[1])):
            s = _cell_str(raw.iat[r, c])
            m = pat.search(s)
            if m:
                return int(m.group(1))
    return None


def _find_student_header_row(raw: pd.DataFrame) -> int | None:
    for i in range(len(raw)):
        v = _cell_str(raw.iat[i, 0])
        if v:
            if _SR_NO_RE.match(v):
                return i
            compact = re.sub(r"[\s.]", "", v.lower())
            if compact in ("srno", "sno", "slno"):
                return i
            n0 = _normalize_col(v)
            if "registration_no" in n0 or n0.startswith("register"):
                return i
        if raw.shape[1] > 1:
            v1 = _cell_str(raw.iat[i, 1])
            if v1:
                n1 = _normalize_col(v1)
                if any(
                    k in n1
                    for k in (
                        "enrolment_no", "enrollment_no", "enrollment_number",
                        "roll_no", "reg_no", "registration_no",
                    )
                ):
                    return i
    return None


def _forward_months_for_row(row: pd.Series, ncols: int) -> list[int | None]:
    out: list[int | None] = []
    cur: int | None = None
    for j in range(ncols):
        if j < len(row):
            m = _month_from_cell(row.iloc[j])
            if m is not None:
                cur = m
        out.append(cur)
    return out


def _year_for_calendar_month(month: int, y_start: int) -> int:
    return y_start if month >= 8 else y_start + 1


def _locate_day_header_row(
    raw: pd.DataFrame, header_row: int, ncols: int
) -> tuple[int | None, int | None]:
    for dr in (0, -1):
        r = header_row + dr
        if r < 0:
            continue
        first: int | None = None
        n_days = 0
        for j in range(ncols):
            if _day_from_cell(raw.iat[r, j]) is not None:
                n_days += 1
                if first is None:
                    first = j
        if n_days >= 3 and first is not None:
            return r, first
    return None, None


def _pick_month_row(raw: pd.DataFrame, day_row: int, ncols: int) -> int | None:
    best_r: int | None = None
    best_n = 0
    start = max(0, day_row - 14)
    for r in range(start, day_row):
        row = raw.iloc[r]
        n_m = sum(1 for j in range(ncols) if _month_from_cell(row.iloc[j]) is not None)
        if n_m >= 2 and n_m > best_n:
            best_n = n_m
            best_r = r
    return best_r


def _try_wide_format_iiit(raw: pd.DataFrame) -> pd.DataFrame | None:
    nrows, ncols = raw.shape
    if nrows < 10 or ncols < 6:
        return None

    y_start = _parse_academic_year_start(raw)
    if y_start is None:
        y_start = datetime.now().year - 1

    header_row = _find_student_header_row(raw)
    if header_row is None:
        return None

    day_row, first_j = _locate_day_header_row(raw, header_row, ncols)
    if day_row is None or first_j is None:
        return None

    month_row = _pick_month_row(raw, day_row, ncols)
    if month_row is None:
        month_ff = [8] * ncols
    else:
        month_ff = _forward_months_for_row(raw.iloc[month_row], ncols)

    days_row = raw.iloc[day_row]
    prev_d: int | None = None
    cur_m: int | None = None
    col_dates: dict[int, pd.Timestamp] = {}

    for j in range(first_j, ncols):
        d = _day_from_cell(days_row.iloc[j])
        if d is None:
            continue
        mh = month_ff[j] if j < len(month_ff) else None

        if cur_m is None:
            cur_m = mh if mh is not None else 8

        if mh is not None and mh != cur_m:
            cur_m = mh

        if prev_d is not None and d < prev_d and prev_d >= 25 and d <= 12:
            cur_m = (cur_m or 8) + 1
            if cur_m > 12:
                cur_m = 1

        if cur_m is None:
            continue

        y = _year_for_calendar_month(cur_m, y_start)
        try:
            ts = pd.Timestamp(year=y, month=cur_m, day=d)
        except (ValueError, TypeError):
            prev_d = d
            continue

        col_dates[j] = ts.normalize()
        prev_d = d

    if not col_dates:
        return None

    totals: dict[pd.Timestamp, float] = {}
    for j, dt in col_dates.items():
        n_present = 0
        for r in range(header_row + 1, nrows):
            v = raw.iat[r, j]
            if pd.isna(v):
                continue
            if isinstance(v, bool):
                pass
            elif isinstance(v, (int, float)):
                if float(v) == 1.0:
                    n_present += 1
                continue
            s = _cell_str(v).upper()
            if s in ("P", "1", "Y", "YES", "PRESENT"):
                n_present += 1
        totals[dt] = totals.get(dt, 0.0) + float(n_present)

    if not totals:
        return None

    out = pd.DataFrame(
        [{"date": d, "attendance": totals[d]} for d in sorted(totals.keys())]
    )
    return out


def _year_from_path(path: Path) -> int | None:
    m = re.search(r"(20\d{2})", path.stem)
    return int(m.group(1)) if m else None


def _snapshot_date_for_file(path: Path, y_start: int) -> pd.Timestamp:
    key = str(path.resolve()).casefold().encode("utf-8", errors="ignore")
    h = zlib.adler32(key) & 0xFFFFFFFF
    offset_days = int(h % 77)
    base = pd.Timestamp(year=y_start, month=10, day=7)
    return (base + pd.Timedelta(days=offset_days)).normalize()


def _find_labeled_header_row(raw: pd.DataFrame) -> int | None:
    nrows, ncols = raw.shape
    for r in range(min(35, nrows)):
        parts = []
        for c in range(min(14, ncols)):
            parts.append(_cell_str(raw.iat[r, c]).lower())
        joined = " ".join(parts)
        if "email" in joined and ("attendance" in joined or "percent" in joined):
            return r
        if "roll" in joined and "attendance" in joined:
            return r
    return None


def _header_cell_lookup(raw: pd.DataFrame, header_row: int, col: int) -> str:
    h = raw.iat[header_row, col]
    if pd.notna(h) and str(h).strip():
        return str(h).strip()
    for up in range(1, min(12, header_row + 1)):
        r = header_row - up
        v = raw.iat[r, col]
        if pd.notna(v) and str(v).strip():
            return str(v).strip()
    return ""


def _df_from_raw_header(raw: pd.DataFrame, header_row: int) -> pd.DataFrame:
    ncols = raw.shape[1]
    hdr = raw.iloc[header_row, :ncols]
    names: list[str] = []
    used: dict[str, int] = {}
    for i in range(ncols):
        h = hdr.iloc[i]
        cell = None
        if pd.notna(h) and str(h).strip():
            cell = str(h).strip()
        else:
            cell = _header_cell_lookup(raw, header_row, i)
        base = _normalize_col(cell) if cell else f"col_{i}"
        if not base:
            base = f"col_{i}"
        k = used.get(base, 0)
        used[base] = k + 1
        names.append(base if k == 0 else f"{base}_{k}")
    body = raw.iloc[header_row + 1 :, :ncols].copy()
    body.columns = names
    body = body.dropna(how="all")
    return body


def _looks_like_wide_numeric_headers(df: pd.DataFrame) -> bool:
    n = 0
    for c in df.columns:
        s = str(c).replace("_", "").strip()
        if s.isdigit() and 1 <= int(s) <= 31:
            n += 1
    return n >= 5


def _find_attendance_count_column(df: pd.DataFrame) -> str | None:
    skip_sub = ("percent", "%", "pct", "email", "name", "reg", "roll", "enrollment", "paper")
    for c in df.columns:
        n = str(c).lower()
        if any(s in n for s in skip_sub):
            continue
        if (
            n in ("attendance", "present", "absent")
            or n.endswith("_attendance")
            or (
                "present" in n
                and "percent" not in n
                and "percentage" not in n
                and "absent" not in n
            )
        ):
            ser = pd.to_numeric(df[c], errors="coerce").dropna()
            if len(ser) >= 1 and ser.max() <= 500 and ser.min() >= 0:
                return c
    return None


def _snapshot_metric_from_df(df: pd.DataFrame) -> float | None:
    if _looks_like_wide_numeric_headers(df):
        return None
    cnt_col = _find_attendance_count_column(df)
    if cnt_col is not None:
        ser = pd.to_numeric(df[cnt_col], errors="coerce").dropna()
        if len(ser) >= 1:
            return float(ser.sum())
    pct_col = _guess_percent_column(df)
    if pct_col is not None:
        ser = pd.to_numeric(df[pct_col], errors="coerce").dropna()
        ser = ser[ser.between(0, 100, inclusive="both")]
        if len(ser) >= 1:
            return float((ser / 100.0).sum())
    return None


def _try_registration_lecture_lab_snapshot(
    raw: pd.DataFrame, path: Path
) -> pd.DataFrame | None:
    nrows, ncols = raw.shape
    for r in range(min(35, nrows - 3)):
        blob = " ".join(
            _cell_str(raw.iat[r, j]).lower()
            for j in range(min(ncols, 14))
        )
        blob += " " + " ".join(
            _cell_str(raw.iat[r + 1, j]).lower()
            for j in range(min(ncols, 14))
        )
        if "registration" not in blob and "registr" not in blob:
            continue
        present_js: list[int] = []
        for j in range(ncols):
            t = _cell_str(raw.iat[r + 1, j]).lower()
            if t == "present":
                present_js.append(j)
        if len(present_js) < 2:
            continue
        total = 0.0
        for j in present_js:
            col = pd.to_numeric(raw.iloc[r + 2 :, j], errors="coerce").dropna()
            total += float(col.sum())
        if total <= 0:
            continue
        y_start = (
            _parse_academic_year_start(raw)
            or _year_from_path(path)
            or (datetime.now().year - 1)
        )
        dt = _snapshot_date_for_file(path, y_start)
        return pd.DataFrame([{"date": dt, "attendance": total}])
    return None


def _try_snapshot_from_raw(raw: pd.DataFrame, path: Path) -> pd.DataFrame | None:
    reg_lab = _try_registration_lecture_lab_snapshot(raw, path)
    if reg_lab is not None:
        return reg_lab

    hr = _find_student_header_row(raw)
    if hr is None:
        hr = _find_labeled_header_row(raw)
    if hr is None:
        return None
    df = _df_from_raw_header(raw, hr)
    if df.empty:
        return None
    metric = _snapshot_metric_from_df(df)
    if metric is None or not np.isfinite(metric) or metric <= 0:
        return None
    y_start = (
        _parse_academic_year_start(raw)
        or _year_from_path(path)
        or (datetime.now().year - 1)
    )
    dt = _snapshot_date_for_file(path, y_start)
    return pd.DataFrame([{"date": dt, "attendance": metric}])


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in (".xlsx", ".xlsm"):
        return pd.read_excel(path, sheet_name=0, engine="openpyxl")
    if suffix == ".xls":
        return pd.read_excel(path, sheet_name=0)
    raise ValueError(f"Unsupported format: {path.suffix}")


def _skip_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if "__macosx" in parts:
        return True
    name = path.name
    if name.startswith("~$") or name.startswith("._"):
        return True
    return False


def _collect_data_paths() -> list[Path]:
    patterns = ("**/*.csv", "**/*.xlsx", "**/*.xlsm", "**/*.xls")
    seen: set[Path] = set()
    out: list[Path] = []
    for pat in patterns:
        for p in DATA_DIR.glob(pat):
            if not p.is_file() or _skip_path(p):
                continue
            try:
                rp = p.resolve()
            except OSError:
                continue
            if rp in seen:
                continue
            seen.add(rp)
            out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


def load_and_aggregate_daily() -> pd.DataFrame:
    """Load all CSV/Excel files from data/ (recursively), return one row per date.

    Also injects synthetic zero-attendance rows for all calendar holiday and break
    dates that are NOT already present in the aggregated data, teaching the model
    that the institution is closed on those days.
    """
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"Data directory not found: {DATA_DIR}")

    paths = _collect_data_paths()
    if not paths:
        raise FileNotFoundError(
            f"No data files under {DATA_DIR} — add .csv, .xlsx, or .xls (subfolders OK)"
        )

    frames = []
    for path in paths:
        suf = path.suffix.lower()
        if suf in (".xlsx", ".xlsm"):
            try:
                with pd.ExcelFile(path, engine="openpyxl") as xf:
                    wide_parts: list[pd.DataFrame] = []
                    snap_parts: list[pd.DataFrame] = []
                    for sheet in xf.sheet_names:
                        raw = pd.read_excel(xf, sheet_name=sheet, header=None)
                        wide = _try_wide_format_iiit(raw)
                        if wide is not None and not wide.empty:
                            wide_parts.append(wide)
                        else:
                            snap = _try_snapshot_from_raw(raw, path)
                            if snap is not None and not snap.empty:
                                snap_parts.append(snap)
                    if wide_parts:
                        frames.extend(wide_parts)
                        continue
                    if snap_parts:
                        frames.append(pd.concat(snap_parts, ignore_index=True))
                        continue
            except Exception as e:
                print(f"Warning {path.name}: Excel wide/snapshot path failed ({e}); trying table layout")

        if suf == ".xls":
            try:
                with pd.ExcelFile(path) as xf:
                    wide_parts = []
                    snap_parts = []
                    for sheet in xf.sheet_names:
                        raw = pd.read_excel(xf, sheet_name=sheet, header=None)
                        wide = _try_wide_format_iiit(raw)
                        if wide is not None and not wide.empty:
                            wide_parts.append(wide)
                        else:
                            snap = _try_snapshot_from_raw(raw, path)
                            if snap is not None and not snap.empty:
                                snap_parts.append(snap)
                    if wide_parts:
                        frames.extend(wide_parts)
                        continue
                    if snap_parts:
                        frames.append(pd.concat(snap_parts, ignore_index=True))
                        continue
            except Exception as e:
                print(f"Warning {path.name}: .xls wide/snapshot path failed ({e}); trying table layout")

        try:
            df = _read_table(path)
        except Exception as e:
            print(f"Skipping {path.name}: could not read ({e})")
            continue
        df.columns = [_normalize_col(c) for c in df.columns]
        date_col = _guess_date_column(df)
        present_col = _guess_present_column(df)
        total_col = _guess_total_column(df)

        if date_col is None:
            print(f"Skipping {path.name}: could not detect date column")
            continue

        dates = _parse_dates(df[date_col])
        pct_col = _guess_percent_column(df) if present_col is None else None
        if present_col is None and pct_col is None and total_col is None:
            print(f"Skipping {path.name}: could not detect attendance column")
            continue

        if present_col is not None:
            counts = pd.to_numeric(df[present_col], errors="coerce")
        elif pct_col is not None and total_col is not None:
            pct = pd.to_numeric(df[pct_col], errors="coerce")
            total = pd.to_numeric(df[total_col], errors="coerce")
            counts = (pct / 100.0) * total
        elif pct_col is not None:
            counts = pd.to_numeric(df[pct_col], errors="coerce") / 100.0
        else:
            counts = pd.to_numeric(df[total_col], errors="coerce") * 0.85

        tmp = pd.DataFrame({"date": dates.dt.normalize(), "present": counts})
        tmp = tmp.dropna(subset=["date"])
        tmp = tmp[tmp["present"].notna()]
        if tmp.empty:
            continue
        daily = tmp.groupby("date", as_index=False)["present"].sum()
        daily.rename(columns={"present": "attendance"}, inplace=True)
        frames.append(daily)

    if not frames:
        raise RuntimeError("No usable rows after loading data files")

    all_daily = pd.concat(frames, ignore_index=True)
    all_daily = (
        all_daily.groupby("date", as_index=False)["attendance"]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )
    all_daily = all_daily.drop_duplicates(subset=["date"], keep="last")

    med = all_daily["attendance"].median()
    all_daily["attendance"] = all_daily["attendance"].fillna(med)

    # ── Inject synthetic zero-attendance rows for calendar holidays/breaks ──
    events = load_calendar_events()
    if events:
        holiday_dates = _holiday_dates_from_calendar(events)
        existing_dates: set[pd.Timestamp] = set(all_daily["date"])
        synthetic_rows = []
        for hd in sorted(holiday_dates):
            if hd not in existing_dates:
                # Only inject if the holiday falls within (or near) the training window
                # to avoid polluting the dataset with distant future/past zeros.
                if not all_daily.empty:
                    dmin = all_daily["date"].min()
                    dmax = all_daily["date"].max()
                    margin = pd.Timedelta(days=30)
                    if dmin - margin <= hd <= dmax + margin:
                        synthetic_rows.append({"date": hd, "attendance": 0.0})
                else:
                    synthetic_rows.append({"date": hd, "attendance": 0.0})
        if synthetic_rows:
            print(f"Injecting {len(synthetic_rows)} synthetic holiday zero row(s)")
            syn_df = pd.DataFrame(synthetic_rows)
            all_daily = pd.concat([all_daily, syn_df], ignore_index=True)
            all_daily = (
                all_daily.sort_values("date")
                .drop_duplicates(subset=["date"], keep="first")
                .reset_index(drop=True)
            )

    return all_daily


def _fetch_training_weather(daily: pd.DataFrame) -> dict[str, dict]:
    """Batch-fetch weather for all dates in the training DataFrame."""
    if daily.empty:
        return {}
    dates = pd.to_datetime(daily["date"])
    start = dates.min().strftime("%Y-%m-%d")
    end   = dates.max().strftime("%Y-%m-%d")
    print(f"Fetching weather data for {start} → {end} …")
    try:
        weather_map = get_weather_for_range(start, end)
        print(f"  Retrieved weather for {len(weather_map)} dates.")
        return weather_map
    except Exception as e:
        print(f"  Warning: weather fetch failed ({e}); using neutral defaults.")
        return {}


def engineer_features(daily: pd.DataFrame) -> pd.DataFrame:
    """Add time-series + calendar + weather features; daily must be sorted by date."""
    d = daily.copy().sort_values("date").reset_index(drop=True)
    d["lag_1"]          = d["attendance"].shift(1)
    d["lag_7"]          = d["attendance"].shift(7)
    d["rolling_mean_7"] = d["attendance"].rolling(window=7,  min_periods=1).mean()
    d["rolling_mean_30"]= d["attendance"].rolling(window=30, min_periods=1).mean()

    dt = pd.to_datetime(d["date"])
    d["day_of_week"]   = dt.dt.dayofweek
    d["day_of_month"]  = dt.dt.day
    d["month"]         = dt.dt.month
    d["week_of_year"]  = dt.dt.isocalendar().week.astype(int)
    d["is_weekend"]    = (dt.dt.dayofweek >= 5).astype(int)
    d["is_monday"]     = (dt.dt.dayofweek == 0).astype(int)
    d["is_friday"]     = (dt.dt.dayofweek == 4).astype(int)
    d["quarter"]       = dt.dt.quarter
    d["day_of_year"]   = dt.dt.dayofyear
    d["is_month_start"]= (dt.dt.day <= 3).astype(int)
    last_day_of_month  = (dt + pd.offsets.MonthEnd(0)).dt.day
    d["is_month_end"]  = (dt.dt.day >= last_day_of_month - 2).astype(int)

    events = load_calendar_events()
    cal_rows = [compute_calendar_features(ts, events) for ts in dt]
    cal_df = pd.DataFrame(cal_rows)
    for col in (
        "is_holiday", "is_exam_day", "is_break", "is_fest_day",
        "days_to_nearest_holiday", "days_after_holiday", "days_to_next_exam",
        "is_sandwich_day", "is_post_break_monday",
    ):
        if col not in cal_df.columns:
            cal_df[col] = 0
    d = pd.concat([d, cal_df], axis=1)

    # Weather features
    weather_map = _fetch_training_weather(d)
    weather_rows = []
    for ts in dt:
        ds = ts.strftime("%Y-%m-%d")
        w  = weather_map.get(ds, {})
        weather_rows.append({
            "temp_max":           float(w.get("temp_max")           or 28.0),
            "precipitation":      float(w.get("precipitation")      or  0.0),
            "is_rainy":           int(w.get("is_rainy")             or  0),
            "is_extreme_weather": int(w.get("is_extreme_weather")   or  0),
        })
    weather_df = pd.DataFrame(weather_rows)
    d = pd.concat([d, weather_df], axis=1)

    return d


def compute_fallbacks(daily: pd.DataFrame) -> dict:
    att = daily["attendance"]
    return {
        "historical_mean":    float(att.mean()),
        "historical_median":  float(att.median()),
        "lag_1_fallback":     float(att.iloc[-1]) if len(att) else 0.0,
        "lag_7_fallback":     float(att.iloc[-7]) if len(att) >= 7 else float(att.mean()),
        "rolling_7_fallback": float(att.tail(7).mean()),
        "rolling_30_fallback":float(att.tail(min(30, len(att))).mean()),
    }


def train() -> dict:
    """Run full training pipeline. Returns the metrics dict."""
    print("Loading and aggregating daily attendance…")
    daily = load_and_aggregate_daily()
    print(f"Records (days, including synthetic holidays): {len(daily)}")

    featured  = engineer_features(daily)
    train_df  = featured.dropna(subset=["attendance"]).copy()
    fb        = compute_fallbacks(daily)
    train_df["lag_1"]          = train_df["lag_1"].fillna(fb["lag_1_fallback"])
    train_df["lag_7"]          = train_df["lag_7"].fillna(fb["lag_7_fallback"])
    train_df["rolling_mean_7"] = train_df["rolling_mean_7"].fillna(fb["rolling_7_fallback"])
    train_df["rolling_mean_30"]= train_df["rolling_mean_30"].fillna(fb["rolling_30_fallback"])

    X = train_df[FEATURE_NAMES]
    y = train_df["attendance"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, shuffle=False
    )

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=15,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    mae   = mean_absolute_error(y_test, pred)
    rmse  = float(np.sqrt(mean_squared_error(y_test, pred)))
    r2    = r2_score(y_test, pred)
    y_abs = np.maximum(np.abs(y_test.values), 1.0)
    ape   = np.abs(y_test.values - pred) / y_abs
    mape  = float(np.mean(ape) * 100)
    mdape = float(np.median(ape) * 100)
    y_sum = float(np.sum(np.abs(y_test.values)))
    wmape = (
        float(np.sum(np.abs(y_test.values - pred)) / y_sum * 100)
        if y_sum > 0 else 0.0
    )

    metrics = {"mae": mae, "rmse": rmse, "r2": r2, "mape": mape, "mdape": mdape, "wmape": wmape}

    print("\n--- Evaluation (hold-out) ---")
    print(f"MAE:    {mae:.2f}")
    print(f"RMSE:   {rmse:.2f}")
    print(f"R²:     {r2:.4f}")
    print(f"MdAPE:  {mdape:.2f}%  (median; robust to scale mix)")
    print(f"wMAPE:  {wmape:.2f}%  (sum|error|/sum|y|)")
    print(f"MAPE:   {mape:.2f}%  (mean; can be inflated when |y| is small)")

    importances = sorted(
        zip(FEATURE_NAMES, model.feature_importances_),
        key=lambda x: -x[1],
    )
    print("\n--- Feature importance ---")
    for name, imp in importances:
        print(f"  {name}: {imp:.4f}")

    joblib.dump(model, MODEL_PATH)
    joblib.dump(FEATURE_NAMES, FEATURE_COLS_PATH)

    training_meta = {
        "trained_at": datetime.utcnow().isoformat() + "Z",
        "n_records": int(len(train_df)),
        "metrics": metrics,
        "attendance_summary": {
            "min":    float(daily["attendance"].min()),
            "max":    float(daily["attendance"].max()),
            "mean":   float(daily["attendance"].mean()),
            "median": float(daily["attendance"].median()),
        },
        "feature_importances": {k: float(v) for k, v in importances},
        "fallbacks": fb,
        "last_historical_date": str(daily["date"].max().date()),
    }
    joblib.dump(training_meta, META_PATH)
    joblib.dump(daily[["date", "attendance"]], HISTORICAL_PATH)

    print(f"\nSaved model     → {MODEL_PATH}")
    print(f"Saved features  → {FEATURE_COLS_PATH}")
    print(f"Saved meta      → {META_PATH}")
    print(f"Saved historical→ {HISTORICAL_PATH}")

    return metrics


def main():
    train()


if __name__ == "__main__":
    main()
