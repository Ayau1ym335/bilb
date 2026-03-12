import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";

const HeroSection = () => {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
      {/* Animated grid */}
      <div className="absolute inset-0 opacity-10"
        style={{
          backgroundImage: `
            linear-gradient(hsl(var(--neon-blue) / 0.15) 1px, transparent 1px),
            linear-gradient(90deg, hsl(var(--neon-blue) / 0.15) 1px, transparent 1px)
          `,
          backgroundSize: "60px 60px",
        }}
      />

      {/* Radial glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full opacity-20"
        style={{ background: "radial-gradient(circle, hsl(var(--gold) / 0.3), transparent 70%)" }}
      />

      {/* Building SVG illustration */}
      <div className="absolute inset-0 flex items-center justify-center opacity-10 pointer-events-none">
        <svg width="600" height="700" viewBox="0 0 600 700">
          <motion.rect x="150" y="100" width="300" height="500" fill="none" stroke="hsl(var(--gold))" strokeWidth="0.5"
            initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 3, ease: "easeInOut" }}
          />
          <motion.polygon points="100,100 300,10 500,100" fill="none" stroke="hsl(var(--gold))" strokeWidth="0.5"
            initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 3, delay: 0.5 }}
          />
          {/* Window grid */}
          {Array.from({ length: 6 }).map((_, row) =>
            Array.from({ length: 4 }).map((_, col) => (
              <motion.rect
                key={`w-${row}-${col}`}
                x={180 + col * 65}
                y={130 + row * 70}
                width="35" height="50"
                fill="none"
                stroke="hsl(var(--neon-blue))"
                strokeWidth="0.3"
                initial={{ opacity: 0 }}
                animate={{ opacity: [0, 0.5, 0.3] }}
                transition={{ delay: 1 + (row * 4 + col) * 0.05, duration: 1 }}
              />
            ))
          )}
        </svg>
      </div>

      {/* Floating data panels */}
      {[
        { label: "Structural Integrity", value: "87%", x: "10%", y: "25%", delay: 0.5 },
        { label: "Sustainability Score", value: "A+", x: "78%", y: "20%", delay: 0.8 },
        { label: "Reuse Potential", value: "HIGH", x: "5%", y: "65%", delay: 1.1 },
        { label: "Heritage Value", value: "92/100", x: "80%", y: "60%", delay: 1.4 },
      ].map((panel) => (
        <motion.div
          key={panel.label}
          className="absolute glass rounded-lg p-3 hidden lg:block"
          style={{ left: panel.x, top: panel.y }}
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1, y: [0, -8, 0] }}
          transition={{
            opacity: { delay: panel.delay, duration: 0.6 },
            scale: { delay: panel.delay, duration: 0.6 },
            y: { delay: panel.delay + 0.6, duration: 4, repeat: Infinity, ease: "easeInOut" },
          }}
        >
          <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{panel.label}</p>
          <p className="text-lg font-bold text-accent">{panel.value}</p>
        </motion.div>
      ))}

      {/* Content */}
      <div className="relative z-10 mx-auto max-w-4xl px-6 text-center">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3 }}
        >
          <p className="mb-4 font-sans text-sm uppercase tracking-[0.4em] text-accent">
            Adaptive Reuse Intelligence
          </p>
          <h1 className="font-serif text-5xl font-bold leading-tight md:text-7xl lg:text-8xl">
            Turn forgotten buildings{" "}
            <span className="text-gradient-gold">into the future.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl font-sans text-lg text-muted-foreground md:text-xl">
            BILB analyzes buildings and generates data-driven adaptive reuse scenarios — helping cities preserve history while creating new economic value.
          </p>
        </motion.div>

        <motion.div
          className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6, duration: 0.6 }}
        >
          <Button size="lg" className="rounded-full px-8 font-sans text-sm uppercase tracking-wider glow-gold">
            <a href="#early-access">Request Early Access</a>
          </Button>
          <Button variant="outline" size="lg" className="rounded-full border-primary/30 px-8 font-sans text-sm uppercase tracking-wider hover:bg-primary/10">
            Watch the Vision
          </Button>
        </motion.div>

        <motion.p
          className="mt-6 font-sans text-xs text-muted-foreground"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1 }}
        >
          Pre-prototype stage · AI + robotic inspection system in development
        </motion.p>
      </div>
    </section>
  );
};

export default HeroSection;
