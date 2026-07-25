/**
 * Derive the "smart" bits of the dashboard from data already on /stats and
 * /summaries — no new backend. Pure functions, unit-testable, no React.
 */

import type { StatsResponse, SummaryResponse } from "./types";
import { humanize, sentimentWord } from "./format";

export interface Delta {
  /** Signed change vs the previous period (current - previous). */
  change: number;
  /** Percent change vs previous, or null when previous was 0 (no base). */
  pct: number | null;
  direction: "up" | "down" | "flat";
}

export function delta(current: number, previous: number | undefined): Delta | null {
  if (previous == null) return null;
  const change = current - previous;
  const direction = change > 0 ? "up" : change < 0 ? "down" : "flat";
  const pct = previous === 0 ? null : (change / previous) * 100;
  return { change, pct, direction };
}

/** The single headline finding for the hero strip. `tone` drives the accent. */
export interface HeroInsight {
  headline: string;
  detail: string;
  tone: "critical" | "warning" | "positive" | "neutral";
}

const topEntry = (rec: Record<string, number>): [string, number] | null => {
  const entries = Object.entries(rec);
  if (!entries.length) return null;
  return entries.sort((a, b) => b[1] - a[1])[0];
};

/**
 * Build the hero insight from this week's stats, last week's stats (for the
 * delta), and the generated summary (for its headline, if present). Priority:
 *   1. a real week-over-week jump in the top category (most "intelligent"),
 *   2. otherwise the summary's own headline,
 *   3. otherwise a plain top-driver / sentiment statement.
 */
export function buildHeroInsight(
  stats: StatsResponse,
  prev: StatsResponse | null,
  summary: SummaryResponse | null,
): HeroInsight | null {
  if (stats.total_issues === 0) return null;

  const top = topEntry(stats.category_distribution);
  const criticals = stats.urgency_counts.critical ?? 0;
  const latest = stats.sentiment_over_time.at(-1);
  const sentiment = latest?.avg_sentiment ?? 0;

  // 1. Week-over-week jump in the leading category.
  if (top && prev) {
    const [cat, count] = top;
    const prevCount = prev.category_distribution[cat] ?? 0;
    if (prevCount > 0 && count > prevCount) {
      const jump = Math.round(((count - prevCount) / prevCount) * 100);
      if (jump >= 15) {
        return {
          headline: `${humanize(cat)} issues up ${jump}% vs last week, now the #1 driver.`,
          detail: `${count} ${humanize(cat).toLowerCase()} issue${
            count === 1 ? "" : "s"
          } this week, up from ${prevCount}. Overall sentiment is ${sentimentWord(
            sentiment,
          ).toLowerCase()}.`,
          tone: cat === "incident" || cat === "bug" ? "critical" : "warning",
        };
      }
    }
  }

  // 2. Critical spike.
  if (criticals > 0) {
    return {
      headline: `${criticals} critical issue${criticals === 1 ? "" : "s"} need attention now.`,
      detail:
        top != null
          ? `${humanize(top[0])} leads the ${stats.total_issues} issues this period; sentiment is ${sentimentWord(
              sentiment,
            ).toLowerCase()}.`
          : `${stats.total_issues} issues this period.`,
      tone: "critical",
    };
  }

  // 3. Summary's own headline if we have one. Detail = the first highlight
  //    bullet (falling back to the first sentence of the joined narrative).
  if (summary?.headline) {
    const firstHighlight =
      summary.highlights?.[0] ?? summary.narrative.split(". ").slice(0, 1).join(". ") + ".";
    return {
      headline: summary.headline,
      detail: firstHighlight,
      tone: sentiment <= -0.2 ? "warning" : "neutral",
    };
  }

  // 4. Plain top-driver fallback.
  if (top) {
    return {
      headline: `${humanize(top[0])} is the top driver this period (${top[1]} of ${stats.total_issues}).`,
      detail: `Customer sentiment is ${sentimentWord(sentiment).toLowerCase()}${
        latest ? ` (${sentiment.toFixed(2)})` : ""
      }.`,
      tone: sentiment <= -0.2 ? "warning" : "positive",
    };
  }

  return null;
}

/** The single most urgent theme to highlight: the top theme when criticals or
 *  negative sentiment are present. Returns its label, else null. */
export function mostUrgentTheme(stats: StatsResponse): string | null {
  const t = stats.top_themes[0];
  if (!t) return null;
  const criticals = stats.urgency_counts.critical ?? 0;
  const negative = (stats.sentiment_over_time.at(-1)?.avg_sentiment ?? 0) <= -0.2;
  return criticals > 0 || negative ? t.theme : t.theme;
}
