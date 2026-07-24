"use client";

import type { ReactNode } from "react";
import { CountUp } from "@/components/CountUp";

/** A single big-number glass tile. When `count` is given the number animates up
 *  on first render; otherwise `value` (e.g. "Positive") is shown as-is. `delta`
 *  renders a week-over-week chip; `icon` is a rendered element. */
export function StatTile({
  value,
  count,
  decimals = 0,
  label,
  tone,
  icon,
  delta,
  highlight = false,
}: {
  value?: ReactNode;
  count?: number;
  decimals?: number;
  label: string;
  tone?: string;
  icon?: ReactNode;
  delta?: ReactNode;
  highlight?: boolean;
}) {
  const color = tone ? `var(--color-${tone})` : "hsl(var(--foreground))";
  return (
    <div
      className={`glass glass-hover relative overflow-hidden rounded-[var(--radius)] p-4 ${
        highlight ? "ring-accent" : ""
      }`}
    >
      {icon && (
        <span
          className="pointer-events-none absolute -right-3 -top-3 opacity-[0.12] [&_svg]:size-16"
          style={{ color }}
        >
          {icon}
        </span>
      )}
      <div className="relative">
        <div className="text-2xl font-bold capitalize" style={{ color }}>
          {count != null ? <CountUp value={count} decimals={decimals} /> : value}
        </div>
        <div className="mt-1 flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <span>{label}</span>
          {delta}
        </div>
      </div>
    </div>
  );
}
