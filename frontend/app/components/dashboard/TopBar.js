"use client";

import { Bell, Search, User } from "lucide-react";
import styles from "../../dashboard/layout.module.css";
import { motion } from "framer-motion";

export function TopBar() {
  return (
    <header className={styles.topbar}>
      <div className={styles.searchContainer}>
        <Search size={16} className={styles.searchIcon} />
        <input 
          type="text" 
          placeholder="Search symbols, strategies, or docs..." 
          className={styles.searchInput}
        />
      </div>

      <div className={styles.actions}>
        <div className={styles.marketStatus}>
          <span className={styles.statusDot}></span>
          <span className={styles.statusText}>NSE Open</span>
        </div>

        <button className={styles.iconBtn}>
          <Bell size={18} />
          <span className={styles.badge}>3</span>
        </button>

        <div className={styles.userProfile}>
          <div className={styles.avatar}>
            <User size={16} />
          </div>
          <div className={styles.userInfo}>
            <div className={styles.userName}>Pro Trader</div>
            <div className={styles.userTier}>Premium</div>
          </div>
        </div>
      </div>
    </header>
  );
}
