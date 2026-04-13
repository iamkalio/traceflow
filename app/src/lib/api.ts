import { TRACEFLOW_API_URL } from "@/lib/env";
import { getStoredOpenAIKey } from "@/lib/openaiKey";

// ---------------------------------------------------------------------------
// Auth token helpers
// ---------------------------------------------------------------------------

const AUTH_TOKEN_KEY = "tf_auth_token";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

function authHeaders(): HeadersInit {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function openaiKeyHeaders(): HeadersInit {
  const key = getStoredOpenAIKey();
  return key ? { "X-OpenAI-API-Key": key } : {};
}

// ---------------------------------------------------------------------------
// Eval provider local key (stored in browser, sent as header per request)
// ---------------------------------------------------------------------------

export const EVAL_LOCAL_KEY_QUERY_KEY = ["eval-provider-local"] as const;

export function getEvalProviderConfiguredLocal(): { configured: boolean } {
  if (typeof window === "undefined") return { configured: false };
  return { configured: !!getStoredOpenAIKey() };
}

// ---------------------------------------------------------------------------
// Types (mirror backend Pydantic schemas)
// ---------------------------------------------------------------------------

export interface TraceListItem {
  trace_id: string;
  name: string | null;
  input: string | null;
  output: string | null;
  annotations: number | null;
  eval_status: string | null;
  eval_score: number | null;
  eval_label: string | null;
  start_time: string | null;
  latency_ms: number | null;
  first_seen: string;
  last_seen: string;
  span_count: number;
  status: string;
  total_tokens: number | null;
  total_cost_usd: number | null;
}

export interface TraceListResponse {
  items: TraceListItem[];
  next_cursor: string | null;
}

export interface TraceSpan {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  kind: string;
  event_time: string;
  model: string;
  name: string;
  prompt: string | null;
  completion: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cost_usd: number | null;
  latency_ms: number | null;
  status: string;
  error: string | null;
  context: Record<string, unknown> | null;
  attributes: Record<string, unknown>;
  tenant_id: string | null;
}

export interface EvalRun {
  id: number;
  group_id: number | null;
  trace_id: string;
  span_id: string | null;
  status: string;
  evaluator_type: string;
  evaluator_version: string;
  score: number | null;
  label: string | null;
  reasoning: string | null;
  context: Record<string, unknown> | null;
  error: string | null;
  latency_ms: number | null;
  cost_usd: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface FailureTypeCount {
  failure_type: string;
  count: number;
}

export interface InsightsSummary {
  sample_size: number;
  completed_with_score: number;
  avg_score: number | null;
  good_count: number;
  borderline_count: number;
  bad_count: number;
  good_pct: number | null;
  borderline_pct: number | null;
  bad_pct: number | null;
  total_eval_cost_usd: number;
  top_failure_types: FailureTypeCount[];
}

export interface WorstRegression {
  trace_id: string;
  delta_score: number | null;
  verdict: string;
  regression_compare_score: number | null;
}

export interface EvalRunGroupDetail {
  id: number;
  name: string;
  status: string;
  total_jobs: number;
  tenant_id: string | null;
  created_at: string;
  avg_score: number | null;
  good_count: number;
  borderline_count: number;
  bad_count: number;
  good_pct: number | null;
  borderline_pct: number | null;
  bad_pct: number | null;
  total_eval_cost_usd: number;
  completed_jobs: number;
  top_failure_types: FailureTypeCount[];
  eval_runs: EvalRun[];
  pct_improved: number | null;
  pct_regressed: number | null;
  pct_unchanged: number | null;
  avg_delta_score: number | null;
  worst_regressions: WorstRegression[];
  regression_summary: string;
}

export interface AuthUser {
  tenant_id: string;
  github_login: string;
  email: string;
  avatar_url: string;
}

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${TRACEFLOW_API_URL}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Trace queries
// ---------------------------------------------------------------------------

export interface ListTracesParams {
  limit?: number;
  cursor?: string | null;
  q?: string | null;
  status?: string | null;
  model?: string | null;
  tenant_id?: string | null;
  start_time?: string | null;
  end_time?: string | null;
}

export async function listTraces(params: ListTracesParams = {}): Promise<TraceListResponse> {
  const qs = new URLSearchParams();
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.cursor) qs.set("cursor", params.cursor);
  if (params.q) qs.set("q", params.q);
  if (params.status) qs.set("status", params.status);
  if (params.model) qs.set("model", params.model);
  if (params.tenant_id) qs.set("tenant_id", params.tenant_id);
  if (params.start_time) qs.set("start_time", params.start_time);
  if (params.end_time) qs.set("end_time", params.end_time);
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiFetch<TraceListResponse>(`/v1/traces${suffix}`);
}

export async function getTrace(traceId: string): Promise<TraceSpan[]> {
  return apiFetch<TraceSpan[]>(`/v1/traces/${traceId}`);
}

export async function listTraceEvalRuns(traceId: string): Promise<EvalRun[]> {
  return apiFetch<EvalRun[]>(`/v1/traces/${traceId}/eval-runs`);
}

// ---------------------------------------------------------------------------
// Eval actions
// ---------------------------------------------------------------------------

export async function runTraceEval(
  traceId: string,
  evalName: string,
): Promise<{ status: string; eval_run_id: number }> {
  return apiFetch(`/v1/traces/${traceId}/evals/run`, {
    method: "POST",
    headers: openaiKeyHeaders(),
    body: JSON.stringify({ eval_name: evalName }),
  });
}

export async function runRegression(payload: {
  n: number;
  eval_name?: string;
}): Promise<{ status: string; group_id: number; eval_run_ids: number[] }> {
  return apiFetch(`/v1/regression/run`, {
    method: "POST",
    headers: openaiKeyHeaders(),
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Insights & eval runs
// ---------------------------------------------------------------------------

export async function getInsightsSummary(limit = 100): Promise<InsightsSummary> {
  return apiFetch<InsightsSummary>(`/v1/insights/summary?limit=${limit}`);
}

export async function listEvalRuns(params: { limit?: number; trace_id?: string } = {}): Promise<EvalRun[]> {
  const qs = new URLSearchParams();
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.trace_id) qs.set("trace_id", params.trace_id);
  const suffix = qs.toString() ? `?${qs}` : "";
  return apiFetch<EvalRun[]>(`/v1/eval-runs${suffix}`);
}

export async function getEvalRunGroup(groupId: number): Promise<EvalRunGroupDetail> {
  return apiFetch<EvalRunGroupDetail>(`/v1/eval-run-groups/${groupId}`);
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function getMe(): Promise<AuthUser> {
  return apiFetch<AuthUser>("/auth/me");
}
