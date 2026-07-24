"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SentimentPoint, ThemeCount } from "@/lib/types";
import { humanize, sentimentWord } from "@/lib/format";

const AXIS = "#8a95ad";
const GRID = "#26304a";

function color(token: string): string {
  // Read the CSS custom property so chart colours match the badges. Falls back
  // to the accent colour on the server / if the token is missing.
  if (typeof window === "undefined") return "#6366f1";
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(`--color-${token}`)
    .trim();
  return v || "#6366f1";
}

const tooltipStyle = {
  background: "#1a2234",
  border: "1px solid #26304a",
  borderRadius: 12,
  color: "#e6eaf2",
  fontSize: 12,
} as const;

/** Category distribution — one coloured bar per issue category. */
export function CategoryChart({ data }: { data: Record<string, number> }) {
  const rows = Object.entries(data)
    .map(([category, count]) => ({ category, label: humanize(category), count }))
    .sort((a, b) => b.count - a.count);

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} />
        <YAxis allowDecimals={false} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#ffffff10" }} />
        <Bar dataKey="count" radius={[6, 6, 0, 0]} name="Issues">
          {rows.map((r) => (
            <Cell key={r.category} fill={color(r.category)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Severity/urgency breakdown — low→critical, always in that order. */
export function UrgencyChart({ data }: { data: Record<string, number> }) {
  const order = ["low", "medium", "high", "critical"];
  const rows = order
    .filter((sev) => data[sev] != null)
    .map((sev) => ({ sev, label: humanize(sev), count: data[sev] }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} />
        <YAxis allowDecimals={false} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#ffffff10" }} />
        <Bar dataKey="count" radius={[6, 6, 0, 0]} name="Issues">
          {rows.map((r) => (
            <Cell key={r.sev} fill={color(r.sev)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Sentiment over time — average sentiment (-1..1) per week, with urgency. */
export function SentimentTrendChart({ data }: { data: SentimentPoint[] }) {
  const rows = data.map((p) => ({
    week: p.week,
    Sentiment: Number(p.avg_sentiment.toFixed(2)),
    Urgency: Number(p.avg_urgency.toFixed(2)),
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="week" tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} />
        <YAxis domain={[-1, 1]} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} />
        <Tooltip
          contentStyle={tooltipStyle}
          formatter={(value: number, name: string) =>
            name === "Sentiment"
              ? [`${value} (${sentimentWord(value)})`, name]
              : [value, "Urgency (0–1)"]
          }
        />
        <Line
          type="monotone"
          dataKey="Sentiment"
          stroke={color("question")}
          strokeWidth={2.5}
          dot={{ r: 3 }}
        />
        <Line
          type="monotone"
          dataKey="Urgency"
          stroke={color("high")}
          strokeWidth={2.5}
          dot={{ r: 3 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Top themes — horizontal bars, biggest first. */
export function ThemesChart({ data }: { data: ThemeCount[] }) {
  const rows = [...data]
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
    .map((t) => ({ theme: t.theme, count: t.count }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(200, rows.length * 38)}>
      <BarChart
        layout="vertical"
        data={rows}
        margin={{ top: 4, right: 16, bottom: 4, left: 8 }}
      >
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" allowDecimals={false} tick={{ fill: AXIS, fontSize: 12 }} />
        <YAxis
          type="category"
          dataKey="theme"
          width={150}
          tick={{ fill: AXIS, fontSize: 12 }}
          tickLine={false}
        />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#ffffff10" }} />
        <Bar dataKey="count" radius={[0, 6, 6, 0]} fill={color("accent")} name="Mentions" />
      </BarChart>
    </ResponsiveContainer>
  );
}
