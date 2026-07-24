import { humanize } from "@/lib/format";

/** Colour-coded pill for a category or severity. Colours come from the CSS
 *  tokens in globals.css so a category is the same colour everywhere. */
export function Badge({
  label,
  tone,
  title,
}: {
  label: string;
  tone?: string;
  title?: string;
}) {
  const color = tone ? `var(--color-${tone})` : "var(--color-muted)";
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium"
      style={{ borderColor: color, color }}
    >
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      {humanize(label)}
    </span>
  );
}

/** A neutral count chip, e.g. the "3 issues" badge on a multi-issue ticket. */
export function CountChip({ n, singular }: { n: number; singular: string }) {
  const label = n === 1 ? singular : `${singular}s`;
  return (
    <span className="rounded-full bg-surface-2 px-2.5 py-0.5 text-xs font-semibold text-text">
      {n} {label}
    </span>
  );
}

/** Small amber flag for anything needing a human. */
export function ReviewFlag() {
  return (
    <span className="rounded-full border border-medium px-2.5 py-0.5 text-xs font-medium text-medium">
      Needs review
    </span>
  );
}
