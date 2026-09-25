import Hero from "./sections/Hero";
import Momentum from "./sections/Momentum";
import Stats from "./sections/Stats";
import CityMarquee from "./sections/CityMarquee";
import Features from "./sections/Features";
import Compare from "./sections/Compare";
import HowItWorks from "./sections/HowItWorks";
import FAQ from "./sections/FAQ";
import FooterCTA from "./sections/FooterCTA";

export default function App() {
  return (
    <div id="todira-landing-root">
      <Hero />
      <Momentum />
      <Stats />
      <CityMarquee />
      <Features />
      <Compare />
      <HowItWorks />
      <FAQ />
      <FooterCTA />
    </div>
  );
}
