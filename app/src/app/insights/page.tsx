"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Suspense } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  getEvalRunGroup,
  getInsightsSummary,
  type EvalRunGroupDetail,
  type InsightsSummary,
} from "@/lib/api";
import { formatDateTime, formatUsd } from "@/lib/format";

export default function InsightsPage() {
  return (
    <AppShell active="insights">
      <Suspense
        fallback={
          <div className="flex min-h-[40vh] items-center justify-center px-6 text-sm text-muted-foreground">
            Loading insights…
          </div>
        }
      >
        <InsightsContent />
      </Suspense>
    </AppShell>
  );
}

function InsightsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const groupParam = searchParams.get("group");
  const groupId = groupParam ? Number.parseInt(groupParam, 10) : NaN;
  const validGroup = Number.isFinite(groupId) && groupId > 0 ? groupId : null;

  const summaryQ = useQuery({
    queryKey: ["insights-summary"],
    queryFn: () => getInsightsSummary({ limit: 120 }),
    refetchInterval: 8000,
  });

  const groupQ = useQuery({
    queryKey: ["eval-run-group", validGroup],
    queryFn: () => getEvalRunGroup(validGroup as number),
    enabled: validGroup != null,
    refetchInterval: (q) => {
      const d = q.state.data as EvalRunGroupDetail | undefined;
      if (!d) return 2500;
      return d.status === "running" ? 2500 : false;
    },
  });

  const clearGroup = () => {
    router.push("/insights");
  };

  return (
    <div className="px-6 py-5">
      <div className="mb-6">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">Quality</div>
        <h1 className="mt-1 text-xl font-semibold">Insights</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Aggregates over recent LLM-as-a-judge runs: score mix, failure-type clusters, and eval spend. Open a
          regression batch via <span className="text-foreground">?group=</span> after running &quot;last N
          traces&quot; from Tracing.
        </p>
      </div>

      {validGroup != null ? (
        <div className="mb-6">
          {groupQ.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading regression batch…</p>
          ) : groupQ.isError ? (
            <p className="text-sm text-destructive">{(groupQ.error as Error).message}</p>
          ) : groupQ.data ? (
            <RegressionGroupCard data={groupQ.data} onClear={clearGroup} />
          ) : null}
        </div>
      ) : null}

      <div className="space-y-6">
        {summaryQ.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading summary…</p>
        ) : summaryQ.isError ? (
          <p className="text-sm text-destructive">{(summaryQ.error as Error).message}</p>
        ) : summaryQ.data ? (
          <SummaryGrid data={summaryQ.data} />
        ) : null}
      </div>
    </div>
  );
}

function pct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function SummaryGrid({ data }: { data: InsightsSummary }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="rounded-none border-border/60">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Recent eval mix</CardTitle>
          <p className="text-xs text-muted-foreground">
            Last {data.sample_size} judge runs (any status). Score buckets use completed runs with groundedness
            labels.
          </p>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary">Avg score: {data.avg_score != null ? data.avg_score.toFixed(3) : "—"}</Badge>
            <Badge variant="outline">Completed w/ score: {data.completed_with_score}</Badge>
            <Badge variant="outline">Eval spend: {formatUsd(data.total_eval_cost_usd)}</Badge>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="border border-border/60 p-3">
              <div className="text-xs text-muted-foreground">Good</div>
              <div className="text-lg font-semibold">{pct(data.good_pct)}</div>
              <div className="text-xs text-muted-foreground">{data.good_count} runs</div>
            </div>
            <div className="border border-border/60 p-3">
              <div className="text-xs text-muted-foreground">Borderline</div>
              <div className="text-lg font-semibold">{pct(data.borderline_pct)}</div>
              <div className="text-xs text-muted-foreground">{data.borderline_count} runs</div>
            </div>
            <div className="border border-border/60 p-3">
              <div className="text-xs text-muted-foreground">Bad</div>
              <div className="text-lg font-semibold">{pct(data.bad_pct)}</div>
              <div className="text-xs text-muted-foreground">{data.bad_count} runs</div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-none border-border/60">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Top failure types</CardTitle>
          <p className="text-xs text-muted-foreground">From structured failure_type on completed runs (newer judges).</p>
        </CardHeader>
        <CardContent>
          {data.top_failure_types.length === 0 ? (
            <p className="text-sm text-muted-foreground">No failure_type data yet — run new evals after upgrading the judge.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {data.top_failure_types.map((row) => (
                <li key={row.failure_type} className="flex justify-between gap-2 border-b border-border/40 py-1 last:border-0">
                  <span className="font-mono text-xs">{row.failure_type}</span>
                  <span className="text-muted-foreground">{row.count}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function RegressionGroupCard({
  data,
  onClear,
}: {
  data: EvalRunGroupDetail;
  onClear: () => void;
}) {
  return (
    <Card className="rounded-none border-border/60 border-primary/30">
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2 pb-2">
        <div>
          <CardTitle className="text-base">Regression batch</CardTitle>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{data.name}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={data.status === "completed" ? "secondary" : "outline"}>{data.status}</Badge>
          <button
            type="button"
            onClick={onClear}
            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          >
            Clear
          </button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2 text-sm">
          <Badge variant="outline">
            Jobs {data.completed_jobs}/{data.total_jobs}
          </Badge>
          <Badge variant="secondary">
            Avg compare score: {data.avg_score != null ? data.avg_score.toFixed(3) : "—"}
          </Badge>
          {data.avg_delta_score != null ? (
            <Badge variant="outline">Avg Δ groundedness: {data.avg_delta_score.toFixed(4)}</Badge>
          ) : null}
          <Badge variant="outline">Spend: {formatUsd(data.total_eval_cost_usd)}</Badge>
        </div>
        {data.pct_improved != null ? (
          <div className="grid grid-cols-3 gap-2 text-center text-sm">
            <div className="border border-border/60 p-2">
              <div className="text-[11px] text-muted-foreground">Improved</div>
              <div>{pct(data.pct_improved)}</div>
            </div>
            <div className="border border-border/60 p-2">
              <div className="text-[11px] text-muted-foreground">Unchanged</div>
              <div>{pct(data.pct_unchanged)}</div>
            </div>
            <div className="border border-border/60 p-2">
              <div className="text-[11px] text-muted-foreground">Regressed</div>
              <div>{pct(data.pct_regressed)}</div>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-2 text-center text-sm">
            <div className="border border-border/60 p-2">
              <div className="text-[11px] text-muted-foreground">Good</div>
              <div>{pct(data.good_pct)}</div>
            </div>
            <div className="border border-border/60 p-2">
              <div className="text-[11px] text-muted-foreground">Borderline</div>
              <div>{pct(data.borderline_pct)}</div>
            </div>
            <div className="border border-border/60 p-2">
              <div className="text-[11px] text-muted-foreground">Bad</div>
              <div>{pct(data.bad_pct)}</div>
            </div>
          </div>
        )}
        {data.top_failure_types.length > 0 ? (
          <div>
            <div className="mb-1 text-xs font-medium text-muted-foreground">Failure types</div>
            <ul className="flex flex-wrap gap-2">
              {data.top_failure_types.map((row) => (
                <li key={row.failure_type}>
                  <Badge variant="outline" className="font-mono text-[11px]">
                    {row.failure_type} ×{row.count}
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div>
          <div className="mb-2 text-xs font-medium text-muted-foreground">Traces in batch</div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[100px]">Trace</TableHead>
                <TableHead className="w-[72px]">Compare</TableHead>
                <TableHead className="w-[140px]">Verdict</TableHead>
                <TableHead className="min-w-[180px] max-w-[280px]">Reasoning</TableHead>
                <TableHead className="w-[56px]">Prev G</TableHead>
                <TableHead className="w-[56px]">Cur G</TableHead>
                <TableHead className="w-[56px]">Δ</TableHead>
                <TableHead className="w-[100px]">Status</TableHead>
                <TableHead className="w-[90px]">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.eval_runs.map((r) => {
                const ctx = r.context && typeof r.context === "object" ? r.context : {};
                const prevG = typeof ctx.previous_score === "number" ? ctx.previous_score : null;
                const curG = typeof ctx.current_score === "number" ? ctx.current_score : null;
                const delta = typeof ctx.delta_score === "number" ? ctx.delta_score : null;
                return (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">
                    <Link
                      href={`/traces/${encodeURIComponent(r.trace_id)}`}
                      className="text-primary underline-offset-2 hover:underline"
                    >
                      {r.trace_id.length > 6 ? `${r.trace_id.slice(0, 6)}…` : r.trace_id}
                    </Link>
                  </TableCell>
                  <TableCell className="text-xs">{r.score ?? "—"}</TableCell>
                  <TableCell className="max-w-[160px] truncate text-xs">{r.label ?? "—"}</TableCell>
                  <TableCell
                    className="max-w-[280px] truncate text-xs text-muted-foreground"
                    title={r.reasoning ?? undefined}
                  >
                    {r.reasoning?.trim() ? r.reasoning : "—"}
                  </TableCell>
                  <TableCell className="text-xs">{prevG != null ? prevG.toFixed(3) : "—"}</TableCell>
                  <TableCell className="text-xs">{curG != null ? curG.toFixed(3) : "—"}</TableCell>
                  <TableCell className="text-xs">{delta != null ? delta.toFixed(4) : "—"}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-[10px]">
                      {r.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {r.cost_usd != null ? formatUsd(r.cost_usd) : "—"}
                  </TableCell>
                </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
        {data.regression_summary?.trim() ? (
          <div className="rounded-md border border-border/60 bg-muted/25 p-3">
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Summary
            </div>
            <div className="space-y-2 text-sm leading-relaxed text-foreground">
              {data.regression_summary.split(/\n\n+/).map((para, i) => (
                <p key={i}>{para.trim()}</p>
              ))}
            </div>
          </div>
        ) : null}
        <p className="text-xs text-muted-foreground">Created {formatDateTime(data.created_at)} UTC</p>
      </CardContent>
    </Card>
  );
}
