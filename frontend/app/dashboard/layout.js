import { Sidebar } from "../components/dashboard/Sidebar";
import { TopBar } from "../components/dashboard/TopBar";
import styles from "./layout.module.css";

export const metadata = {
  title: "Quantioa - Trader Dashboard",
  description: "Advanced AI Trading Platform Dashboard",
};

export default function DashboardLayout({ children }) {
  return (
    <div className={styles.dashboardContainer}>
      <Sidebar />
      <div className={styles.mainContent}>
        <TopBar />
        <main className={styles.pageContent}>
          {children}
        </main>
      </div>
    </div>
  );
}
