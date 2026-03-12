import { motion, useInView } from "framer-motion";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";

const EarlyAccessSection = () => {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !email || !role) {
      toast.error("Please fill in all required fields.");
      return;
    }
    setLoading(true);
    try {
      const { error } = await supabase.from("early_access_leads").insert({
        name,
        email,
        company: company || null,
        role,
      });
      if (error) throw error;
      toast.success("Welcome to the BILB network! We'll be in touch.");
      setName("");
      setEmail("");
      setCompany("");
      setRole("");
    } catch {
      toast.error("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section ref={ref} id="early-access" className="relative py-32">
      <div className="absolute inset-0 bg-gradient-to-b from-background via-secondary/10 to-background" />

      <div className="relative z-10 mx-auto max-w-xl px-6">
        <motion.div
          className="text-center"
          initial={{ opacity: 0, y: 40 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
        >
          <p className="mb-4 font-sans text-sm uppercase tracking-[0.4em] text-accent">
            Early Access
          </p>
          <h2 className="font-serif text-3xl font-bold md:text-5xl">
            Join the first adaptive reuse{" "}
            <span className="text-gradient-gold">intelligence network.</span>
          </h2>
        </motion.div>

        <motion.form
          className="mt-12 glass rounded-2xl p-8 space-y-4"
          onSubmit={handleSubmit}
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ delay: 0.3 }}
        >
          <Input
            placeholder="Full Name *"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="bg-background/50 border-border/50"
          />
          <Input
            type="email"
            placeholder="Email *"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="bg-background/50 border-border/50"
          />
          <Input
            placeholder="Company (optional)"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            className="bg-background/50 border-border/50"
          />
          <Select value={role} onValueChange={setRole}>
            <SelectTrigger className="bg-background/50 border-border/50">
              <SelectValue placeholder="Your Role *" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="architect">Architect</SelectItem>
              <SelectItem value="developer">Developer</SelectItem>
              <SelectItem value="investor">Investor</SelectItem>
              <SelectItem value="government">Government</SelectItem>
              <SelectItem value="other">Other</SelectItem>
            </SelectContent>
          </Select>
          <Button
            type="submit"
            size="lg"
            className="w-full rounded-full font-sans text-sm uppercase tracking-wider glow-gold"
            disabled={loading}
          >
            {loading ? "Submitting..." : "Request Early Access"}
          </Button>
        </motion.form>
      </div>
    </section>
  );
};

export default EarlyAccessSection;
