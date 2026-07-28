"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Loader2,
  MessagesSquare,
  Plus,
  Send,
  Sparkles,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ApiError,
  createSession,
  endSession,
  getSession,
  listSessions,
  streamMessage,
} from "@/lib/api";
import type { AnalyticsCell, AnalyticsChart, AnalyticsTable } from "@/lib/api";
import type { ChatMessageOut, ChatSessionOut } from "@/lib/types";
import { humanize } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Card } from "@/components/Card";
import { ErrorState } from "@/components/States";
import { PageTransition } from "@/components/motion";

interface UiMessage {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  // Present when the answer was backed by a live analytics query, so the exact
  // numbers are shown as a table alongside the prose.
  table?: AnalyticsTable;
  tableCaption?: string;
  chart?: AnalyticsChart;
}

const SUGGESTIONS = [
  "What are my top themes this week?",
  "How many critical issues do I have?",
  "What's driving negative sentiment?",
];

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSessionOut[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [booting, setBooting] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load sessions on mount; a fresh session sweeps idle ones first so their
  // memory is written before this new conversation recalls it.
  useEffect(() => {
    (async () => {
      try {
        const existing = await listSessions();
        setSessions(existing);
      } catch (err) {
        if (err instanceof ApiError) setError(err);
      } finally {
        setBooting(false);
      }
    })();
  }, []);

  // Auto-scroll to the newest message.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const openSession = useCallback(async (id: string) => {
    setError(null);
    setActiveId(id);
    try {
      const detail = await getSession(id);
      setMessages(
        detail.messages
          .filter((m: ChatMessageOut) => m.role !== "system")
          .map((m) => ({ role: m.role as "user" | "assistant", content: m.content })),
      );
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    }
  }, []);

  const newSession = useCallback(async () => {
    setError(null);
    try {
      const s = await createSession();
      setActiveId(s.id);
      setMessages([]);
      // Re-read rather than prepending: creating a session prunes the oldest
      // ones past the cap, so the server list is the only accurate one.
      setSessions(await listSessions().catch(() => []));
    } catch (err) {
      if (err instanceof ApiError) setError(err);
    }
  }, []);

  const send = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || sending) return;

      // Ensure there is a session to post into.
      let sessionId = activeId;
      if (!sessionId) {
        try {
          const s = await createSession();
          sessionId = s.id;
          setSessions((prev) => [s, ...prev]);
          setActiveId(s.id);
        } catch (err) {
          if (err instanceof ApiError) setError(err);
          return;
        }
      }

      setInput("");
      setSending(true);
      setError(null);
      setMessages((prev) => [
        ...prev,
        { role: "user", content: question },
        { role: "assistant", content: "", streaming: true },
      ]);

      try {
        await streamMessage(
          sessionId,
          question,
          (token) => {
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last?.role === "assistant") {
                next[next.length - 1] = { ...last, content: last.content + token };
              }
              return next;
            });
          },
          {
            // Arrives before the first token, so the table renders while the
            // written answer is still streaming in beneath it.
            onTable: (table, explanation) => {
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === "assistant") {
                  next[next.length - 1] = { ...last, table, tableCaption: explanation };
                }
                return next;
              });
            },
            onChart: (chart) => {
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === "assistant") {
                  next[next.length - 1] = { ...last, chart };
                }
                return next;
              });
            },
          },
        );
      } catch (err) {
        setMessages((prev) => prev.slice(0, -1)); // drop the empty assistant bubble
        setError(
          err instanceof ApiError
            ? err
            : new ApiError("The chat failed. Please try again.", { kind: "http" }),
        );
      } finally {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant") next[next.length - 1] = { ...last, streaming: false };
          return next;
        });
        setSending(false);
      }
    },
    [activeId, sending],
  );

  // End (and summarise) the active session when leaving the page.
  useEffect(() => {
    return () => {
      if (activeId) void endSession(activeId).catch(() => {});
    };
  }, [activeId]);

  return (
    <PageTransition className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Chat</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Ask about your tickets. Answers are grounded in your own data.
          </p>
        </div>
        <button
          onClick={newSession}
          className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.05] px-3.5 py-2 text-sm font-medium transition-all hover:border-primary/50 hover:bg-white/[0.09] active:scale-[0.98]"
        >
          <Plus className="size-4" /> New chat
        </button>
      </header>

      <div className="grid gap-5 lg:grid-cols-[220px_1fr]">
        {/* Session list */}
        <Card className="hidden h-fit lg:block" title="Conversations">
          {booting ? (
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          ) : sessions.length === 0 ? (
            <p className="text-xs text-muted-foreground">No conversations yet.</p>
          ) : (
            <ul className="space-y-1">
              {sessions.map((s) => (
                <li key={s.id}>
                  <button
                    onClick={() => openSession(s.id)}
                    className={cn(
                      "w-full truncate rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors",
                      s.id === activeId
                        ? "bg-primary/15 text-foreground"
                        : "text-muted-foreground hover:bg-white/[0.05] hover:text-foreground",
                    )}
                  >
                    {s.title || new Date(s.created_at).toLocaleString()}
                    {s.status === "archived" && " · ended"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Thread */}
        <Card className="flex min-h-[60vh] flex-col">
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto pr-1">
            {messages.length === 0 ? (
              <EmptyChat onPick={send} disabled={sending} />
            ) : (
              messages.map((m, i) => <Bubble key={i} message={m} />)
            )}
          </div>

          {error && (
            <div className="mt-3">
              <ErrorState error={error} onRetry={() => setError(null)} />
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send(input);
            }}
            className="mt-4 flex items-end gap-2 border-t border-white/10 pt-4"
          >
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send(input);
                }
              }}
              rows={1}
              placeholder="Ask about your tickets…"
              className="max-h-32 min-h-[42px] flex-1 resize-none rounded-xl border border-white/15 bg-white/[0.04] px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 outline-none focus:border-primary/60 focus:ring-2 focus:ring-ring/40"
            />
            <button
              type="submit"
              disabled={sending || !input.trim()}
              className="flex size-[42px] shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground transition-all hover:brightness-110 active:scale-95 disabled:opacity-50"
              aria-label="Send"
            >
              {sending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
            </button>
          </form>
        </Card>
      </div>
    </PageTransition>
  );
}

function Bubble({ message }: { message: UiMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground"
            : "border border-white/10 bg-white/[0.04] text-foreground",
        )}
      >
        {message.table && <ResultTable table={message.table} caption={message.tableCaption} />}
        {message.chart && <ResultChart chart={message.chart} />}
        {message.content}
        {message.streaming && message.content === "" && (
          <span className="inline-flex items-center gap-1 text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" /> thinking…
          </span>
        )}
        {message.streaming && message.content !== "" && (
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-current align-middle" />
        )}
      </div>
    </div>
  );
}

/**
 * Render a jsonb cell as readable text rather than "[object Object]".
 *
 * Postgres json columns reach us as arrays (a themes list, or a json_agg of
 * rows) or plain objects. We flatten to the values a reader actually wants:
 * a list of strings joined by commas, and for objects the scalar fields only.
 */
function formatJsonCell(value: object): string {
  if (Array.isArray(value)) {
    const parts = value.map((v) =>
      v !== null && typeof v === "object" ? formatJsonCell(v) : String(v),
    );
    return parts.filter(Boolean).join(", ") || "—";
  }
  // Prefer an obviously human-facing field when the object has one.
  const record = value as Record<string, unknown>;
  for (const key of ["title", "name", "label", "theme", "summary"]) {
    if (typeof record[key] === "string") return record[key] as string;
  }
  const scalars = Object.entries(record)
    .filter(([, v]) => v === null || typeof v !== "object")
    .map(([k, v]) => `${k}: ${v === null ? "—" : String(v)}`);
  return scalars.join(", ") || "—";
}

/**
 * The exact numbers behind an answer, from a live query. Rendered above the
 * prose so the figures are scannable and the assistant's sentence reads as
 * commentary on a table the user can already see.
 */
function ResultTable({ table, caption }: { table: AnalyticsTable; caption?: string }) {
  // Hide opaque identifier columns: a uuid is unreadable and crowds out the
  // columns that actually answer the question. Kept only if that is all there is.
  const isId = (c: string) => c.toLowerCase() === "id" || c.toLowerCase().endsWith("_id");
  const visible = table.columns.some((c) => !isId(c))
    ? table.columns.map((c, i) => i).filter((i) => !isId(table.columns[i]))
    : table.columns.map((_, i) => i);

  const format = (value: AnalyticsCell) => {
    if (value === null) return "—";
    if (typeof value === "number") {
      return Number.isInteger(value) ? String(value) : value.toFixed(2);
    }
    if (typeof value === "boolean") return value ? "yes" : "no";
    // A jsonb column (themes, or a json_agg of rows) arrives as an object or
    // array. String() would render "[object Object]", so unwrap it into
    // something readable instead.
    if (typeof value === "object") return formatJsonCell(value);
    const text = String(value);
    // Long free text (a ticket title) is truncated so one cell cannot stretch
    // the table; the full value stays in the answer prose.
    return text.length > 90 ? `${text.slice(0, 88)}…` : text;
  };

  return (
    <figure className="mb-3 space-y-1.5">
      {/* Wide result sets scroll inside the bubble rather than stretching it. */}
      <div className="overflow-x-auto rounded-lg border border-white/10 bg-black/20">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-white/10">
              {visible.map((i) => (
                <th
                  key={table.columns[i]}
                  className="px-3 py-2 text-left font-medium whitespace-nowrap text-muted-foreground"
                >
                  {table.columns[i].replace(/_/g, " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, r) => (
              <tr key={r} className="border-b border-white/5 last:border-0">
                {visible.map((i) => {
                  const text = format(row[i]);
                  // Free text wraps; short scalars stay on one line and use
                  // tabular figures so columns of numbers line up.
                  const isText = typeof row[i] === "string" && text.length > 24;
                  return (
                    <td
                      key={i}
                      className={cn(
                        "px-3 py-1.5 align-top",
                        isText ? "min-w-[16rem] whitespace-normal" : "whitespace-nowrap tabular-nums",
                      )}
                    >
                      {text}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(caption || table.truncated) && (
        <figcaption className="text-[11px] leading-snug text-muted-foreground">
          {caption}
          {table.truncated && " (showing the first rows only)"}
        </figcaption>
      )}
    </figure>
  );
}

const CHART_COLORS = [
  "#04f0f0",
  "#ff7a90",
  "#f6c85f",
  "#7ee787",
  "#9d8cff",
  "#6cb6ff",
  "#f090d9",
  "#b6e880",
];

const chartTooltipStyle = {
  background: "#f8fbff",
  border: "1px solid rgba(4,240,240,0.55)",
  borderRadius: 8,
  color: "#0b1020",
  fontSize: 12,
  padding: "8px 10px",
  boxShadow: "0 14px 36px rgba(0,0,0,0.45)",
} as const;

const chartTooltipLabelStyle = {
  color: "#0b1020",
  fontWeight: 700,
} as const;

const chartTooltipItemStyle = {
  color: "#0b1020",
  fontWeight: 600,
} as const;

function ResultChart({ chart }: { chart: AnalyticsChart }) {
  const rows = chart.series[0]?.points.map((point, index) => {
    const row: Record<string, string | number> = { label: point.label };
    for (const series of chart.series) {
      row[series.name] = series.points[index]?.value ?? 0;
    }
    return row;
  }) ?? [];

  if (!rows.length) return null;

  const label = humanize(chart.label_column);

  return (
    <figure className="mb-3 rounded-lg border border-white/10 bg-black/20 px-2 py-3">
      {chart.kind === "pie" ? (
        <ResponsiveContainer width="100%" height={240}>
          <PieChart>
            <Tooltip
              contentStyle={chartTooltipStyle}
              labelStyle={chartTooltipLabelStyle}
              itemStyle={chartTooltipItemStyle}
            />
            <Pie
              data={chart.series[0].points}
              dataKey="value"
              nameKey="label"
              innerRadius={44}
              outerRadius={82}
              paddingAngle={2}
            >
              {chart.series[0].points.map((point, index) => (
                <Cell key={point.label} fill={CHART_COLORS[index % CHART_COLORS.length]} />
              ))}
            </Pie>
            <Legend formatter={(value) => humanize(String(value))} />
          </PieChart>
        </ResponsiveContainer>
      ) : chart.kind === "line" ? (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: "#8891a5", fontSize: 12 }} tickLine={false} />
            <YAxis allowDecimals={false} tick={{ fill: "#8891a5", fontSize: 12 }} tickLine={false} />
            <Tooltip
              contentStyle={chartTooltipStyle}
              itemStyle={chartTooltipItemStyle}
              labelFormatter={(value) => `${label}: ${value}`}
              labelStyle={chartTooltipLabelStyle}
            />
            <Legend formatter={(value) => humanize(String(value))} />
            {chart.series.map((series, index) => (
              <Line
                key={series.name}
                type="monotone"
                dataKey={series.name}
                stroke={CHART_COLORS[index % CHART_COLORS.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.07)" vertical={false} />
            <XAxis dataKey="label" tick={{ fill: "#8891a5", fontSize: 12 }} tickLine={false} />
            <YAxis allowDecimals={false} tick={{ fill: "#8891a5", fontSize: 12 }} tickLine={false} />
            <Tooltip
              contentStyle={chartTooltipStyle}
              itemStyle={chartTooltipItemStyle}
              labelFormatter={(value) => `${label}: ${value}`}
              labelStyle={chartTooltipLabelStyle}
            />
            <Legend formatter={(value) => humanize(String(value))} />
            {chart.series.map((series, index) => (
              <Bar
                key={series.name}
                dataKey={series.name}
                fill={CHART_COLORS[index % CHART_COLORS.length]}
                radius={[5, 5, 0, 0]}
                maxBarSize={56}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </figure>
  );
}

function EmptyChat({
  onPick,
  disabled,
}: {
  onPick: (q: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 py-10 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-primary/15 text-primary">
        <MessagesSquare className="size-6" />
      </span>
      <div>
        <p className="text-sm font-semibold text-foreground">Ask about your data</p>
        <p className="mt-1 text-xs text-muted-foreground">
          I answer only from your own tickets and remember earlier chats.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            disabled={disabled}
            onClick={() => onPick(s)}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/[0.04] px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground disabled:opacity-50"
          >
            <Sparkles className="size-3" />
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
