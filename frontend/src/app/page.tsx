"use client";

import { useState } from "react";
import Link from "next/link";
import { getStats } from "@/lib/api";
import type { StatsResponse } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";
import { currentIsoWeek, sentimentWord } from "@/lib/format";
import { Card } from "@/components/Card";
import { StatTile } from "@/components/StatTile";
import { WeekSelector } from "@/components/WeekSelector";
import { WeeklySummaryPanel } from "@/components/WeeklySummaryPanel";
import { LoadingCard, ErrorState, EmptyState } from "@/components/States";
import {
  CategoryChart,
  SentimentTrendChart,
  ThemesChart,
  UrgencyChart,
} from "@/components/charts";

export default function OverviewPage() {
  // Default to this week; "" means all-time (no week filter on /stats).
  const [week, setWeek] = useState<string>(currentIsoWeek());
  const stats = useAsync<StatsResponse>(
    () => getStats(week ? { week } : {}),
    [week],
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold">Overview</h1>
          <p className="mt-1 text-sm text-muted">
            What your customers are telling you — at a glance.
          </p>
        </div>
        <WeekSelector value={week} onChange={setWeek} />
      </header>

      {/* Narrative summary, front and centre — only for a specific week. */}
      {week ? (
        <WeeklySummaryPanel week={week} />
      ) : (
        <Card title="Weekly summary">
          <p className="text-sm text-muted">
            Pick a specific week above to see (or generate) its written summary.
          </p>
        </Card>
      )}

      {stats.loading && <LoadingCard lines={4} />}

      {stats.error && <ErrorState error={stats.error} onRetry={stats.reload} />}

      {stats.data && <StatsView data={stats.data} week={week} />}
    </div>
  );
}

function StatsView({ data, week }: { data: StatsResponse; week: string }) {
  if (data.total_issues === 0) {
    return (
      <EmptyState
        icon="🗂️"
        title={week ? "No analysed issues for this week" : "No analysed issues yet"}
      >
        <p>
          Upload tickets on the{" "}
          <Link href="/upload" className="text-accent hover:underline">
            Upload
          </Link>{" "}
          page, then analyse them from{" "}
          <Link href="/tickets" className="text-accent hover:underline">
            Tickets
          </Link>
          . Analysed issues show up here.
        </p>
      </EmptyState>
    );
  }

  const latest = data.sentiment_over_time.at(-1);
  const topCategory = Object.entries(data.category_distribution).sort(
    (a, b) => b[1] - a[1],
  )[0]?.[0];

  return (
    <div className="space-y-5">
      {/* Headline tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile value={data.total_issues} label="Total issues" />
        <StatTile
          value={topCategory ? topCategory.replace(/_/g, " ") : "—"}
          label="Most common"
          tone={topCategory ?? "text"}
        />
        <StatTile
          value={latest ? sentimentWord(latest.avg_sentiment) : "—"}
          label="Sentiment"
          tone="question"
          sub={latest ? latest.avg_sentiment.toFixed(2) : undefined}
        />
        <StatTile
          value={data.urgency_counts.critical ?? 0}
          label="Critical"
          tone="critical"
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title="Category distribution"
          hint="How many issues fall into each type."
        >
          <CategoryChart data={data.category_distribution} />
        </Card>

        <Card
          title="Urgency breakdown"
          hint="Issues by severity — critical needs attention first."
        >
          <UrgencyChart data={data.urgency_counts} />
        </Card>
      </div>

      <Card
        title="Sentiment over time"
        hint="Average customer sentiment (−1 negative to +1 positive) and urgency, week by week."
      >
        {data.sentiment_over_time.length > 0 ? (
          <SentimentTrendChart data={data.sentiment_over_time} />
        ) : (
          <p className="py-8 text-center text-sm text-muted">
            Not enough data yet for a trend.
          </p>
        )}
      </Card>

      <Card
        title="Top themes"
        hint="The recurring topics across issues — biggest drivers first."
      >
        {data.top_themes.length > 0 ? (
          <ThemesChart data={data.top_themes} />
        ) : (
          <p className="py-8 text-center text-sm text-muted">No themes yet.</p>
        )}
      </Card>
    </div>
  );
}
