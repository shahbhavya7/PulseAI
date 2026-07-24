/**
 * The one place the dashboard talks to FastAPI.
 *
 * Everything goes through `apiFetch`, which:
 *   - prefixes the configured API base URL,
 *   - attaches the dev-stub `X-User-Id` header (Phase 1 auth stub),
 *   - turns a dead backend into a friendly typed error (not a blank screen),
 *   - unwraps the backend's `{ detail: { code, message } }` error shape.
 *
 * Callers get typed helpers (`getStats`, `getTickets`, …) and never touch
 * `fetch` directly, so the header and error handling can never be forgotten.
 */

import type {
  StatsResponse,
  SummaryResponse,
  TicketAnalyzeResponse,
  TicketListResponse,
  UploadSummary,
} from "./types";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api"
).replace(/\/$/, "");

const USER_ID = process.env.NEXT_PUBLIC_USER_ID ?? "";

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
}

function buildHeaders(extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  // Only send X-User-Id when configured; a blank value makes the backend fall
  // back to its seeded dev user, which is exactly what we want for local use.
  if (USER_ID) headers.set("X-User-Id", USER_ID);
  return headers;
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

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: buildHeaders(init?.headers),
      cache: "no-store",
    });
  } catch {
    // fetch only rejects on network-level failure — the backend is unreachable.
    throw new ApiError(
      "Can't reach the PulseAI backend. Is it running on port 8000?",
      { kind: "network" },
    );
  }
  if (!res.ok) throw await readError(res);
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
