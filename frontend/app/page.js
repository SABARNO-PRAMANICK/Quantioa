"use client";

import { useRef } from "react";
import styles from "./page.module.css";
import SplineBackground from "./components/SplineBackground";
import { motion, useScroll, useTransform, useSpring } from "framer-motion";

/* Scattered background shapes — deterministic positions */
const BG_SHAPES = [
  { top: "8%", left: "12%", delay: "0s", size: 6, speed: 1.2 },
  { top: "15%", left: "78%", delay: "1.5s", size: 8, speed: 0.8 },
  { top: "25%", left: "45%", delay: "0.8s", size: 5, speed: 1.5 },
  { top: "32%", left: "88%", delay: "2.2s", size: 7, speed: 0.9 },
  { top: "45%", left: "5%", delay: "0.3s", size: 6, speed: 1.1 },
  { top: "52%", left: "65%", delay: "1.8s", size: 9, speed: 1.4 },
  { top: "60%", left: "30%", delay: "2.5s", size: 5, speed: 0.7 },
  { top: "68%", left: "92%", delay: "0.6s", size: 7, speed: 1.3 },
  { top: "75%", left: "18%", delay: "1.2s", size: 8, speed: 1.6 },
  { top: "82%", left: "55%", delay: "3s", size: 6, speed: 0.8 },
  { top: "10%", left: "35%", delay: "1s", size: 5, speed: 1.2 },
  { top: "40%", left: "72%", delay: "2s", size: 7, speed: 1.4 },
  { top: "55%", left: "15%", delay: "0.5s", size: 6, speed: 0.9 },
  { top: "88%", left: "40%", delay: "1.7s", size: 8, speed: 1.5 },
  { top: "20%", left: "60%", delay: "2.8s", size: 5, speed: 0.6 },
  { top: "70%", left: "80%", delay: "0.9s", size: 6, speed: 1.1 },
  { top: "35%", left: "25%", delay: "3.2s", size: 7, speed: 1.3 },
  { top: "90%", left: "70%", delay: "1.4s", size: 5, speed: 0.8 },
];

function ParallaxShape({ s, smoothProgress }) {
  const y = useTransform(smoothProgress, [0, 1], ["0vh", `${50 * s.speed}vh`]);
  return (
    <motion.div
      className={styles.bgShape}
      style={{
        top: s.top,
        left: s.left,
        width: s.size,
        height: s.size,
        animationDelay: s.delay,
        y
      }}
    />
  );
}

export default function Home() {
  const containerRef = useRef(null);
  const { scrollYProgress } = useScroll({ target: containerRef, offset: ["start start", "end end"] });
  const smoothProgress = useSpring(scrollYProgress, { stiffness: 100, damping: 30, restDelta: 0.001 });

  // Parallax properties
  const splineOpacity = useTransform(smoothProgress, [0, 0.3], [1, 0.4]);
  const splineBlur = useTransform(smoothProgress, [0, 0.2], ["blur(0px)", "blur(6px)"]);
  const heroY = useTransform(smoothProgress, [0, 0.2], ["0vh", "30vh"]);
  const heroOpacity = useTransform(smoothProgress, [0, 0.15], [1, 0]);
  const heroScale = useTransform(smoothProgress, [0, 0.2], [1, 0.9]);

  // Make stats strip slide in and slightly parallax
  const statsY = useTransform(smoothProgress, [0, 0.3], ["50px", "0px"]);
  const statsOpacity = useTransform(smoothProgress, [0.05, 0.15], [0, 1]);

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.15 },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 40 },
    show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 300, damping: 24 } },
  };

  return (
    <div className={styles.page} ref={containerRef}>
      {/* ─── Background Pattern ────────────────────────────────────────── */}
      <div className={styles.bgPattern}>
        {BG_SHAPES.map((s, i) => (
          <ParallaxShape key={i} s={s} smoothProgress={smoothProgress} />
        ))}
      </div>

      {/* ─── 3D Spline Background ──────────────────────────────────────── */}
      <motion.div
        className={styles.splineWrapper}
        style={{
          opacity: splineOpacity,
          filter: splineBlur,
        }}
      >
        <SplineBackground />
      </motion.div>

      {/* ─── Navbar ────────────────────────────────────────────────────── */}
      <motion.nav 
        className={styles.navbar} 
        id="navbar"
        initial={{ y: -100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
      >
        <a href="/" className={styles.logo}>Q</a>
        <div className={styles.navLinks}>
          <a href="#features" className={styles.navLink}>About</a>
          <a href="#how-it-works" className={styles.navLink}>How It Works</a>
          <a href="/dashboard" className={styles.navLink}>Dashboard</a>
          <a href="#cta" className={styles.navLink}>Docs</a>
          <a href="#footer" className={styles.navLink}>Contact</a>
        </div>
        <a href="#cta">
          <button className={styles.navCta} id="nav-cta">Leave a note</button>
        </a>
      </motion.nav>

      {/* ─── Hero Section ──────────────────────────────────────────────── */}
      <motion.section 
        className={styles.hero} 
        id="hero"
        style={{ y: heroY, opacity: heroOpacity, scale: heroScale }}
      >
        <motion.h1 
          className={styles.heroTitle}
          initial={{ opacity: 0, scale: 0.9, filter: "blur(10px)" }}
          animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
          transition={{ duration: 1.2, delay: 0.2, ease: "easeOut" }}
        >
          Quantioa
        </motion.h1>

        <motion.p 
          className={styles.heroSubtitle}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, delay: 0.6, ease: "easeOut" }}
        >
          Systematic quantitative trading infrastructure.
          Engineered for precision. Driven by logic. Defined by rigorous risk control.
        </motion.p>

        <motion.div 
          className={styles.heroCursor} 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2, duration: 2 }}
        />
      </motion.section>

      {/* ─── Stats Strip ───────────────────────────────────────────────── */}
      <motion.section 
        className={styles.statsStrip} 
        id="stats"
        style={{ y: statsY, opacity: statsOpacity }}
      >
        <div className={styles.statsContainer}>
          <div className={styles.statItem}>
            <div className={styles.statValue}>Optimized</div>
            <div className={styles.statLabel}>Order Execution</div>
          </div>
          <div className={styles.statItem}>
            <div className={styles.statValue}>Dynamic</div>
            <div className={styles.statLabel}>Exposure Management</div>
          </div>
          <div className={styles.statItem}>
            <div className={styles.statValue}>Continuous</div>
            <div className={styles.statLabel}>Market Analysis</div>
          </div>
          <div className={styles.statItem}>
            <div className={styles.statValue}>Robust</div>
            <div className={styles.statLabel}>Regulatory Alignment</div>
          </div>
        </div>
      </motion.section>

      {/* ─── Features Section ──────────────────────────────────────────── */}
      <section className={styles.features} id="features">
        <div className={styles.sectionContainer}>
          <motion.div 
            className={styles.sectionHeader}
            initial={{ opacity: 0, y: 50 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.8, ease: "easeOut" }}
          >
            <span className={styles.sectionTag}>System Architecture</span>
            <h2 className={styles.sectionTitle}>
              Engineered for absolute operational discipline.
            </h2>
            <p className={styles.sectionSubtitle}>
              Our infrastructure is designed to transform market complexity
              into calculated, methodical execution frameworks.
            </p>
          </motion.div>

          <motion.div 
            className={styles.featuresGrid}
            variants={containerVariants}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-100px" }}
          >
            {[
              { icon: "🧠", title: "Quantitative Analysis", desc: "Proprietary models evaluate broad market factors systematically to identify statistical probabilities and execute upon aligned scenarios." },
              { icon: "📡", title: "Data Ingestion pipeline", desc: "Robust information processing ensures our algorithms remain synchronized with shifting market conditions, enabling rapid analytical adaptation." },
              { icon: "🛡️", title: "Comprehensive Risk Control", desc: "Integrated risk parameters dynamically manage market exposure, strictly enforcing predefined safeguards to protect capital under varying regimes." },
              { icon: "📊", title: "Adaptive Intelligence", desc: "Heuristics continuously adjust to newly normalized data, ensuring execution directives remain relevant in an evolving landscape." },
              { icon: "⚡", title: "Optimized Routing", desc: "Advanced logistics govern order placement, prioritizing fill quality while seeking to eliminate operational friction and slippage." },
              { icon: "🏛️", title: "Strict Accountability", desc: "Constructed with adherence to established compliance standards, delivering transparent operational workflows and rigorous internal auditing." }
            ].map((feat, i) => (
              <motion.div key={i} className={styles.featureCard} variants={itemVariants} whileHover={{ y: -10, scale: 1.02 }}>
                <div className={styles.featureIcon}>{feat.icon}</div>
                <h3 className={styles.featureTitle}>{feat.title}</h3>
                <p className={styles.featureDesc}>{feat.desc}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ─── How It Works ──────────────────────────────────────────────── */}
      <section className={styles.howItWorks} id="how-it-works">
        <div className={styles.sectionContainer}>
          <motion.div 
            className={styles.sectionHeader}
            initial={{ opacity: 0, y: 50 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.8, ease: "easeOut" }}
          >
            <span className={styles.sectionTag}>Execution Lifecycle</span>
            <h2 className={styles.sectionTitle}>
              The anatomy of automated execution.
            </h2>
            <p className={styles.sectionSubtitle}>
              A streamlined, systematic process designed to convert market
              information into strictly defined actions.
            </p>
          </motion.div>

          <motion.div 
            className={styles.stepsGrid}
            variants={containerVariants}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-100px" }}
          >
            {[
              { num: "01", title: "Ingest", desc: "The infrastructure continuously normalizes a broad spectrum of global market data streams into actionable formats." },
              { num: "02", title: "Evaluate", desc: "Quantitative systems process the aggregated information to recognize established statistical patterns." },
              { num: "03", title: "Validate", desc: "Potential actions undergo rigorous stress tests against active exposure limits and portfolio constraints." },
              { num: "04", title: "Deploy", desc: "Approved instructions are algorithmically managed for market entry or exit, minimizing slippage footprints." }
            ].map((step, i) => (
              <motion.div key={i} className={styles.stepCard} variants={itemVariants}>
                <div className={styles.stepNumber}>{step.num}</div>
                <h3 className={styles.stepTitle}>{step.title}</h3>
                <p className={styles.stepDesc}>{step.desc}</p>
                {i < 3 && <div className={styles.stepConnector} />}
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ─── CTA Section ───────────────────────────────────────────────── */}
      <section className={styles.cta} id="cta">
        <motion.div 
          className={styles.ctaContainer}
          initial={{ opacity: 0, scale: 0.9, filter: "blur(10px)" }}
          whileInView={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 1, ease: "easeOut" }}
        >
          <h2 className={styles.ctaTitle}>
            Remove the noise.{" "}
            <span className={styles.ctaAccent}>Execute with Quantioa.</span>
          </h2>
          <p className={styles.ctaSubtitle}>
            Leverage professional-grade algorithmic execution —
            systematic, rigorous, and strictly controlled.
          </p>
          <motion.div 
            className={styles.ctaButtons}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8, delay: 0.4 }}
          >
            <a href="/register">
              <motion.button 
                className={styles.btnPrimary} 
                id="cta-start"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                Get Early Access →
              </motion.button>
            </a>
            <a href="/docs">
              <motion.button 
                className={styles.btnOutline} 
                id="cta-docs"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                Learn More
              </motion.button>
            </a>
          </motion.div>
        </motion.div>
      </section>

      {/* ─── Footer ────────────────────────────────────────────────────── */}
      <footer className={styles.footer} id="footer">
        <div className={styles.footerContainer}>
          <a href="/" className={styles.footerLogo}>Q</a>
          <div className={styles.footerLinks}>
            <a href="#features" className={styles.footerLink}>Features</a>
            <a href="/docs" className={styles.footerLink}>Documentation</a>
            <a href="/pricing" className={styles.footerLink}>Pricing</a>
            <a href="mailto:support@quantioa.com" className={styles.footerLink}>Support</a>
            <a href="/privacy" className={styles.footerLink}>Privacy</a>
          </div>
          <div className={styles.footerCopy}>© 2026 Quantioa. All rights reserved.</div>
        </div>
      </footer>
    </div>
  );
}
