import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

const easeOut = [0.22, 1, 0.36, 1];

function isoDate(d) {
  return d.toISOString().slice(0, 10);
}

function clamp(n, lo, hi) {
  return Math.max(lo, Math.min(hi, n));
}

function rankStyle(rank) {
  if (rank === 1) return { label: "1", cls: "border-amber-400/40 bg-amber-500/10 text-amber-200" };
  if (rank === 2) return { label: "2", cls: "border-slate-300/30 bg-slate-500/10 text-slate-200" };
  if (rank === 3) return { label: "3", cls: "border-orange-400/30 bg-orange-500/10 text-orange-200" };
  return { label: String(rank), cls: "border-white/10 bg-white/5 text-slate-200" };
}

function ConfidenceBand({ low, high, value, maxValue }) {
  const span = Math.max(1, maxValue || 1);
  const left = clamp((low / span) * 100, 0, 100);
  const right = clamp((high / span) * 100, 0, 100);
  const v = clamp((value / span) * 100, 0, 100);

  return (
    <div className="mt-4">
      <div className="h-2 w-full rounded-full bg-white/5 ring-1 ring-white/10">
        <div
          className="relative h-2 rounded-full bg-gradient-to-r from-teal-500/35 to-cyan-500/20"
          style={{ marginLeft: `${left}%`, width: `${Math.max(2, right - left)}%` }}
        >
          <div
            className="absolute -top-1 h-4 w-1.5 rounded-full bg-teal-300 shadow-[0_0_18px_rgba(45,212,191,0.35)]"
            style={{ left: `${clamp(v - left, 0, Math.max(0, right - left))}%` }}
            aria-hidden
          />
        </div>
      </div>
      <div className="mt-2 flex justify-between text-[11px] font-semibold text-slate-500 tabular-nums">
        <span>
          Low <span className="text-slate-300">{low}</span>
        </span>
        <span>
          High <span className="text-slate-300">{high}</span>
        </span>
      </div>
    </div>
  );
}

export default function BestDaysFinder() {
  const reduce = useReducedMotion();

  const [start, setStart] = useState(() => isoDate(new Date()));
  const [end, setEnd] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 30);
    return isoDate(d);
  });
  const [eventType, setEventType] = useState("event");
  const [includeSaturdays, setIncludeSaturdays] = useState(false);
  const [minAttendance, setMinAttendance] = useState(0);
  const [maxHistorical, setMaxHistorical] = useState(300);

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [showAvoid, setShowAvoid] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/historical");
        const data = await res.json();
        if (!res.ok) return;
        const maxV = Math.max(
          0,
          ...(data?.data || []).map((r) => Number(r.attendance) || 0)
        );
        setMaxHistorical(maxV > 0 ? Math.ceil(maxV) : 300);
      } catch {
        /* optional */
      }
    })();
  }, []);

  const topMax = useMemo(() => {
    const recs = result?.recommendations || [];
    const highs = recs.map((r) => Number(r?.confidence_range?.high) || 0);
    const maxR = Math.max(0, ...highs);
    return Math.max(maxR, maxHistorical || 1);
  }, [result, maxHistorical]);

  const fetchBestDays = async () => {
    setLoading(true);
    setResult(null);
    setShowAvoid(false);
    try {
      const qs = new URLSearchParams();
      qs.set("start", start);
      qs.set("end", end);
      qs.set("top_n", "3");
      qs.set("event_type", eventType);
      qs.set("include_saturdays", includeSaturdays ? "true" : "false");
      if (minAttendance > 0) qs.set("min_attendance", String(minAttendance));

      const res = await fetch(`/api/best-days?${qs.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Best days request failed");
      setResult(data);
      if ((data?.avoid_dates || []).length) setShowAvoid(true);
    } catch (e) {
      toast.error(e.message || "Could not load best days");
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.section
      layout
      className="ui-panel relative overflow-hidden rounded-3xl border-teal-500/15 p-6 sm:p-10"
    >
      <div className="pointer-events-none absolute -right-24 -top-24 h-56 w-56 rounded-full bg-teal-500/10 blur-3xl" />
      <div className="relative">
        <div className="ui-badge mb-4 border-teal-400/30 bg-teal-500/10 text-teal-300">
          Ranking · Calendar-aware
        </div>
        <motion.h2
          className="font-display text-2xl font-bold tracking-tight text-white sm:text-3xl"
          initial={{ opacity: 0, x: -12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.45, ease: easeOut }}
        >
          Best Days Finder
        </motion.h2>
        <motion.p
          className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-400"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1, duration: 0.4 }}
        >
          Pick a window and we’ll rank the strongest days. This is optimized for relative ordering,
          not exact headcount precision.
        </motion.p>

        <div className="mt-8 grid gap-4 lg:grid-cols-4">
          <label className="flex flex-col text-xs font-semibold uppercase tracking-wider text-slate-500">
            Start
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="ui-input font-sans text-base font-medium"
            />
          </label>
          <label className="flex flex-col text-xs font-semibold uppercase tracking-wider text-slate-500">
            End
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="ui-input font-sans text-base font-medium"
            />
          </label>
          <label className="flex flex-col text-xs font-semibold uppercase tracking-wider text-slate-500">
            Event type
            <select
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              className="ui-input font-sans text-base font-medium"
            >
              <option value="event">Event</option>
              <option value="class">Class</option>
              <option value="workshop">Workshop</option>
              <option value="exam">Exam</option>
            </select>
          </label>
          <div className="flex flex-col justify-between gap-3 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Include Saturdays
              </span>
              <button
                type="button"
                onClick={() => setIncludeSaturdays((v) => !v)}
                className={`h-7 w-12 rounded-full border transition-colors ${
                  includeSaturdays
                    ? "border-teal-400/40 bg-teal-500/20"
                    : "border-white/10 bg-white/5"
                }`}
                aria-pressed={includeSaturdays}
              >
                <span
                  className={`block h-6 w-6 translate-x-0 rounded-full bg-white shadow transition-transform ${
                    includeSaturdays ? "translate-x-5 bg-teal-200" : "translate-x-0 bg-slate-200"
                  }`}
                />
              </button>
            </div>
            <div>
              <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500">
                <span>Min attendance</span>
                <span className="tabular-nums text-slate-300">{minAttendance}</span>
              </div>
              <input
                type="range"
                min={0}
                max={Math.max(10, maxHistorical)}
                value={minAttendance}
                onChange={(e) => setMinAttendance(Number(e.target.value))}
                className="mt-2 w-full accent-teal-400"
              />
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <motion.button
            type="button"
            onClick={fetchBestDays}
            disabled={loading}
            whileHover={{ scale: loading ? 1 : 1.03 }}
            whileTap={{ scale: loading ? 1 : 0.98 }}
            className="ui-btn-primary relative overflow-hidden disabled:opacity-50"
          >
            {loading ? (
              <span className="relative z-10 inline-flex items-center gap-2">
                <motion.span
                  className="h-4 w-4 rounded-full border-2 border-white border-t-transparent"
                  animate={{ rotate: 360 }}
                  transition={{ duration: 0.65, repeat: Infinity, ease: "linear" }}
                />
                Ranking…
              </span>
            ) : (
              <span className="relative z-10">Find Best Days</span>
            )}
          </motion.button>
          <p className="text-xs text-slate-500">
            Sundays are excluded. Saturdays are optional.
          </p>
        </div>

        <AnimatePresence mode="wait">
          {result ? (
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.45, ease: easeOut }}
              className="mt-10 space-y-8"
            >
              {result.recommendations?.length ? (
                <div className="grid gap-5 lg:grid-cols-3">
                  {result.recommendations.map((r, i) => {
                    const rs = rankStyle(r.rank);
                    const low = Number(r?.confidence_range?.low) || 0;
                    const high = Number(r?.confidence_range?.high) || 0;
                    const pred = Number(r?.predicted_attendance) || 0;
                    return (
                      <motion.div
                        key={r.date}
                        initial={{ opacity: 0, y: 18 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.05 + i * 0.06, type: "spring", stiffness: 140, damping: 22 }}
                        className="ui-panel rounded-3xl p-6"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">
                              Recommendation
                            </p>
                            <p className="font-display mt-2 text-2xl font-extrabold tracking-tight text-white">
                              {r.date}
                            </p>
                            <p className="mt-1 text-sm font-semibold text-teal-200">{r.day_of_week}</p>
                          </div>
                          <div className={`shrink-0 rounded-2xl border px-3 py-2 text-sm font-extrabold ${rs.cls}`}>
                            #{rs.label}
                          </div>
                        </div>

                        <div className="mt-5 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">
                            Predicted strength
                          </p>
                          <p className="font-display mt-2 text-4xl font-extrabold tabular-nums text-white">
                            {pred}
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            Confidence band:{" "}
                            <span className="font-semibold text-slate-300">
                              {low} – {high}
                            </span>
                          </p>
                          <ConfidenceBand low={low} high={high} value={pred} maxValue={topMax} />
                        </div>

                        {r.reasons?.length ? (
                          <ul className="mt-5 space-y-2 text-sm text-slate-300">
                            {r.reasons.map((x, idx) => (
                              <li key={idx} className="flex gap-2">
                                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-300/80" />
                                <span>{x}</span>
                              </li>
                            ))}
                          </ul>
                        ) : null}

                        {r.warnings?.length ? (
                          <div className="mt-5 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
                            <p className="font-bold uppercase tracking-wider">Warnings</p>
                            <ul className="mt-2 list-disc space-y-1 pl-4">
                              {r.warnings.map((w, idx) => (
                                <li key={idx}>{w}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null}

                        <p className="mt-4 text-[11px] font-semibold text-slate-500">
                          Score {Number(r.score).toFixed(4)}
                        </p>
                      </motion.div>
                    );
                  })}
                </div>
              ) : (
                <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-6 text-sm text-slate-400">
                  No recommendations matched this range/filters.
                </div>
              )}

              <div className="ui-panel rounded-3xl p-6">
                <button
                  type="button"
                  onClick={() => setShowAvoid((v) => !v)}
                  className="flex w-full items-center justify-between gap-4 text-left"
                >
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">
                      Avoid these dates
                    </p>
                    <p className="mt-1 text-sm text-slate-300">
                      Holidays/exams and adjacent days within your window.
                    </p>
                  </div>
                  <span className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold text-slate-300">
                    {showAvoid ? "Hide" : "Show"}
                  </span>
                </button>

                <AnimatePresence initial={false}>
                  {showAvoid ? (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.35, ease: easeOut }}
                      className="mt-5 overflow-hidden"
                    >
                      {result.avoid_dates?.length ? (
                        <ul className="space-y-2 text-sm text-slate-300">
                          {result.avoid_dates.map((a) => (
                            <li key={a.date} className="flex items-center justify-between gap-4 rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3">
                              <span className="font-semibold tabular-nums text-slate-200">{a.date}</span>
                              <span className="text-xs text-slate-500">{a.reason}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-sm text-slate-500">No avoid-dates detected in this window.</p>
                      )}
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </div>

              <p className="text-xs text-slate-500">
                {result.disclaimer}
              </p>
            </motion.div>
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="mt-10 rounded-2xl border border-dashed border-white/10 bg-slate-950/40 p-8 text-center"
            >
              <p className="font-display text-lg font-semibold text-slate-300">Pick a range to begin</p>
              <p className="mt-2 text-sm text-slate-500">
                We’ll return top-ranked days plus a small avoid list.
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.section>
  );
}

