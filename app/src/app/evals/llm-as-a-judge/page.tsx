"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Suspense } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

import { AppShell } from "@/components/shell/AppShell";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EvalPageHeader, EvalSplit } from "@/components/evaluation/EvalSplit";
import { getInsightsSummary, listEvalRuns, type EvalRun } from "@/lib/api";
import { formatDateTime, formatUsd } from "@/lib/format";

const GLOBAL_EVAL_KEY = ["eval-runs-global"] as const;

export default function LlmAsJudgePage() {
  return (
    <AppShell active="evals">
      <Suspense
        fallback={
          <div className="flex min-h-[40vh] items-center justify-center px-6 text-sm text-muted-foreground">
            Loading LLM-as-a-Judge…
          </div>
        }
      >
        <LlmAsJudgeContent />
      </Suspense>
    </AppShell>
  );
}

function LlmAsJudgeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const traceFilter = searchParams.get("trace");

  const runsQ = useQuery({
    queryKey: [...GLOBAL_EVAL_KEY, traceFilter ?? "all"],
    queryFn: () =>
      listEvalRuns({
        limit: 150,
        traceId: traceFilter ?? undefined,
      }),
    refetchInterval: (q) => {
      const rows = q.state.data;
      if (!Array.isArray(rows) || !rows.length) return false;
      return rows.some((r) => r.status === "queued" || r.status === "running") ? 2500 : false;
    },
  });

  const summaryQ = useQuery({
    queryKey: ["insights-summary"],
    queryFn: () => getInsightsSummary({ limit: 100 }),
    refetchInterval: 15000,
  });

  const runs = React.useMemo(() => runsQ.data ?? [], [runsQ.data]);
  const [selectedId, setSelectedId] = React.useState<number | null>(null);

  React.useEffect(() => {
    if (!runs.length) {
      setSelectedId(null);
      return;
    }
    setSelectedId((curr) => {
      if (curr != null && runs.some((r) => r.id === curr)) return curr;
      return runs[0]?.id ?? null;
    });
  }, [runs]);

  const selected = runs.find((r) => r.id === selectedId) ?? null;

  const setTraceFilter = (tid: string | null) => {
    const p = new URLSearchParams(searchParams.toString());
    if (tid) p.set("trace", tid);
    else p.delete("trace");
    router.push(`/evals/llm-as-a-judge${p.toString() ? `?${p.toString()}` : ""}`);
  };

  return (
      <div className="px-6 py-5">
        <EvalPageHeader
          eyebrow="Evaluation"
          title="LLM-as-a-Judge"
          description="Groundedness and other judge runs: scores, verdict, reasoning, and actionable prompt/context improvements. Data comes from live eval runs (worker must be running for jobs to finish)."
          actions={
            traceFilter ? (
              <Badge variant="outline" className="font-mono text-xs" title={traceFilter}>
                trace: {shortTraceId(traceFilter)}
              </Badge>
            ) : null
          }
        />

        {traceFilter ? (
          <div className="mb-4 text-sm">
            <button
              type="button"
              onClick={() => setTraceFilter(null)}
              className="text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              Show all traces
            </button>
          </div>
        ) : null}

        {summaryQ.data ? (
          <div className="mb-5 rounded-none border border-border/60 bg-card/40 px-4 py-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Last {summaryQ.data.sample_size} judge runs
              </div>
              <Link
                href="/insights"
                className="text-xs font-medium text-primary underline-offset-2 hover:underline"
              >
                Open Insights
              </Link>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge variant="secondary">
                Avg score:{" "}
                {summaryQ.data.avg_score != null ? summaryQ.data.avg_score.toFixed(3) : "—"}
              </Badge>
              <Badge variant="outline">
                Good:{" "}
                {summaryQ.data.good_pct != null
                  ? `${(summaryQ.data.good_pct * 100).toFixed(0)}%`
                  : "—"}
              </Badge>
              <Badge variant="outline">
                Borderline:{" "}
                {summaryQ.data.borderline_pct != null
                  ? `${(summaryQ.data.borderline_pct * 100).toFixed(0)}%`
                  : "—"}
              </Badge>
              <Badge variant="outline">
                Bad:{" "}
                {summaryQ.data.bad_pct != null
                  ? `${(summaryQ.data.bad_pct * 100).toFixed(0)}%`
                  : "—"}
              </Badge>
              <Badge variant="outline">Eval spend: {formatUsd(summaryQ.data.total_eval_cost_usd)}</Badge>
            </div>
          </div>
        ) : summaryQ.isLoading ? (
          <div className="mb-5 text-sm text-muted-foreground">Loading summary…</div>
        ) : null}

        <EvalSplit
          list={
            <Card className="border-border/60 rounded-none">
              <CardContent className="p-0">
                {runsQ.isLoading ? (
                  <div className="p-6 text-sm text-muted-foreground">Loading eval runs…</div>
                ) : runsQ.isError ? (
                  <div className="p-6 text-sm text-destructive">{(runsQ.error as Error).message}</div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[72px] min-w-[72px] max-w-[72px]">Trace</TableHead>
                        <TableHead className="w-[120px]">Eval type</TableHead>
                        <TableHead className="w-[90px]">Score</TableHead>
                        <TableHead className="w-[110px]">Status</TableHead>
                        <TableHead className="w-[180px]">Time (UTC)</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {runs.map((r) => (
                        <TableRow
                          key={r.id}
                          className={selectedId === r.id ? "bg-secondary/60" : "cursor-pointer"}
                          onClick={() => setSelectedId(r.id)}
                        >
                          <TableCell className="w-[72px] min-w-[72px] max-w-[72px] overflow-hidden">
                            <button
                              type="button"
                              title={r.trace_id}
                              className="block w-full truncate font-mono text-left text-xs text-primary underline-offset-2 hover:underline"
                              onClick={(e) => {
                                e.stopPropagation();
                                setTraceFilter(r.trace_id);
                              }}
                            >
                              {shortTraceId(r.trace_id)}
                            </button>
                          </TableCell>
                          <TableCell className="text-sm">{r.evaluator_type}</TableCell>
                          <TableCell>{r.score ?? "—"}</TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                r.status === "failed"
                                  ? "destructive"
                                  : r.status === "completed"
                                    ? "secondary"
                                    : "outline"
                              }
                            >
                              {r.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {formatDateTime(r.created_at)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
                {!runsQ.isLoading && !runs.length ? (
                  <div className="p-6 text-sm text-muted-foreground">
                    No eval runs yet. Run a groundedness eval from a trace (trace drawer → Run eval), then refresh or wait
                    for the worker.
                  </div>
                ) : null}
              </CardContent>
            </Card>
          }
          detail={
            selected ? (
              <JudgeRunDetail run={selected} />
            ) : (
              <p className="text-sm text-muted-foreground">Select a run for details.</p>
            )
          }
        />
      </div>
  );
}

function shortTraceId(traceId: string): string {
  if (traceId.length <= 4) return traceId;
  return `${traceId.slice(0, 4)}…`;
}

function JudgeRunDetail({ run }: { run: EvalRun }) {
  const ctx = run.context && typeof run.context === "object" ? run.context : {};
  const promptImprovement =
    typeof ctx.prompt_improvement === "string" ? ctx.prompt_improvement : "";
  const contextImprovement =
    typeof ctx.context_improvement === "string" ? ctx.context_improvement : "";
  const failureType = typeof ctx.failure_type === "string" ? ctx.failure_type : "";
  const suggestedFix = typeof ctx.suggested_fix === "string" ? ctx.suggested_fix : "";

  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">Score: {run.score ?? "—"}</Badge>
        <Badge variant="outline">{run.evaluator_type}</Badge>
        <Badge variant="outline">{run.status}</Badge>
        {run.group_id != null ? (
          <Link
            href={`/insights?group=${run.group_id}`}
            className="text-xs text-primary underline-offset-2 hover:underline"
          >
            Batch #{run.group_id}
          </Link>
        ) : null}
        {run.cost_usd != null ? (
          <Badge variant="outline">Run cost: {formatUsd(run.cost_usd)}</Badge>
        ) : null}
        {run.latency_ms != null ? (
          <Badge variant="outline">{run.latency_ms} ms judge</Badge>
        ) : null}
      </div>

      <DetailRow label="Trace" mono value={run.trace_id} />
      {run.span_id ? <DetailRow label="Span" mono value={run.span_id} /> : null}
      <DetailRow label="Label" value={run.label || "—"} />
      {failureType ? <DetailRow label="Failure type" value={failureType} /> : null}
      {typeof ctx.previous_score === "number" ? (
        <DetailRow label="Previous eval score" value={String(ctx.previous_score)} />
      ) : null}
      {typeof ctx.previous_eval_run_id === "number" ? (
        <DetailRow label="Compared to eval run" mono value={String(ctx.previous_eval_run_id)} />
      ) : null}
      {suggestedFix ? (
        <div className="flex flex-col gap-0.5">
          <div className="text-xs uppercase tracking-wider text-muted-foreground">Suggested fix</div>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{suggestedFix}</p>
        </div>
      ) : null}
      <div className="flex flex-col gap-0.5">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">Reasoning</div>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{run.reasoning || "—"}</p>
      </div>

      {(promptImprovement || contextImprovement) && (
        <div className="space-y-3 border-t border-border/60 pt-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Improvements</div>
          {promptImprovement ? (
            <div>
              <div className="text-xs text-muted-foreground">Prompt / instructions</div>
              <p className="mt-1 whitespace-pre-wrap text-sm">{promptImprovement}</p>
            </div>
          ) : null}
          {contextImprovement ? (
            <div>
              <div className="text-xs text-muted-foreground">Retrieval / context</div>
              <p className="mt-1 whitespace-pre-wrap text-sm">{contextImprovement}</p>
            </div>
          ) : null}
        </div>
      )}

      {run.error ? (
        <div className="rounded-none border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive">
          {run.error}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2 border-t border-border/60 pt-3 text-xs text-muted-foreground">
        <span>Created {formatDateTime(run.created_at)}</span>
        {run.completed_at ? <span>· Done {formatDateTime(run.completed_at)}</span> : null}
      </div>

      <Link
        href={`/traces/${encodeURIComponent(run.trace_id)}`}
        className="inline-flex items-center gap-1 text-sm font-medium text-primary underline-offset-2 hover:underline"
      >
        Open trace
        <ChevronRight className="size-4" />
      </Link>
    </div>
  );
}

function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={mono ? "break-all font-mono text-xs" : ""}>{value}</div>
    </div>
  );
}
