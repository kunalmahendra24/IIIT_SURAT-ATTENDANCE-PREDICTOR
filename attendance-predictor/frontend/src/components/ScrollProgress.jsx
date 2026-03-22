import { motion, useScroll, useSpring } from "framer-motion";

export default function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, {
    stiffness: 100,
    damping: 28,
    restDelta: 0.001,
  });

  return (
    <motion.div
      className="fixed left-0 right-0 top-0 z-50 h-1 origin-left bg-gradient-to-r from-teal-400 via-cyan-400 to-sky-500 shadow-[0_0_20px_rgba(45,212,191,0.5)]"
      style={{ scaleX }}
      aria-hidden
    />
  );
}
