"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** A titled glass panel. `hint` explains the section in plain language so a
 *  non-technical viewer never has to guess what they're looking at. `icon` is a
 *  rendered element (e.g. `<Layers className="size-4" />`), not a component, so
 *  it serialises cleanly through the client boundary. */
export function Card({
  title,
  hint,
  icon,
  right,
  children,
  className = "",
}: {
  title?: string;
  hint?: string;
  icon?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "glass glass-hover rounded-[var(--radius)] p-5",
        className,
      )}
    >
      {(title || right) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            {icon && (
              <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary [&_svg]:size-4">
                {icon}
              </span>
            )}
            <div>
              {title && (
                <h2 className="text-sm font-semibold text-foreground">{title}</h2>
              )}
              {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
            </div>
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}
