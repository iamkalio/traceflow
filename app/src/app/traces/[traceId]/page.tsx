"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import * as React from "react";

import { AppShell } from "@/components/shell/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  EVAL_LOCAL_KEY_QUERY_KEY,
  getEvalProviderConfiguredLocal,
  getTrace,
  listTraceEvalRuns,
  runTraceEval,
  type TraceSpan,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ChevronRight } from "lucide-react";

export default function TraceDetailPage({
  params,
}: {
  params: Promise<{ traceId: string }>;
}) {
  const { traceId } = React.use(params);
  const search = useSearchParams();
  const selectedFromUrl = search.get("span");
  const qc = useQueryClient();
  const [runEvalLoading, setRunEvalLoading] = React.useState(false);

  const spansQ = useQuery({
    queryKey: ["trace", traceId],
    queryFn: () => getTrace(traceId),
  });

  const evalRunsQ = useQuery({
    queryKey: ["trace-eval-runs", traceId],
    queryFn: () => listTraceEvalRuns(traceId),
    enabled: spansQ.isSuccess,
    refetchInterval: (q) => {
      const rows = q.state.data;
      if (!Array.isArray(rows) || !rows.length) return false;
      return rows.some((r) => r.status === "queued" || r.status === "running") ? 2500 : false;
    },
  });

  const providerQ = useQuery({
    queryKey: EVAL_LOCAL_KEY_QUERY_KEY,
    queryFn: () => getEvalProviderConfiguredLocal(),
  });
  const evalConfigured = providerQ.data?.configured ?? false;

  const spans = React.useMemo(() => spansQ.data ?? [], [spansQ.data]);
  const evalRuns = React.useMemo(() => evalRunsQ.data ?? [], [evalRunsQ.data]);
  const defaultSpanId = spans[0]?.span_id ?? null;
  const selectedSpanId = selectedFromUrl ?? defaultSpanId;
  const selectedSpan = spans.find((s) => s.span_id === selectedSpanId) ?? null;

  const spanChildren = React.useMemo(() => buildChildrenIndex(spans), [spans]);
  const roots = React.useMemo(() => spans.filter((s) => !s.parent_span_id), [spans]);

  return (
    <AppShell active="traces">
      <div className="px-6 py-5">
        <div className="flex items-end justify-between">
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground">Trace</div>
            <h1 className="mt-1 font-mono text-sm">{traceId}</h1>
          </div>
        </div>

        {spansQ.isLoading ? (
          <div className="mt-6 text-sm text-muted-foreground">Loading trace...</div>
        ) : spansQ.isError ? (
          <div className="mt-6 text-sm text-destructive">{(spansQ.error as Error).message}</div>
        ) : (
          <div className="mt-6 grid grid-cols-[340px_1fr_420px] gap-4">
            <Panel title="Spans">
              <div className="space-y-1">
                {roots.length === 0 ? (
                  <div className="text-sm text-muted-foreground">No spans found.</div>
                ) : (
                  roots.map((r) => (
                    <SpanNode
                      key={r.span_id}
                      traceId={traceId}
                      span={r}
                      selectedSpanId={selectedSpanId}
                      childrenIndex={spanChildren}
                      depth={0}
                    />
                  ))
                )}
              </div>
            </Panel>

            <Panel title={selectedSpan ? selectedSpan.name || "Span" : "Span"}>
              {!selectedSpan ? (
                <div className="text-sm text-muted-foreground">Select a span to inspect.</div>
              ) : (
                <div className="space-y-4">
                  <KeyValue label="Span ID" value={selectedSpan.span_id} mono />
                  <KeyValue label="Model" value={selectedSpan.model || "—"} />
                  <KeyValue label="Latency" value={fmtMs(selectedSpan.latency_ms)} />
                  <KeyValue label="Tokens" value={fmtNum(selectedSpan.total_tokens)} />
                  <KeyValue label="Cost" value={fmtUsd(selectedSpan.cost_usd)} />

                  <div className="grid grid-cols-2 gap-3">
                    <TextBlock title="Input" text={selectedSpan.prompt ?? ""} />
                    <TextBlock title="Output" text={selectedSpan.completion ?? ""} />
                  </div>

                  <JsonBlock title="Context" value={selectedSpan.context} />
                  <JsonBlock title="Attributes" value={selectedSpan.attributes} />
                </div>
              )}
            </Panel>

            <Panel title="Evals">
              <div className="space-y-4">
                <div className="flex flex-col gap-3 border-b border-border/60 pb-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                      LLM-as-a-Judge
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {!evalConfigured ? (
                        <Link href="/settings" className="text-xs text-muted-foreground hover:underline">
                          Connect OpenAI key
                        </Link>
                      ) : (
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={runEvalLoading}
                          onClick={async () => {
                            setRunEvalLoading(true);
                            try {
                              await runTraceEval(traceId, "groundedness");
                              await qc.invalidateQueries({ queryKey: ["trace-eval-runs", traceId] });
                              await qc.invalidateQueries({ queryKey: ["eval-runs-global"] });
                              await qc.invalidateQueries({ queryKey: ["insights-summary"] });
                              await qc.invalidateQueries({ queryKey: ["traces"] });
                            } finally {
                              setRunEvalLoading(false);
                            }
                          }}
                        >
                          {runEvalLoading ? "Running…" : "Run eval"}
                        </Button>
                      )}
                      <Link
                        href={`/evals/llm-as-a-judge?trace=${encodeURIComponent(traceId)}`}
                        className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-1")}
                      >
                        Open tab
                        <ChevronRight className="size-3.5" />
                      </Link>
                    </div>
                  </div>
                  {evalRunsQ.isLoading ? (
                    <p className="text-xs text-muted-foreground">Loading eval status…</p>
                  ) : evalRunsQ.isError ? (
                    <p className="text-xs text-destructive">{(evalRunsQ.error as Error).message}</p>
                  ) : evalRuns.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      No runs yet. Use Run eval, then{" "}
                      <Link
                        href={`/evals/llm-as-a-judge?trace=${encodeURIComponent(traceId)}`}
                        className="font-medium underline underline-offset-2"
                      >
                        LLM-as-a-Judge
                      </Link>{" "}
                      for score, reasoning, and improvements.
                    </p>
                  ) : (
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      Latest:{" "}
                      <span className="font-medium text-foreground">{evalRuns[0].status}</span>
                      {evalRuns[0].score != null ? (
                        <> · score {evalRuns[0].score}</>
                      ) : null}
                      {evalRuns[0].label ? <> · {evalRuns[0].label}</> : null}
                      {evalRuns[0].created_at ? <> · {formatDateTime(evalRuns[0].created_at)}</> : null}.
                      Details in{" "}
                      <Link
                        href={`/evals/llm-as-a-judge?trace=${encodeURIComponent(traceId)}`}
                        className="font-medium text-foreground underline underline-offset-2"
                      >
                        LLM-as-a-Judge
                      </Link>
                      .
                    </p>
                  )}
                </div>
              </div>
            </Panel>
          </div>
        )}
      </div>
    </AppShell>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="rounded-none">
      <CardHeader>
        <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <Separator />
      <CardContent className="pt-4">{children}</CardContent>
    </Card>
  );
}

function SpanNode({
  traceId,
  span,
  selectedSpanId,
  childrenIndex,
  depth,
}: {
  traceId: string;
  span: TraceSpan;
  selectedSpanId: string | null;
  childrenIndex: Map<string, TraceSpan[]>;
  depth: number;
}) {
  const kids = childrenIndex.get(span.span_id) ?? [];
  const isSelected = selectedSpanId === span.span_id;

  return (
    <div>
      <a
        href={`/traces/${traceId}?span=${encodeURIComponent(span.span_id)}`}
        className={`flex items-center justify-between rounded-md px-2 py-1.5 text-sm ${
          isSelected ? "bg-secondary" : "hover:bg-accent"
        }`}
        style={{ marginLeft: `${depth * 10}px` }}
      >
        <div className="min-w-0">
          <div className="truncate">{span.name || "span"}</div>
          <div className="truncate font-mono text-[11px] text-muted-foreground">{span.span_id}</div>
        </div>
        <div className="text-xs text-muted-foreground">{fmtMs(span.latency_ms)}</div>
      </a>
      {kids.length ? (
        <div className="mt-1 space-y-1">
          {kids.map((k) => (
            <SpanNode
              key={k.span_id}
              traceId={traceId}
              span={k}
              selectedSpanId={selectedSpanId}
              childrenIndex={childrenIndex}
              depth={depth + 1}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function buildChildrenIndex(spans: TraceSpan[]) {
  const m = new Map<string, TraceSpan[]>();
  for (const s of spans) {
    if (!s.parent_span_id) continue;
    const arr = m.get(s.parent_span_id) ?? [];
    arr.push(s);
    m.set(s.parent_span_id, arr);
  }
  return m;
}

function KeyValue({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={mono ? "font-mono text-xs" : "text-sm"}>
        {value}
      </div>
    </div>
  );
}

function TextBlock({ title, text }: { title: string; text: string }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <Separator />
      <CardContent className="pt-3">
      <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap wrap-break-word text-sm">
        {text || "—"}
      </pre>
      </CardContent>
    </Card>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <Separator />
      <CardContent className="pt-3">
      <pre className="max-h-[280px] overflow-auto whitespace-pre-wrap wrap-break-word font-mono text-xs">
        {value == null ? "—" : JSON.stringify(value, null, 2)}
      </pre>
      </CardContent>
    </Card>
  );
}

function fmtMs(v: number | null) {
  if (v == null) return "—";
  return `${v}ms`;
}
function fmtUsd(v: number | null) {
  if (v == null) return "—";
  return `$${v.toFixed(4)}`;
}
function fmtNum(v: number | null) {
  if (v == null) return "—";
  return String(v);
}

