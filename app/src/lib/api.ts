import { TRACEFLOW_API_URL } from "./env";
import { getStoredOpenAIKey, isOpenAIKeyConfigured } from "./openaiKey";

export type TraceListItem = {
  trace_id: string;
  name: string | null;
  input: string | null;
  output: string | null;
  annotations: number | null;
  eval_status?: string | null;
  eval_score?: number | null;
  eval_label?: string | null;
  start_time: string | null;
  latency_ms: number | null;
  first_seen: string;
  last_seen: string;
  span_count: number;
  status: string;
  total_tokens: number | null;
  total_cost_usd: number | null;
};

export type TraceListResponse = {
  items: TraceListItem[];
  next_cursor: string | null;
};

export type TraceSpan = {
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
  context: unknown | null;
  attributes: unknown;
  tenant_id: string | null;
};

export type EvalResult = {
  id: number;
  trace_id: string;
  span_id: string;
  eval_name: string;
  eval_version: string;
  score: number | null;
  label: string;
  reason: string | null;
  details: unknown;
  created_at: string;
};

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${TRACEFLOW_API_URL}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
  }
  return (await res.json()) as T;
}

async function httpOrNull<T>(path: string, init?: RequestInit): Promise<T | null> {
  const res = await fetch(`${TRACEFLOW_API_URL}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
  }
  return (await res.json()) as T;
}

export function listTraces(params: {
  limit: number;
  cursor?: string;
  q?: string;
  status?: string;
}): Promise<TraceListResponse> {
  const usp = new URLSearchParams();
  usp.set("limit", String(params.limit));
  if (params.cursor) usp.set("cursor", params.cursor);
  if (params.q) usp.set("q", params.q);
  if (params.status) usp.set("status", params.status);
  return http<TraceListResponse>(`/v1/traces?${usp.toString()}`);
}

export function getTrace(traceId: string): Promise<TraceSpan[]> {
  return http<TraceSpan[]>(`/v1/traces/${encodeURIComponent(traceId)}`);
}

export function listTraceEvals(traceId: string, evalName?: string): Promise<EvalResult[]> {
  const usp = new URLSearchParams();
  if (evalName) usp.set("eval_name", evalName);
  const qs = usp.toString();
  return http<EvalResult[]>(
    `/v1/traces/${encodeURIComponent(traceId)}/evals${qs ? `?${qs}` : ""}`,
  );
}

export type EvalProviderSettings = {
  configured: boolean;
  provider: "openai";
};

/** React Query key: localStorage-backed eval key presence (invalidate after Settings save). */
export const EVAL_LOCAL_KEY_QUERY_KEY = ["eval-openai-key-local"] as const;

/** Whether an API key is stored in the browser (not a server call). */
export async function getEvalProviderConfiguredLocal(): Promise<EvalProviderSettings> {
  return {
    configured: isOpenAIKeyConfigured(),
    provider: "openai",
  };
}

export async function runTraceEval(traceId: string, evalName: string): Promise<{ status: string }> {
  const key = getStoredOpenAIKey();
  if (!key) {
    throw new Error("No OpenAI API key in this browser. Add it under Settings.");
  }
  return http<{ status: string }>(`/v1/traces/${encodeURIComponent(traceId)}/evals/run`, {
    method: "POST",
    body: JSON.stringify({ eval_name: evalName }),
    headers: {
      "X-OpenAI-API-Key": key,
    },
  });
}

export type EvalRun = {
  id: number;
  group_id?: number | null;
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
  latency_ms?: number | null;
  cost_usd?: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export function listTraceEvalRuns(traceId: string): Promise<EvalRun[]> {
  return http<EvalRun[]>(`/v1/traces/${encodeURIComponent(traceId)}/eval-runs`);
}

/** Recent eval runs (LLM-as-a-Judge, etc.) across all traces or filtered by trace. */
export function listEvalRuns(params?: { limit?: number; traceId?: string }): Promise<EvalRun[]> {
  const usp = new URLSearchParams();
  if (params?.limit != null) usp.set("limit", String(params.limit));
  if (params?.traceId) usp.set("trace_id", params.traceId);
  const qs = usp.toString();
  return http<EvalRun[]>(`/v1/eval-runs${qs ? `?${qs}` : ""}`);
}

export type InsightsSummary = {
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
  top_failure_types: { failure_type: string; count: number }[];
};

export function getInsightsSummary(params?: { limit?: number }): Promise<InsightsSummary> {
  const usp = new URLSearchParams();
  if (params?.limit != null) usp.set("limit", String(params.limit));
  const qs = usp.toString();
  return http<InsightsSummary>(`/v1/insights/summary${qs ? `?${qs}` : ""}`);
}

export type WorstRegression = {
  trace_id: string;
  delta_score: number | null;
  verdict: string;
  regression_compare_score: number | null;
};

export type EvalRunGroupDetail = {
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
  top_failure_types: { failure_type: string; count: number }[];
  eval_runs: EvalRun[];
  pct_improved?: number | null;
  pct_regressed?: number | null;
  pct_unchanged?: number | null;
  avg_delta_score?: number | null;
  worst_regressions?: WorstRegression[];
  /** Plain-language batch summary (from server). */
  regression_summary?: string;
};

export function getEvalRunGroup(groupId: number): Promise<EvalRunGroupDetail> {
  return http<EvalRunGroupDetail>(`/v1/eval-run-groups/${groupId}`);
}

export function runRegression(params: {
  n: number;
  evalName?: string;
}): Promise<{ status: string; group_id: number; eval_run_ids: number[] }> {
  const key = getStoredOpenAIKey();
  if (!key) {
    throw new Error("No OpenAI API key in this browser. Add it under Settings.");
  }
  return http<{ status: string; group_id: number; eval_run_ids: number[] }>(
    `/v1/regression/run`,
    {
      method: "POST",
      body: JSON.stringify({
        n: params.n,
        eval_name: params.evalName ?? "regression_compare_v1",
      }),
      headers: {
        "X-OpenAI-API-Key": key,
      },
    },
  );
}
