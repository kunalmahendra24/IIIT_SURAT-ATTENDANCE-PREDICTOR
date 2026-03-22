import { motion, useReducedMotion } from "framer-motion";
import { useMemo } from "react";

export default function AmbientParticles() {
  const reduce = useReducedMotion();

  const dots = useMemo(
    () =>
      Array.from({ length: 22 }, (_, i) => ({
        id: i,
        left: `${(i * 19 + 5) % 100}%`,
        top: `${(i * 27 + 9) % 96}%`,
        size: 1.5 + (i % 3),
        duration: 6 + (i % 6),
        delay: i * 0.12,
      })),
    []
  );

  if (reduce) return null;

  return (
    <div className="pointer-events-none fixed inset-0 -z-[5] overflow-hidden" aria-hidden>
      {dots.map((d) => (
        <motion.span
          key={d.id}
          className="absolute rounded-full bg-teal-400/40 shadow-[0_0_12px_rgba(45,212,191,0.4)]"
          style={{
            left: d.left,
            top: d.top,
            width: d.size,
            height: d.size,
          }}
          animate={{
            y: [0, -22, 0],
            opacity: [0.2, 0.7, 0.2],
            scale: [1, 1.5, 1],
          }}
          transition={{
            duration: d.duration,
            delay: d.delay,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}
