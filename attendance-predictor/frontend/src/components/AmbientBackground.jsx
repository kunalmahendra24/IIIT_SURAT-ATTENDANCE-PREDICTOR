import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";

export default function AmbientBackground() {
  const { scrollYProgress } = useScroll();
  const reduce = useReducedMotion();

  const y1 = useTransform(scrollYProgress, [0, 1], ["0%", "38%"]);
  const y2 = useTransform(scrollYProgress, [0, 1], ["0%", "-28%"]);
  const y3 = useTransform(scrollYProgress, [0, 1], ["10%", "-16%"]);
  const rotate = useTransform(scrollYProgress, [0, 1], [0, 22]);
  const scale = useTransform(scrollYProgress, [0, 0.5, 1], [1, 1.05, 1]);

  return (
    <div
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
      aria-hidden
    >
      <div
        className="absolute inset-0 bg-[size:64px_64px] bg-grid-fine opacity-[0.35]"
        style={{ maskImage: "linear-gradient(180deg, black, transparent 85%)" }}
      />
      <motion.div
        style={{ y: y1, rotate, scale }}
        className="absolute -left-48 top-20 h-[min(520px,95vw)] w-[min(520px,95vw)] rounded-full bg-gradient-to-br from-teal-500/25 via-cyan-500/10 to-transparent blur-3xl"
      />
      <motion.div
        style={{ y: y2 }}
        animate={reduce ? {} : { scale: [1, 1.05, 1] }}
        transition={reduce ? undefined : { duration: 10, repeat: Infinity, ease: "easeInOut", delay: 1 }}
        className="absolute -right-40 top-1/4 h-[min(600px,100vw)] w-[min(600px,100vw)] rounded-full bg-gradient-to-bl from-primary/40 via-indigo-900/20 to-transparent blur-3xl"
      />
      <motion.div
        style={{ y: y3 }}
        animate={reduce ? {} : { opacity: [0.35, 0.65, 0.35], x: [0, 16, 0] }}
        transition={reduce ? undefined : { duration: 12, repeat: Infinity, ease: "easeInOut", delay: 0.5 }}
        className="absolute bottom-[12%] left-1/4 h-80 w-80 rounded-full bg-cyan-500/15 blur-3xl"
      />
      <motion.div
        className="absolute right-[15%] top-[6%] h-40 w-40 rounded-full bg-teal-400/20 blur-2xl"
        animate={reduce ? {} : { y: [0, 24, 0], scale: [1, 1.2, 1] }}
        transition={reduce ? undefined : { duration: 7, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );
}
