"use client";

import { Home, Layers, PieChart, Settings, LogOut, Code, Activity, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "../../dashboard/layout.module.css";
import { motion } from "framer-motion";

const navItems = [
  { icon: Home, label: "Dashboard", href: "/dashboard" },
  { icon: PieChart, label: "Positions", href: "/dashboard/positions" },
  { icon: Layers, label: "Strategies", href: "/dashboard/strategies" },
  { icon: Code, label: "API Keys", href: "/dashboard/api" },
  { icon: ShieldAlert, label: "Risk Limits", href: "/dashboard/risk" },
  { icon: Settings, label: "Settings", href: "/dashboard/settings" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <div className={styles.sidebar}>
      <div className={styles.logoContainer}>
        <Link href="/" className={styles.logo}>Quantioa</Link>
        <span className={styles.statusBadge}>
          <Activity size={12} className={styles.pulse} /> Live
        </span>
      </div>

      <nav className={styles.nav}>
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link key={item.href} href={item.href} className={`${styles.navItem} ${isActive ? styles.active : ""}`}>
              {isActive && (
                <motion.div
                  layoutId="active-nav"
                  className={styles.activeIndicator}
                  transition={{ type: "spring", stiffness: 300, damping: 30 }}
                />
              )}
              <item.icon size={18} className={styles.navIcon} />
              <span className={styles.navLabel}>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className={styles.sidebarFooter}>
        <div className={styles.brokerInfo}>
          <div className={styles.brokerLabel}>Connected Broker</div>
          <div className={styles.brokerName}>Upstox API v3</div>
        </div>
        <button className={styles.logoutBtn}>
          <LogOut size={16} />
          <span>Exit</span>
        </button>
      </div>
    </div>
  );
}
