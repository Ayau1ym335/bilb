import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { Cpu, MapPin, Scale, FolderOpen } from "lucide-react";

const features = [
  {
    icon: Cpu,
    title: "AI Scenario Generation",
    desc: "Generate multiple reuse strategies based on structural, social, and environmental data.",
  },
  {
    icon: MapPin,
    title: "Urban Context Analysis",
    desc: "Understand how a building fits into the city ecosystem.",
  },
  {
    icon: Scale,
    title: "Sustainability Comparison",
    desc: "Compare demolition vs preservation impact with hard data.",
  },
  {
    icon: FolderOpen,
    title: "Portfolio Analytics",
    desc: "Analyze entire building portfolios at scale.",
  },
];

const dashboardItems = [
  { label: "Building Digital Twin", value: "Active", color: "text-accent" },
  { label: "Sustainability Score", value: "A+", color: "text-primary" },
  { label: "Economic Viability", value: "94%", color: "text-primary" },
  { label: "Reuse Scenarios", value: "3 Ready", color: "text-accent" },
];

const ProductVisionSection = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <section ref={ref} className="relative py-32 overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-b from-background via-secondary/10 to-background" />

      <div className="relative z-10 mx-auto max-w-6xl px-6">
        <motion.div
          className="text-center"
          initial={{ opacity: 0, y: 40 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
        >
          <p className="mb-4 font-sans text-sm uppercase tracking-[0.4em] text-accent">
            Product Vision
          </p>
          <h2 className="font-serif text-4xl font-bold md:text-6xl">
            The future <span className="text-gradient-gold">platform.</span>
          </h2>
        </motion.div>

        {/* Mock UI Dashboard */}
        <motion.div
          className="mt-16 glass rounded-2xl p-1 glow-blue"
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ delay: 0.3, duration: 0.8 }}
        >
          <div className="rounded-xl bg-background/80 p-6">
            {/* Top bar */}
            <div className="flex items-center justify-between border-b border-border/50 pb-4 mb-6">
              <div className="flex items-center gap-3">
                <div className="h-3 w-3 rounded-full bg-destructive/60" />
                <div className="h-3 w-3 rounded-full bg-primary/60" />
                <div className="h-3 w-3 rounded-full bg-accent/60" />
              </div>
              <p className="font-sans text-xs text-muted-foreground tracking-wider">BILB Platform — Building Analysis Dashboard</p>
              <div />
            </div>

            {/* Dashboard grid */}
            <div className="grid gap-4 md:grid-cols-4 mb-6">
              {dashboardItems.map((item, i) => (
                <motion.div
                  key={item.label}
                  className="rounded-lg border border-border/50 bg-card/50 p-4"
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={isInView ? { opacity: 1, scale: 1 } : {}}
                  transition={{ delay: 0.5 + i * 0.1 }}
                >
                  <p className="font-sans text-[10px] uppercase tracking-widest text-muted-foreground">{item.label}</p>
                  <p className={`mt-1 text-2xl font-bold ${item.color}`}>{item.value}</p>
                </motion.div>
              ))}
            </div>

            {/* Chart placeholder */}
            <div className="rounded-lg border border-border/50 bg-card/30 p-6">
              <p className="font-sans text-xs uppercase tracking-widest text-muted-foreground mb-4">Adaptive Reuse Scenarios Comparison</p>
              <div className="flex items-end gap-3 h-32">
                {[65, 88, 45, 72, 95, 58, 82].map((h, i) => (
                  <motion.div
                    key={i}
                    className="flex-1 rounded-t"
                    style={{ background: i % 2 === 0 ? "hsl(var(--gold) / 0.6)" : "hsl(var(--neon-blue) / 0.4)" }}
                    initial={{ height: 0 }}
                    animate={isInView ? { height: `${h}%` } : {}}
                    transition={{ delay: 0.8 + i * 0.08, duration: 0.6, ease: "easeOut" }}
                  />
                ))}
              </div>
            </div>
          </div>
        </motion.div>

        {/* Feature cards */}
        <div className="mt-16 grid gap-6 md:grid-cols-2">
          {features.map((feature, i) => (
            <motion.div
              key={feature.title}
              className="glass rounded-xl p-6 flex gap-4 group"
              initial={{ opacity: 0, x: i % 2 === 0 ? -30 : 30 }}
              animate={isInView ? { opacity: 1, x: 0 } : {}}
              transition={{ delay: 0.4 + i * 0.1, duration: 0.6 }}
            >
              <div className="flex-shrink-0 flex h-12 w-12 items-center justify-center rounded-lg border border-primary/20 bg-primary/5 transition-colors group-hover:bg-primary/10">
                <feature.icon className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h3 className="font-sans text-base font-semibold">{feature.title}</h3>
                <p className="mt-1 font-sans text-sm text-muted-foreground">{feature.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default ProductVisionSection;
