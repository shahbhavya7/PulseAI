"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertOctagon,
  BarChart3,
  FileText,
  Flame,
  Layers,
  LineChart,
  Sparkles,
  Tags,
  TrendingUp,
} from "lucide-react";
import { getStats } from "@/lib/api";
import type { StatsResponse, SummaryResponse } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";
import { currentIsoWeek, previousIsoWeek, sentimentWord } from "@/lib/format";
import { buildHeroInsight, delta, mostUrgentTheme } from "@/lib/insight";
import { getSummary } from "@/lib/api";
import { CATEGORY_ICON } from "@/lib/icons";
import { Card } from "@/components/Card";
import { StatTile } from "@/components/StatTile";
import { DeltaBadge } from "@/components/Badge";
import { HeroInsight } from "@/components/HeroInsight";
import { WeekSelector } from "@/components/WeekSelector";
import { WeeklySummaryPanel } from "@/components/WeeklySummaryPanel";
import { LoadingCard, ErrorState, EmptyState } from "@/components/States";
import { MotionItem, MotionStagger, PageTransition } from "@/components/motion";
import {
  CategoryChart,
  SentimentTrendChart,
  ThemesChart,
  UrgencyChart,
} from "@/components/charts";

export default function OverviewPage() {
  const [week, setWeek] = useState<string>(currentIsoWeek());

  const stats = useAsync<StatsResponse>(() => getStats(week ? { week } : {}), [week]);
  // Previous-week stats power the week-over-week deltas + the hero insight. Only
  // meaningful for a specific week; "" (all-time) has no "previous".
  const prev = useAsync<StatsResponse | null>(
    () => (week ? getStats({ week: previousIsoWeek(week) }) : Promise.resolve(null)),
    [week],
  );
  // The summary (if generated) gives the hero a ready-made headline to fall back
  // on. A 404 (not generated) is fine — we just get null.
  const summary = useAsync<SummaryResponse | null>(
    () => (week ? getSummary(week).catch(() => null) : Promise.resolve(null)),
    [week],
  );

  return (
    <PageTransition className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Overview</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            What your customers are telling you — at a glance.
          </p>
        </div>
        <WeekSelector value={week} onChange={setWeek} />
      </header>

      {/* Hero insight strip — the week's headline finding, in plain language. */}
      {stats.data && (
        <HeroStrip stats={stats.data} prev={prev.data ?? null} summary={summary.data ?? null} />
      )}

      {week ? (
        <WeeklySummaryPanel week={week} />
      ) : (
        <Card icon={<FileText />} title="Weekly summary">
          <p className="text-sm text-muted-foreground">
            Pick a specific week above to see (or generate) its written summary.
          </p>
        </Card>
      )}

      {stats.loading && (
        <Card>
          <LoadingCard lines={4} />
        </Card>
      )}

      {stats.error && <ErrorState error={stats.error} onRetry={stats.reload} />}

      {stats.data && (
        <StatsView data={stats.data} prev={prev.data ?? null} week={week} />
      )}
    </PageTransition>
  );
}

function HeroStrip({
  stats,
  prev,
  summary,
}: {
  stats: StatsResponse;
  prev: StatsResponse | null;
  summary: SummaryResponse | null;
}) {
  const insight = useMemo(
    () => buildHeroInsight(stats, prev, summary),
    [stats, prev, summary],
  );
  if (!insight) return null;
  return <HeroInsight insight={insight} />;
}

function StatsView({
  data,
  prev,
  week,
}: {
  data: StatsResponse;
  prev: StatsResponse | null;
  week: string;
}) {
  const router = useRouter();

  if (data.total_issues === 0) {
    return (
      <EmptyState
        icon={<Layers />}
        title={week ? "No analysed issues for this week" : "No analysed issues yet"}
      >
        <p>
          Upload tickets on the{" "}
          <Link href="/upload" className="text-primary hover:underline">
            Upload
          </Link>{" "}
          page, then analyse them from{" "}
          <Link href="/tickets" className="text-primary hover:underline">
            Tickets
          </Link>
          . Analysed issues show up here.
        </p>
      </EmptyState>
    );
  }

  const latest = data.sentiment_over_time.at(-1);
  const sentiment = latest?.avg_sentiment ?? 0;
  const topCategory = Object.entries(data.category_distribution).sort(
    (a, b) => b[1] - a[1],
  )[0]?.[0];
  const TopIcon = topCategory ? CATEGORY_ICON[topCategory] : Layers;
  const urgentTheme = mostUrgentTheme(data);

  // Week-over-week deltas (null when there's no previous week loaded).
  const dIssues = delta(data.total_issues, prev?.total_issues);
  const dCritical = delta(
    data.urgency_counts.critical ?? 0,
    prev ? prev.urgency_counts.critical ?? 0 : undefined,
  );
  const prevSentiment = prev?.sentiment_over_time.at(-1)?.avg_sentiment;
  const dSentiment = delta(sentiment, prevSentiment);

  return (
    <div className="space-y-5">
      <MotionStagger className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MotionItem>
          <StatTile
            count={data.total_issues}
            label="Total issues"
            icon={<Layers />}
            delta={<DeltaBadge delta={dIssues} goodWhen="down" />}
          />
        </MotionItem>
        <MotionItem>
          <StatTile
            value={topCategory ? topCategory.replace(/_/g, " ") : "—"}
            label="Most common"
            tone={topCategory ?? undefined}
            icon={<TopIcon />}
          />
        </MotionItem>
        <MotionItem>
          <StatTile
            value={latest ? sentimentWord(sentiment) : "—"}
            label={latest ? `Sentiment (${sentiment.toFixed(2)})` : "Sentiment"}
            tone="question"
            icon={<TrendingUp />}
            delta={<DeltaBadge delta={dSentiment} goodWhen="up" />}
          />
        </MotionItem>
        <MotionItem>
          <StatTile
            count={data.urgency_counts.critical ?? 0}
            label="Critical"
            tone="critical"
            icon={<AlertOctagon />}
            delta={<DeltaBadge delta={dCritical} goodWhen="down" />}
          />
        </MotionItem>
      </MotionStagger>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          icon={<BarChart3 />}
          title="Category distribution"
          hint="How many issues fall into each type. Click a bar to see those tickets."
        >
          <CategoryChart
            data={data.category_distribution}
            onSelect={(category) =>
              router.push(`/tickets?category=${encodeURIComponent(category)}`)
            }
          />
        </Card>

        <Card
          icon={<AlertOctagon />}
          title="Urgency breakdown"
          hint="Issues by severity — click a bar to see those tickets."
        >
          <UrgencyChart
            data={data.urgency_counts}
            onSelect={(severity) =>
              router.push(`/tickets?severity=${encodeURIComponent(severity)}`)
            }
          />
        </Card>
      </div>

      <Card
        icon={<LineChart />}
        title="Sentiment over time"
        hint="Average customer sentiment (−1 negative to +1 positive) and urgency, week by week."
      >
        {data.sentiment_over_time.length > 0 ? (
          <SentimentTrendChart data={data.sentiment_over_time} />
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Not enough data yet for a trend.
          </p>
        )}
      </Card>

      <Card
        icon={<Tags />}
        title="Top themes"
        hint="The recurring topics across issues — biggest drivers first."
      >
        {urgentTheme && (
          <div className="mb-4 flex items-center gap-2 rounded-xl border border-primary/30 bg-primary/10 px-3 py-2 text-sm">
            <Flame className="size-4 text-primary" />
            <span className="text-muted-foreground">Most urgent theme:</span>
            <span className="font-semibold text-foreground">{urgentTheme}</span>
          </div>
        )}
        {data.top_themes.length > 0 ? (
          <ThemesChart data={data.top_themes} />
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">
            <Sparkles className="mr-1 inline size-4" />
            No themes yet.
          </p>
        )}
      </Card>
    </div>
  );
}
