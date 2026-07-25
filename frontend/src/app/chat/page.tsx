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
  ApiError,
  createSession,
  endSession,
  getSession,
  listSessions,
  streamMessage,
} from "@/lib/api";
import type { ChatMessageOut, ChatSessionOut } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Card } from "@/components/Card";
import { ErrorState } from "@/components/States";
import { PageTransition } from "@/components/motion";

interface UiMessage {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
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
      setSessions((prev) => [s, ...prev]);
      setActiveId(s.id);
      setMessages([]);
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
        await streamMessage(sessionId, question, (token) => {
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant") {
              next[next.length - 1] = { ...last, content: last.content + token };
            }
            return next;
          });
        });
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
