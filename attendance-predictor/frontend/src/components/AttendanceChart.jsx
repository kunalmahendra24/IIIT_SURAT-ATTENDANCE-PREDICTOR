import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";

function addDays(iso, n) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

const chartTooltip = {
  backgroundColor: "rgba(15, 23, 42, 0.95)",
  border: "1px solid rgba(45, 212, 191, 0.25)",
  borderRadius: 12,
  color: "#e2e8f0",
  fontSize: 12,
};

export default function AttendanceChart() {
  const [windowDays, setWindowDays] = useState(30);
  const [hist, setHist] = useState([]);
  const [future, setFuture] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const hRes = await fetch("/api/historical");
        const hJson = await hRes.json();
        if (!hRes.ok) throw new Error(hJson.error || "Historical load failed");
        const rows = (hJson.data || []).map((r) => ({
          date: r.date,
          actual: r.attendance,
        }));
        const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
        const tomorrow = addDays(new Date().toISOString().slice(0, 10), 1);
        const end = addDays(tomorrow, 13);
        const pRes = await fetch(
          `/api/predict-range?start=${encodeURIComponent(tomorrow)}&end=${encodeURIComponent(end)}`
        );
        const pJson = await pRes.json();
        if (!pRes.ok) throw new Error(pJson.error || "Range predict failed");
        const fut = (pJson.predictions || []).map((p) => ({
          date: p.date,
          predicted: p.predicted_attendance,
        }));
        if (!cancelled) {
          setHist(sorted);
          setFuture(fut);
        }
      } catch (e) {
        if (!cancelled) toast.error(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const chartData = useMemo(() => {
    if (!hist.length) return [];
    const startIdx = Math.max(0, hist.length - windowDays);
    const slice = hist.slice(startIdx);
    const lastHist = hist[hist.length - 1].date;
    const out = slice.map((r) => ({ ...r, predicted: null }));
    future.forEach((f) => {
      if (f.date <= lastHist) return;
      out.push({ date: f.date, actual: null, predicted: f.predicted });
    });
    return out.sort((a, b) => a.date.localeCompare(b.date));
  }, [hist, future, windowDays]);

  const axisStyle = { fill: "#94a3b8", fontSize: 11 };

  return (
    <motion.section
      layout
      className="ui-panel rounded-3xl p-6 sm:p-8"
      initial={{ opacity: 0.9 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="font-display text-sm font-semibold text-slate-400">History window</p>
        <div className="flex gap-2">
          {[30, 60, 90].map((d) => (
            <motion.button
              key={d}
              type="button"
              layout
              onClick={() => setWindowDays(d)}
              whileHover={{ scale: 1.05, y: -2 }}
              whileTap={{ scale: 0.95 }}
              transition={{ type: "spring", stiffness: 400, damping: 22 }}
              className={`rounded-xl px-4 py-2 text-xs font-bold transition-all ${
                windowDays === d
                  ? "bg-gradient-to-r from-teal-500 to-cyan-500 text-slate-950 shadow-lg shadow-teal-500/25 ring-2 ring-teal-400/50"
                  : "border border-white/10 bg-slate-950/50 text-slate-400 hover:border-teal-500/30 hover:text-slate-200"
              }`}
            >
              {d}d
            </motion.button>
          ))}
        </div>
      </div>
      <motion.div
        className="relative mt-8 h-80 w-full overflow-hidden rounded-2xl border border-white/5 bg-slate-950/60"
        initial={false}
        animate={{ opacity: loading ? 0.75 : 1 }}
      >
        <AnimatePresence mode="wait">
          {loading ? (
            <motion.div
              key="load"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex h-full flex-col items-center justify-center gap-5 text-slate-500"
            >
              <motion.span
                className="h-12 w-12 rounded-full border-2 border-teal-500/40 border-t-teal-400"
                animate={{ rotate: 360 }}
                transition={{ duration: 0.75, repeat: Infinity, ease: "linear" }}
              />
              <div className="flex gap-1.5">
                {[0, 1, 2, 3, 4].map((i) => (
                  <motion.div
                    key={i}
                    className="h-10 w-1.5 rounded-full bg-teal-500/30"
                    animate={{ scaleY: [0.35, 1, 0.35], opacity: [0.35, 1, 0.35] }}
                    transition={{
                      duration: 0.65,
                      repeat: Infinity,
                      delay: i * 0.07,
                      ease: "easeInOut",
                    }}
                  />
                ))}
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="chart"
              className="h-full w-full p-3"
              initial={{ opacity: 0, scale: 0.97, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ type: "spring", stiffness: 100, damping: 20 }}
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                  <XAxis dataKey="date" tick={axisStyle} stroke="#475569" />
                  <YAxis tick={axisStyle} stroke="#475569" />
                  <Tooltip contentStyle={chartTooltip} />
                  <Legend
                    wrapperStyle={{ paddingTop: 12, fontSize: 12, color: "#cbd5e1" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="actual"
                    name="Actual"
                    stroke="#7dd3fc"
                    strokeWidth={2.5}
                    dot={false}
                    connectNulls
                    animationDuration={1000}
                  />
                  <Line
                    type="monotone"
                    dataKey="predicted"
                    name="Predicted"
                    stroke="#2dd4bf"
                    strokeWidth={2.5}
                    dot={false}
                    connectNulls
                    animationDuration={1000}
                  />
                </LineChart>
              </ResponsiveContainer>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.section>
  );
}
