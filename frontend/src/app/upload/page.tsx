"use client";

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, uploadFile } from "@/lib/api";
import type { UploadSummary } from "@/lib/types";
import { humanize } from "@/lib/format";
import { Card } from "@/components/Card";
import { StatTile } from "@/components/StatTile";
import { Badge, ReviewFlag } from "@/components/Badge";
import { ErrorState } from "@/components/States";

const ACCEPTED = ".csv,.pdf,.txt,.text";

export default function UploadPage() {
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<UploadSummary | null>(null);
  const [lastFile, setLastFile] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    setBusy(true);
    setError(null);
    setResult(null);
    setLastFile(file.name);
    try {
      const summary = await uploadFile(file);
      setResult(summary);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err
          : new ApiError("Upload failed.", { kind: "http" }),
      );
    } finally {
      setBusy(false);
    }
  }, []);

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
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold">Upload tickets</h1>
        <p className="mt-1 text-sm text-muted">
          Drop a CSV, PDF, or text file of customer messages. We&apos;ll clean and
          store each one — you&apos;ll see exactly what was created, skipped, or
          flagged.
        </p>
      </header>

      {/* Drop zone */}
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
        className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-[var(--radius-card)] border-2 border-dashed px-6 py-14 text-center transition ${
          dragging
            ? "border-accent bg-accent-soft/40"
            : "border-border bg-surface hover:border-accent/60"
        } ${busy ? "pointer-events-none opacity-60" : ""}`}
      >
        <div className="text-4xl" aria-hidden>
          {busy ? "⏳" : "📥"}
        </div>
        <p className="text-sm font-semibold text-text">
          {busy
            ? `Uploading ${lastFile ?? "file"}…`
            : "Drag a file here, or click to choose"}
        </p>
        <p className="text-xs text-muted">CSV, PDF, or plain text · one file at a time</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
            e.target.value = ""; // allow re-uploading the same file
          }}
        />
      </div>

      {error && <ErrorState error={error} onRetry={() => setError(null)} />}

      {result && <UploadResult summary={result} />}
    </div>
  );
}

function UploadResult({ summary }: { summary: UploadSummary }) {
  const c = summary.counts;
  const flaggedItems = summary.created_items.filter(
    (i) => i.flags.length > 0 || i.needs_manual_review,
  );

  return (
    <div className="space-y-5">
      <Card
        title={`Processed ${summary.filename}`}
        hint={`Parsed as ${summary.parser}${
          summary.encoding_recovered ? " · encoding auto-repaired" : ""
        }`}
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <StatTile value={c.detected} label="Detected" />
          <StatTile value={c.created} label="Created" tone="feature_request" />
          <StatTile value={c.flagged} label="Flagged" tone="medium" />
          <StatTile value={c.skipped} label="Skipped" tone="muted" />
          <StatTile value={c.duplicates} label="Duplicates" tone="muted" />
          <StatTile value={c.blanks} label="Blank rows" tone="muted" />
        </div>
        {c.created > 0 && (
          <p className="mt-4 text-sm text-muted">
            Next: head to{" "}
            <Link href="/tickets" className="text-accent hover:underline">
              Tickets
            </Link>{" "}
            to analyse and review them, or the{" "}
            <Link href="/" className="text-accent hover:underline">
              Overview
            </Link>{" "}
            for the weekly picture.
          </p>
        )}
      </Card>

      {summary.created_items.length > 0 && (
        <Card
          title="Created items"
          hint="Each stored issue, with the language detected and how confident the ingest was."
        >
          <ul className="divide-y divide-border">
            {summary.created_items.map((item) => (
              <li
                key={item.issue_id}
                className="flex items-start justify-between gap-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text">
                    {item.title || item.source_ref}
                  </p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <span className="text-xs text-muted">
                      {item.language.toUpperCase()} · {Math.round(item.confidence * 100)}%
                      confidence
                    </span>
                    {item.flags.map((f) => (
                      <Badge key={f} label={f} tone="other" />
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
          <ul className="divide-y divide-border">
            {summary.skipped_items.map((item, i) => (
              <li key={i} className="flex items-center justify-between gap-4 py-2.5">
                <span className="truncate text-sm text-muted">{item.source_ref}</span>
                <Badge label={humanize(item.reason)} tone="muted" />
              </li>
            ))}
          </ul>
        </Card>
      )}

      {flaggedItems.length === 0 && summary.skipped_items.length === 0 && c.created > 0 && (
        <p className="text-center text-sm text-muted">
          Clean batch — nothing needed flagging. 🎉
        </p>
      )}
    </div>
  );
}
