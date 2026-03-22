import { motion, useReducedMotion } from "framer-motion";
import Dashboard from "./components/Dashboard.jsx";

export default function App() {
  const reduce = useReducedMotion();

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: reduce ? 0 : 0.55, ease: [0.22, 1, 0.36, 1] }}
    >
      <Dashboard />
    </motion.div>
  );
}
