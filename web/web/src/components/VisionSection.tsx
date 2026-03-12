import { motion, useInView } from "framer-motion";
import { useRef } from "react";

const VisionSection = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <section ref={ref} className="relative py-32 overflow-hidden">
      <div className="relative z-10 mx-auto max-w-4xl px-6 text-center">
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
        >
          <p className="mb-4 font-sans text-sm uppercase tracking-[0.4em] text-accent">
            Our Mission
          </p>
          <h2 className="font-serif text-4xl font-bold md:text-6xl leading-tight">
            Become the global{" "}
            <span className="text-gradient-gold">intelligence layer</span>{" "}
            for adaptive reuse.
          </h2>
          <p className="mx-auto mt-8 max-w-2xl font-sans text-lg text-muted-foreground leading-relaxed">
            Our goal is to help cities preserve cultural heritage while unlocking new economic value — through data, AI, and robotics.
          </p>
        </motion.div>

        {/* Connected buildings network visualization */}
        <motion.div
          className="mt-16 flex justify-center"
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : {}}
          transition={{ delay: 0.5 }}
        >
          <svg width="400" height="200" viewBox="0 0 400 200" className="w-full max-w-md">
            {/* Buildings */}
            {[50, 130, 210, 290, 370].map((x, i) => (
              <g key={i}>
                <motion.rect
                  x={x - 15} y={100 + (i % 2) * 20} width="30" height={50 - (i % 2) * 20}
                  fill="none" stroke="hsl(var(--gold))" strokeWidth="0.8"
                  initial={{ opacity: 0 }}
                  animate={isInView ? { opacity: 0.6 } : {}}
                  transition={{ delay: 0.6 + i * 0.1 }}
                />
                <motion.polygon
                  points={`${x - 18},${100 + (i % 2) * 20} ${x},${85 + (i % 2) * 20} ${x + 18},${100 + (i % 2) * 20}`}
                  fill="none" stroke="hsl(var(--gold))" strokeWidth="0.8"
                  initial={{ opacity: 0 }}
                  animate={isInView ? { opacity: 0.6 } : {}}
                  transition={{ delay: 0.7 + i * 0.1 }}
                />
                <motion.circle
                  cx={x} cy={80 + (i % 2) * 20} r="3"
                  fill="hsl(var(--neon-blue))"
                  initial={{ opacity: 0 }}
                  animate={isInView ? { opacity: [0, 1, 0.5] } : {}}
                  transition={{ delay: 1 + i * 0.1, duration: 0.6 }}
                />
              </g>
            ))}
            {/* Connection lines */}
            {[[50, 130], [130, 210], [210, 290], [290, 370], [50, 210], [130, 290], [210, 370]].map(([x1, x2], i) => (
              <motion.line
                key={i}
                x1={x1} y1={80 + (([50, 130, 210, 290, 370].indexOf(x1)) % 2) * 20}
                x2={x2} y2={80 + (([50, 130, 210, 290, 370].indexOf(x2)) % 2) * 20}
                stroke="hsl(var(--neon-blue))" strokeWidth="0.5"
                initial={{ opacity: 0 }}
                animate={isInView ? { opacity: 0.3 } : {}}
                transition={{ delay: 1.2 + i * 0.05 }}
              />
            ))}
          </svg>
        </motion.div>
      </div>
    </section>
  );
};

export default VisionSection;
