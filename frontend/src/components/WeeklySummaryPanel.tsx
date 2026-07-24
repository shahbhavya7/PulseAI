"use client";

import { useState } from "react";
import { ApiError, generateSummary, getSummary } from "@/lib/api";
import type { SummaryResponse } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";
import { Card } from "@/components/Card";
import { LoadingCard, ErrorState, EmptyState } from "@/components/States";
import { Badge } from "@/components/Badge";
import { sentimentWord } from "@/lib/format";

/**
 * The week's narrative, shown prominently at the top of the Overview. If a
 * summary hasn't been generated for the week yet (404 → "not_generated"), we
 * show a one-click Generate button that POSTs to the backend.
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
      <Card title={`Weekly summary · ${week}`}>
        <LoadingCard lines={4} />
      </Card>
    );
  }

  // A missing summary isn't an error — offer to generate it.
  const notGenerated =
    state.error && state.error.kind === "http" && state.error.status === 404;

  if (notGenerated || genError?.code === "no_issues") {
    return (
      <Card title={`Weekly summary · ${week}`}>
        <EmptyState icon="📝" title="No summary for this week yet">
          <p>
            Generate a plain-language recap of the week&apos;s tickets — the
            headline, what happened, and what to do next.
          </p>
          <button
            onClick={onGenerate}
            disabled={generating}
            className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
          >
            {generating ? "Generating…" : "Generate summary"}
          </button>
          {genError && genError.code !== "no_issues" && (
            <p className="mt-2 text-xs text-critical">{genError.message}</p>
          )}
        </EmptyState>
      </Card>
    );
  }

  if (state.error) {
    return (
      <Card title={`Weekly summary · ${week}`}>
        <ErrorState error={state.error} onRetry={state.reload} />
      </Card>
    );
  }

  const s = state.data!;
  return (
    <Card
      title={`Weekly summary · ${s.week}`}
      hint={`Based on ${s.issue_count} issue${s.issue_count === 1 ? "" : "s"} this week`}
      right={
        <button
          onClick={onGenerate}
          disabled={generating}
          className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition hover:text-text disabled:opacity-50"
        >
          {generating ? "Refreshing…" : "Regenerate"}
        </button>
      }
    >
      <h3 className="text-lg font-semibold leading-snug text-text">{s.headline}</h3>
      <p className="mt-3 text-sm leading-relaxed text-muted">{s.narrative}</p>

      {s.recommendations.length > 0 && (
        <div className="mt-5">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Recommended next steps
          </p>
          <ul className="space-y-1.5">
            {s.recommendations.map((rec, i) => (
              <li key={i} className="flex gap-2 text-sm text-text">
                <span className="text-accent">→</span>
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border pt-4 text-xs text-muted">
        <span>
          Avg sentiment: {sentimentWord(s.metrics.avg_sentiment)} (
          {s.metrics.avg_sentiment.toFixed(2)})
        </span>
        <span>·</span>
        <span>Needs review: {s.metrics.needs_review}</span>
        {s.themes.slice(0, 3).map((t) => (
          <Badge key={t.theme} label={t.theme} tone="other" />
        ))}
      </div>
    </Card>
  );
}
