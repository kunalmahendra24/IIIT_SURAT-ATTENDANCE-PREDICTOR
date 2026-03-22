import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { toast } from "sonner";

const easeOut = [0.22, 1, 0.36, 1];

export default function NotificationSettings() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    staff_email: "",
    smtp_host: "smtp.gmail.com",
    smtp_port: 587,
    sender_email: "",
    sender_password: "",
    enabled: false,
    send_time: "18:00",
  });
  const [lastSent, setLastSent] = useState(null);
  const [passwordSet, setPasswordSet] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/settings/email");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load settings");
      setForm((f) => ({
        ...f,
        staff_email: data.staff_email || "",
        smtp_host: data.smtp_host || f.smtp_host,
        smtp_port: data.smtp_port ?? f.smtp_port,
        sender_email: data.sender_email || "",
        enabled: !!data.enabled,
        send_time: data.send_time || "18:00",
      }));
      setPasswordSet(!!data.sender_password_set);
      setLastSent(data.last_notification_at || null);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) load();
  }, [open]);

  const save = async () => {
    setSaving(true);
    try {
      const body = { ...form };
      if (!body.sender_password) delete body.sender_password;
      const res = await fetch("/api/settings/email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Save failed");
      toast.success("Settings saved");
      setPasswordSet(!!data.sender_password_set);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async () => {
    try {
      const res = await fetch("/api/send-notification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ staff_email: form.staff_email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Send failed");
      toast.success(data.message || "Test email sent");
      load();
    } catch (e) {
      toast.error(e.message);
    }
  };

  return (
    <motion.section layout className="ui-panel overflow-hidden rounded-3xl p-6 sm:p-8">
      <motion.button
        type="button"
        onClick={() => setOpen((o) => !o)}
        whileHover={{ x: 3 }}
        className="flex w-full items-center justify-between gap-4 text-left"
      >
        <span>
          <h2 className="font-display text-xl font-bold text-white sm:text-2xl">Email &amp; alerts</h2>
          <p className="mt-1 text-sm text-slate-400">
            SMTP, daily digest time, and test sends for tomorrow&apos;s forecast
          </p>
        </span>
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.3, ease: easeOut }}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-slate-900/80 text-lg text-teal-400"
          aria-hidden
        >
          ▾
        </motion.span>
      </motion.button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: easeOut }}
            className="overflow-hidden"
          >
            <div className="mt-8 space-y-5 border-t border-white/10 pt-8">
              {loading ? (
                <div className="flex justify-center py-10">
                  <motion.span
                    className="h-9 w-9 rounded-full border-2 border-teal-500/40 border-t-teal-400"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 0.75, repeat: Infinity, ease: "linear" }}
                  />
                </div>
              ) : (
                <>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Staff email
                    <input
                      type="email"
                      value={form.staff_email}
                      onChange={(e) => setForm({ ...form, staff_email: e.target.value })}
                      className="ui-input"
                    />
                  </label>
                  <label className="flex cursor-pointer items-center gap-3 text-sm font-medium text-slate-300">
                    <input
                      type="checkbox"
                      checked={form.enabled}
                      onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                      className="h-4 w-4 rounded border-white/20 bg-slate-900 text-teal-500 focus:ring-teal-500/30"
                    />
                    Enable scheduled daily notifications
                  </label>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Send time (24h)
                    <input
                      type="time"
                      value={form.send_time}
                      onChange={(e) => setForm({ ...form, send_time: e.target.value })}
                      className="ui-input max-w-[200px]"
                    />
                  </label>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                      SMTP host
                      <input
                        value={form.smtp_host}
                        onChange={(e) => setForm({ ...form, smtp_host: e.target.value })}
                        className="ui-input"
                      />
                    </label>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                      SMTP port
                      <input
                        type="number"
                        value={form.smtp_port}
                        onChange={(e) =>
                          setForm({ ...form, smtp_port: Number(e.target.value) })
                        }
                        className="ui-input"
                      />
                    </label>
                  </div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Sender email
                    <input
                      type="email"
                      value={form.sender_email}
                      onChange={(e) => setForm({ ...form, sender_email: e.target.value })}
                      className="ui-input"
                    />
                  </label>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Sender password / app password
                    <input
                      type="password"
                      placeholder={passwordSet ? "(leave blank to keep)" : ""}
                      value={form.sender_password}
                      onChange={(e) => setForm({ ...form, sender_password: e.target.value })}
                      className="ui-input"
                    />
                  </label>
                  <div className="flex flex-wrap gap-3 pt-2">
                    <motion.button
                      type="button"
                      onClick={save}
                      disabled={saving}
                      whileHover={{ scale: saving ? 1 : 1.02 }}
                      whileTap={{ scale: saving ? 1 : 0.98 }}
                      className="ui-btn-primary disabled:opacity-50"
                    >
                      {saving ? "Saving…" : "Save settings"}
                    </motion.button>
                    <motion.button
                      type="button"
                      onClick={sendTest}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      className="rounded-xl border border-teal-500/40 bg-teal-500/10 px-6 py-3 text-sm font-semibold text-teal-200 transition-colors hover:bg-teal-500/20"
                    >
                      Send test email
                    </motion.button>
                  </div>
                  {lastSent && (
                    <p className="text-xs text-slate-500">
                      Last sent: {new Date(lastSent).toLocaleString()}
                    </p>
                  )}
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}
