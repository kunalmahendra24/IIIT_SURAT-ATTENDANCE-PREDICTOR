import { motion, useReducedMotion } from "framer-motion";

function buildLinks() {
  let adminMode = false;
  try {
    const params = new URLSearchParams(window.location.search);
    adminMode = params.get("admin") === "1";
  } catch {
    adminMode = false;
  }
  const links = [
    { id: "predict", label: "Predict" },
    { id: "best-days", label: "Best Days" },
  ];
  if (adminMode) links.push({ id: "calendar-admin", label: "Admin" });
  links.push(
    { id: "resources", label: "Resources" },
    { id: "week", label: "7-day" },
    { id: "trends", label: "Trends" },
    { id: "notify", label: "Alerts" }
  );
  return links;
}

const SCROLL_OFFSET = 88;

function scrollToSection(id, preferSmooth) {
  const el = document.getElementById(id);
  if (!el) return;
  const top = el.getBoundingClientRect().top + window.scrollY - SCROLL_OFFSET;
  window.scrollTo({
    top: Math.max(0, top),
    behavior: preferSmooth ? "smooth" : "auto",
  });
}

function NavButtons({ layout = "row" }) {
  const reduce = useReducedMotion();
  const LINKS = buildLinks();

  const go = (hash) => {
    scrollToSection(hash, !reduce);
  };

  const baseBtn =
    "rounded-2xl px-3.5 py-2.5 text-xs font-semibold transition-all duration-200";

  return (
    <div
      className={
        layout === "col"
          ? "flex flex-col gap-1.5"
          : "flex gap-1.5 overflow-x-auto pb-1 pt-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      }
    >
      {LINKS.map((link, i) => (
        <motion.button
          key={link.id}
          type="button"
          initial={{ opacity: 0, y: layout === "col" ? 10 : 0, x: layout === "col" ? 0 : 10 }}
          animate={{ opacity: 1, y: 0, x: 0 }}
          transition={{ delay: 0.6 + i * 0.04 }}
          whileHover={
            reduce
              ? undefined
              : {
                  scale: 1.04,
                  boxShadow: "0 0 24px rgba(45, 212, 191, 0.25)",
                }
          }
          whileTap={{ scale: 0.97 }}
          onClick={() => go(link.id)}
          className={
            layout === "col"
              ? `${baseBtn} border border-white/10 bg-slate-900/80 text-left text-slate-300 hover:border-teal-400/40 hover:bg-teal-500/10 hover:text-teal-100`
              : `${baseBtn} shrink-0 border border-white/10 bg-slate-900/90 text-slate-300 shadow-lg shadow-black/40 backdrop-blur-xl hover:border-teal-400/35 hover:text-teal-200`
          }
        >
          {link.label}
        </motion.button>
      ))}
    </div>
  );
}

export default function FloatingNav() {
  return (
    <>
      <motion.nav
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.45, duration: 0.45 }}
        className="pointer-events-auto fixed bottom-5 left-4 right-4 z-40 md:hidden"
        aria-label="Section navigation"
      >
        <div className="rounded-2xl border border-white/10 bg-slate-950/85 p-2 shadow-2xl shadow-black/60 backdrop-blur-2xl">
          <NavButtons layout="row" />
        </div>
      </motion.nav>

      <motion.nav
        initial={{ opacity: 0, x: 28 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.5, duration: 0.5 }}
        className="pointer-events-auto fixed bottom-10 right-4 z-40 hidden flex-col gap-1.5 rounded-2xl border border-white/10 bg-slate-950/85 p-2.5 shadow-2xl shadow-black/60 backdrop-blur-2xl md:flex lg:right-8"
        aria-label="Section navigation"
      >
        <NavButtons layout="col" />
      </motion.nav>
    </>
  );
}
