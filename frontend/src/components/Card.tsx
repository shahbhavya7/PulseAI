import type { ReactNode } from "react";

/** A titled panel. `hint` explains the chart/section in plain language so a
 *  non-technical viewer never has to guess what they're looking at. */
export function Card({
  title,
  hint,
  right,
  children,
  className = "",
}: {
  title?: string;
  hint?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-[var(--radius-card)] border border-border bg-surface p-5 ${className}`}
    >
      {(title || right) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="text-sm font-semibold text-text">{title}</h2>}
            {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}
