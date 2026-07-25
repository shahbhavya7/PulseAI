/**
 * The one place the dashboard talks to FastAPI.
 *
 * Everything goes through `apiFetch`, which:
 *   - prefixes the configured API base URL,
 *   - sends the session cookie (`credentials: "include"`) — auth is a signed
 *     httpOnly cookie set by the backend after OAuth, so there's no token to
 *     manage in JS,
 *   - turns a dead backend into a friendly typed error (not a blank screen),
 *   - unwraps the backend's `{ detail: { code, message } }` error shape,
 *   - surfaces 401 via a subscribable hook so the app can redirect to sign-in.
 *
 * Callers get typed helpers (`getStats`, `getTickets`, …) and never touch
 * `fetch` directly.
 */

import type {
  ChatSessionDetail,
  ChatSessionOut,
  CurrentUser,
  ProvidersResponse,
  StatsResponse,
  SummaryResponse,
  TicketAnalyzeResponse,
  TicketListResponse,
  UploadSummary,
} from "./types";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api"
).replace(/\/$/, "");

/** A failure the UI can render kindly. `kind` tells the UI what to say. */
export class ApiError extends Error {
  readonly kind: "network" | "http";
  readonly status?: number;
  readonly code?: string;

  constructor(
    message: string,
    opts: { kind: "network" | "http"; status?: number; code?: string },
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = opts.kind;
    this.status = opts.status;
    this.code = opts.code;
  }

  /** True when the backend appears unreachable (server down, CORS, offline). */
  get isBackendDown(): boolean {
    return this.kind === "network";
  }

  /** True when the user isn't signed in (or the session expired). */
  get isUnauthorized(): boolean {
    return this.kind === "http" && this.status === 401;
  }
}

// A single listener the auth provider registers so any 401 from any call can
// drop the user back to the sign-in screen without every caller handling it.
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
}

async function readError(res: Response): Promise<ApiError> {
  // The API returns `{ detail: ... }`; detail may be a string or {code,message}.
  let code: string | undefined;
  let message = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      code = detail.code;
      message = detail.message ?? message;
    }
  } catch {
    // Non-JSON error body — keep the generic message.
  }
  return new ApiError(message, { kind: "http", status: res.status, code });
}

interface FetchOpts extends RequestInit {
  /** Set false to NOT trigger the global 401 handler (used by the auth probe,
   *  where a 401 is an expected "not signed in" answer, not a session drop). */
  handleUnauthorized?: boolean;
}

async function apiFetch<T>(path: string, init?: FetchOpts): Promise<T> {
  const { handleUnauthorized = true, ...rest } = init ?? {};
  const url = `${API_BASE_URL}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...rest,
      // Send the session cookie on every cross-origin call.
      credentials: "include",
      cache: "no-store",
    });
  } catch {
    // fetch only rejects on network-level failure — the backend is unreachable.
    throw new ApiError(
      "Can't reach the PulseAI backend. Is it running on port 8000?",
      { kind: "network" },
    );
  }
  if (!res.ok) {
    const err = await readError(res);
    if (err.isUnauthorized && handleUnauthorized) onUnauthorized?.();
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- Typed endpoint helpers ------------------------------------------------

export function uploadFile(file: File): Promise<UploadSummary> {
  const form = new FormData();
  form.append("file", file);
  // Do NOT set Content-Type: the browser sets the multipart boundary itself.
  return apiFetch<UploadSummary>("/uploads", { method: "POST", body: form });
}

/** Submit one typed/pasted ticket — same ingestion + auto-classify as a text file. */
export function uploadText(text: string, title?: string): Promise<UploadSummary> {
  return apiFetch<UploadSummary>("/uploads/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, title: title?.trim() || null }),
  });
}

export function getStats(params: {
  week?: string;
  minConfidence?: number;
  needsManualReview?: boolean;
}): Promise<StatsResponse> {
  const q = new URLSearchParams();
  if (params.week) q.set("week", params.week);
  if (params.minConfidence != null) q.set("min_confidence", String(params.minConfidence));
  if (params.needsManualReview != null)
    q.set("needs_manual_review", String(params.needsManualReview));
  const qs = q.toString();
  return apiFetch<StatsResponse>(`/stats${qs ? `?${qs}` : ""}`);
}

export function getSummary(week: string): Promise<SummaryResponse> {
  return apiFetch<SummaryResponse>(`/summaries/${encodeURIComponent(week)}`);
}

export function generateSummary(week: string): Promise<SummaryResponse> {
  return apiFetch<SummaryResponse>(`/summaries/${encodeURIComponent(week)}`, {
    method: "POST",
  });
}

export function getTickets(params: {
  category?: string;
  sentiment?: string;
  minConfidence?: number;
  needsManualReview?: boolean;
  limit?: number;
  offset?: number;
}): Promise<TicketListResponse> {
  const q = new URLSearchParams();
  if (params.category) q.set("category", params.category);
  if (params.sentiment) q.set("sentiment", params.sentiment);
  if (params.minConfidence != null) q.set("min_confidence", String(params.minConfidence));
  if (params.needsManualReview != null)
    q.set("needs_manual_review", String(params.needsManualReview));
  if (params.limit != null) q.set("limit", String(params.limit));
  if (params.offset != null) q.set("offset", String(params.offset));
  const qs = q.toString();
  return apiFetch<TicketListResponse>(`/tickets${qs ? `?${qs}` : ""}`);
}

export function analyzeTicket(ticketId: string): Promise<TicketAnalyzeResponse> {
  return apiFetch<TicketAnalyzeResponse>(
    `/tickets/${encodeURIComponent(ticketId)}/analyze`,
    { method: "POST" },
  );
}

/** Delete a ticket (and its issues) permanently. Resolves on 204. */
export function deleteTicket(ticketId: string): Promise<void> {
  return apiFetch<void>(`/tickets/${encodeURIComponent(ticketId)}`, {
    method: "DELETE",
  });
}

// ---- Auth ------------------------------------------------------------------

/** The current user, or null if not signed in (a 401 here is expected, not a
 *  session drop, so it doesn't trigger the global handler). */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  try {
    return await apiFetch<CurrentUser>("/auth/me", { handleUnauthorized: false });
  } catch (err) {
    if (err instanceof ApiError && err.isUnauthorized) return null;
    throw err;
  }
}

export function getProviders(): Promise<ProvidersResponse> {
  return apiFetch<ProvidersResponse>("/auth/providers", {
    handleUnauthorized: false,
  });
}

/** Full-page navigate to the backend's OAuth login (a redirect flow, not fetch). */
export function loginUrl(provider: string): string {
  return `${API_BASE_URL}/auth/login/${encodeURIComponent(provider)}`;
}

export function logout(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/auth/logout", {
    method: "POST",
    handleUnauthorized: false,
  });
}

/** Email + password sign-in. Sets the session cookie and returns the user.
 *  A 401 here is a bad-credentials answer, not a session drop. */
export function loginEmail(email: string, password: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/auth/login/email", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    handleUnauthorized: false,
  });
}

/** Register a new email/password account (also signs in). */
export function registerEmail(
  email: string,
  password: string,
  fullName?: string,
): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, full_name: fullName || null }),
    handleUnauthorized: false,
  });
}

// ---- Chat (Phase 6) --------------------------------------------------------

export function listSessions(): Promise<ChatSessionOut[]> {
  return apiFetch<ChatSessionOut[]>("/chat/sessions");
}

export function createSession(title?: string): Promise<ChatSessionOut> {
  return apiFetch<ChatSessionOut>("/chat/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title ?? null }),
  });
}

export function getSession(id: string): Promise<ChatSessionDetail> {
  return apiFetch<ChatSessionDetail>(`/chat/sessions/${encodeURIComponent(id)}`);
}

export function endSession(id: string): Promise<void> {
  return apiFetch<void>(`/chat/sessions/${encodeURIComponent(id)}/end`, {
    method: "POST",
    handleUnauthorized: false,
  });
}

/**
 * Send a message and stream the grounded answer. Calls `onToken` for each token
 * as it arrives (SSE), resolves when the stream closes. Rejects with ApiError on
 * a network/HTTP failure before the stream starts.
 */
export async function streamMessage(
  sessionId: string,
  message: string,
  onToken: (token: string) => void,
  opts?: { week?: string; category?: string; signal?: AbortSignal },
): Promise<void> {
  const url = `${API_BASE_URL}/chat/sessions/${encodeURIComponent(sessionId)}/messages`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        week: opts?.week ?? null,
        category: opts?.category ?? null,
      }),
      signal: opts?.signal,
    });
  } catch {
    throw new ApiError("Can't reach the PulseAI backend.", { kind: "network" });
  }
  if (!res.ok) {
    const err = await readError(res);
    if (err.isUnauthorized) onUnauthorized?.();
    throw err;
  }
  if (!res.body) throw new ApiError("No response stream.", { kind: "http" });

  // Parse the SSE body: `data: {json}` lines, blank-line separated.
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const evt of events) {
      for (const line of evt.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const raw = line.slice(5).trim();
        if (!raw || raw === "{}") continue;
        try {
          const parsed = JSON.parse(raw) as { token?: string; error?: string };
          if (parsed.token) onToken(parsed.token);
        } catch {
          // Ignore malformed keep-alive lines.
        }
      }
    }
  }
}
