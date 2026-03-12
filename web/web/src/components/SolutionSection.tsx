import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { Scan, Brain, Layers, BarChart3 } from "lucide-react";

const steps = [
  { icon: Scan, title: "Robot scans building", desc: "Robotic & drone inspection captures every detail" },
  { icon: Brain, title: "AI analyzes data", desc: "Structural, environmental & heritage assessment" },
  { icon: Layers, title: "Scenarios generated", desc: "Multiple adaptive reuse strategies created" },
  { icon: BarChart3, title: "Decision support", desc: "Financial viability & sustainability comparison" },
];

const SolutionSection = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <section ref={ref} className="relative py-32 overflow-hidden">
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full opacity-10"
        style={{ background: "radial-gradient(circle, hsl(var(--neon-blue) / 0.4), transparent 70%)" }}
      />

      <div className="relative z-10 mx-auto max-w-6xl px-6">
        <motion.div
          className="text-center"
          initial={{ opacity: 0, y: 40 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
        >
          <p className="mb-4 font-sans text-sm uppercase tracking-[0.4em] text-accent">
            The Solution
          </p>
          <h2 className="font-serif text-4xl font-bold md:text-6xl">
            Meet <span className="text-gradient-gold">BILB.</span>
          </h2>
          <p className="mx-auto mt-4 max-w-2xl font-sans text-lg text-muted-foreground">
            The intelligence layer for adaptive reuse.
          </p>
        </motion.div>

        {/* Process flow */}
        <div className="mt-20 grid gap-6 md:grid-cols-4">
          {steps.map((step, i) => (
            <motion.div
              key={step.title}
              className="relative glass rounded-xl p-6 text-center group"
              initial={{ opacity: 0, y: 40 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ delay: 0.2 + i * 0.15, duration: 0.6 }}
            >
              {/* Connector line */}
              {i < 3 && (
                <div className="absolute top-1/2 -right-3 hidden h-px w-6 bg-primary/30 md:block" />
              )}
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full border border-accent/30 bg-accent/5 transition-colors group-hover:bg-accent/10">
                <step.icon className="h-6 w-6 text-accent" />
              </div>
              <p className="font-sans text-xs uppercase tracking-widest text-muted-foreground mb-2">
                Step {i + 1}
              </p>
              <h3 className="font-sans text-base font-semibold">{step.title}</h3>
              <p className="mt-2 font-sans text-sm text-muted-foreground">{step.desc}</p>
            </motion.div>
          ))}
        </div>

        {/* Output cards */}
        <motion.div
          className="mt-16 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ delay: 1, duration: 0.6 }}
        >
          {["Structural Condition", "Sustainability Impact", "Financial Viability", "Reuse Scenarios"].map((label) => (
            <div key={label} className="rounded-lg border border-accent/20 bg-accent/5 px-4 py-3 text-center">
              <p className="font-sans text-xs uppercase tracking-wider text-accent">{label}</p>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
};

export default SolutionSection;
