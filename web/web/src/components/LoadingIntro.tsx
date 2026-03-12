import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";

const LoadingIntro = ({ onComplete }: { onComplete: () => void }) => {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    const timers = [
      setTimeout(() => setPhase(1), 500),
      setTimeout(() => setPhase(2), 1500),
      setTimeout(() => setPhase(3), 2500),
      setTimeout(() => setPhase(4), 3500),
      setTimeout(() => onComplete(), 4500),
    ];
    return () => timers.forEach(clearTimeout);
  }, [onComplete]);

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center bg-background"
        exit={{ opacity: 0 }}
        transition={{ duration: 0.8 }}
      >
        {/* Grid background */}
        <div className="absolute inset-0 overflow-hidden opacity-20">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `
                linear-gradient(hsl(var(--neon-blue) / 0.1) 1px, transparent 1px),
                linear-gradient(90deg, hsl(var(--neon-blue) / 0.1) 1px, transparent 1px)
              `,
              backgroundSize: "40px 40px",
            }}
          />
        </div>

        {/* Building wireframe */}
        <div className="relative">
          <motion.svg
            width="200"
            height="280"
            viewBox="0 0 200 280"
            className="mx-auto"
            initial={{ opacity: 0 }}
            animate={{ opacity: phase >= 0 ? 1 : 0 }}
          >
            {/* Building outline */}
            <motion.rect
              x="40" y="60" width="120" height="200"
              fill="none"
              stroke="hsl(var(--gold))"
              strokeWidth="1"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: phase >= 0 ? 1 : 0 }}
              transition={{ duration: 1.5 }}
            />
            {/* Windows */}
            {[0, 1, 2, 3].map((row) =>
              [0, 1, 2].map((col) => (
                <motion.rect
                  key={`${row}-${col}`}
                  x={55 + col * 35}
                  y={80 + row * 45}
                  width="20"
                  height="30"
                  fill="none"
                  stroke="hsl(var(--neon-blue))"
                  strokeWidth="0.5"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: phase >= 1 ? [0, 1, 0.6] : 0 }}
                  transition={{ delay: (row * 3 + col) * 0.1, duration: 0.5 }}
                />
              ))
            )}
            {/* Roof */}
            <motion.polygon
              points="30,60 100,10 170,60"
              fill="none"
              stroke="hsl(var(--gold))"
              strokeWidth="1"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: phase >= 0 ? 1 : 0 }}
              transition={{ duration: 1.5, delay: 0.3 }}
            />
            {/* Scan lines */}
            {phase >= 1 && (
              <motion.line
                x1="20" y1="0" x2="180" y2="0"
                stroke="hsl(var(--neon-blue))"
                strokeWidth="2"
                initial={{ y1: 0, y2: 0 }}
                animate={{ y1: [0, 280], y2: [0, 280] }}
                transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                opacity={0.3}
              />
            )}
            {/* Data points */}
            {phase >= 1 &&
              [
                [50, 90], [90, 120], [140, 80], [70, 200], [130, 180],
                [60, 150], [120, 140], [100, 220], [150, 110], [80, 170],
              ].map(([cx, cy], i) => (
                <motion.circle
                  key={i}
                  cx={cx}
                  cy={cy}
                  r="2"
                  fill="hsl(var(--neon-blue))"
                  initial={{ opacity: 0, scale: 0 }}
                  animate={{ opacity: [0, 1, 0.5], scale: [0, 1.5, 1] }}
                  transition={{ delay: i * 0.1, duration: 0.6 }}
                />
              ))}
            {/* Connection lines */}
            {phase >= 2 && (
              <>
                <motion.line x1="50" y1="90" x2="90" y2="120" stroke="hsl(var(--neon-blue))" strokeWidth="0.5" initial={{ opacity: 0 }} animate={{ opacity: 0.4 }} />
                <motion.line x1="90" y1="120" x2="140" y2="80" stroke="hsl(var(--neon-blue))" strokeWidth="0.5" initial={{ opacity: 0 }} animate={{ opacity: 0.4 }} />
                <motion.line x1="70" y1="200" x2="130" y2="180" stroke="hsl(var(--neon-blue))" strokeWidth="0.5" initial={{ opacity: 0 }} animate={{ opacity: 0.4 }} />
                <motion.line x1="60" y1="150" x2="120" y2="140" stroke="hsl(var(--neon-blue))" strokeWidth="0.5" initial={{ opacity: 0 }} animate={{ opacity: 0.4 }} />
              </>
            )}
          </motion.svg>

          {/* Transformation labels */}
          {phase >= 2 && (
            <motion.div
              className="mt-6 flex justify-center gap-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              {["Restoration", "Adaptive Reuse", "Alternative"].map((label, i) => (
                <motion.span
                  key={label}
                  className="rounded border border-accent/30 px-2 py-1 font-sans text-[10px] uppercase tracking-widest text-accent"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.2 }}
                >
                  {label}
                </motion.span>
              ))}
            </motion.div>
          )}

          {/* Brand text */}
          {phase >= 3 && (
            <motion.div
              className="mt-10 text-center"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8 }}
            >
              <h1 className="font-serif text-5xl font-bold tracking-wider text-primary">
                BILB
              </h1>
              <p className="mt-2 font-sans text-sm tracking-[0.3em] text-muted-foreground">
                Brighter with history
              </p>
            </motion.div>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
};

export default LoadingIntro;
