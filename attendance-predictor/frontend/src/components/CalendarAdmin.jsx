import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

const TYPE_OPTIONS = ["exam", "holiday", "break", "fest", "class_resumes", "other"];
const easeOut = [0.22, 1, 0.36, 1];

function emptyEvent() {
  return {
    date: "",
    end_date: null,
    name: "",
    type: "other",
    affects_attendance: true,
    source_text: "",
  };
}

function truncate(s, n = 60) {
  if (!s) return "";
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

function ConfirmModal({ open, title, body, confirmText, confirmTone = "primary", onConfirm, onClose }) {
  if (!open) return null;
  const btnCls =
    confirmTone === "danger"
      ? "rounded-xl border border-rose-500/25 bg-rose-500/15 px-5 py-3 text-sm font-semibold text-rose-100 hover:border-rose-400/40"
      : confirmTone === "amber"
        ? "rounded-xl border border-amber-500/25 bg-amber-500/15 px-5 py-3 text-sm font-semibold text-amber-100 hover:border-amber-400/40"
        : "ui-btn-primary";
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 px-4">
      <motion.div
        initial={{ opacity: 0, y: 18, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -10, scale: 0.98 }}
        transition={{ duration: 0.25 }}
        className="ui-panel w-full max-w-lg rounded-3xl p-6"
        role="dialog"
        aria-modal="true"
      >
        <p className="font-display text-xl font-bold text-white">{title}</p>
        <p className="mt-2 text-sm leading-relaxed text-slate-400">{body}</p>
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-white/10 bg-slate-950/40 px-5 py-3 text-sm font-semibold text-slate-300 hover:border-white/20"
          >
            Cancel
          </button>
          <button type="button" onClick={onConfirm} className={btnCls}>
            {confirmText}
          </button>
        </div>
      </motion.div>
    </div>
  );
}

function MetricRow({ label, oldV, newV, betterIsLower = false }) {
  const oldN = Number(oldV);
  const newN = Number(newV);
  const delta = Number.isFinite(oldN) && Number.isFinite(newN) ? newN - oldN : null;
  const good = delta == null ? null : betterIsLower ? delta < 0 : delta > 0;
  const bad = delta == null ? null : betterIsLower ? delta > 0 : delta < 0;
  const tone = good ? "text-emerald-300" : bad ? "text-rose-300" : "text-slate-300";
  return (
    <div className="grid grid-cols-[1fr_auto_auto] items-center gap-4 rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3">
      <span className="text-sm font-semibold text-slate-200">{label}</span>
      <span className="text-sm tabular-nums text-slate-400">{oldV ?? "—"}</span>
      <span className={`text-sm tabular-nums font-semibold ${tone}`}>
        {newV ?? "—"}
        {delta != null && Number.isFinite(delta) ? (
          <span className="ml-2 text-xs font-semibold text-slate-500">
            ({delta >= 0 ? "+" : ""}
            {delta.toFixed(4)})
          </span>
        ) : null}
      </span>
    </div>
  );
}

export default function CalendarAdmin() {
  const [authChecked, setAuthChecked] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [warnings, setWarnings] = useState([]);

  const [academicYear, setAcademicYear] = useState("");
  const [semester, setSemester] = useState("");
  const [events, setEvents] = useState([]);

  const [dirty, setDirty] = useState(false);
  const fileInputRef = useRef(null);
  const userOverrideRef = useRef(false);
  const [lastSaveOk, setLastSaveOk] = useState(false);

  const [retrainOpen, setRetrainOpen] = useState(false);
  const [rollbackOpen, setRollbackOpen] = useState(false);
  const [retraining, setRetraining] = useState(false);
  const [retrainResult, setRetrainResult] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const me = await fetch("/api/admin/me", { credentials: "include" });
        const meJson = await me.json().catch(() => ({}));
        setAuthenticated(!!meJson?.authenticated);
        const res = await fetch("/api/calendar/events");
        const data = await res.json();
        if (!res.ok) return;
        // Avoid racing: if an upload/extraction already populated state,
        // don't overwrite it with the on-disk calendar fetch response.
        if (userOverrideRef.current) return;
        setAcademicYear(data.academic_year || "");
        setSemester(data.semester || "");
        setEvents(Array.isArray(data.events) ? data.events : []);
      } catch {
        /* optional */
      } finally {
        setAuthChecked(true);
      }
    })();
  }, []);

  const authHeaders = useMemo(() => ({ "Content-Type": "application/json" }), []);

  const onPickFile = () => fileInputRef.current?.click();

  const onDrop = async (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) await uploadPdf(f);
  };

  const login = async () => {
    if (!username || !password) {
      toast.error("Enter username and password");
      return;
    }
    setLoggingIn(true);
    try {
      const res = await fetch("/api/admin/login", {
        method: "POST",
        credentials: "include",
        headers: authHeaders,
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Login failed");
      setAuthenticated(true);
      toast.success("Admin login successful");
    } catch (err) {
      setAuthenticated(false);
      toast.error(err.message || "Login failed");
    } finally {
      setLoggingIn(false);
    }
  };

  const logout = async () => {
    try {
      await fetch("/api/admin/logout", { method: "POST", credentials: "include" });
    } finally {
      setAuthenticated(false);
      toast.message("Logged out");
    }
  };

  const uploadPdf = async (file) => {
    if (!authenticated) return;
    if (!file || !file.name?.toLowerCase().endsWith(".pdf")) {
      toast.error("Please upload a PDF file");
      return;
    }
    setUploading(true);
    setWarnings([]);
    try {
      userOverrideRef.current = true;
      const fd = new FormData();
      fd.append("pdf", file);
      const res = await fetch("/api/calendar/upload", {
        method: "POST",
        credentials: "include",
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload failed");
      // Response is top-level: { events, academic_year, semester, warnings }
      setAcademicYear(data.academic_year || "");
      setSemester(data.semester || "");
      setEvents(Array.isArray(data.events) ? data.events : []);
      setWarnings(Array.isArray(data.warnings) ? data.warnings : []);
      setDirty(true);
      setLastSaveOk(false);
      setRetrainResult(null);
      toast.success("Calendar extracted. Review and save.");
    } catch (err) {
      toast.error(err.message || "Could not extract calendar");
    } finally {
      setUploading(false);
    }
  };

  const updateEvent = (idx, patch) => {
    setEvents((prev) => {
      const next = prev.slice();
      next[idx] = { ...next[idx], ...patch };
      return next;
    });
    setDirty(true);
  };

  const deleteEvent = (idx) => {
    setEvents((prev) => prev.filter((_, i) => i !== idx));
    setDirty(true);
  };

  const addEvent = () => {
    setEvents((prev) => [...prev, emptyEvent()]);
    setDirty(true);
  };

  const resetEdits = () => {
    setWarnings([]);
    setDirty(false);
    setLastSaveOk(false);
    setRetrainResult(null);
    toast.message("Edits cleared (not reloaded from disk)");
  };

  const save = async () => {
    if (!authenticated) return;
    setUploading(true);
    try {
      userOverrideRef.current = true;
      const payload = {
        academic_year: academicYear,
        semester,
        events,
      };
      const res = await fetch("/api/calendar/save", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Save failed");
      setAcademicYear(data.academic_year || "");
      setSemester(data.semester || "");
      setEvents(Array.isArray(data.events) ? data.events : []);
      setWarnings(Array.isArray(data.warnings) ? data.warnings : []);
      setDirty(false);
      setLastSaveOk(true);
      setRetrainResult(null);
      toast.success("Saved calendar_events.json");
    } catch (err) {
      toast.error(err.message || "Could not save calendar");
    } finally {
      setUploading(false);
    }
  };

  const retrain = async () => {
    if (!authenticated) return;
    setRetrainOpen(false);
    setRetraining(true);
    setRetrainResult(null);
    try {
      const res = await fetch("/api/calendar/retrain", { method: "POST", credentials: "include" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Retrain failed");
      setRetrainResult(data);
      if (data.status === "success") toast.success("Model updated successfully");
      else toast.error(data.reverted_reason || "Model reverted");
    } catch (err) {
      toast.error(err.message || "Retrain failed");
    } finally {
      setRetraining(false);
    }
  };

  const rollback = async () => {
    if (!authenticated) return;
    setRollbackOpen(false);
    setRetraining(true);
    try {
      const res = await fetch("/api/calendar/rollback", { method: "POST", credentials: "include" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Rollback failed");
      toast.success("Rollback complete");
      setRetrainResult({ status: "rolled_back", ...data });
      setLastSaveOk(false);
    } catch (err) {
      toast.error(err.message || "Rollback failed");
    } finally {
      setRetraining(false);
    }
  };

  if (!authChecked) {
    return (
      <motion.section layout className="ui-panel relative overflow-hidden rounded-3xl p-6 sm:p-10">
        <p className="text-sm text-slate-400">Loading admin session…</p>
      </motion.section>
    );
  }

  return (
    <motion.section layout className="ui-panel relative overflow-hidden rounded-3xl p-6 sm:p-10">
      <div className="pointer-events-none absolute -right-24 -top-24 h-56 w-56 rounded-full bg-teal-500/10 blur-3xl" />
      <div className="relative">
        <div className="ui-badge mb-4 border-amber-400/30 bg-amber-500/10 text-amber-200">
          Admin · Calendar
        </div>
        <motion.h2
          className="font-display text-2xl font-bold tracking-tight text-white sm:text-3xl"
          initial={{ opacity: 0, x: -12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.45, ease: easeOut }}
        >
          Academic Calendar Admin
        </motion.h2>
        <p className="mt-3 max-w-2xl text-sm text-slate-400">
          Upload the institute calendar PDF, review extracted events, then save. Changes apply immediately.
        </p>

        {!authenticated ? (
          <div className="mt-6 rounded-3xl border border-white/10 bg-slate-950/40 p-6">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Admin login</p>
            <div className="mt-4 grid gap-4 lg:grid-cols-3">
              <label className="flex flex-col text-xs font-semibold uppercase tracking-wider text-slate-500">
                Username
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="ui-input font-sans text-base font-medium"
                  placeholder="admin"
                />
              </label>
              <label className="flex flex-col text-xs font-semibold uppercase tracking-wider text-slate-500">
                Password
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="ui-input font-sans text-base font-medium"
                  placeholder="••••••••"
                />
              </label>
              <div className="flex items-end">
                <motion.button
                  type="button"
                  onClick={login}
                  disabled={loggingIn}
                  whileHover={{ scale: loggingIn ? 1 : 1.03 }}
                  whileTap={{ scale: loggingIn ? 1 : 0.98 }}
                  className="ui-btn-primary w-full disabled:opacity-50"
                >
                  {loggingIn ? "Signing in…" : "Sign in"}
                </motion.button>
              </div>
            </div>
            <p className="mt-4 text-xs text-slate-500">
              Configure `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `SECRET_KEY` in Vercel Environment Variables.
            </p>
          </div>
        ) : (
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-emerald-500/20 bg-emerald-500/10 px-5 py-4">
            <p className="text-sm font-semibold text-emerald-100">Signed in as admin</p>
            <button
              type="button"
              onClick={logout}
              className="rounded-xl border border-white/10 bg-slate-950/40 px-4 py-2 text-sm font-semibold text-slate-200 hover:border-white/20"
            >
              Logout
            </button>
          </div>
        )}

        <div className="mt-6 grid gap-4 lg:grid-cols-3">
          <label className="flex flex-col text-xs font-semibold uppercase tracking-wider text-slate-500">
            Academic year
            <input
              value={academicYear}
              onChange={(e) => {
                setAcademicYear(e.target.value);
                setDirty(true);
              }}
              className="ui-input font-sans text-base font-medium"
              placeholder="2025-2026"
            />
          </label>
          <label className="flex flex-col text-xs font-semibold uppercase tracking-wider text-slate-500">
            Semester
            <select
              value={semester}
              onChange={(e) => {
                setSemester(e.target.value);
                setDirty(true);
              }}
              className="ui-input font-sans text-base font-medium"
            >
              <option value="">—</option>
              <option value="Odd">Odd</option>
              <option value="Even">Even</option>
            </select>
          </label>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) uploadPdf(f);
            e.target.value = "";
          }}
        />

        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={onDrop}
          className="mt-6 rounded-3xl border border-dashed border-white/15 bg-slate-950/40 p-8 text-center"
        >
          <p className="font-display text-lg font-semibold text-slate-200">Drop your calendar PDF here</p>
          <p className="mt-2 text-sm text-slate-500">Or choose a file. Max 10MB. Up to 10 pages.</p>
          <div className="mt-5 flex flex-wrap justify-center gap-3">
            <motion.button
              type="button"
              onClick={onPickFile}
              disabled={uploading || !authenticated}
              whileHover={{ scale: uploading ? 1 : 1.03 }}
              whileTap={{ scale: uploading ? 1 : 0.98 }}
              className="ui-btn-primary disabled:opacity-50"
            >
              {!authenticated ? "Sign in to upload" : uploading ? "Working…" : "Browse PDF"}
            </motion.button>
          </div>
        </div>

        {warnings?.length ? (
          <div className="mt-6 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            <p className="font-bold uppercase tracking-wider text-[11px]">Warnings</p>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <motion.button
            type="button"
            onClick={addEvent}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.98 }}
            className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-slate-200 hover:border-teal-400/30"
          >
            Add Event
          </motion.button>
          <motion.button
            type="button"
            onClick={save}
            disabled={uploading || !dirty || !authenticated}
            whileHover={{ scale: uploading || !dirty ? 1 : 1.03 }}
            whileTap={{ scale: uploading || !dirty ? 1 : 0.98 }}
            className="ui-btn-primary disabled:opacity-50"
          >
            Save
          </motion.button>

          <motion.button
            type="button"
            onClick={() => setRetrainOpen(true)}
            disabled={uploading || retraining || !authenticated || dirty}
            title={
              !authenticated
                ? "Sign in to admin"
                : dirty
                  ? "Save changes before retraining"
                  : retraining
                    ? "Retraining in progress..."
                    : undefined
            }
            whileHover={{ scale: uploading || retraining || !authenticated || dirty ? 1 : 1.03 }}
            whileTap={{ scale: uploading || retraining || !authenticated || dirty ? 1 : 0.98 }}
            className="rounded-xl border border-teal-400/25 bg-teal-500/10 px-4 py-3 text-sm font-semibold text-teal-100 hover:border-teal-400/40 disabled:opacity-50"
          >
            {retraining ? "Retraining — up to 60s…" : "Retrain Model"}
          </motion.button>

          <motion.button
            type="button"
            onClick={() => setRollbackOpen(true)}
            disabled={uploading || retraining}
            whileHover={{ scale: uploading || retraining ? 1 : 1.03 }}
            whileTap={{ scale: uploading || retraining ? 1 : 0.98 }}
            className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm font-semibold text-amber-100 hover:border-amber-400/40 disabled:opacity-50"
          >
            Rollback
          </motion.button>

          <button
            type="button"
            onClick={resetEdits}
            className="rounded-xl border border-white/10 bg-slate-950/40 px-4 py-3 text-sm font-semibold text-slate-300 hover:border-rose-400/30"
          >
            Cancel / Reset
          </button>
          <span className="text-xs text-slate-500">
            {dirty ? "Unsaved changes" : "Up to date"}
          </span>
        </div>

        {retrainResult?.status ? (
          <div className="mt-6 space-y-4">
            {retrainResult.status === "success" ? (
              <div className="rounded-2xl border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
                Model updated successfully.
              </div>
            ) : retrainResult.status === "reverted" ? (
              <div className="rounded-2xl border border-rose-500/25 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
                {retrainResult.reverted_reason || "Model reverted to previous version."}
              </div>
            ) : retrainResult.status === "rolled_back" ? (
              <div className="rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                Rolled back to previous artifacts.
              </div>
            ) : null}

            {retrainResult.old_metrics || retrainResult.new_metrics ? (
              <div className="ui-panel rounded-3xl p-5">
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-slate-500">
                  Metrics comparison
                </p>
                <div className="mt-4 space-y-3">
                  <MetricRow
                    label="MdAPE"
                    oldV={retrainResult.old_metrics?.mdape}
                    newV={retrainResult.new_metrics?.mdape}
                    betterIsLower
                  />
                  <MetricRow
                    label="wMAPE"
                    oldV={retrainResult.old_metrics?.wmape}
                    newV={retrainResult.new_metrics?.wmape}
                    betterIsLower
                  />
                  <MetricRow
                    label="R²"
                    oldV={retrainResult.old_metrics?.r2}
                    newV={retrainResult.new_metrics?.r2}
                  />
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="mt-8 overflow-x-auto rounded-3xl border border-white/10 bg-slate-950/40">
          <table className="min-w-[980px] w-full text-left text-sm">
            <thead>
              <tr className="border-b border-white/10 bg-white/[0.03] text-xs font-bold uppercase tracking-wider text-slate-500">
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">End Date</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Affects</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3">Delete</th>
              </tr>
            </thead>
            <AnimatePresence initial={false}>
              <tbody>
                {events.map((ev, idx) => (
                  <motion.tr
                    key={`${idx}-${ev.date}-${ev.name}`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -10 }}
                    transition={{ duration: 0.2 }}
                    className="border-b border-white/[0.06] last:border-0"
                  >
                    <td className="px-4 py-3">
                      <input
                        type="date"
                        value={ev.date || ""}
                        onChange={(e) => updateEvent(idx, { date: e.target.value })}
                        className="ui-input mt-0 py-2"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="date"
                        value={ev.end_date || ""}
                        onChange={(e) =>
                          updateEvent(idx, { end_date: e.target.value ? e.target.value : null })
                        }
                        className="ui-input mt-0 py-2"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <input
                        value={ev.name || ""}
                        onChange={(e) => updateEvent(idx, { name: e.target.value })}
                        className="ui-input mt-0 py-2"
                        placeholder="Event name"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={ev.type || "other"}
                        onChange={(e) => updateEvent(idx, { type: e.target.value })}
                        className="ui-input mt-0 py-2"
                      >
                        {TYPE_OPTIONS.map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={!!ev.affects_attendance}
                        onChange={(e) => updateEvent(idx, { affects_attendance: e.target.checked })}
                        className="h-5 w-5 accent-teal-400"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className="text-xs text-slate-400"
                        title={ev.source_text || ""}
                      >
                        {truncate(ev.source_text || "", 70)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => deleteEvent(idx)}
                        className="rounded-xl border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-200 hover:border-rose-400/40"
                      >
                        Delete
                      </button>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </AnimatePresence>
          </table>
        </div>
      </div>

      <ConfirmModal
        open={retrainOpen}
        title="Retrain model?"
        body="This will take up to 60 seconds. The previous model will be automatically restored if the new one performs significantly worse. Continue?"
        confirmText="Continue"
        confirmTone="primary"
        onConfirm={retrain}
        onClose={() => setRetrainOpen(false)}
      />
      <ConfirmModal
        open={rollbackOpen}
        title="Rollback model artifacts?"
        body="This restores the previous model artifacts (and calendar_events.prev.json if present). Continue?"
        confirmText="Rollback"
        confirmTone="amber"
        onConfirm={rollback}
        onClose={() => setRollbackOpen(false)}
      />
    </motion.section>
  );
}

