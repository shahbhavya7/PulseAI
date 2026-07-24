"use client";

import { AlertTriangle, PlugZap, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import type { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export { Skeleton };

/** A full-card loading placeholder: a few shimmering bars. */
export function LoadingCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="h-4" style={{ width: `${90 - i * 12}%` }} />
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
  const Icon = down ? PlugZap : AlertTriangle;
  return (
    <div className="glass flex flex-col items-center justify-center gap-3 rounded-[var(--radius)] px-6 py-10 text-center animate-fade-up">
      <span
        className="flex size-12 items-center justify-center rounded-2xl text-destructive"
        style={{ background: "hsl(var(--destructive) / 0.12)" }}
      >
        <Icon className="size-6" />
      </span>
      <p className="text-sm font-semibold text-foreground">
        {down ? "The dashboard can't reach the server" : "Something went wrong"}
      </p>
      <p className="max-w-md text-sm text-muted-foreground">
        {down
          ? "Start the PulseAI backend (it should be listening on port 8000), then try again."
          : error.message}
      </p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-1">
          <RefreshCw className="size-4" />
          Try again
        </Button>
      )}
    </div>
  );
}

/** The "nothing here yet" state, with a suggestion on what to do next. `icon`
 *  is a rendered element. */
export function EmptyState({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="glass flex flex-col items-center justify-center gap-2 rounded-[var(--radius)] border-dashed px-6 py-12 text-center animate-fade-up">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary [&_svg]:size-6">
        {icon}
      </span>
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {children && (
        <div className="max-w-md text-sm text-muted-foreground">{children}</div>
      )}
    </div>
  );
}
