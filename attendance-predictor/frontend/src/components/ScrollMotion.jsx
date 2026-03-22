import { motion, useReducedMotion } from "framer-motion";

const easeOut = [0.22, 1, 0.36, 1];

export function ScrollSection({ children, id, className = "", delay = 0 }) {
  const reduce = useReducedMotion();

  const variants = reduce
    ? {
        hidden: { opacity: 1, y: 0, filter: "blur(0px)", rotateX: 0 },
        visible: { opacity: 1, y: 0, filter: "blur(0px)", rotateX: 0 },
      }
    : {
        hidden: {
          opacity: 0,
          y: 64,
          filter: "blur(12px)",
          rotateX: 4,
        },
        visible: {
          opacity: 1,
          y: 0,
          filter: "blur(0px)",
          rotateX: 0,
          transition: {
            type: "spring",
            stiffness: 68,
            damping: 22,
            delay,
          },
        },
      };

  return (
    <motion.section
      id={id}
      className={`scroll-mt-[5.5rem] ${className}`.trim()}
      style={{ perspective: 1200 }}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.12, margin: "0px 0px -14% 0px" }}
      variants={variants}
    >
      {children}
    </motion.section>
  );
}

export function Stagger({ children, className = "" }) {
  const reduce = useReducedMotion();

  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.15 }}
      variants={
        reduce
          ? {
              hidden: {},
              visible: { transition: { staggerChildren: 0, delayChildren: 0 } },
            }
          : {
              hidden: {},
              visible: {
                transition: { staggerChildren: 0.08, delayChildren: 0.06 },
              },
            }
      }
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({ children, className = "" }) {
  const reduce = useReducedMotion();

  return (
    <motion.div
      className={className}
      variants={
        reduce
          ? {
              hidden: { opacity: 1, y: 0, scale: 1, rotateY: 0 },
              visible: { opacity: 1, y: 0, scale: 1, rotateY: 0 },
            }
          : {
              hidden: { opacity: 0, y: 36, scale: 0.94, rotateY: -6 },
              visible: {
                opacity: 1,
                y: 0,
                scale: 1,
                rotateY: 0,
                transition: { type: "spring", stiffness: 90, damping: 18 },
              },
            }
      }
      style={{ transformStyle: "preserve-3d" }}
    >
      {children}
    </motion.div>
  );
}

export function CardSurface({ children, className = "" }) {
  const reduce = useReducedMotion();

  return (
    <motion.div
      className={`group/card relative ${className}`}
      whileHover={
        reduce
          ? undefined
          : {
              y: -6,
              rotateX: 2,
              rotateY: -2,
              boxShadow:
                "0 32px 64px -16px rgba(0,0,0,0.55), 0 0 0 1px rgba(45, 212, 191, 0.25), 0 0 40px -12px rgba(45, 212, 191, 0.15)",
              transition: { type: "spring", stiffness: 400, damping: 24 },
            }
      }
      whileTap={reduce ? undefined : { scale: 0.992 }}
      style={{ transformStyle: "preserve-3d" }}
    >
      {!reduce && (
        <div
          className="pointer-events-none absolute inset-0 rounded-3xl bg-gradient-to-tr from-teal-400/15 via-transparent to-cyan-500/10 opacity-0 transition-opacity duration-500 group-hover/card:opacity-100"
          aria-hidden
        />
      )}
      <div className="relative z-10">{children}</div>
    </motion.div>
  );
}
