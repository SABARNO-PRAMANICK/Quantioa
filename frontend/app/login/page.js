"use client";

import { Mail, Lock, LogIn } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import styles from "./layout.module.css";
import { motion } from "framer-motion";

export default function LoginPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = (e) => {
    e.preventDefault();
    setIsLoading(true);
    // Simulate API call
    setTimeout(() => {
      router.push("/dashboard");
    }, 1000);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className={styles.formHeader}>
        <span className={styles.logo}>Quantioa</span>
        <h1 className={styles.title}>Welcome back</h1>
        <p className={styles.subtitle}>Enter your credentials to access your trading cluster.</p>
      </div>

      <form className={styles.form} onSubmit={handleLogin}>
        <div className={styles.inputGroup}>
          <label className={styles.label}>Email Address</label>
          <div className={styles.inputWrapper}>
            <Mail size={18} className={styles.inputIcon} />
            <input 
              type="email" 
              placeholder="trader@hedgefund.com" 
              className={styles.input}
              required
            />
          </div>
        </div>

        <div className={styles.inputGroup}>
          <div className={styles.label}>
            Password
            <Link href="#" className={styles.forgotLink}>Forgot password?</Link>
          </div>
          <div className={styles.inputWrapper}>
            <Lock size={18} className={styles.inputIcon} />
            <input 
              type="password" 
              placeholder="••••••••••••" 
              className={styles.input}
              required
            />
          </div>
        </div>

        <button type="submit" className={styles.button} disabled={isLoading}>
          {isLoading ? "Authenticating..." : (
            <>
              Sign In <LogIn size={18} />
            </>
          )}
        </button>
      </form>

      <div className={styles.divider}>or</div>

      <button type="button" className={styles.googleBtn}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M22.56 12.25C22.56 11.47 22.49 10.72 22.36 10H12V14.26H17.92C17.67 15.63 16.86 16.8 15.69 17.58V20.34H19.26C21.35 18.42 22.56 15.6 22.56 12.25Z" fill="#4285F4"/>
          <path d="M12 23C14.97 23 17.46 22.02 19.26 20.34L15.69 17.58C14.71 18.23 13.46 18.66 12 18.66C9.17001 18.66 6.77001 16.75 5.90001 14.19H2.22001V17.04C4.02001 20.61 7.71001 23 12 23Z" fill="#34A853"/>
          <path d="M5.89998 14.19C5.67998 13.53 5.54998 12.78 5.54998 12C5.54998 11.22 5.67998 10.47 5.89998 9.81V6.96H2.21998C1.45998 8.48 1.01998 10.18 1.01998 12C1.01998 13.82 1.45998 15.52 2.21998 17.04L5.89998 14.19Z" fill="#FBBC05"/>
          <path d="M12 5.34C13.62 5.34 15.06 5.9 16.2 6.99L19.34 3.85C17.45 2.09 14.96 1 12 1C7.70998 1 4.01998 3.39 2.21998 6.96L5.89998 9.81C6.76998 7.25 9.16998 5.34 12 5.34Z" fill="#EA4335"/>
        </svg>
        Continue with Google
      </button>

      <p className={styles.footerText}>
        New to Quantioa? 
        <Link href="/register" className={styles.link}>Apply for Access</Link>
      </p>
    </motion.div>
  );
}
