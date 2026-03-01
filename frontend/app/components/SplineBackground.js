"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import styles from "../page.module.css";

const Spline = dynamic(
  () => import("@splinetool/react-spline"),
  {
    ssr: false,
    loading: () => null,
  }
);

export default function SplineBackground() {
  const [loaded, setLoaded] = useState(false);

  return (
    <div className={styles.splineWrapper}>
      <Spline
        scene="https://prod.spline.design/7pxfoTqR3HEceO82/scene.splinecode"
        onLoad={() => setLoaded(true)}
        style={{
          width: "100%",
          height: "100%",
          opacity: loaded ? 1 : 0,
          transition: "opacity 0.8s ease",
        }}
      />
    </div>
  );
}
