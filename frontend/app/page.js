import styles from "./page.module.css";

/* Scattered background shapes — deterministic positions */
const BG_SHAPES = [
  { top: "8%", left: "12%", delay: "0s", size: 6 },
  { top: "15%", left: "78%", delay: "1.5s", size: 8 },
  { top: "25%", left: "45%", delay: "0.8s", size: 5 },
  { top: "32%", left: "88%", delay: "2.2s", size: 7 },
  { top: "45%", left: "5%", delay: "0.3s", size: 6 },
  { top: "52%", left: "65%", delay: "1.8s", size: 9 },
  { top: "60%", left: "30%", delay: "2.5s", size: 5 },
  { top: "68%", left: "92%", delay: "0.6s", size: 7 },
  { top: "75%", left: "18%", delay: "1.2s", size: 8 },
  { top: "82%", left: "55%", delay: "3s", size: 6 },
  { top: "10%", left: "35%", delay: "1s", size: 5 },
  { top: "40%", left: "72%", delay: "2s", size: 7 },
  { top: "55%", left: "15%", delay: "0.5s", size: 6 },
  { top: "88%", left: "40%", delay: "1.7s", size: 8 },
  { top: "20%", left: "60%", delay: "2.8s", size: 5 },
  { top: "70%", left: "80%", delay: "0.9s", size: 6 },
  { top: "35%", left: "25%", delay: "3.2s", size: 7 },
  { top: "90%", left: "70%", delay: "1.4s", size: 5 },
];

export default function Home() {
  return (
    <div className={styles.page}>
      {/* ─── Background Pattern ────────────────────────────────────────── */}
      <div className={styles.bgPattern}>
        {BG_SHAPES.map((s, i) => (
          <div
            key={i}
            className={styles.bgShape}
            style={{
              top: s.top,
              left: s.left,
              width: s.size,
              height: s.size,
              animationDelay: s.delay,
            }}
          />
        ))}
      </div>

      {/* ─── Navbar ────────────────────────────────────────────────────── */}
      <nav className={styles.navbar} id="navbar">
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
      </nav>

      {/* ─── Hero Section ──────────────────────────────────────────────── */}
      <section className={styles.hero} id="hero">
        <h1 className={styles.heroTitle}>Quantioa</h1>

        {/* 3D Artifact Placeholder — will be replaced with user's asset */}
        <div className={styles.heroPlaceholder}>
          <div className={styles.placeholderGlow} />
          <div className={styles.placeholderBox}>
            <div className={styles.placeholderIcon}>◇</div>
            <div className={styles.placeholderLabel}>3D Artifact</div>
          </div>
        </div>

        <p className={styles.heroSubtitle}>
          We are proud to present Quantioa, the AI-powered trading platform.
          A truly unique approach to autonomous trading, underpinned by
          institutional-grade risk management and real-time market intelligence
          built for the Indian markets.
        </p>

        <div className={styles.heroCursor} />
      </section>

      {/* ─── Stats Strip ───────────────────────────────────────────────── */}
      <section className={styles.statsStrip} id="stats">
        <div className={styles.statsContainer}>
          <div className={styles.statItem}>
            <div className={styles.statValue}>{"<"}50ms</div>
            <div className={styles.statLabel}>Execution Latency</div>
          </div>
          <div className={styles.statItem}>
            <div className={styles.statValue}>6-Layer</div>
            <div className={styles.statLabel}>Risk Management</div>
          </div>
          <div className={styles.statItem}>
            <div className={styles.statValue}>24/7</div>
            <div className={styles.statLabel}>AI Monitoring</div>
          </div>
          <div className={styles.statItem}>
            <div className={styles.statValue}>SEBI</div>
            <div className={styles.statLabel}>Fully Compliant</div>
          </div>
        </div>
      </section>

      {/* ─── Features Section ──────────────────────────────────────────── */}
      <section className={styles.features} id="features">
        <div className={styles.sectionContainer}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTag}>Core Capabilities</span>
            <h2 className={styles.sectionTitle}>
              Everything you need to trade intelligently
            </h2>
            <p className={styles.sectionSubtitle}>
              From real-time data ingestion to autonomous execution, every layer
              is designed for institutional-grade performance.
            </p>
          </div>

          <div className={styles.featuresGrid}>
            <div className={styles.featureCard}>
              <div className={styles.featureIcon}>🧠</div>
              <h3 className={styles.featureTitle}>LLM Strategy Engine</h3>
              <p className={styles.featureDesc}>
                Multi-agent LangGraph workflow powered by DeepSeek and OpenRouter.
                AI analyzes technicals, fundamentals, and sentiment in real-time.
              </p>
            </div>

            <div className={styles.featureCard}>
              <div className={styles.featureIcon}>📡</div>
              <h3 className={styles.featureTitle}>Live Market Data</h3>
              <p className={styles.featureDesc}>
                Upstox WebSocket integration with Kafka streaming delivers
                sub-50ms tick-to-decision latency for lightning-fast reactions.
              </p>
            </div>

            <div className={styles.featureCard}>
              <div className={styles.featureIcon}>🛡️</div>
              <h3 className={styles.featureTitle}>6-Layer Risk Framework</h3>
              <p className={styles.featureDesc}>
                Position limits, circuit breakers, drawdown protection, volatility
                guards, kill switch, and portfolio heat management.
              </p>
            </div>

            <div className={styles.featureCard}>
              <div className={styles.featureIcon}>📊</div>
              <h3 className={styles.featureTitle}>Sentiment Analysis</h3>
              <p className={styles.featureDesc}>
                Perplexity-powered real-time news and social sentiment scoring
                feeds directly into the AI decision pipeline.
              </p>
            </div>

            <div className={styles.featureCard}>
              <div className={styles.featureIcon}>⚡</div>
              <h3 className={styles.featureTitle}>Fast-Path Execution</h3>
              <p className={styles.featureDesc}>
                Critical stop-loss orders bypass the main pipeline via a dedicated
                fast-path for guaranteed sub-10ms execution.
              </p>
            </div>

            <div className={styles.featureCard}>
              <div className={styles.featureIcon}>🏛️</div>
              <h3 className={styles.featureTitle}>SEBI Compliant</h3>
              <p className={styles.featureDesc}>
                Full regulatory compliance with audit trails, position limits,
                margin validation, and automated circuit breakers.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── How It Works ──────────────────────────────────────────────── */}
      <section className={styles.howItWorks} id="how-it-works">
        <div className={styles.sectionContainer}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTag}>How It Works</span>
            <h2 className={styles.sectionTitle}>
              From data to execution in milliseconds
            </h2>
            <p className={styles.sectionSubtitle}>
              A fully autonomous pipeline that ingests, analyzes, decides, and
              executes — all within a single tick.
            </p>
          </div>

          <div className={styles.stepsGrid}>
            <div className={styles.stepCard}>
              <div className={styles.stepNumber}>01</div>
              <h3 className={styles.stepTitle}>Ingest</h3>
              <p className={styles.stepDesc}>
                Live market ticks stream through Upstox WebSocket into our Kafka
                pipeline in real-time.
              </p>
              <div className={styles.stepConnector} />
            </div>

            <div className={styles.stepCard}>
              <div className={styles.stepNumber}>02</div>
              <h3 className={styles.stepTitle}>Analyze</h3>
              <p className={styles.stepDesc}>
                The AI engine processes technicals, sentiment, and fundamentals
                through a multi-agent LLM workflow.
              </p>
              <div className={styles.stepConnector} />
            </div>

            <div className={styles.stepCard}>
              <div className={styles.stepNumber}>03</div>
              <h3 className={styles.stepTitle}>Decide</h3>
              <p className={styles.stepDesc}>
                The strategy synthesizer generates actionable signals with
                confidence scores and risk parameters.
              </p>
              <div className={styles.stepConnector} />
            </div>

            <div className={styles.stepCard}>
              <div className={styles.stepNumber}>04</div>
              <h3 className={styles.stepTitle}>Execute</h3>
              <p className={styles.stepDesc}>
                Orders are validated through all 6 risk layers, then routed to
                Upstox for instant execution.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── CTA Section ───────────────────────────────────────────────── */}
      <section className={styles.cta} id="cta">
        <div className={styles.ctaContainer}>
          <h2 className={styles.ctaTitle}>
            Ready to let AI{" "}
            <span className={styles.ctaAccent}>trade for you?</span>
          </h2>
          <p className={styles.ctaSubtitle}>
            Join the next generation of intelligent trading. Set up your
            portfolio, connect your broker, and let Quantioa handle the rest.
          </p>
          <div className={styles.ctaButtons}>
            <a href="/register">
              <button className={styles.btnPrimary} id="cta-start">
                Get Started →
              </button>
            </a>
            <a href="/docs">
              <button className={styles.btnOutline} id="cta-docs">
                View Documentation
              </button>
            </a>
          </div>
        </div>
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
