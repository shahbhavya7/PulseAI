"use client";

import { useState } from "react";
import {
  Check,
  ChevronDown,
  Copy,
  FileText,
  Gauge,
  Hash,
  Loader2,
  Smile,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import { ApiError, analyzeTicket, deleteTicket } from "@/lib/api";
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
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

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

  async function onDelete() {
    setDeleting(true);
    setError(null);
    try {
      await deleteTicket(ticket.id);
      onChanged(); // parent refetches → this card drops out of the list
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed. Try again.");
      setDeleting(false);
      setConfirmingDelete(false);
    }
  }

  return (
    <MotionCard delay={Math.min(index * 0.05, 0.3)} className="p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-foreground">
            {ticket.title}
          </h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
            <TicketIdChip id={ticket.id} />
            <span>·</span>
            <span>{humanize(ticket.source)}</span>
            <span>·</span>
            <span>{new Date(ticket.created_at).toLocaleDateString()}</span>
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

          {confirmingDelete ? (
            <div className="flex items-center gap-1">
              <Button
                size="sm"
                variant="destructive"
                onClick={onDelete}
                disabled={deleting}
              >
                {deleting ? <Loader2 className="size-4 animate-spin" /> : "Delete"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setConfirmingDelete(false)}
                disabled={deleting}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <Button
              size="icon"
              variant="ghost"
              aria-label="Delete ticket"
              title="Delete ticket"
              onClick={() => setConfirmingDelete(true)}
              className="text-muted-foreground hover:text-destructive"
            >
              <Trash2 className="size-4" />
            </Button>
          )}
        </div>
      </header>

      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}

      <RawTicket body={ticket.body} title={ticket.title} />

      <ul className="mt-4 space-y-3">
        {ticket.issues.map((issue) => (
          <IssueRow key={issue.id} issue={issue} analysed={analysed} />
        ))}
      </ul>
    </MotionCard>
  );
}

/** The ticket's short id (first 8 chars of its UUID), click to copy the full id.
 *  Gives every card a stable reference a user can quote in support. */
function TicketIdChip({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  const short = id.slice(0, 8);

  async function copy(e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // Clipboard blocked (insecure context) — the id is still visible to read.
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      title={`Ticket ${id} · click to copy`}
      className="group/id inline-flex items-center rounded-md bg-white/[0.05] px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground transition-colors hover:text-foreground"
    >
      #{short}
      {copied ? (
        <Check className="ml-1 h-2.5 w-2.5 text-[var(--color-feature_request)]" />
      ) : (
        // Collapsed to zero width until hover, so no empty gap is reserved.
        <Copy className="h-2.5 w-0 opacity-0 transition-all group-hover/id:ml-1 group-hover/id:w-2.5 group-hover/id:opacity-70" />
      )}
    </button>
  );
}

/** The original raw ticket text (as stored — cleaned + PII-redacted), collapsible
 *  so a long forwarded email doesn't dominate the card. Shows a one-line preview
 *  when collapsed. Hidden only when the body adds nothing over the title. */
function RawTicket({ body, title }: { body: string; title: string }) {
  const [open, setOpen] = useState(false);
  const text = body.trim();
  // Nothing extra to show if the stored body is just the title line.
  if (!text || text === title.trim()) return null;

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        <FileText className="size-3.5" />
        Original ticket
        <ChevronDown
          className={`size-3.5 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open ? (
        <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-xl border border-white/5 bg-white/[0.03] p-3 font-mono text-xs leading-relaxed text-muted-foreground">
          {text}
        </pre>
      ) : (
        <p className="mt-1 truncate text-xs text-muted-foreground/70">{text}</p>
      )}
    </div>
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
