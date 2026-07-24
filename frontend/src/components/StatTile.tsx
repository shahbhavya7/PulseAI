import type { ReactNode } from "react";

/** A single big-number tile (e.g. "12 Created"). Used in the upload summary and
 *  the overview header row. */
export function StatTile({
  value,
  label,
  tone = "text",
  sub,
}: {
  value: ReactNode;
  label: string;
  tone?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface p-4">
      <div
        className="text-2xl font-bold tabular-nums"
        style={{ color: `var(--color-${tone})` }}
      >
        {value}
      </div>
      <div className="mt-1 text-xs font-medium text-muted">{label}</div>
      {sub && <div className="mt-0.5 text-xs text-muted/70">{sub}</div>}
    </div>
  );
}
