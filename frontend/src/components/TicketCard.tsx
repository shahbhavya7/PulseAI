"use client";

import { useState } from "react";
import { Gauge, Hash, Loader2, Smile, Sparkles, Zap } from "lucide-react";
import { ApiError, analyzeTicket } from "@/lib/api";
import type { IssueOut, TicketOut } from "@/lib/types";
import { humanize, sentimentWord } from "@/lib/format";
import { DomainBadge, CountChip, ReviewFlag } from "@/components/Badge";
import { Button } from "@/components/ui/button";
import { MotionCard } from "@/components/motion";

/** One ticket, with its issues grouped underneath. A ticket that fanned out
 *  into more than one issue gets an "N issues" badge. Unanalysed tickets show
 *  an Analyse button that calls the AI pipeline in place. */
export function TicketCard({
  ticket,
  index = 0,
  onChanged,
}: {
  ticket: TicketOut;
  index?: number;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analysed = ticket.issues.some((i) => i.analyzed_at != null);
  const multi = ticket.issue_count > 1;

  async function onAnalyse() {
    setBusy(true);
    setError(null);
    try {
      await analyzeTicket(ticket.id);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Analysis failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <MotionCard delay={Math.min(index * 0.05, 0.3)} className="p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-foreground">
            {ticket.title}
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {humanize(ticket.source)} ·{" "}
            {new Date(ticket.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {multi && <CountChip n={ticket.issue_count} singular="issue" />}
          {!analysed && (
            <Button size="sm" onClick={onAnalyse} disabled={busy}>
              {busy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Sparkles className="size-4" />
              )}
              {busy ? "Analysing…" : "Analyse"}
            </Button>
          )}
        </div>
      </header>

      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}

      <ul className="mt-4 space-y-3">
        {ticket.issues.map((issue) => (
          <IssueRow key={issue.id} issue={issue} analysed={analysed} />
        ))}
      </ul>
    </MotionCard>
  );
}

function IssueRow({ issue, analysed }: { issue: IssueOut; analysed: boolean }) {
  return (
    <li className="rounded-xl border border-white/5 bg-white/[0.03] p-3 transition-colors hover:bg-white/[0.05]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-sm text-foreground">{issue.title}</p>
        <div className="flex flex-wrap items-center gap-1.5">
          {analysed && (
            <DomainBadge label={issue.category} tone={issue.category} kind="category" />
          )}
          {analysed && (
            <DomainBadge label={issue.severity} tone={issue.severity} kind="severity" />
          )}
          {issue.needs_manual_review && <ReviewFlag />}
        </div>
      </div>

      {analysed && (
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Smile className="size-3" />
            {sentimentWord(issue.sentiment_score)}
          </span>
          <span className="inline-flex items-center gap-1">
            <Zap className="size-3" />
            Urgency {Math.round(issue.urgency_score * 100)}%
          </span>
          <span className="inline-flex items-center gap-1">
            <Gauge className="size-3" />
            {Math.round(issue.confidence * 100)}%
          </span>
        </div>
      )}

      {issue.themes.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {issue.themes.map((theme) => (
            <span
              key={theme}
              className="inline-flex items-center gap-0.5 rounded-md bg-white/[0.05] px-2 py-0.5 text-xs text-muted-foreground"
            >
              <Hash className="size-2.5" />
              {theme}
            </span>
          ))}
        </div>
      )}
    </li>
  );
}
