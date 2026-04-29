import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { toast } from "sonner";

const WEATHER_ICONS = {
  clear:  "☀️",
  cloudy: "⛅",
  fog:    "🌫️",
  rain:   "🌧️",
  snow:   "❄️",
  storm:  "⛈️",
};

function tomorrowISODate() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function useCountUp(target, duration = 800) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (target == null || Number.isNaN(target)) return;
    const start = performance.now();
    const from = 0;
    let frame;
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) ** 3;
      setV(Math.round(from + (target - from) * eased));
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);
  return v;
}

function WeatherPill({ weather }) {
  if (!weather) return null;
  const icon = WEATHER_ICONS[weather.icon] ?? "🌤️";
  return (
    <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs">
      <span aria-hidden>{icon}</span>
      <span className="text-slate-300 font-medium">{weather.description}</span>
      {weather.temp_max != null && (
        <span className="text-teal-400 font-semibold tabular-nums">
          {weather.temp_max.toFixed(1)} °C
        </span>
      )}
      {weather.is_rainy && (
        <span className="text-sky-400">
          {weather.precipitation != null ? `${weather.precipitation.toFixed(1)} mm` : "Rain"}
        </span>
      )}
      {weather.is_extreme && (
        <span className="font-bold text-rose-400">⚠ Extreme</span>
      )}
    </div>
  );
}

const easeOut = [0.22, 1, 0.36, 1];

export default function PredictionCard({ onPrediction }) {
  const reduce = useReducedMotion();
  const [date, setDate] = useState(tomorrowISODate());
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const animated = useCountUp(result?.predicted_attendance ?? 0);

  const fetchPredict = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch(`/api/predict?date=${encodeURIComponent(date)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Prediction failed");
      setResult(data);
      onPrediction?.(data);
    } catch (e) {
      toast.error(e.message || "Could not load prediction");
    } finally {
      setLoading(false);
    }
  };

  const hist    = result?.historical_avg ?? 0;
  const pred    = result?.predicted_attendance ?? 0;
  const diffPct = hist > 0 ? Math.round(((pred - hist) / hist) * 1000) / 10 : 0;
  let tone = "text-amber-400";
  if (diffPct > 3)  tone = "text-emerald-400";
  if (diffPct < -3) tone = "text-rose-400";

  const isHolidayOrBreak = result?.is_holiday || result?.is_break;

  return (
    <motion.section
      layout
      className="ui-panel relative overflow-hidden rounded-3xl border-teal-500/15 p-6 sm:p-10"
    >
      {!reduce && (
        <motion.div
          className="pointer-events-none absolute -inset-32 opacity-[0.12]"
          style={{
            background:
              "conic-gradient(from 0deg, rgba(45,212,191,0.6), rgba(14,165,233,0.4), rgba(45,212,191,0.6))",
          }}
          animate={{ rotate: 360 }}
          transition={{ duration: 28, repeat: Infinity, ease: "linear" }}
        />
      )}

      <div className="pointer-events-none absolute -right-24 -top-24 h-56 w-56 rounded-full bg-teal-500/15 blur-3xl" />
      <motion.div
        className="pointer-events-none absolute -bottom-20 -left-20 h-48 w-48 rounded-full bg-cyan-500/10 blur-3xl"
        animate={reduce ? {} : { scale: [1, 1.15, 1], opacity: [0.4, 0.75, 0.4] }}
        transition={reduce ? undefined : { duration: 5, repeat: Infinity, ease: "easeInOut" }}
      />

      <div className="relative grid gap-10 lg:grid-cols-[1fr_1.1fr] lg:items-end">
        <div>
          <div className="ui-badge mb-4 border-teal-400/30 bg-teal-500/10 text-teal-300">
            Random Forest · Daily
          </div>
          <motion.h2
            className="font-display text-2xl font-bold tracking-tight text-white sm:text-3xl"
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.45, ease: easeOut }}
          >
            Run a forecast
          </motion.h2>
          <motion.p
            className="mt-3 max-w-md text-sm leading-relaxed text-slate-400"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1, duration: 0.4 }}
          >
            Select any date to estimate campus headcount. Weather conditions and calendar
            holidays are factored in automatically.
          </motion.p>
          <div className="mt-8 flex flex-wrap items-end gap-4">
            <label className="flex flex-col text-xs font-semibold uppercase tracking-wider text-slate-500">
              Target date
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="ui-input mt-2 max-w-[200px] font-sans text-base font-medium"
              />
            </label>
            <motion.button
              type="button"
              onClick={fetchPredict}
              disabled={loading}
              whileHover={{ scale: loading ? 1 : 1.03 }}
              whileTap={{ scale: loading ? 1 : 0.98 }}
              className="ui-btn-primary relative overflow-hidden disabled:opacity-50"
            >
              {!loading && !reduce && (
                <motion.span
                  className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent"
                  initial={{ x: "-100%" }}
                  animate={{ x: "200%" }}
                  transition={{ duration: 2.5, repeat: Infinity, repeatDelay: 2, ease: "easeInOut" }}
                />
              )}
              {loading ? (
                <span className="relative z-10 inline-flex items-center gap-2">
                  <motion.span
                    className="h-4 w-4 rounded-full border-2 border-white border-t-transparent"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 0.65, repeat: Infinity, ease: "linear" }}
                  />
                  Working…
                </span>
              ) : (
                <span className="relative z-10">Generate prediction</span>
              )}
            </motion.button>
          </div>
        </div>

        <AnimatePresence mode="wait">
          {result ? (
            <motion.div
              key={result.date}
              initial={{ opacity: 0, y: 20, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -12, scale: 0.98 }}
              transition={{ duration: 0.45, ease: easeOut }}
              className="relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-slate-900/90 via-slate-900/50 to-teal-950/30 p-6 sm:p-8 ring-1 ring-teal-500/20"
            >
              <div className="absolute right-4 top-4 rounded-full bg-teal-500/20 px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-teal-300">
                Result
              </div>

              {/* Holiday / closure banner */}
              {isHolidayOrBreak && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mb-4 mt-6 flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5"
                >
                  <span aria-hidden className="text-lg">🏖️</span>
                  <p className="text-xs font-semibold text-amber-300">
                    {result.is_break ? "Institution break / vacation" : "Public holiday"} — campus closed, attendance is 0.
                  </p>
                </motion.div>
              )}

              <div className="mt-4 flex flex-wrap items-end gap-2">
                <motion.span
                  className={`font-display text-5xl font-extrabold tracking-tight tabular-nums sm:text-7xl ${
                    isHolidayOrBreak ? "text-slate-500" : "text-white"
                  }`}
                  initial={{ scale: 0.6, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 180, damping: 16 }}
                >
                  {animated}
                </motion.span>
                <span className="mb-2 text-sm font-medium text-slate-400">students</span>
              </div>

              {!isHolidayOrBreak && (
                <p className="mt-4 text-sm text-slate-400">
                  Confidence band{" "}
                  <span className="font-semibold text-teal-300">
                    {result.confidence_range.low} – {result.confidence_range.high}
                  </span>
                </p>
              )}

              <div className="mt-5 flex flex-wrap gap-2">
                <span className="rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs font-bold text-slate-200">
                  {result.day_of_week}
                </span>
                {result.is_weekend && (
                  <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-300">
                    Weekend
                  </span>
                )}
                {result.is_holiday && (
                  <span className="rounded-full border border-orange-500/30 bg-orange-500/10 px-3 py-1.5 text-xs font-semibold text-orange-300">
                    Public holiday
                  </span>
                )}
                {result.is_break && (
                  <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-xs font-semibold text-violet-300">
                    Institute break
                  </span>
                )}
                {result.weather?.is_extreme && (
                  <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-300">
                    ⚠ Extreme weather
                  </span>
                )}
              </div>

              {/* Weather pill */}
              {result.weather && (
                <div className="mt-4">
                  <WeatherPill weather={result.weather} />
                </div>
              )}

              {!isHolidayOrBreak && (
                <p className={`mt-5 text-sm font-semibold ${tone}`}>
                  {diffPct >= 0 ? "↑" : "↓"} {Math.abs(diffPct)}% vs same weekday historical avg (
                  {hist})
                </p>
              )}

              {result.warning && (
                <p className="mt-4 rounded-xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
                  {result.warning}
                </p>
              )}
            </motion.div>
          ) : (
            <motion.div
              key="placeholder"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex min-h-[280px] flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-slate-950/40 p-8 text-center"
            >
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-500/20 to-cyan-500/10 ring-1 ring-teal-400/20">
                <svg className="h-8 w-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                  />
                </svg>
              </div>
              <p className="font-display text-lg font-semibold text-slate-300">Ready when you are</p>
              <p className="mt-2 max-w-xs text-sm text-slate-500">
                Your predicted headcount, weather conditions, and confidence range will appear here.
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.section>
  );
}
