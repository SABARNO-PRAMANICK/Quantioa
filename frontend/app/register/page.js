"use client";

import { Mail, Lock, User, Briefcase, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import styles from "../login/layout.module.css";
import { motion } from "framer-motion";

export default function RegisterPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);

  const handleRegister = (e) => {
    e.preventDefault();
    setIsLoading(true);
    // Simulate API registration
    setTimeout(() => {
      router.push("/dashboard");
    }, 1500);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className={styles.formHeader}>
        <span className={styles.logo}>Quantioa</span>
        <h1 className={styles.title}>Apply for Access</h1>
        <p className={styles.subtitle}>Join the next generation of algorithmic traders.</p>
      </div>

      <form className={styles.form} onSubmit={handleRegister}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          <div className={styles.inputGroup}>
            <label className={styles.label}>First Name</label>
            <div className={styles.inputWrapper}>
              <User size={18} className={styles.inputIcon} />
              <input type="text" placeholder="Jane" className={styles.input} required />
            </div>
          </div>
          <div className={styles.inputGroup}>
            <label className={styles.label}>Last Name</label>
            <div className={styles.inputWrapper}>
              <User size={18} className={styles.inputIcon} />
              <input type="text" placeholder="Doe" className={styles.input} required />
            </div>
          </div>
        </div>

        <div className={styles.inputGroup}>
          <label className={styles.label}>Corporate Email</label>
          <div className={styles.inputWrapper}>
            <Mail size={18} className={styles.inputIcon} />
            <input type="email" placeholder="jane.doe@fund.com" className={styles.input} required />
          </div>
        </div>

        <div className={styles.inputGroup}>
          <label className={styles.label}>Trading Experience</label>
          <div className={styles.inputWrapper}>
            <Briefcase size={18} className={styles.inputIcon} />
            <select className={styles.input} required style={{ appearance: 'none' }}>
              <option value="" disabled selected>Select experience level</option>
              <option value="retail">Retail Trader (1-3 yrs)</option>
              <option value="pro">Pro Retail (3+ yrs)</option>
              <option value="institutional">Institutional / Prop Desk</option>
            </select>
          </div>
        </div>

        <div className={styles.inputGroup}>
          <label className={styles.label}>Password</label>
          <div className={styles.inputWrapper}>
            <Lock size={18} className={styles.inputIcon} />
            <input type="password" placeholder="Create a strong password" className={styles.input} required />
          </div>
        </div>

        <button type="submit" className={styles.button} disabled={isLoading}>
          {isLoading ? "Provisioning Cluster..." : (
            <>
              Request Access <Zap size={18} />
            </>
          )}
        </button>
      </form>

      <p className={styles.footerText} style={{ marginTop: '24px' }}>
        Already have an account? 
        <Link href="/login" className={styles.link}>Sign In</Link>
      </p>
    </motion.div>
  );
}
