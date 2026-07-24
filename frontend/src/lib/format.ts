/** Small display + date helpers shared across the dashboard. */

/**
 * Current ISO week as "YYYY-Www" — the exact format the backend uses to key
 * weekly summaries (see app.services.ingestion.iso_week). ISO weeks start on
 * Monday and week 1 is the week containing the first Thursday of the year.
 */
export function currentIsoWeek(date = new Date()): string {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = d.getUTCDay() || 7; // Sunday → 7
  d.setUTCDate(d.getUTCDate() + 4 - day); // shift to the week's Thursday
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

/** The ISO week immediately before `week` (parsed from a "YYYY-Www" string).
 *  Used for week-over-week deltas. Falls back to the string itself if unparsable. */
export function previousIsoWeek(week: string): string {
  const m = /^(\d{4})-W(\d{2})$/.exec(week);
  if (!m) return week;
  const [, year, wk] = m;
  // Reconstruct the Thursday of the given ISO week, step back 7 days, re-derive.
  const jan4 = new Date(Date.UTC(Number(year), 0, 4));
  const jan4Day = jan4.getUTCDay() || 7;
  const week1Monday = new Date(jan4);
  week1Monday.setUTCDate(jan4.getUTCDate() - jan4Day + 1);
  const thisMonday = new Date(week1Monday);
  thisMonday.setUTCDate(week1Monday.getUTCDate() + (Number(wk) - 1) * 7);
  thisMonday.setUTCDate(thisMonday.getUTCDate() - 7);
  return currentIsoWeek(thisMonday);
}

/** Build a list of the last `count` ISO weeks, newest first, for the selector. */
export function recentIsoWeeks(count = 12, from = new Date()): string[] {
  const weeks: string[] = [];
  const cursor = new Date(from);
  for (let i = 0; i < count; i++) {
    weeks.push(currentIsoWeek(cursor));
    cursor.setUTCDate(cursor.getUTCDate() - 7);
  }
  return weeks;
}

/** Turn "feature_request" into "Feature request" for display. */
export function humanize(value: string): string {
  const spaced = value.replace(/[_-]+/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Sentiment score (-1..1) → a short human word. */
export function sentimentWord(score: number): string {
  if (score <= -0.2) return "Negative";
  if (score >= 0.2) return "Positive";
  return "Neutral";
}

/** Percentage string from a 0..1 fraction. */
export function pct(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}
