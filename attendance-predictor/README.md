# Attendance Predictor

Full-stack system that forecasts daily student attendance with a **Random Forest** model (scikit-learn), a **Flask** API, optional **SMTP** digests via **APScheduler**, and a **React + Vite + Tailwind** dashboard.

**Full technical guide (backend, frontend, model, training, API):** [DOCUMENTATION.md](./DOCUMENTATION.md)

## Project layout

- `backend/data/` — place attendance **CSV** or **Excel** (`.xlsx`, `.xlsm`, `.xls`) files here (subfolders are scanned; `__MACOSX`, `~$`, and `._*` files are ignored)
- `backend/model/train_model.py` — training pipeline
- `backend/model/*.pkl` — trained model, features, metadata, historical series (generated)
- `backend/prediction_service.py` — shared inference for API and scheduler
- `backend/app.py` — REST API
- `backend/email_scheduler.py` — daily email job (standalone or embedded)
- `frontend/` — Vite React UI (proxies `/api` to Flask)

## Quick start

1. **Add data**  
   Put CSV or Excel exports anywhere under `backend/data/`. The trainer supports:

   - **Long tables**: a date column plus present counts, or attendance % with a total/enrollment column.
   - **IIIT-style grids**: month row + day row (including `29th` / `1st` style headings) + `Sr. No` / `Enrolment No` + **P/A** or **1/0** per session; **all sheets** in a workbook are read.
   - **Summary-only sheets** (no daily dates): student rows with **attendance %** or **session counts** (e.g. “Number of present”, email + “Attendance” columns). These contribute **one rollup row per sheet** on a synthetic mid-semester date (spread per file path) so mixed exports still train.
   - **Lecture + lab blocks**: “Registration” header rows with two **Present** count columns (lecture/lab) are summed for a rollup.

   For `.xlsx` you need `openpyxl` (included in `requirements.txt`). Training metrics print **MdAPE** and **wMAPE** (mean MAPE can be inflated when daily totals mix very small and large values).

2. **Train the model**

   ```bash
   cd backend
   pip install -r requirements.txt
   python model/train_model.py
   ```

3. **Start the API**

   ```bash
   cd backend
   python app.py
   ```

   Optional: run the email scheduler in the same process:

   ```bash
   set RUN_EMAIL_SCHEDULER=1
   python app.py
   ```

   Or run the scheduler alone:

   ```bash
   python email_scheduler.py
   ```

4. **Start the dashboard**

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

5. Open **http://localhost:5173** and use **Predict** / charts / notification settings.

## Environment

Copy or edit `backend/.env`:

- `STAFF_EMAIL`, `SMTP_HOST`, `SMTP_PORT`, `SENDER_EMAIL`, `SENDER_PASSWORD`
- `NOTIFICATION_TIME` (default `18:00`)
- `FLASK_PORT` (default `5000`)

Dashboard email settings are stored in `backend/email_settings.json` (password is not returned by the API).

## API summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/predict?date=YYYY-MM-DD` | Single-day forecast + RF tree percentile band |
| GET | `/api/predict-range?start=&end=` | Range forecast (chains lags for sequential days) |
| GET | `/api/historical` | Aggregated daily series for charts |
| GET | `/api/model-info` | Training metrics and feature importances |
| GET | `/api/settings/email` | Safe email settings + last notification time |
| POST | `/api/settings/email` | Update SMTP / staff / enable / send time |
| POST | `/api/send-notification` | Test email for tomorrow’s forecast |

CORS is enabled for the Vite dev server on `http://localhost:5173`–`5175` (and `127.0.0.1` equivalents).

## Notes

- Predictions are **rounded integers**; confidence bands use **per-tree** predictions from the Random Forest (10th–90th percentiles).
- **Sunday** predictions are **0** (no regular classes). **Saturday** outputs are damped if the model predicts high counts.
- Dates **far past the last training date** return a **warning** in the JSON and UI.
