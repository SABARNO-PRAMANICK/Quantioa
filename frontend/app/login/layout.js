import styles from "./layout.module.css";
import SplineBackground from "../components/SplineBackground";

export const metadata = {
  title: "Quantioa - Login",
  description: "Secure login to the Quantioa AI Trading Platform",
};

export default function AuthLayout({ children }) {
  return (
    <div className={styles.authContainer}>
      <div className={styles.authBackground}>
        <div className={styles.splineWrapper}>
            <SplineBackground />
        </div>
        <div className={styles.bgOverlay} />
      </div>
      <div className={styles.authFormWrapper}>
        <div className={styles.authPanel}>
          {children}
        </div>
      </div>
    </div>
  );
}
