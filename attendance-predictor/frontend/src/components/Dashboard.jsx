import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import AmbientBackground from "./AmbientBackground.jsx";
import AmbientParticles from "./AmbientParticles.jsx";
import AttendanceChart from "./AttendanceChart.jsx";
import FloatingNav from "./FloatingNav.jsx";
import NotificationSettings from "./NotificationSettings.jsx";
import BestDaysFinder from "./BestDaysFinder.jsx";
import CalendarAdmin from "./CalendarAdmin.jsx";
import PredictionCard from "./PredictionCard.jsx";
import ScrollProgress from "./ScrollProgress.jsx";
import { CardSurface, ScrollSection, Stagger, StaggerItem } from "./ScrollMotion.jsx";
import { AnimatedWords, SectionHeading } from "./TextMotion.jsx";

const RESOURCE_STYLES = [
  {
    border: "border-teal-400",
    glow: "from-teal-500/20",
    icon: "🍽️",
  },
  {
    border: "border-sky-400",
    glow: "from-sky-500/20",
    icon: "🚌",
  },
  {
    border: "border-violet-400",
    glow: "from-violet-500/20",
    icon: "✨",
  },
];

function ResourcePanel({ prediction }) {
  const reduce = useReducedMotion();

  if (!prediction) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 120, damping: 22 }}
        className="ui-panel relative overflow-hidden rounded-3xl p-10 text-center"
      >
        {!reduce && (
          <motion.div
            className="pointer-events-none absolute inset-0 bg-gradient-to-r from-transparent via-teal-500/[0.04] to-transparent"
            animate={{ x: ["-100%", "100%"] }}
            transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
          />
        )}
        <div className="relative">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-500/20 to-cyan-500/10 ring-1 ring-teal-400/25">
            <span className="text-3xl" aria-hidden>
              📊
            </span>
          </div>
          <p className="font-display text-lg font-semibold text-slate-200">Awaiting a forecast</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
            Generate a prediction above to unlock canteen, transport, and staffing estimates tailored
            to that headcount.
          </p>
        </div>
      </motion.div>
    );
  }
  const p = prediction.predicted_attendance;
  const meals = Math.ceil(p * 1.05);
  const buses = Math.max(1, Math.ceil(p / 30));
  const cleaning = Math.max(1, Math.ceil(p / 50));
  const cards = [
    { title: "Canteen meals", value: meals, hint: "Predicted × 1.05" },
    { title: "Transport buses", value: `${buses}`, hint: "~30 / bus" },
    { title: "Cleaning teams", value: `${cleaning}`, hint: "~50 / team" },
  ];
  return (
    <Stagger className="grid gap-5 sm:grid-cols-3">
      {cards.map((c, i) => {
        const s = RESOURCE_STYLES[i] ?? RESOURCE_STYLES[0];
        return (
          <StaggerItem key={c.title}>
            <CardSurface
              className={`ui-panel h-full overflow-hidden rounded-3xl border-t-4 ${s.border} pt-1`}
            >
              <div
                className={`pointer-events-none absolute -right-8 -top-8 h-32 w-32 rounded-full bg-gradient-to-br ${s.glow} to-transparent blur-2xl`}
                aria-hidden
              />
              <div className="relative p-6">
                <span className="text-2xl" aria-hidden>
                  {s.icon}
                </span>
                <p className="mt-3 text-[11px] font-bold uppercase tracking-[0.2em] text-slate-500">
                  {c.title}
                </p>
                <motion.p
                  className="font-display mt-3 text-4xl font-extrabold tracking-tight text-white tabular-nums"
                  initial={{ scale: 0.85, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 200, damping: 16 }}
                >
                  {c.value}
                </motion.p>
                <p className="mt-2 text-xs text-slate-500">{c.hint}</p>
              </div>
            </CardSurface>
          </StaggerItem>
        );
      })}
    </Stagger>
  );
}

function WeeklyTable() {
  const reduce = useReducedMotion();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const start = new Date();
    start.setDate(start.getDate() + 1);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    const s = start.toISOString().slice(0, 10);
    const e = end.toISOString().slice(0, 10);
    (async () => {
      try {
        const res = await fetch(
          `/api/predict-range?start=${encodeURIComponent(s)}&end=${encodeURIComponent(e)}`
        );
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Weekly forecast failed");
        setRows(data.predictions || []);
      } catch (err) {
        toast.error(err.message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <motion.section layout className="ui-panel overflow-hidden rounded-3xl p-6 sm:p-10">
      <SectionHeading
        title="7-day runway"
        subtitle="Forecasts from tomorrow — ideal for rotas, meal prep, and fleet planning."
      />
      <div className="overflow-x-auto rounded-2xl border border-white/5 bg-slate-950/40">
        {loading ? (
          <div className="flex flex-col items-center justify-center gap-5 py-16">
            <motion.span
              className="h-11 w-11 rounded-full border-2 border-teal-500/40 border-t-teal-400"
              animate={{ rotate: 360 }}
              transition={{ duration: 0.85, repeat: Infinity, ease: "linear" }}
            />
            <div className="flex gap-2">
              {[0, 1, 2, 3].map((i) => (
                <motion.div
                  key={i}
                  className="h-2 w-12 rounded-full bg-teal-500/20"
                  animate={reduce ? {} : { opacity: [0.25, 1, 0.25], scaleY: [1, 1.5, 1] }}
                  transition={
                    reduce
                      ? undefined
                      : { duration: 0.85, repeat: Infinity, delay: i * 0.1, ease: "easeInOut" }
                  }
                />
              ))}
            </div>
          </div>
        ) : (
          <table className="w-full min-w-[520px] text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 bg-white/[0.03] text-xs font-bold uppercase tracking-wider text-slate-500">
                <th className="px-5 py-4">Date</th>
                <th className="px-5 py-4">Day</th>
                <th className="px-5 py-4">Predicted</th>
                <th className="px-5 py-4">Range</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <motion.tr
                  key={r.date}
                  initial={{ opacity: 0, x: -16 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.05, type: "spring", stiffness: 120, damping: 22 }}
                  whileHover={{ backgroundColor: "rgba(45, 212, 191, 0.06)" }}
                  className="border-b border-white/[0.04] transition-colors last:border-0"
                >
                  <td className="px-5 py-4 tabular-nums text-slate-400">{r.date}</td>
                  <td className="px-5 py-4 font-medium text-slate-300">{r.day_of_week}</td>
                  <td className="px-5 py-4 font-display text-lg font-bold tabular-nums text-teal-300">
                    {r.predicted_attendance}
                  </td>
                  <td className="px-5 py-4 text-slate-500">
                    {r.confidence_range.low} – {r.confidence_range.high}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </motion.section>
  );
}

function ModelFooter() {
  const [info, setInfo] = useState(null);
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/model-info");
        const data = await res.json();
        if (res.ok) setInfo(data);
      } catch {
        /* optional */
      }
    })();
  }, []);
  if (!info) return null;
  const r2 = info.metrics?.r2;
  return (
    <motion.footer
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      className="mt-20 border-t border-white/10 py-12"
    >
      <div className="flex flex-col items-center gap-3 text-center sm:flex-row sm:justify-center sm:gap-8">
        <span className="rounded-full border border-white/10 bg-white/[0.03] px-4 py-1.5 text-xs font-semibold text-slate-400">
          R² {r2 != null ? r2.toFixed(4) : "—"}
        </span>
        <span className="text-xs text-slate-500">
          {info.n_records ?? "—"} training days · Last fit{" "}
          {info.trained_at ? new Date(info.trained_at).toLocaleDateString() : "—"}
        </span>
      </div>
    </motion.footer>
  );
}

const easeOut = [0.22, 1, 0.36, 1];

export default function Dashboard() {
  const reduce = useReducedMotion();
  const [now, setNow] = useState(new Date());
  const [lastPrediction, setLastPrediction] = useState(null);

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <>
      <AmbientBackground />
      <AmbientParticles />
      <ScrollProgress />
      <FloatingNav />

      <div className="relative mx-auto min-h-screen max-w-7xl px-4 py-8 pb-32 sm:px-6 sm:py-12 sm:pb-24 lg:px-10">
        <motion.header
          initial={{ opacity: 0, y: -28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: easeOut }}
          className="mb-16 border-b border-white/10 pb-12 lg:mb-20"
        >
          <div className="flex flex-col gap-10 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl">
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <span className="ui-badge">Campus intelligence</span>
                <span className="text-xs font-medium text-slate-500">v1 · Random Forest</span>
              </div>
              <h1 className="font-display text-4xl font-extrabold leading-[1.1] tracking-tight text-white sm:text-5xl lg:text-6xl xl:text-7xl">
                <AnimatedWords text="Attendance Predictor" />
              </h1>
              <motion.p
                className="mt-6 max-w-xl text-base leading-relaxed text-slate-400 sm:text-lg"
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4, duration: 0.6, ease: easeOut }}
              >
                Forecast daily headcount from your history. Align canteen, buses, and facilities before
                the bell rings.
              </motion.p>
            </div>

            <motion.div
              initial={{ opacity: 0, scale: 0.94 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.35, type: "spring", stiffness: 100, damping: 18 }}
              className="lg:pt-2"
            >
              <div className="ui-panel relative overflow-hidden rounded-2xl px-6 py-5 ring-1 ring-teal-500/20">
                {!reduce && (
                  <motion.div
                    className="pointer-events-none absolute inset-0 bg-gradient-to-br from-teal-500/10 via-transparent to-cyan-500/5"
                    animate={{ opacity: [0.5, 1, 0.5] }}
                    transition={{ duration: 4, repeat: Infinity }}
                  />
                )}
                <p className="relative text-[10px] font-bold uppercase tracking-[0.25em] text-slate-500">
                  System time
                </p>
                <p className="relative mt-2 font-display text-xl font-semibold tabular-nums text-white sm:text-2xl">
                  {now.toLocaleString()}
                </p>
              </div>
            </motion.div>
          </div>
        </motion.header>

        <div className="flex flex-col gap-14 sm:gap-16 lg:gap-20">
          <ScrollSection id="predict" delay={0}>
            <SectionHeading
              title="Live forecast"
              subtitle="Pick a date — we surface the point estimate plus a tree-based confidence band."
            />
            <PredictionCard onPrediction={setLastPrediction} />
          </ScrollSection>

          <ScrollSection id="best-days" delay={0.01}>
            <SectionHeading
              title="Best days"
              subtitle="Rank the strongest dates in a window, factoring calendar context."
            />
            <BestDaysFinder />
          </ScrollSection>

          <ScrollSection id="calendar-admin" delay={0.015}>
            <SectionHeading
              title="Admin"
              subtitle="Upload and maintain the academic calendar used by rankings and features."
            />
            <CalendarAdmin />
          </ScrollSection>

          <ScrollSection id="resources" delay={0.02}>
            <SectionHeading
              title="Resource matrix"
              subtitle="Heuristic capacity from your latest prediction. Tune multipliers for your campus."
            />
            <ResourcePanel prediction={lastPrediction} />
          </ScrollSection>

          <ScrollSection id="week" delay={0.02}>
            <WeeklyTable />
          </ScrollSection>

          <ScrollSection id="trends" delay={0.02}>
            <SectionHeading
              title="Attendance curves"
              subtitle="Historical actuals with a short predicted tail. Resize the window to zoom."
            />
            <AttendanceChart />
          </ScrollSection>

          <ScrollSection id="notify" delay={0.02}>
            <SectionHeading
              title="Stay informed"
              subtitle="Wire SMTP once — staff get a polished digest before the next school day."
            />
            <NotificationSettings />
          </ScrollSection>
        </div>

        <ModelFooter />
      </div>
    </>
  );
}
