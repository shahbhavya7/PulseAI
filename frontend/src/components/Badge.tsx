"use client";

import { Flag, Minus, TrendingDown, TrendingUp } from "lucide-react";
import { humanize } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CATEGORY_ICON, SEVERITY_ICON, domainColor } from "@/lib/icons";
import type { Delta } from "@/lib/insight";

/** Colour-coded pill for a category or severity, with its lucide icon. Colours
 *  come from the CSS tokens so a category is the same colour everywhere. */
export function DomainBadge({
  label,
  tone,
  kind,
  title,
  className,
}: {
  label: string;
  tone?: string;
  kind?: "category" | "severity" | "theme";
  title?: string;
  className?: string;
}) {
  const color = tone ? domainColor(tone) : "hsl(var(--muted-foreground))";
  const Icon =
    kind === "category"
      ? CATEGORY_ICON[label]
      : kind === "severity"
        ? SEVERITY_ICON[label]
        : undefined;

  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium backdrop-blur",
        className,
      )}
      style={{ borderColor: `${color}66`, color, backgroundColor: `${color}14` }}
    >
      {Icon ? (
        <Icon className="size-3" />
      ) : (
        <span
          className="inline-block size-1.5 rounded-full"
          style={{ backgroundColor: color }}
        />
      )}
      {humanize(label)}
    </span>
  );
}

/** A neutral count chip, e.g. the "3 issues" badge on a multi-issue ticket. */
export function CountChip({ n, singular }: { n: number; singular: string }) {
  const label = n === 1 ? singular : `${singular}s`;
  return (
    <span className="rounded-full border border-primary/40 bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
      {n} {label}
    </span>
  );
}

/** Week-over-week ▲/▼ delta chip. `goodWhen` sets which direction is coloured
 *  green vs red (e.g. more issues = bad, higher sentiment = good). */
export function DeltaBadge({
  delta,
  goodWhen = "down",
  suffix = "",
}: {
  delta: Delta | null;
  goodWhen?: "up" | "down";
  suffix?: string;
}) {
  if (!delta || delta.direction === "flat") {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs text-muted-foreground">
        <Minus className="size-3" /> 0
      </span>
    );
  }
  const good = delta.direction === goodWhen;
  const color = good ? "var(--color-feature_request)" : "var(--color-critical)";
  const Icon = delta.direction === "up" ? TrendingUp : TrendingDown;
  const magnitude =
    delta.pct != null ? `${Math.abs(Math.round(delta.pct))}%` : `${Math.abs(delta.change)}`;
  return (
    <span
      className="inline-flex items-center gap-0.5 text-xs font-semibold"
      style={{ color }}
      title="vs previous week"
    >
      <Icon className="size-3" />
      {magnitude}
      {suffix}
    </span>
  );
}

/** Small amber flag for anything needing a human. */
export function ReviewFlag() {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium"
      style={{
        color: "var(--color-medium)",
        borderColor: "color-mix(in srgb, var(--color-medium) 45%, transparent)",
        backgroundColor: "color-mix(in srgb, var(--color-medium) 12%, transparent)",
      }}
    >
      <Flag className="size-3" />
      Needs review
    </span>
  );
}
