"use client";

import { TrendingUp, Activity, Crosshair, ArrowUpRight, ArrowDownRight, Clock, Info } from "lucide-react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import styles from "./page.module.css";
import { motion } from "framer-motion";

// Mock Data
const performanceData = [
  { time: "09:15", value: 100000 },
  { time: "10:30", value: 102500 },
  { time: "11:45", value: 101800 },
  { time: "13:00", value: 104200 },
  { time: "14:15", value: 103900 },
  { time: "15:30", value: 108500 },
];

const activePositions = [
  { symbol: "MON100", strategy: "Mean Reversion", entry: 2000, current: 2045, pnl: 2250, pnlPct: 2.3, stopLoss: 1960 },
  { symbol: "INFY", strategy: "Momentum", entry: 3500, current: 3520, pnl: 1200, pnlPct: 0.6, stopLoss: 3430 },
  { symbol: "TCS", strategy: "Trend Following", entry: 4100, current: 4050, pnl: -1500, pnlPct: -1.2, stopLoss: 4000 },
];

const aiDecisions = [
  { time: "14:22:05", action: "Stop Loss Updated", symbol: "INFY", detail: "Trail stop adjusted to ₹3430. Favorable volatility regime detected." },
  { time: "13:45:12", action: "Position Trimmed", symbol: "MON100", detail: "RSI indicating overbought conditions. Locked in 50% profits." },
  { time: "11:15:00", action: "Signal Rejected", symbol: "RELIANCE", detail: "Technical buy signal ignored due to bearish Perplexity sentiment score (0.2)." },
];

export default function Dashboard() {
  const containerVariants = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.1 } }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 300, damping: 24 } }
  };

  return (
    <motion.div 
      className={styles.dashboard}
      variants={containerVariants}
      initial="hidden"
      animate="show"
    >
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Welcome back, Pro Trader</h1>
          <p className={styles.subtitle}>System status: All engines operating at optimal parameters.</p>
        </div>
        <div className={styles.liveIndicator}>
          <span className={styles.pulseDot}></span>
          Engine Active via WebSockets
        </div>
      </div>

      {/* ─── Macro Metrics ──────────────────────────────────────────────── */}
      <div className={styles.metricsGrid}>
        <motion.div className={styles.metricCard} variants={itemVariants}>
          <div className={styles.metricHeader}>
            <span className={styles.metricLabel}>Net Liquidity</span>
            <Activity size={16} className={styles.metricIcon} />
          </div>
          <div className={styles.metricValue}>₹1,25,000</div>
          <div className={styles.metricMeta}>
            <span className={styles.positive}>+₹3,250 (+2.6%)</span> Today
          </div>
        </motion.div>

        <motion.div className={styles.metricCard} variants={itemVariants}>
          <div className={styles.metricHeader}>
            <span className={styles.metricLabel}>Win Rate (30D)</span>
            <Crosshair size={16} className={styles.metricIcon} />
          </div>
          <div className={styles.metricValue}>54.2%</div>
          <div className={styles.metricMeta}>
            Sharpe Ratio: <span className={styles.highlight}>1.35</span>
          </div>
        </motion.div>

        <motion.div className={styles.metricCard} variants={itemVariants}>
          <div className={styles.metricHeader}>
            <span className={styles.metricLabel}>Active Strategies</span>
            <TrendingUp size={16} className={styles.metricIcon} />
          </div>
          <div className={styles.metricValue}>3</div>
          <div className={styles.metricMeta}>
            Risk Exposure: <span className={styles.highlight}>Medium</span>
          </div>
        </motion.div>

        <motion.div className={styles.metricCard} variants={itemVariants}>
          <div className={styles.metricHeader}>
            <span className={styles.metricLabel}>Max Drawdown</span>
            <ArrowDownRight size={16} className={styles.metricIcon} />
          </div>
          <div className={styles.metricValue}>-16.8%</div>
          <div className={styles.metricMeta}>
            Limit set at: <span className={styles.highlight}>-20.0%</span>
          </div>
        </motion.div>
      </div>

      <div className={styles.mainGrid}>
        {/* ─── Equity Curve Chart ─────────────────────────────────────────── */}
        <motion.div className={`${styles.panel} ${styles.chartPanel}`} variants={itemVariants}>
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>Portfolio Trajectory</h2>
            <div className={styles.chartActions}>
              <button className={`${styles.chartBtn} ${styles.active}`}>1D</button>
              <button className={styles.chartBtn}>1W</button>
              <button className={styles.chartBtn}>1M</button>
              <button className={styles.chartBtn}>ALL</button>
            </div>
          </div>
          <div className={styles.chartContainer}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={performanceData} margin={{ top: 10, right: 0, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#AD0021" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#AD0021" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="time" stroke="rgba(255,255,255,0.4)" fontSize={12} tickLine={false} axisLine={false} dy={10} />
                <YAxis domain={["dataMin - 1000", "dataMax + 1000"]} hide />
                <Tooltip 
                  contentStyle={{ backgroundColor: "#1a080c", border: "1px solid rgba(173,0,33,0.3)", borderRadius: "8px" }}
                  itemStyle={{ color: "#FFF0F5" }}
                  formatter={(value) => [`₹${value.toLocaleString()}`, "Value"]}
                />
                <Area type="monotone" dataKey="value" stroke="#AD0021" strokeWidth={2} fillOpacity={1} fill="url(#colorValue)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </motion.div>

        {/* ─── AI Decision Feed ───────────────────────────────────────────── */}
        <motion.div className={`${styles.panel} ${styles.feedPanel}`} variants={itemVariants}>
          <div className={styles.panelHeader}>
            <h2 className={styles.panelTitle}>Live AI Decisions</h2>
            <Info size={16} className={styles.infoIcon} />
          </div>
          <div className={styles.feedList}>
            {aiDecisions.map((decision, idx) => (
              <div key={idx} className={styles.feedItem}>
                <div className={styles.feedTime}><Clock size={12} /> {decision.time}</div>
                <div className={styles.feedAction}>
                  <span className={styles.feedSymbol}>{decision.symbol}</span>
                  <span className={styles.feedBadge}>{decision.action}</span>
                </div>
                <p className={styles.feedDetail}>{decision.detail}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* ─── Active Positions ─────────────────────────────────────────────── */}
      <motion.div className={`${styles.panel} ${styles.positionsPanel}`} variants={itemVariants}>
        <div className={styles.panelHeader}>
          <h2 className={styles.panelTitle}>Active Positions</h2>
          <button className={styles.outlineBtn}>View All History</button>
        </div>
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Symbol / Strategy</th>
                <th>Avg Entry</th>
                <th>Current Price</th>
                <th>Trailing Stop</th>
                <th className={styles.textRight}>Unrealized P&L</th>
              </tr>
            </thead>
            <tbody>
              {activePositions.map((pos, idx) => {
                const isPositive = pos.pnl > 0;
                return (
                  <tr key={idx}>
                    <td>
                      <div className={styles.cellSymbol}>{pos.symbol}</div>
                      <div className={styles.cellStrategy}>{pos.strategy}</div>
                    </td>
                    <td className={styles.cellMono}>₹{pos.entry.toLocaleString()}</td>
                    <td className={styles.cellMono}>₹{pos.current.toLocaleString()}</td>
                    <td className={styles.cellMono}>₹{pos.stopLoss.toLocaleString()}</td>
                    <td className={styles.textRight}>
                      <div className={`${styles.cellPnl} ${isPositive ? styles.positive : styles.negative}`}>
                        {isPositive ? "+" : ""}₹{Math.abs(pos.pnl).toLocaleString()} ({isPositive ? "+" : ""}{pos.pnlPct}%)
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </motion.div>
    </motion.div>
  );
}
