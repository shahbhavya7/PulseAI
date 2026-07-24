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
