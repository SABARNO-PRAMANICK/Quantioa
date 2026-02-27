import { Inter, Silkscreen, Space_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
  variable: "--font-inter",
});

const silkscreen = Silkscreen({
  subsets: ["latin"],
  weight: ["400", "700"],
  display: "swap",
  variable: "--font-pixel",
});

const spaceMono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  display: "swap",
  variable: "--font-mono",
});

export const metadata = {
  title: "Quantioa — AI-Powered Trading Platform",
  description:
    "Institutional-grade AI trading with real-time market analysis, autonomous strategy execution, and 6-layer risk management. Built for the Indian markets.",
  keywords: [
    "AI trading",
    "algorithmic trading",
    "quantitative finance",
    "Indian stock market",
    "automated trading",
  ],
  openGraph: {
    title: "Quantioa — AI-Powered Trading Platform",
    description:
      "Institutional-grade AI trading with real-time market analysis, autonomous strategy execution, and 6-layer risk management.",
    type: "website",
    locale: "en_IN",
    siteName: "Quantioa",
  },
};

export default function RootLayout({ children }) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${silkscreen.variable} ${spaceMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
