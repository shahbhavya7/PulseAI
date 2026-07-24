"use client";

import { motion } from "framer-motion";
import { Sparkles, TrendingUp, AlertTriangle, CheckCircle2 } from "lucide-react";
import type { HeroInsight as Insight } from "@/lib/insight";
import { cn } from "@/lib/utils";

const TONE: Record<
  Insight["tone"],
  { color: string; Icon: typeof Sparkles; label: string }
> = {
  critical: { color: "var(--color-critical)", Icon: AlertTriangle, label: "Needs attention" },
  warning: { color: "var(--color-medium)", Icon: TrendingUp, label: "Trending" },
  positive: { color: "var(--color-feature_request)", Icon: CheckCircle2, label: "Looking good" },
  neutral: { color: "var(--color-accent-cyan)", Icon: Sparkles, label: "This week" },
};

/** The hero "insight" strip — the week's headline finding in plain language,
 *  auto-derived from /stats + /summaries. Glows in the tone's accent colour. */
export function HeroInsight({ insight }: { insight: Insight }) {
  const { color, Icon, label } = TONE[insight.tone];
  return (
    <motion.section
      initial={{ opacity: 0, y: 24, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className="glass ring-accent relative overflow-hidden rounded-[var(--radius)] p-6"
      style={{
        // Tone-tinted glow bleeding in from the left.
        boxShadow: `inset 0 1px 0 0 hsl(0 0% 100% / 0.1)`,
      }}
    >
      {/* Animated tone glow */}
      <div
        className="pointer-events-none absolute -left-24 top-1/2 size-64 -translate-y-1/2 rounded-full blur-3xl animate-glow"
        style={{ background: color, opacity: 0.18 }}
      />
      <div className="relative flex items-start gap-4">
        <span
          className="flex size-11 shrink-0 items-center justify-center rounded-xl [&_svg]:size-5"
          style={{ background: `${color}22`, color }}
        >
          <Icon />
        </span>
        <div className="min-w-0">
          <span
            className="text-[11px] font-semibold uppercase tracking-wider"
            style={{ color }}
          >
            {label}
          </span>
          <h2
            className={cn(
              "mt-1 text-lg font-bold leading-snug text-foreground sm:text-xl",
            )}
          >
            {insight.headline}
          </h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
            {insight.detail}
          </p>
        </div>
      </div>
    </motion.section>
  );
}
