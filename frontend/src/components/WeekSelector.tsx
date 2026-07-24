"use client";

import { recentIsoWeeks } from "@/lib/format";

/** Dropdown of recent ISO weeks. "All time" (empty value) shows unfiltered data. */
export function WeekSelector({
  value,
  onChange,
  includeAllTime = true,
}: {
  value: string;
  onChange: (week: string) => void;
  includeAllTime?: boolean;
}) {
  const weeks = recentIsoWeeks(12);
  return (
    <label className="flex items-center gap-2 text-sm text-muted">
      <span>Week</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm text-text outline-none focus:border-accent"
      >
        {includeAllTime && <option value="">All time</option>}
        {weeks.map((w) => (
          <option key={w} value={w}>
            {w}
          </option>
        ))}
      </select>
    </label>
  );
}
