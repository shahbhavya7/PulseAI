"use client";

import { useState } from "react";
import { ApiError, analyzeTicket } from "@/lib/api";
import type { IssueOut, TicketOut } from "@/lib/types";
import { humanize, sentimentWord } from "@/lib/format";
import { Badge, CountChip, ReviewFlag } from "@/components/Badge";

/** One ticket, with its issues grouped underneath. A ticket that fanned out
 *  into more than one issue gets an "N issues" badge. Unanalysed tickets show
 *  an Analyse button that calls the AI pipeline in place. */
export function TicketCard({
  ticket,
  onChanged,
}: {
  ticket: TicketOut;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A ticket is "unanalysed" if none of its issues have been through the AI
  // pipeline yet (no analyzed_at timestamp).
  const analysed = ticket.issues.some((i) => i.analyzed_at != null);
  const multi = ticket.issue_count > 1;

  async function onAnalyse() {
    setBusy(true);
    setError(null);
    try {
      await analyzeTicket(ticket.id);
      onChanged();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Analysis failed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="rounded-[var(--radius-card)] border border-border bg-surface p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-text">{ticket.title}</h3>
          <p className="mt-0.5 text-xs text-muted">
            {humanize(ticket.source)} · {new Date(ticket.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {multi && <CountChip n={ticket.issue_count} singular="issue" />}
          {!analysed && (
            <button
              onClick={onAnalyse}
              disabled={busy}
              className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
            >
              {busy ? "Analysing…" : "Analyse"}
            </button>
          )}
        </div>
      </header>

      {error && <p className="mt-2 text-xs text-critical">{error}</p>}

      <ul className="mt-4 space-y-3">
        {ticket.issues.map((issue) => (
          <IssueRow key={issue.id} issue={issue} analysed={analysed} />
        ))}
      </ul>
    </article>
  );
}

function IssueRow({ issue, analysed }: { issue: IssueOut; analysed: boolean }) {
  return (
    <li className="rounded-xl border border-border bg-surface-2 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-sm text-text">{issue.title}</p>
        <div className="flex flex-wrap items-center gap-1.5">
          {analysed && <Badge label={issue.category} tone={issue.category} />}
          {analysed && <Badge label={issue.severity} tone={issue.severity} />}
          {issue.needs_manual_review && <ReviewFlag />}
        </div>
      </div>

      {analysed && (
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          <span>{sentimentWord(issue.sentiment_score)} sentiment</span>
          <span>Urgency {Math.round(issue.urgency_score * 100)}%</span>
          <span>{Math.round(issue.confidence * 100)}% confidence</span>
        </div>
      )}

      {issue.themes.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {issue.themes.map((theme) => (
            <span
              key={theme}
              className="rounded-md bg-surface px-2 py-0.5 text-xs text-muted"
            >
              #{theme}
            </span>
          ))}
        </div>
      )}
    </li>
  );
}
