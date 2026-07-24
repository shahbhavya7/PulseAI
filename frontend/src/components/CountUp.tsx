"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";

/** Animates a number from 0 → `value` on first render (and whenever `value`
 *  changes). Honours prefers-reduced-motion by snapping straight to the value.
 *  `format` lets callers render "Positive" etc. for non-numeric tiles. */
export function CountUp({
  value,
  duration = 900,
  decimals = 0,
  suffix = "",
}: {
  value: number;
  duration?: number;
  decimals?: number;
  suffix?: string;
}) {
  const reduce = useReducedMotion();
  const [display, setDisplay] = useState(reduce ? value : 0);
  const fromRef = useRef(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (reduce) {
      setDisplay(value);
      return;
    }
    const from = fromRef.current;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (value - from) * eased);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        fromRef.current = value;
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [value, duration, reduce]);

  const text =
    decimals > 0 ? display.toFixed(decimals) : Math.round(display).toLocaleString();

  return (
    <span className="tabular-nums">
      {text}
      {suffix}
    </span>
  );
}
