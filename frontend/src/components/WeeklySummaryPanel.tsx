"use client";

import { useState } from "react";
import {
  ArrowRight,
  FileText,
  Loader2,
  RefreshCw,
  Smile,
  Sparkles,
} from "lucide-react";
import { ApiError, generateSummary, getSummary } from "@/lib/api";
import type { SummaryResponse } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";
import { sentimentWord } from "@/lib/format";
import { Card } from "@/components/Card";
import { LoadingCard, ErrorState } from "@/components/States";
import { DomainBadge } from "@/components/Badge";
import { Button } from "@/components/ui/button";

/**
 * The week's narrative, shown prominently at the top of the Overview. If a
 * summary hasn't been generated yet (404) we show a one-click Generate button.
 */
export function WeeklySummaryPanel({ week }: { week: string }) {
  const state = useAsync<SummaryResponse>(() => getSummary(week), [week]);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<ApiError | null>(null);

  async function onGenerate() {
    setGenerating(true);
    setGenError(null);
    try {
      await generateSummary(week);
      state.reload();
    } catch (err) {
      setGenError(
        err instanceof ApiError
          ? err
          : new ApiError("Couldn't generate the summary.", { kind: "http" }),
      );
    } finally {
      setGenerating(false);
    }
  }

  if (state.loading) {
    return (
      <Card icon={<FileText />} title={`Weekly summary · ${week}`}>
        <LoadingCard lines={4} />
      </Card>
    );
  }

  const notGenerated =
    state.error && state.error.kind === "http" && state.error.status === 404;

  if (notGenerated || genError?.code === "no_issues") {
    return (
      <Card icon={<FileText />} title={`Weekly summary · ${week}`}>
        <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-6">
          <p className="text-sm text-muted-foreground">
            Generate a plain-language recap of the week&apos;s tickets: the
            headline, what happened, and what to do next.
          </p>
          <Button onClick={onGenerate} disabled={generating}>
            {generating ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Sparkles className="size-4" />
            )}
            {generating ? "Generating…" : "Generate summary"}
          </Button>
          {genError && genError.code !== "no_issues" && (
            <p className="text-xs text-destructive">{genError.message}</p>
          )}
        </div>
      </Card>
    );
  }

  if (state.error) {
    return (
      <Card icon={<FileText />} title={`Weekly summary · ${week}`}>
        <ErrorState error={state.error} onRetry={state.reload} />
      </Card>
    );
  }

  const s = state.data!;
  return (
    <Card
      icon={<Sparkles />}
      title={`Weekly summary · ${s.week}`}
      hint={`Based on ${s.issue_count} issue${s.issue_count === 1 ? "" : "s"} this week`}
      className="relative overflow-hidden"
      right={
        <Button variant="ghost" size="sm" onClick={onGenerate} disabled={generating}>
          {generating ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
          {generating ? "Refreshing…" : "Regenerate"}
        </Button>
      }
    >
      {/* Accent glow behind the headline */}
      <div className="pointer-events-none absolute -left-16 -top-16 size-48 rounded-full bg-primary/20 blur-3xl animate-glow" />

      <h3 className="relative text-lg font-semibold leading-snug text-foreground">
        {s.headline}
      </h3>
      <p className="relative mt-3 text-sm leading-relaxed text-muted-foreground">
        {s.narrative}
      </p>

      {s.recommendations.length > 0 && (
        <div className="relative mt-5">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Recommended next steps
          </p>
          <ul className="space-y-1.5">
            {s.recommendations.map((rec, i) => (
              <li key={i} className="flex gap-2 text-sm text-foreground">
                <ArrowRight className="mt-0.5 size-4 shrink-0 text-primary" />
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="relative mt-5 flex flex-wrap items-center gap-2 border-t border-white/10 pt-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <Smile className="size-3.5" />
          {sentimentWord(s.metrics.avg_sentiment)} ({s.metrics.avg_sentiment.toFixed(2)})
        </span>
        <span>·</span>
        <span>Needs review: {s.metrics.needs_review}</span>
        {s.themes.slice(0, 3).map((t) => (
          <DomainBadge key={t.theme} label={t.theme} tone="other" />
        ))}
      </div>
    </Card>
  );
}
