"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
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

// Near-opaque so the tooltip reads clearly against the aurora background (the
// old translucent+blur version blended in). Kept dark to match the theme.
const tooltipStyle = {
  background: "rgba(10,12,20,0.97)",
  border: "1px solid rgba(255,255,255,0.16)",
  borderRadius: 12,
  color: "#f2f5fa",
  fontSize: 12,
  padding: "8px 12px",
  boxShadow: "0 12px 40px -8px rgba(0,0,0,0.85)",
} as const;

/** A tooltip that shows the value and — for clickable charts — a subtle one-line
 *  "click to filter" hint under a divider, so the hint never clutters the value. */
function ClickableTooltip({
  active,
  payload,
  label,
  unit,
  clickable,
}: {
  active?: boolean;
  payload?: Array<{ value: number; payload: Record<string, unknown> }>;
  label?: string;
  unit: string;
  clickable?: boolean;
}) {
  if (!active || !payload?.length) return null;
  const value = payload[0].value;
  return (
    <div style={tooltipStyle}>
      <div style={{ fontWeight: 600 }}>{label}</div>
      <div style={{ color: "#c4ccda" }}>
        {unit}: {value}
      </div>
      {clickable && (
        <div
          style={{
            marginTop: 6,
            paddingTop: 6,
            borderTop: "1px solid rgba(255,255,255,0.12)",
            color: "#7e8aa0",
            fontSize: 11,
          }}
        >
          Click to view these tickets
        </div>
      )}
    </div>
  );
}

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
        <Tooltip
          cursor={{ fill: "#ffffff0d" }}
          content={<ClickableTooltip unit="Issues" clickable={!!onSelect} />}
        />
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

/** Severity/urgency breakdown — low→critical, always in that order. Click a bar
 *  to filter the Tickets route by that severity (via `onSelect`). */
export function UrgencyChart({
  data,
  onSelect,
}: {
  data: Record<string, number>;
  onSelect?: (severity: string) => void;
}) {
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
        <Tooltip
          cursor={{ fill: "#ffffff0d" }}
          content={<ClickableTooltip unit="Issues" clickable={!!onSelect} />}
        />
        <Bar
          dataKey="count"
          radius={[6, 6, 0, 0]}
          name="Issues"
          {...BAR_ANIM}
          onClick={(d: { sev?: string }) => d?.sev && onSelect?.(d.sev)}
          style={onSelect ? { cursor: "pointer" } : undefined}
        >
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
              : [value, "Urgency (0 to 1)"]
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

/** Ramp a bar's colour by rank: the #1 driver is bright cyan, each lower rank
 *  fades toward a dim slate, so the ranking is visible at a glance. */
function themeBarColor(rank: number, total: number): string {
  if (rank === 0) return CYAN;
  // Interpolate opacity from ~0.62 (2nd) down to ~0.20 (last).
  const t = total > 1 ? rank / (total - 1) : 0;
  const opacity = 0.62 - t * 0.42;
  return `rgba(64, 224, 224, ${opacity.toFixed(2)})`;
}

/** Top themes — horizontal bars, biggest first, on a cyan intensity ramp so the
 *  ranking reads instantly. Count labels sit at the end of each bar. */
export function ThemesChart({ data }: { data: ThemeCount[] }) {
  const rows = [...data]
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
    .map((t) => ({ theme: t.theme, label: humanize(t.theme), count: t.count }));
  const max = rows[0]?.count ?? 1;

  return (
    <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 46)}>
      <BarChart
        layout="vertical"
        data={rows}
        margin={{ top: 4, right: 40, bottom: 4, left: 8 }}
        barCategoryGap="28%"
      >
        {/* No vertical grid lines — they clutter a ranked bar list. */}
        <XAxis
          type="number"
          allowDecimals={false}
          domain={[0, Math.max(1, max)]}
          hide
        />
        <YAxis
          type="category"
          dataKey="label"
          width={150}
          tick={{ fill: "#c4ccda", fontSize: 12 }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          cursor={{ fill: "#ffffff0d" }}
          content={<ClickableTooltip unit="Mentions" />}
        />
        <Bar dataKey="count" radius={[0, 6, 6, 0]} name="Mentions" {...BAR_ANIM}>
          {rows.map((r, i) => (
            <Cell key={r.theme} fill={themeBarColor(i, rows.length)} />
          ))}
          <LabelList
            dataKey="count"
            position="right"
            offset={8}
            fill="#8891a5"
            fontSize={12}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
