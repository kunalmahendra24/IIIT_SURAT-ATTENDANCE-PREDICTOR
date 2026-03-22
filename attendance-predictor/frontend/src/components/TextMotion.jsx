import { motion, useReducedMotion } from "framer-motion";

const easeOut = [0.22, 1, 0.36, 1];

export function AnimatedWords({ text, className = "" }) {
  const reduce = useReducedMotion();
  const words = text.split(" ");

  if (reduce) {
    return <span className={`font-display text-gradient-hero ${className}`}>{text}</span>;
  }

  return (
    <span className={`inline-block font-display ${className}`}>
      {words.map((word, i) => (
        <motion.span
          key={`${word}-${i}`}
          className="inline-block origin-bottom"
          style={{ marginRight: "0.22em", perspective: 600 }}
          initial={{ opacity: 0, y: 48, rotateX: -28, filter: "blur(10px)" }}
          animate={{ opacity: 1, y: 0, rotateX: 0, filter: "blur(0px)" }}
          transition={{
            delay: 0.06 + i * 0.1,
            duration: 0.65,
            ease: easeOut,
          }}
        >
          <span className="text-gradient-hero inline-block">{word}</span>
        </motion.span>
      ))}
    </span>
  );
}

export function SectionHeading({ title, subtitle, className = "" }) {
  const reduce = useReducedMotion();

  return (
    <div className={`mb-6 ${className}`}>
      <motion.h2
        className="font-display text-xs font-bold uppercase tracking-[0.28em] text-teal-400/90"
        initial={reduce ? false : { opacity: 0, x: -20 }}
        whileInView={reduce ? undefined : { opacity: 1, x: 0 }}
        viewport={{ once: true, amount: 0.9 }}
        transition={{ duration: 0.5, ease: easeOut }}
      >
        {title}
      </motion.h2>
      <motion.div
        className="mt-3 h-1 w-20 rounded-full bg-gradient-to-r from-teal-400 via-cyan-400 to-sky-500 shadow-glow-sm"
        initial={reduce ? false : { scaleX: 0, opacity: 0 }}
        whileInView={reduce ? undefined : { scaleX: 1, opacity: 1 }}
        viewport={{ once: true }}
        transition={{ delay: 0.1, duration: 0.55, ease: easeOut }}
        style={{ originX: 0 }}
      />
      {subtitle && (
        <motion.p
          className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-400"
          initial={reduce ? false : { opacity: 0, y: 10 }}
          whileInView={reduce ? undefined : { opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.18, duration: 0.45 }}
        >
          {subtitle}
        </motion.p>
      )}
    </div>
  );
}
