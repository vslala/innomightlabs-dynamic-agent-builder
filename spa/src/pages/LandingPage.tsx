import { Navbar } from '../components/Navbar';
import { Hero } from '../components/Hero';
import { Features } from '../components/Features';
import { HowItWorks } from '../components/HowItWorks';
import { WaitlistForm } from '../components/WaitlistForm';
import { Footer } from '../components/Footer';

export function LandingPage() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <Features />
        <HowItWorks />
        <WaitlistForm />
      </main>
      <Footer />
    </>
  );
}
