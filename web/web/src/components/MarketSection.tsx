import { motion, useInView } from "framer-motion";
import { useRef } from "react";

const points = [
  "Historic building restoration costs are rising globally",
  "Cities face urbanization & sustainability goals pressure",
  "Cultural preservation is becoming a policy priority",
  "Data-driven reuse decisions are in massive demand",
];

const MarketSection = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <section ref={ref} className="relative py-32 overflow-hidden">
      <div className="relative z-10 mx-auto max-w-6xl px-6">
        <motion.div
          className="text-center"
          initial={{ opacity: 0, y: 40 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
        >
          <p className="mb-4 font-sans text-sm uppercase tracking-[0.4em] text-accent">
            Market Opportunity
          </p>
          <h2 className="font-serif text-4xl font-bold md:text-6xl">
            A massive <span className="text-gradient-gold">untapped market.</span>
          </h2>
        </motion.div>

        {/* Globe visualization */}
        <motion.div
          className="mt-16 flex justify-center"
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ delay: 0.3 }}
        >
          <div className="relative w-64 h-64 md:w-80 md:h-80">
            {/* Globe circle */}
            <div className="absolute inset-0 rounded-full border border-primary/20" />
            <div className="absolute inset-4 rounded-full border border-primary/10" />
            <div className="absolute inset-8 rounded-full border border-primary/5" />

            {/* Meridians */}
            <div className="absolute inset-0 rounded-full border border-primary/10" style={{ transform: "rotateY(60deg)" }} />
            <div className="absolute inset-0 rounded-full border border-primary/10" style={{ transform: "rotateX(60deg)" }} />

            {/* Glowing dots */}
            {[
              { top: "20%", left: "45%" },
              { top: "35%", left: "60%" },
              { top: "40%", left: "30%" },
              { top: "55%", left: "50%" },
              { top: "30%", left: "70%" },
              { top: "60%", left: "35%" },
              { top: "25%", left: "55%" },
            ].map((pos, i) => (
              <motion.div
                key={i}
                className="absolute h-2 w-2 rounded-full bg-accent"
                style={pos}
                animate={{ opacity: [0.3, 1, 0.3], scale: [1, 1.5, 1] }}
                transition={{ delay: i * 0.3, duration: 2, repeat: Infinity }}
              />
            ))}

            {/* Center glow */}
            <div className="absolute inset-0 rounded-full" style={{ background: "radial-gradient(circle, hsl(var(--gold) / 0.1), transparent 60%)" }} />
          </div>
        </motion.div>

        {/* Points */}
        <div className="mt-16 grid gap-4 md:grid-cols-2 max-w-3xl mx-auto">
          {points.map((point, i) => (
            <motion.div
              key={point}
              className="flex items-center gap-3 glass rounded-lg p-4"
              initial={{ opacity: 0, x: -20 }}
              animate={isInView ? { opacity: 1, x: 0 } : {}}
              transition={{ delay: 0.5 + i * 0.1 }}
            >
              <div className="h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
              <p className="font-sans text-sm text-foreground/80">{point}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default MarketSection;
