"use client";

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  CloudUpload,
  FileCheck2,
  Gauge,
  Languages,
  Loader2,
  PartyPopper,
  PenLine,
  Sparkles,
  Upload as UploadIcon,
} from "lucide-react";
import { ApiError, uploadFile, uploadText } from "@/lib/api";
import type { UploadSummary } from "@/lib/types";
import { humanize } from "@/lib/format";
import { cn } from "@/lib/utils";
import { SKIP_REASON_ICON } from "@/lib/icons";
import { Card } from "@/components/Card";
import { StatTile } from "@/components/StatTile";
import { DomainBadge, ReviewFlag } from "@/components/Badge";
import { ErrorState } from "@/components/States";
import { MotionItem, MotionStagger, PageTransition } from "@/components/motion";

const ACCEPTED = ".csv,.pdf,.txt,.text";

type Mode = "file" | "text";

export default function UploadPage() {
  const [mode, setMode] = useState<Mode>("file");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<UploadSummary | null>(null);
  const [lastFile, setLastFile] = useState<string | null>(null);

  // Paste-a-ticket form.
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const run = useCallback(async (task: () => Promise<UploadSummary>) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await task());
    } catch (err) {
      setError(
        err instanceof ApiError ? err : new ApiError("Upload failed.", { kind: "http" }),
      );
    } finally {
      setBusy(false);
    }
  }, []);

  const handleFile = useCallback(
    (file: File) => {
      setLastFile(file.name);
      return run(() => uploadFile(file));
    },
    [run],
  );

  const handlePaste = useCallback(() => {
    const body = text.trim();
    if (!body) return;
    return run(async () => {
      const summary = await uploadText(body, title);
      setText("");
      setTitle("");
      return summary;
    });
  }, [run, text, title]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) void handleFile(file);
    },
    [handleFile],
  );

  return (
    <PageTransition className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Add tickets</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Upload a file of customer messages or paste a single ticket. Each one is
          cleaned, stored, and{" "}
          <span className="text-foreground">classified automatically</span>, no extra
          step needed.
        </p>
      </header>

      {/* Mode switch */}
      <div className="glass inline-flex rounded-full p-1 text-sm">
        {(
          [
            { key: "file", label: "Upload file", icon: <UploadIcon className="size-4" /> },
            { key: "text", label: "Paste a ticket", icon: <PenLine className="size-4" /> },
          ] as const
        ).map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setMode(tab.key)}
            className={cn(
              "inline-flex items-center gap-2 rounded-full px-4 py-1.5 font-medium transition-colors",
              mode === tab.key
                ? "bg-primary/20 text-primary"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {mode === "text" ? (
        <PasteForm
          text={text}
          title={title}
          busy={busy}
          onText={setText}
          onTitle={setTitle}
          onSubmit={() => void handlePaste()}
        />
      ) : (
      /* Drop zone */
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
        className={cn(
          "glass group flex cursor-pointer flex-col items-center justify-center gap-4 rounded-[var(--radius)] border-2 border-dashed px-6 py-16 text-center transition-all duration-300",
          dragging
            ? "scale-[1.01] border-primary bg-primary/10 shadow-[0_0_40px_-8px_hsl(243_75%_55%/0.5)]"
            : "border-white/15 hover:border-primary/50",
          busy && "pointer-events-none opacity-70",
        )}
      >
        <span
          className={cn(
            "flex size-16 items-center justify-center rounded-2xl bg-primary/15 text-primary transition-transform duration-300",
            dragging ? "scale-110 animate-float" : "group-hover:scale-105",
          )}
        >
          {busy ? (
            <Loader2 className="size-8 animate-spin" />
          ) : (
            <CloudUpload className="size-8" />
          )}
        </span>
        <div>
          <p className="text-sm font-semibold text-foreground">
            {busy
              ? `Uploading ${lastFile ?? "file"}…`
              : dragging
                ? "Release to upload"
                : "Drag a file here, or click to choose"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            CSV, PDF, or plain text · one file at a time
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
            e.target.value = "";
          }}
        />
      </div>
      )}

      {error && <ErrorState error={error} onRetry={() => setError(null)} />}

      {result && <UploadResult summary={result} />}
    </PageTransition>
  );
}

function PasteForm({
  text,
  title,
  busy,
  onText,
  onTitle,
  onSubmit,
}: {
  text: string;
  title: string;
  busy: boolean;
  onText: (v: string) => void;
  onTitle: (v: string) => void;
  onSubmit: () => void;
}) {
  const canSubmit = text.trim().length > 0 && !busy;
  return (
    <Card
      icon={<PenLine />}
      title="Paste a single ticket"
      hint="Type or paste one customer message. We'll clean, store, and classify it."
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) onSubmit();
        }}
      >
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
            Label <span className="opacity-60">(optional)</span>
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => onTitle(e.target.value)}
            placeholder="e.g. Angry customer, refund"
            disabled={busy}
            className="w-full rounded-[var(--radius)] border border-white/10 bg-white/5 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/40"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
            Ticket message
          </label>
          <textarea
            value={text}
            onChange={(e) => onText(e.target.value)}
            rows={7}
            placeholder="Paste the customer's message here…"
            disabled={busy}
            className="w-full resize-y rounded-[var(--radius)] border border-white/10 bg-white/5 px-3 py-2.5 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground/60 focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/40"
          />
        </div>
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            {text.trim().length} characters · one ticket at a time
          </p>
          <button
            type="submit"
            disabled={!canSubmit}
            className={cn(
              "inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-semibold transition-all",
              canSubmit
                ? "bg-primary text-primary-foreground hover:brightness-110"
                : "cursor-not-allowed bg-white/10 text-muted-foreground",
            )}
          >
            {busy ? (
              <>
                <Loader2 className="size-4 animate-spin" /> Processing…
              </>
            ) : (
              <>
                <Sparkles className="size-4" /> Add &amp; classify
              </>
            )}
          </button>
        </div>
      </form>
    </Card>
  );
}

function UploadResult({ summary }: { summary: UploadSummary }) {
  const c = summary.counts;

  return (
    <div className="space-y-5">
      <Card
        icon={<FileCheck2 />}
        title={`Processed ${summary.filename}`}
        hint={`Parsed as ${summary.parser}${
          summary.encoding_recovered ? " · encoding auto-repaired" : ""
        }`}
      >
        {summary.analyzed_count > 0 ? (
          <div className="mb-4 flex items-center gap-2 rounded-[var(--radius)] border border-primary/25 bg-primary/10 px-3 py-2 text-sm text-primary">
            <Sparkles className="size-4 shrink-0" />
            <span>
              Auto-classified {summary.analyzed_count}{" "}
              {summary.analyzed_count === 1 ? "ticket" : "tickets"}. Categories,
              sentiment, and themes are ready on the dashboard.
            </span>
          </div>
        ) : (
          c.created > 0 && (
            <div className="mb-4 flex items-center gap-2 rounded-[var(--radius)] border border-white/10 bg-white/5 px-3 py-2 text-sm text-muted-foreground">
              <Gauge className="size-4 shrink-0" />
              <span>
                Stored, but not yet classified (the AI service was unavailable). Open a
                ticket and click <span className="text-foreground">Analyse</span> to
                categorise it.
              </span>
            </div>
          )
        )}
        <MotionStagger className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {[
            { count: c.detected, label: "Detected" },
            { count: c.created, label: "Created", tone: "feature_request" },
            { count: c.flagged, label: "Flagged", tone: "medium" },
            { count: c.skipped, label: "Skipped" },
            { count: c.duplicates, label: "Duplicates" },
            { count: c.blanks, label: "Blank rows" },
          ].map((t) => (
            <MotionItem key={t.label}>
              <StatTile count={t.count} label={t.label} tone={t.tone} />
            </MotionItem>
          ))}
        </MotionStagger>
        {c.created > 0 && (
          <p className="mt-4 flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
            Next: head to{" "}
            <Link
              href="/tickets"
              className="inline-flex items-center gap-1 text-primary hover:underline"
            >
              Tickets <ArrowRight className="size-3.5" />
            </Link>{" "}
            to analyse and review them, or the{" "}
            <Link href="/" className="text-primary hover:underline">
              Overview
            </Link>{" "}
            for the weekly picture.
          </p>
        )}
      </Card>

      {summary.created_items.length > 0 && (
        <Card
          icon={<CheckCircle2 />}
          title="Created items"
          hint="Each stored issue, with the language detected and how confident the ingest was."
        >
          <ul className="divide-y divide-white/5">
            {summary.created_items.map((item) => (
              <li
                key={item.issue_id}
                className="flex items-start justify-between gap-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-foreground">
                    {item.title || item.source_ref}
                  </p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <Languages className="size-3" />
                      {item.language.toUpperCase()}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <Gauge className="size-3" />
                      {Math.round(item.confidence * 100)}%
                    </span>
                    {item.flags.map((f) => (
                      <DomainBadge key={f} label={f} tone="other" />
                    ))}
                    {item.needs_manual_review && <ReviewFlag />}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {summary.skipped_items.length > 0 && (
        <Card
          title="Skipped items"
          hint="These weren't stored. Duplicates and blanks are skipped on purpose."
        >
          <ul className="divide-y divide-white/5">
            {summary.skipped_items.map((item, i) => {
              const Icon = SKIP_REASON_ICON[item.reason];
              return (
                <li key={i} className="flex items-center justify-between gap-4 py-2.5">
                  <span className="truncate text-sm text-muted-foreground">
                    {item.source_ref}
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                    {Icon && <Icon className="size-3.5" />}
                    {humanize(item.reason)}
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {summary.skipped_items.length === 0 &&
        summary.created_items.every((i) => !i.flags.length && !i.needs_manual_review) &&
        c.created > 0 && (
          <p className="flex items-center justify-center gap-2 text-center text-sm text-muted-foreground">
            <PartyPopper className="size-4 text-[var(--color-feature_request)]" />
            Clean batch, nothing needed flagging.
          </p>
        )}
    </div>
  );
}
