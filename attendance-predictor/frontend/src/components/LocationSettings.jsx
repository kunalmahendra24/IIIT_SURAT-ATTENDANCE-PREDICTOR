import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { toast } from "sonner";

const easeOut = [0.22, 1, 0.36, 1];

const WEATHER_ICONS = {
  clear:  "☀️",
  cloudy: "⛅",
  fog:    "🌫️",
  rain:   "🌧️",
  snow:   "❄️",
  storm:  "⛈️",
};

function WeatherBadge({ weather }) {
  if (!weather) return null;
  const icon = WEATHER_ICONS[weather.icon] ?? "🌤️";
  return (
    <div className="mt-5 flex flex-wrap items-center gap-3">
      <span className="text-2xl" aria-label={weather.description}>{icon}</span>
      <div>
        <p className="text-sm font-semibold text-slate-200">
          {weather.description}
          {weather.temp_max != null && (
            <span className="ml-2 text-teal-300">{weather.temp_max.toFixed(1)} °C</span>
          )}
        </p>
        {weather.precipitation != null && (
          <p className="text-xs text-slate-500">
            Precip: {weather.precipitation.toFixed(1)} mm
            {weather.is_extreme && (
              <span className="ml-2 text-rose-400 font-semibold">⚠ Extreme weather</span>
            )}
          </p>
        )}
        <p className="text-xs text-slate-500 mt-0.5">{weather.location} · today</p>
      </div>
    </div>
  );
}

// Popular Indian tech-institute locations for quick pick
const PRESETS = [
  { name: "Surat, Gujarat",        lat: 21.1702, lon: 72.8311 },
  { name: "Ahmedabad, Gujarat",    lat: 23.0225, lon: 72.5714 },
  { name: "Mumbai, Maharashtra",   lat: 19.0760, lon: 72.8777 },
  { name: "Pune, Maharashtra",     lat: 18.5204, lon: 73.8567 },
  { name: "Bengaluru, Karnataka",  lat: 12.9716, lon: 77.5946 },
  { name: "Delhi, NCR",            lat: 28.6139, lon: 77.2090 },
  { name: "Hyderabad, Telangana",  lat: 17.3850, lon: 78.4867 },
  { name: "Chennai, Tamil Nadu",   lat: 13.0827, lon: 80.2707 },
];

export default function LocationSettings() {
  const [open, setOpen]       = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving]   = useState(false);
  const [weather, setWeather] = useState(null);
  const [form, setForm]       = useState({ lat: "", lon: "", name: "" });

  const loadLocation = async () => {
    setLoading(true);
    try {
      const res  = await fetch("/api/settings/location");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load location");
      setForm({ lat: data.lat, lon: data.lon, name: data.name });

      // Fetch today's weather for the stored location
      const wr  = await fetch("/api/weather/today");
      const wd  = await wr.json();
      if (wr.ok) setWeather(wd);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) loadLocation();
  }, [open]);

  const applyPreset = (preset) => {
    setForm({ lat: preset.lat, lon: preset.lon, name: preset.name });
  };

  const save = async () => {
    const lat = parseFloat(form.lat);
    const lon = parseFloat(form.lon);
    if (Number.isNaN(lat) || Number.isNaN(lon)) {
      toast.error("Latitude and longitude must be numbers");
      return;
    }
    setSaving(true);
    try {
      const res = await fetch("/api/settings/location", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ lat, lon, name: form.name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Save failed");
      toast.success(`Location set to ${data.name}`);
      // Refresh weather
      const wr = await fetch("/api/weather/today");
      const wd = await wr.json();
      if (wr.ok) setWeather(wd);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
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
          <h2 className="font-display text-xl font-bold text-white sm:text-2xl">
            Location &amp; weather
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Campus coordinates used for weather-aware predictions
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
            <div className="mt-8 space-y-6 border-t border-white/10 pt-8">
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
                  {/* Quick presets */}
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Quick pick
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {PRESETS.map((p) => (
                        <button
                          key={p.name}
                          type="button"
                          onClick={() => applyPreset(p)}
                          className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                            form.name === p.name
                              ? "border-teal-400/60 bg-teal-500/20 text-teal-200"
                              : "border-white/10 bg-white/[0.03] text-slate-400 hover:border-teal-500/40 hover:text-slate-200"
                          }`}
                        >
                          {p.name}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Manual fields */}
                  <div className="grid gap-4 sm:grid-cols-3">
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Location name
                      <input
                        value={form.name}
                        onChange={(e) => setForm({ ...form, name: e.target.value })}
                        placeholder="e.g. Surat, Gujarat"
                        className="ui-input"
                      />
                    </label>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Latitude
                      <input
                        type="number"
                        step="0.0001"
                        min="-90"
                        max="90"
                        value={form.lat}
                        onChange={(e) => setForm({ ...form, lat: e.target.value })}
                        className="ui-input"
                      />
                    </label>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Longitude
                      <input
                        type="number"
                        step="0.0001"
                        min="-180"
                        max="180"
                        value={form.lon}
                        onChange={(e) => setForm({ ...form, lon: e.target.value })}
                        className="ui-input"
                      />
                    </label>
                  </div>

                  <div className="flex flex-wrap items-center gap-3">
                    <motion.button
                      type="button"
                      onClick={save}
                      disabled={saving}
                      whileHover={{ scale: saving ? 1 : 1.02 }}
                      whileTap={{ scale: saving ? 1 : 0.98 }}
                      className="ui-btn-primary disabled:opacity-50"
                    >
                      {saving ? "Saving…" : "Save location"}
                    </motion.button>
                    <p className="text-xs text-slate-500">
                      Changing location clears the weather cache — next prediction refetches.
                    </p>
                  </div>

                  {/* Live weather preview */}
                  <WeatherBadge weather={weather} />
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}
