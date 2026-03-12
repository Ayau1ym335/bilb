import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { Check } from "lucide-react";

const plans = [
  {
    name: "Standard",
    price: "300,000",
    currency: "KZT",
    period: "per year",
    features: [
      "Unlimited building analyses",
      "Scenario generation",
      "PDF reports",
      "Email support",
    ],
  },
  {
    name: "Premium",
    price: "600,000",
    currency: "KZT",
    period: "per year",
    featured: true,
    features: [
      "Multi-building comparison",
      "BIM integration",
      "Real-time scenario editing",
      "Priority support",
      "API access",
    ],
  },
];

const PricingSection = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <section ref={ref} className="relative py-32">
      <div className="relative z-10 mx-auto max-w-4xl px-6">
        <motion.div
          className="text-center"
          initial={{ opacity: 0, y: 40 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
        >
          <p className="mb-4 font-sans text-sm uppercase tracking-[0.4em] text-accent">
            Future Platform Pricing
          </p>
          <h2 className="font-serif text-4xl font-bold md:text-5xl">
            <span className="text-gradient-gold">Vision</span> pricing.
          </h2>
          <p className="mt-3 font-sans text-sm text-muted-foreground">
            Planned pricing for the production platform
          </p>
        </motion.div>

        <div className="mt-16 grid gap-6 md:grid-cols-2">
          {plans.map((plan, i) => (
            <motion.div
              key={plan.name}
              className={`rounded-2xl p-8 ${plan.featured ? "glass glow-gold border-primary/30" : "glass"}`}
              initial={{ opacity: 0, y: 30 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ delay: 0.3 + i * 0.15 }}
            >
              {plan.featured && (
                <span className="mb-4 inline-block rounded-full bg-primary/10 px-3 py-1 font-sans text-[10px] uppercase tracking-widest text-primary">
                  Recommended
                </span>
              )}
              <h3 className="font-sans text-xl font-semibold">{plan.name}</h3>
              <div className="mt-4 flex items-baseline gap-1">
                <span className="font-serif text-4xl font-bold text-primary">{plan.price}</span>
                <span className="font-sans text-sm text-muted-foreground">{plan.currency}</span>
              </div>
              <p className="font-sans text-xs text-muted-foreground">{plan.period}</p>

              <ul className="mt-6 space-y-3">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 font-sans text-sm text-foreground/80">
                    <Check className="h-4 w-4 text-primary flex-shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default PricingSection;
