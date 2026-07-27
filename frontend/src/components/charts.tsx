"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ThemeCount, WeekSeverityPoint } from "@/lib/types";
import { humanize } from "@/lib/format";

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

const SEVERITIES = ["critical", "high", "medium", "low"] as const;

/** Tooltip for the week comparison: every severity bucket plus the total, and
 *  how that total moved against the week before. */
function WeekCompareTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ payload: Record<string, number & string> }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as unknown as {
    total: number;
    delta: number | null;
  } & Record<string, number>;

  return (
    <div style={tooltipStyle}>
      <div style={{ fontWeight: 600 }}>{label}</div>
      {SEVERITIES.map((sev) =>
        row[sev] ? (
          <div key={sev} style={{ color: "#c4ccda", display: "flex", gap: 8 }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 2,
                background: color(sev),
                alignSelf: "center",
              }}
            />
            {humanize(sev)}: {row[sev]}
          </div>
        ) : null,
      )}
      <div
        style={{
          marginTop: 6,
          paddingTop: 6,
          borderTop: "1px solid rgba(255,255,255,0.12)",
          fontWeight: 600,
        }}
      >
        Total: {row.total}
        {row.delta != null && (
          <span
            style={{
              marginLeft: 8,
              fontWeight: 500,
              color: row.delta > 0 ? "#ff8080" : row.delta < 0 ? "#5fe3a1" : "#7e8aa0",
            }}
          >
            {row.delta > 0 ? "+" : ""}
            {row.delta} vs prev week
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * Week-over-week comparison — one stacked bar per ISO week, split by severity.
 *
 * Stacked rather than grouped because the question is usually "did the total
 * move, and what is it made of": a stack answers both at a glance, where
 * side-by-side bars make the total hard to read. `range` trims to the most
 * recent N weeks so the last two or three can be compared without noise.
 */
export function WeekComparisonChart({
  data,
  range,
}: {
  data: WeekSeverityPoint[];
  range: number | "all";
}) {
  // Data arrives oldest-first; take the most recent slice, keeping that order.
  const start = range === "all" ? 0 : Math.max(0, data.length - range);
  const rows = data.slice(start).map((p, i) => {
    // Compare against the preceding week in the FULL series, so the first
    // visible bar still shows a delta when earlier history exists.
    const prev = data[start + i - 1];
    return { ...p, delta: prev ? p.total - prev.total : null };
  });

  return (
    <div>
      {/* A legend, because a stack is unreadable without one. Static rather than
          Recharts' <Legend/> so it sits above the plot at a fixed size. */}
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {SEVERITIES.map((sev) => (
          <span key={sev} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span
              className="size-2.5 rounded-[3px]"
              style={{ background: color(sev) }}
              aria-hidden
            />
            {humanize(sev)}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart
          data={rows}
          margin={{ top: 20, right: 8, bottom: 0, left: -16 }}
          barCategoryGap="35%"
        >
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="week" tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} />
          <YAxis allowDecimals={false} tick={{ fill: AXIS, fontSize: 12 }} tickLine={false} />
          <Tooltip cursor={{ fill: "#ffffff0d" }} content={<WeekCompareTooltip />} />
          {/* Stack order is low→critical so the most severe sits on top. */}
          {[...SEVERITIES].reverse().map((sev, i, arr) => (
            <Bar
              key={sev}
              dataKey={sev}
              stackId="severity"
              name={humanize(sev)}
              fill={color(sev)}
              // Without a cap, two weeks stretch into slabs half the card wide.
              // A fixed max keeps the bars readable at any range; `barGap` has
              // no effect on a stack, so spacing comes from the category width.
              maxBarSize={64}
              // Only the topmost segment gets rounded corners.
              radius={i === arr.length - 1 ? [6, 6, 0, 0] : undefined}
              {...BAR_ANIM}
            >
              {i === arr.length - 1 && (
                <LabelList
                  dataKey="total"
                  position="top"
                  style={{ fill: AXIS, fontSize: 11 }}
                />
              )}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
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
