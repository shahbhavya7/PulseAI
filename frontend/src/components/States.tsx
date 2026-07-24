"use client";

import type { ApiError } from "@/lib/api";
import type { ReactNode } from "react";

/** Grey shimmering placeholder blocks shown while data loads. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

/** A full-card loading placeholder: a couple of shimmering bars. */
export function LoadingCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="h-4" />
      ))}
    </div>
  );
}

/**
 * The friendly failure state. A dead backend gets a reassuring, actionable
 * message (never a blank screen or a stack trace); any other error shows the
 * backend's own message plus a retry button.
 */
export function ErrorState({
  error,
  onRetry,
}: {
  error: ApiError;
  onRetry?: () => void;
}) {
  const down = error.isBackendDown;
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-[var(--radius-card)] border border-border bg-surface px-6 py-10 text-center">
      <div className="text-3xl" aria-hidden>
        {down ? "🔌" : "⚠️"}
      </div>
      <p className="text-sm font-semibold text-text">
        {down ? "The dashboard can't reach the server" : "Something went wrong"}
      </p>
      <p className="max-w-md text-sm text-muted">
        {down
          ? "Start the PulseAI backend (it should be listening on port 8000), then try again."
          : error.message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 rounded-lg border border-accent px-4 py-1.5 text-sm font-medium text-accent transition hover:bg-accent-soft"
        >
          Try again
        </button>
      )}
    </div>
  );
}

/** The "nothing here yet" state, with a suggestion on what to do next. */
export function EmptyState({
  icon = "📭",
  title,
  children,
}: {
  icon?: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-[var(--radius-card)] border border-dashed border-border bg-surface px-6 py-12 text-center">
      <div className="text-3xl" aria-hidden>
        {icon}
      </div>
      <p className="text-sm font-semibold text-text">{title}</p>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}
