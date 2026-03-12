import { useState, useCallback } from "react";
import { AnimatePresence } from "framer-motion";
import LoadingIntro from "@/components/LoadingIntro";
import HeroSection from "@/components/HeroSection";
import ProblemSection from "@/components/ProblemSection";
import SolutionSection from "@/components/SolutionSection";
import ProductVisionSection from "@/components/ProductVisionSection";
import MarketSection from "@/components/MarketSection";
import PricingSection from "@/components/PricingSection";
import EarlyAccessSection from "@/components/EarlyAccessSection";
import VisionSection from "@/components/VisionSection";
import Footer from "@/components/Footer";

const Index = () => {
  const [showIntro, setShowIntro] = useState(true);

  const handleIntroComplete = useCallback(() => {
    setShowIntro(false);
  }, []);

  return (
    <>
      <AnimatePresence>
        {showIntro && <LoadingIntro onComplete={handleIntroComplete} />}
      </AnimatePresence>

      {!showIntro && (
        <main className="min-h-screen bg-background">
          <HeroSection />
          <ProblemSection />
          <SolutionSection />
          <ProductVisionSection />
          <MarketSection />
          <PricingSection />
          <EarlyAccessSection />
          <VisionSection />
          <Footer />
        </main>
      )}
    </>
  );
};

export default Index;
