"use client";

import { SlidersHorizontal, X } from "lucide-react";
import { humanize } from "@/lib/format";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";

export interface Filters {
  category: string;
  severity: string;
  sentiment: string;
  minConfidence: string;
  needsReview: boolean;
}

export const EMPTY_FILTERS: Filters = {
  category: "",
  severity: "",
  sentiment: "",
  minConfidence: "",
  needsReview: false,
};

// Radix Select disallows an empty-string item value, so "any" is a sentinel we
// translate back to "" (no filter).
const ANY = "__any__";
const CATEGORIES = ["bug", "feature_request", "question", "incident", "other"];
const SEVERITIES = ["low", "medium", "high", "critical"];
const SENTIMENTS = ["negative", "neutral", "positive"];
const CONFIDENCES = [
  { value: ANY, label: "Any confidence" },
  { value: "0.5", label: "≥ 50%" },
  { value: "0.7", label: "≥ 70%" },
  { value: "0.9", label: "≥ 90%" },
];

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-xs text-muted-foreground">
      <span>{label}</span>
      {children}
    </label>
  );
}

/** Filter bar for the Tickets route. Controlled — the page owns state and
 *  refetches when it changes. */
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
    value.category ||
    value.severity ||
    value.sentiment ||
    value.minConfidence ||
    value.needsReview;

  return (
    <div className="glass flex flex-wrap items-end gap-4 rounded-[var(--radius)] p-4">
      <span className="flex items-center gap-2 pb-2 text-xs font-semibold text-muted-foreground">
        <SlidersHorizontal className="size-4" />
        Filters
      </span>

      <Field label="Category">
        <Select
          value={value.category || ANY}
          onValueChange={(v) => set("category", v === ANY ? "" : v)}
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="All categories" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>All categories</SelectItem>
            {CATEGORIES.map((c) => (
              <SelectItem key={c} value={c}>
                {humanize(c)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <Field label="Urgency">
        <Select
          value={value.severity || ANY}
          onValueChange={(v) => set("severity", v === ANY ? "" : v)}
        >
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="Any urgency" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any urgency</SelectItem>
            {SEVERITIES.map((s) => (
              <SelectItem key={s} value={s}>
                {humanize(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <Field label="Sentiment">
        <Select
          value={value.sentiment || ANY}
          onValueChange={(v) => set("sentiment", v === ANY ? "" : v)}
        >
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="Any sentiment" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any sentiment</SelectItem>
            {SENTIMENTS.map((s) => (
              <SelectItem key={s} value={s}>
                {humanize(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <Field label="Confidence">
        <Select
          value={value.minConfidence || ANY}
          onValueChange={(v) => set("minConfidence", v === ANY ? "" : v)}
        >
          <SelectTrigger className="w-[150px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CONFIDENCES.map((c) => (
              <SelectItem key={c.value} value={c.value}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      <label className="flex cursor-pointer items-center gap-2 pb-2 text-sm text-foreground">
        <Checkbox
          checked={value.needsReview}
          onCheckedChange={(checked) => set("needsReview", checked === true)}
        />
        Needs review only
      </label>

      {dirty && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChange(EMPTY_FILTERS)}
          className="ml-auto text-primary"
        >
          <X className="size-3.5" />
          Clear
        </Button>
      )}
    </div>
  );
}
