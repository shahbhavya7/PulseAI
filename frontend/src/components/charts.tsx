"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SentimentPoint, ThemeCount } from "@/lib/types";
import { humanize, sentimentWord } from "@/lib/format";

const AXIS = "#8891a5";
const GRID = "rgba(255,255,255,0.07)";
const CYAN = "#04f0f0"; // the single vivid accent (--primary)

function color(token: string): string {
  // Read the domain CSS custom property (hex) so chart colours match the badges.
  if (typeof window === "undefined") return CYAN;
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(`--color-${token}`)
    .trim();
  return v || CYAN;
}

const tooltipStyle = {
  background: "rgba(12,14,22,0.82)",
  backdropFilter: "blur(16px) saturate(180%)",
  WebkitBackdropFilter: "blur(16px) saturate(180%)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 12,
  color: "#f2f5fa",
  fontSize: 12,
  boxShadow: "0 12px 40px -8px rgba(0,0,0,0.7)",
} as const;

// Bars grow up; lines/areas draw left→right. Kept snappy but visible.
const BAR_ANIM = { isAnimationActive: true, animationDuration: 900 } as const;

/** Category distribution — one coloured bar per category. Click a bar to filter
 *  the Tickets route by that category (via `onSelect`). */
export function CategoryChart({
  data,
  onSelect,
}: {
  data: Record<string, number>;
  onSelect?: (category: string) => void;
}) {
  const rows = Object.entries(data)
    .map(([category, count]) => ({ category, label: humanize(category), count }))
    .sort((a, b) => b.count - a.count);

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} />
        <YAxis allowDecimals={false} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} />
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#ffffff0d" }} />
        <Bar
          dataKey="count"
          radius={[6, 6, 0, 0]}
          name="Issues"
          {...BAR_ANIM}
          onClick={(d: { category?: string }) =>
            d?.category && onSelect?.(d.category)
          }
          style={onSelect ? { cursor: "pointer" } : undefined}
        >
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
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#ffffff0d" }} />
        <Bar dataKey="count" radius={[6, 6, 0, 0]} name="Issues" {...BAR_ANIM}>
          {rows.map((r) => (
            <Cell key={r.sev} fill={color(r.sev)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Sentiment over time — avg sentiment (-1..1) per week, drawn as a glowing line
 *  over a soft area, with urgency as a second line. */
export function SentimentTrendChart({ data }: { data: SentimentPoint[] }) {
  const rows = data.map((p) => ({
    week: p.week,
    Sentiment: Number(p.avg_sentiment.toFixed(2)),
    Urgency: Number(p.avg_urgency.toFixed(2)),
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
        <defs>
          <linearGradient id="sentFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={CYAN} stopOpacity={0.35} />
            <stop offset="100%" stopColor={CYAN} stopOpacity={0} />
          </linearGradient>
        </defs>
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
        <Area
          type="monotone"
          dataKey="Sentiment"
          stroke="none"
          fill="url(#sentFill)"
          isAnimationActive
          animationDuration={1100}
        />
        <Line
          type="monotone"
          dataKey="Sentiment"
          stroke={CYAN}
          strokeWidth={2.5}
          dot={{ r: 3, fill: CYAN }}
          activeDot={{ r: 5 }}
          isAnimationActive
          animationDuration={1100}
        />
        <Line
          type="monotone"
          dataKey="Urgency"
          stroke={color("high")}
          strokeWidth={2.5}
          dot={{ r: 3 }}
          isAnimationActive
          animationDuration={1100}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Top themes — horizontal bars, biggest first. The top theme is highlighted in
 *  cyan; the rest are muted so the #1 driver stands out. */
export function ThemesChart({ data }: { data: ThemeCount[] }) {
  const rows = [...data]
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
    .map((t) => ({ theme: t.theme, count: t.count }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(200, rows.length * 40)}>
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
        <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "#ffffff0d" }} />
        <Bar dataKey="count" radius={[0, 6, 6, 0]} name="Mentions" {...BAR_ANIM}>
          {rows.map((r, i) => (
            <Cell key={r.theme} fill={i === 0 ? CYAN : "rgba(255,255,255,0.22)"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
