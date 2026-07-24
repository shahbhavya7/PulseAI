"use client";

import { humanize } from "@/lib/format";

export interface Filters {
  category: string;
  sentiment: string;
  minConfidence: string; // "" | "0.5" | "0.7" | "0.9"
  needsReview: boolean;
}

export const EMPTY_FILTERS: Filters = {
  category: "",
  sentiment: "",
  minConfidence: "",
  needsReview: false,
};

const CATEGORIES = ["bug", "feature_request", "question", "incident", "other"];
const SENTIMENTS = ["negative", "neutral", "positive"];
const CONFIDENCES = [
  { value: "", label: "Any confidence" },
  { value: "0.5", label: "≥ 50%" },
  { value: "0.7", label: "≥ 70%" },
  { value: "0.9", label: "≥ 90%" },
];

function Select({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted">
      <span>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-sm text-text outline-none focus:border-accent"
      >
        {children}
      </select>
    </label>
  );
}

/** The filter bar for the Tickets route. Purely controlled — the page owns the
 *  state and refetches when it changes. */
export function TicketFilters({
  value,
  onChange,
}: {
  value: Filters;
  onChange: (next: Filters) => void;
}) {
  const set = <K extends keyof Filters>(key: K, v: Filters[K]) =>
    onChange({ ...value, [key]: v });

  const dirty =
    value.category || value.sentiment || value.minConfidence || value.needsReview;

  return (
    <div className="flex flex-wrap items-end gap-4 rounded-[var(--radius-card)] border border-border bg-surface p-4">
      <Select label="Category" value={value.category} onChange={(v) => set("category", v)}>
        <option value="">All categories</option>
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {humanize(c)}
          </option>
        ))}
      </Select>

      <Select label="Sentiment" value={value.sentiment} onChange={(v) => set("sentiment", v)}>
        <option value="">Any sentiment</option>
        {SENTIMENTS.map((s) => (
          <option key={s} value={s}>
            {humanize(s)}
          </option>
        ))}
      </Select>

      <Select
        label="Confidence"
        value={value.minConfidence}
        onChange={(v) => set("minConfidence", v)}
      >
        {CONFIDENCES.map((c) => (
          <option key={c.value} value={c.value}>
            {c.label}
          </option>
        ))}
      </Select>

      <label className="flex items-center gap-2 pb-1.5 text-sm text-text">
        <input
          type="checkbox"
          checked={value.needsReview}
          onChange={(e) => set("needsReview", e.target.checked)}
          className="h-4 w-4 accent-[var(--color-accent)]"
        />
        Needs review only
      </label>

      {dirty && (
        <button
          onClick={() => onChange(EMPTY_FILTERS)}
          className="ml-auto pb-1.5 text-xs font-medium text-accent hover:underline"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
