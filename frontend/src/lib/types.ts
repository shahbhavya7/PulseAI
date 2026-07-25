/**
 * TypeScript mirrors of the FastAPI response schemas. These are hand-maintained
 * to match `src/app/schemas/*` on the backend — the single source of truth for
 * the shapes the dashboard renders.
 */

// ---- Uploads (POST /uploads) ----------------------------------------------

export type SkipReason = "blank" | "empty_after_clean" | "duplicate";

export interface CreatedItem {
  source_ref: string;
  ticket_id: string;
  issue_id: string;
  title: string;
  language: string;
  confidence: number;
  flags: string[];
  needs_manual_review: boolean;
}

export interface SkippedItemOut {
  source_ref: string;
  reason: SkipReason;
}

export interface UploadCounts {
  detected: number;
  created: number;
  skipped: number;
  flagged: number;
  duplicates: number;
  blanks: number;
}

export interface UploadSummary {
  filename: string;
  content_type: string | null;
  parser: string;
  encoding_recovered: boolean;
  analyzed: boolean;
  analyzed_count: number;
  counts: UploadCounts;
  created_items: CreatedItem[];
  skipped_items: SkippedItemOut[];
}

// ---- Stats (GET /stats) ----------------------------------------------------

export interface SentimentPoint {
  week: string;
  avg_sentiment: number;
  avg_urgency: number;
  issue_count: number;
}

export interface ThemeCount {
  theme: string;
  count: number;
  examples: string[];
}

export interface StatsFilters {
  week: string | null;
  min_confidence: number | null;
  needs_manual_review: boolean | null;
}

export interface StatsResponse {
  total_issues: number;
  filters: StatsFilters;
  category_distribution: Record<string, number>;
  urgency_counts: Record<string, number>;
  sentiment_over_time: SentimentPoint[];
  top_themes: ThemeCount[];
}

// ---- Weekly summary (GET/POST /summaries/{week}) ---------------------------

export interface SummaryMetrics {
  total_issues: number;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
  needs_review: number;
  avg_sentiment: number;
  avg_urgency: number;
}

export interface SummaryResponse {
  week: string;
  status: string;
  issue_count: number;
  headline: string;
  narrative: string;
  recommendations: string[];
  themes: ThemeCount[];
  metrics: SummaryMetrics;
}

// ---- Tickets (GET /tickets) ------------------------------------------------

export type IssueCategory =
  | "bug"
  | "feature_request"
  | "question"
  | "incident"
  | "other";

export type IssueSeverity = "low" | "medium" | "high" | "critical";

export type SentimentBucket = "negative" | "neutral" | "positive";

export interface IssueOut {
  id: string;
  title: string;
  category: IssueCategory;
  severity: IssueSeverity;
  confidence: number;
  sentiment_score: number;
  urgency_score: number;
  themes: string[];
  needs_manual_review: boolean;
  flags: string[];
  analyzed_at: string | null;
  created_at: string;
}

export interface TicketOut {
  id: string;
  title: string;
  body: string;
  source: string;
  status: string;
  created_at: string;
  issue_count: number;
  issues: IssueOut[];
}

export interface TicketListResponse {
  total: number;
  limit: number;
  offset: number;
  tickets: TicketOut[];
}

// ---- Ticket analyze (POST /tickets/{id}/analyze) ---------------------------

export interface AnalyzedIssueOut {
  issue_id: string;
  category: IssueCategory;
  severity: string;
  confidence: number;
  sentiment_score: number;
  urgency_score: number;
  themes: string[];
  needs_manual_review: boolean;
}

export interface TicketAnalyzeResponse {
  ticket_id: string;
  source: string;
  created: number;
  issues: AnalyzedIssueOut[];
}

// ---- Auth (GET /auth/me, /auth/providers) ----------------------------------

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  oauth_provider: string | null;
}

export interface ProvidersResponse {
  providers: string[];
  email: boolean;
}

// ---- Chat (Phase 6) --------------------------------------------------------

export interface ChatMessageOut {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

export interface ChatSessionOut {
  id: string;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionDetail extends ChatSessionOut {
  messages: ChatMessageOut[];
}
