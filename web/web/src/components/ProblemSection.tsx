import { motion } from "framer-motion";
import { useInView } from "framer-motion";
import { useRef } from "react";

const stats = [
  { value: "3–5×", label: "More expensive than normal renovation" },
  { value: "70%", label: "Decisions based on intuition, not data" },
  { value: "∞", label: "Lost cultural identity & tourism potential" },
];

const ProblemSection = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <section ref={ref} className="relative py-32 overflow-hidden">
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-background via-secondary/20 to-background" />

      <div className="relative z-10 mx-auto max-w-6xl px-6">
        <motion.div
          className="text-center"
          initial={{ opacity: 0, y: 40 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
        >
          <p className="mb-4 font-sans text-sm uppercase tracking-[0.4em] text-destructive">
            The Problem
          </p>
          <h2 className="font-serif text-4xl font-bold md:text-6xl">
            Historic buildings disappear{" "}
            <span className="text-gradient-gold">every day.</span>
          </h2>
        </motion.div>

        {/* Disappearing buildings visualization */}
        <motion.div
          className="mt-16 flex justify-center gap-4"
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ delay: 0.3, duration: 0.8 }}
        >
          {Array.from({ length: 7 }).map((_, i) => (
            <motion.div
              key={i}
              className="flex flex-col items-center"
              animate={isInView ? {
                opacity: i > 4 ? [1, 0.2] : 1,
              } : {}}
              transition={{ delay: 0.5 + i * 0.2, duration: 1.5 }}
            >
              <div className={`w-8 md:w-12 rounded-sm border ${i > 4 ? "border-destructive/40" : "border-primary/40"}`}
                style={{ height: `${60 + Math.random() * 60}px` }}
              />
              <div className="mt-1 h-1 w-full rounded bg-muted" />
            </motion.div>
          ))}
        </motion.div>

        {/* Stats */}
        <div className="mt-20 grid gap-8 md:grid-cols-3">
          {stats.map((stat, i) => (
            <motion.div
              key={stat.label}
              className="glass rounded-xl p-8 text-center"
              initial={{ opacity: 0, y: 30 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ delay: 0.4 + i * 0.15, duration: 0.6 }}
            >
              <p className="font-serif text-4xl font-bold text-primary">{stat.value}</p>
              <p className="mt-3 font-sans text-sm text-muted-foreground">{stat.label}</p>
            </motion.div>
          ))}
        </div>

        {/* Explanation */}
        <motion.div
          className="mt-16 mx-auto max-w-3xl text-center"
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ delay: 0.8 }}
        >
          <p className="font-sans text-lg text-muted-foreground leading-relaxed">
            Developers choose demolition because restoration is expensive and there are no reliable tools to evaluate reuse potential. Cities lose{" "}
            <span className="text-primary">history</span>,{" "}
            <span className="text-primary">identity</span>, and{" "}
            <span className="text-primary">economic opportunity</span>.
          </p>
        </motion.div>
      </div>
    </section>
  );
};

export default ProblemSection;
