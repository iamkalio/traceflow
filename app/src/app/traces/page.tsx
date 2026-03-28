"use client";

import { useQuery } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { ChevronRight, ExternalLink, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/shell/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TRACEFLOW_API_URL } from "@/lib/env";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  EVAL_LOCAL_KEY_QUERY_KEY,
  getEvalProviderConfiguredLocal,
  getTrace,
  listTraceEvalRuns,
  listTraces,
  runRegression,
  runTraceEval,
  type TraceListResponse,
  type TraceListItem,
  type TraceSpan,
} from "@/lib/api";

export default function TracesPage() {
  const [q, setQ] = React.useState("");
  const [status, setStatus] = React.useState<string>("");
  const [selectedTraceId, setSelectedTraceId] = React.useState<string | null>(
    null,
  );
  const [selectedSpanId, setSelectedSpanId] = React.useState<string | null>(
    null,
  );
  const [selectedTraceIds, setSelectedTraceIds] = React.useState<Set<string>>(
    new Set(),
  );
  const [pageSize, setPageSize] = React.useState<number>(50);
  const [cursor, setCursor] = React.useState<string | null>(null);
  const [cursorStack, setCursorStack] = React.useState<Array<string | null>>([
    null,
  ]);
  const [pageIndex, setPageIndex] = React.useState<number>(0);
  const qc = useQueryClient();
  const router = useRouter();
  const [runEvalLoading, setRunEvalLoading] = React.useState(false);
  const [regressionN, setRegressionN] = React.useState(10);
  const [regressionLoading, setRegressionLoading] = React.useState(false);

  const query = useQuery({
    queryKey: ["traces", { q, status, pageSize, cursor }],
    queryFn: () =>
      listTraces({
        limit: pageSize,
        cursor: cursor ?? undefined,
        q: q || undefined,
        status: status || undefined,
      }),
  });
  const items = React.useMemo(
    () => query.data?.items ?? [],
    [query.data?.items],
  );
  const nextCursor = query.data?.next_cursor ?? null;
  const pageTraceIds = React.useMemo(
    () => items.map((t) => t.trace_id),
    [items],
  );
  const allPageRowsSelected =
    pageTraceIds.length > 0 &&
    pageTraceIds.every((id) => selectedTraceIds.has(id));
  const somePageRowsSelected =
    pageTraceIds.some((id) => selectedTraceIds.has(id)) && !allPageRowsSelected;

  const detailQ = useQuery({
    queryKey: ["trace", selectedTraceId],
    queryFn: () => getTrace(selectedTraceId as string),
    enabled: Boolean(selectedTraceId),
  });

  const evalRunsQ = useQuery({
    queryKey: ["trace-eval-runs", selectedTraceId],
    queryFn: () => listTraceEvalRuns(selectedTraceId as string),
    enabled: Boolean(selectedTraceId),
    refetchInterval: (q) => {
      const rows = q.state.data;
      if (!Array.isArray(rows) || !rows.length) return false;
      return rows.some((r) => r.status === "queued" || r.status === "running")
        ? 2500
        : false;
    },
  });

  const spans = React.useMemo(() => detailQ.data ?? [], [detailQ.data]);
  const evalRuns = React.useMemo(() => evalRunsQ.data ?? [], [evalRunsQ.data]);
  const childrenIndex = React.useMemo(() => buildChildrenIndex(spans), [spans]);
  const roots = React.useMemo(
    () => spans.filter((s) => !s.parent_span_id),
    [spans],
  );

  React.useEffect(() => {
    if (!spans.length) {
      setSelectedSpanId(null);
      return;
    }
    setSelectedSpanId((curr) =>
      curr && spans.some((s) => s.span_id === curr) ? curr : spans[0].span_id,
    );
  }, [spans]);

  React.useEffect(() => {
    // Reset pagination whenever filters change.
    setCursor(null);
    setCursorStack([null]);
    setPageIndex(0);
    setSelectedTraceId(null);
    setSelectedSpanId(null);
  }, [q, status, pageSize]);

  React.useEffect(() => {
    // Live updates: subscribe to new traces.
    // Only auto-apply on the "first page" (cursor=null) so pagination stays stable.
    if (cursor) return;

    const url = TRACEFLOW_API_URL.replace(/^http/, "ws") + "/v1/ws/traces";
    const ws = new WebSocket(url);

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as {
          type?: string;
          item?: TraceListItem;
        };
        if (msg.type !== "trace.upsert" || !msg.item) return;
        const incoming = msg.item;

        // Apply basic client-side filter matching.
        if (status && incoming.status !== status) return;
        if (q) {
          const qq = q.toLowerCase();
          const hay =
            `${incoming.trace_id} ${incoming.name ?? ""} ${incoming.input ?? ""} ${incoming.output ?? ""}`.toLowerCase();
          if (!hay.includes(qq)) return;
        }

        qc.setQueryData<TraceListResponse>(
          ["traces", { q, status, pageSize, cursor }],
          (prev) => {
            const curr = prev?.items ?? [];
            const prevRow = curr.find((t) => t.trace_id === incoming.trace_id);
            const merged: TraceListItem = {
              ...incoming,
              eval_status: incoming.eval_status ?? prevRow?.eval_status ?? null,
              eval_score: incoming.eval_score ?? prevRow?.eval_score ?? null,
              eval_label: incoming.eval_label ?? prevRow?.eval_label ?? null,
            };
            const nextItems = [
              merged,
              ...curr.filter((t) => t.trace_id !== incoming.trace_id),
            ].slice(0, pageSize);
            const next_cursor = nextItems.length
              ? nextItems[nextItems.length - 1].last_seen
              : (prev?.next_cursor ?? null);
            return { items: nextItems, next_cursor };
          },
        );
      } catch {
        // ignore
      }
    };

    return () => {
      ws.close();
    };
  }, [qc, cursor, pageSize, q, status]);

  const selectedSpan = selectedSpanId
    ? (spans.find((s) => s.span_id === selectedSpanId) ?? null)
    : null;

  const providerQ = useQuery({
    queryKey: EVAL_LOCAL_KEY_QUERY_KEY,
    queryFn: () => getEvalProviderConfiguredLocal(),
  });
  const evalConfigured = providerQ.data?.configured ?? false;

  return (
    <AppShell active="traces">
      <div className="overflow-x-hidden px-6 py-5">
        <div className="flex items-end justify-between gap-6">
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              Tracing
            </div>
            <h1 className="mt-1 text-xl font-semibold">Traces</h1>
          </div>
          <div className="flex items-center gap-3">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search trace id, name, prompt..."
              className="w-[320px]"
            />
            <Select
              value={status || "all"}
              onValueChange={(v) => setStatus(!v || v === "all" ? "" : v)}
            >
              <SelectTrigger className="w-[140px]" aria-label="Status filter">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="success">Success</SelectItem>
                <SelectItem value="error">Error</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {!evalConfigured ? (
          <div className="mt-4 rounded-none border border-border/60 bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
            Add your OpenAI API key in{" "}
            <Link
              href="/settings"
              className="font-medium text-foreground underline underline-offset-2"
            >
              Settings
            </Link>{" "}
            to run evals from the browser.
          </div>
        ) : (
          <div className="mt-4 flex flex-wrap items-end gap-4">
            <div className="space-y-1">
              <div className="text-xs uppercase tracking-wider text-muted-foreground">Regression</div>
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  type="number"
                  min={1}
                  max={500}
                  className="w-[76px]"
                  value={regressionN}
                  onChange={(e) => {
                    const v = Number.parseInt(e.target.value, 10);
                    if (Number.isNaN(v)) return;
                    setRegressionN(Math.max(1, Math.min(500, v)));
                  }}
                  aria-label="Number of traces for regression"
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={regressionLoading}
                  onClick={async () => {
                    setRegressionLoading(true);
                    try {
                      const out = await runRegression({
                        n: regressionN,
                        evalName: "regression_compare_v1",
                      });
                      await qc.invalidateQueries({ queryKey: ["eval-runs-global"] });
                      await qc.invalidateQueries({ queryKey: ["insights-summary"] });
                      await qc.invalidateQueries({ queryKey: ["traces"] });
                      router.push(`/insights?group=${out.group_id}`);
                    } finally {
                      setRegressionLoading(false);
                    }
                  }}
                >
                  {regressionLoading ? "Queueing…" : `Run regression (last ${regressionN})`}
                </Button>
                <Link
                  href="/insights"
                  className={cn(
                    buttonVariants({ variant: "ghost", size: "sm" }),
                    "text-muted-foreground",
                  )}
                >
                  Insights
                </Link>
              </div>
              <p className="max-w-xl text-xs text-muted-foreground">
                Compares current vs previous model output when a snapshot exists; if not, runs groundedness once to
                capture a baseline, then compare on the next run. Verdicts: improved / unchanged / regressed.
              </p>
            </div>
          </div>
        )}

        <div className="mt-5 grid grid-cols-4 gap-3">
          <Kpi label="Traces" value={query.data ? String(items.length) : "—"} />
          <Kpi label="Span count" value="—" />
          <Kpi label="Latency p50" value="—" />
          <Kpi label="Cost" value="—" />
        </div>

        <div className="mt-5">
          <Card className="rounded-none border-border/60 ring-0">
            <CardHeader className="rounded-none">
              <CardTitle>All Traces</CardTitle>
            </CardHeader>
            <CardContent className="max-w-full pt-0">
              <div className="w-full max-w-full overflow-x-hidden">
                <Table className="w-full table-fixed">
                  <TableHeader className="[&_tr]:border-b-0">
                    <TableRow className="border-b-0">
                      <TableHead className="sticky left-0 z-20 w-10 min-w-10 max-w-10 bg-card">
                        <Checkbox
                          checked={allPageRowsSelected || somePageRowsSelected}
                          aria-label="Select all traces on this page"
                          onCheckedChange={(checked) => {
                            setSelectedTraceIds((prev) => {
                              const next = new Set(prev);
                              if (checked) {
                                pageTraceIds.forEach((id) => next.add(id));
                              } else {
                                pageTraceIds.forEach((id) => next.delete(id));
                              }
                              return next;
                            });
                          }}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Input</TableHead>
                      <TableHead>Output</TableHead>
                      <TableHead>Eval</TableHead>
                      <TableHead className="w-[200px] min-w-[200px] pr-6">
                        Start time
                      </TableHead>
                      <TableHead className="w-[120px] min-w-[120px] pl-2">
                        Latency
                      </TableHead>
                      <TableHead className="w-[140px] min-w-[140px] pr-6">
                        Tokens
                      </TableHead>
                      <TableHead className="w-[120px] min-w-[120px] pl-2">
                        Cost
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {query.isLoading ? (
                      <TableRow className="border-b-0">
                        <TableCell
                          colSpan={10}
                          className="py-8 text-muted-foreground"
                        >
                          Loading...
                        </TableCell>
                      </TableRow>
                    ) : query.isError ? (
                      <TableRow className="border-b-0">
                        <TableCell
                          colSpan={10}
                          className="py-8 text-destructive"
                        >
                          {(query.error as Error).message}
                        </TableCell>
                      </TableRow>
                    ) : items.length === 0 ? (
                      <TableRow className="border-b-0">
                        <TableCell
                          colSpan={10}
                          className="py-10 text-muted-foreground"
                        >
                          No traces yet. Send OTLP spans to `POST /v1/traces`.
                        </TableCell>
                      </TableRow>
                    ) : (
                      items.map((t) => (
                        <TableRow
                          key={t.trace_id}
                          className="cursor-pointer border-b border-white/20"
                          onClick={() => setSelectedTraceId(t.trace_id)}
                        >
                          <TableCell
                            className="sticky left-0 z-10 w-10 min-w-10 max-w-10 bg-card"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Checkbox
                              checked={selectedTraceIds.has(t.trace_id)}
                              aria-label={`Select trace ${t.trace_id}`}
                              onCheckedChange={(checked) => {
                                setSelectedTraceIds((prev) => {
                                  const next = new Set(prev);
                                  if (checked) {
                                    next.add(t.trace_id);
                                  } else {
                                    next.delete(t.trace_id);
                                  }
                                  return next;
                                });
                              }}
                            />
                          </TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                t.status === "error"
                                  ? "destructive"
                                  : "secondary"
                              }
                            >
                              {t.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="max-w-[220px] truncate">
                            {t.name || "—"}
                          </TableCell>
                          <TableCell className="max-w-[320px] truncate">
                            {t.input || "—"}
                          </TableCell>
                          <TableCell className="max-w-[320px] truncate">
                            {t.output || "—"}
                          </TableCell>
                          <TableCell>
                            <EvalStatusCell
                              status={t.eval_status}
                              score={t.eval_score}
                              label={t.eval_label}
                            />
                          </TableCell>
                          <TableCell className="whitespace-nowrap pr-6">
                            {t.start_time
                              ? new Date(t.start_time).toLocaleString()
                              : "—"}
                          </TableCell>
                          <TableCell className="whitespace-nowrap pl-2">
                            {fmtMs(t.latency_ms)}
                          </TableCell>
                          <TableCell className="whitespace-nowrap pr-6">
                            {t.total_tokens ?? "—"}
                          </TableCell>
                          <TableCell className="whitespace-nowrap pl-2">
                            {fmtUsd(t.total_cost_usd)}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
            <CardFooter className="flex items-center justify-between rounded-none p-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Rows</span>
                <Select
                  value={String(pageSize)}
                  onValueChange={(v) => setPageSize(Number(v))}
                >
                  <SelectTrigger size="sm" className="w-[90px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="25">25</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    if (pageIndex <= 0) return;
                    const prev = cursorStack[pageIndex - 1] ?? null;
                    setCursor(prev);
                    setPageIndex(pageIndex - 1);
                  }}
                  disabled={pageIndex <= 0 || query.isFetching}
                >
                  Prev
                </Button>
                <div className="text-xs text-muted-foreground">
                  Page {pageIndex + 1}
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    if (!nextCursor) return;
                    setCursor(nextCursor);
                    setCursorStack((s) => [
                      ...s.slice(0, pageIndex + 1),
                      nextCursor,
                    ]);
                    setPageIndex(pageIndex + 1);
                  }}
                  disabled={!nextCursor || query.isFetching}
                >
                  Next
                </Button>
              </div>
            </CardFooter>
          </Card>
        </div>
      </div>
      {selectedTraceId ? (
        <div className="fixed inset-0 z-50">
          <button
            type="button"
            aria-label="Close trace details"
            className="absolute inset-0 bg-black/60"
            onClick={() => {
              setSelectedTraceId(null);
              setSelectedSpanId(null);
            }}
          />
          <div
            className="absolute top-3 right-3 bottom-3 w-[70vw] overflow-hidden rounded-none border bg-background shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex h-14 items-center justify-between gap-3 border-b px-4">
              <div className="min-w-0">
                <div className="text-xs uppercase tracking-wider text-muted-foreground">
                  Trace
                </div>
                <div className="truncate font-mono text-sm">
                  {selectedTraceId}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Link
                  href={`/traces/${encodeURIComponent(selectedTraceId)}`}
                  className={cn(
                    buttonVariants({ variant: "ghost", size: "sm" }),
                  )}
                >
                  <ExternalLink className="mr-1 size-3.5" />
                  Full page
                </Link>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => {
                    setSelectedTraceId(null);
                    setSelectedSpanId(null);
                  }}
                >
                  <X className="size-4" />
                </Button>
              </div>
            </div>

            <div className="grid h-[calc(100%-56px)] grid-cols-1 gap-0 lg:grid-cols-[340px_minmax(0,1fr)]">
              <div className="overflow-auto border-b p-3 lg:border-r lg:border-b-0">
                <div className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">
                  Spans
                </div>
                {detailQ.isLoading ? (
                  <div className="text-sm text-muted-foreground">
                    Loading...
                  </div>
                ) : detailQ.isError ? (
                  <div className="text-sm text-destructive">
                    {(detailQ.error as Error).message}
                  </div>
                ) : roots.length === 0 ? (
                  <div className="text-sm text-muted-foreground">
                    No spans found.
                  </div>
                ) : (
                  roots.map((root) => (
                    <SpanTreeNode
                      key={root.span_id}
                      span={root}
                      depth={0}
                      childrenIndex={childrenIndex}
                      selectedSpanId={selectedSpanId}
                      onSelectSpan={setSelectedSpanId}
                    />
                  ))
                )}
              </div>

              <div className="overflow-auto p-4">
                <div className="mb-4 flex flex-col gap-3 border-b border-border/60 pb-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-xs uppercase tracking-wider text-muted-foreground">
                      Evaluation
                    </div>
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      {!evalConfigured ? (
                        <Link
                          href="/settings"
                          className="text-xs text-muted-foreground hover:underline"
                        >
                          Connect OpenAI key in Settings
                        </Link>
                      ) : (
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={
                            !selectedTraceId || runEvalLoading || !evalConfigured
                          }
                          onClick={async () => {
                            if (!selectedTraceId) return;
                            setRunEvalLoading(true);
                            try {
                              await runTraceEval(selectedTraceId, "groundedness");
                              await qc.invalidateQueries({
                                queryKey: ["trace-eval-runs", selectedTraceId],
                              });
                              await qc.invalidateQueries({
                                queryKey: ["eval-runs-global"],
                              });
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
                        href={`/evals/llm-as-a-judge?trace=${encodeURIComponent(selectedTraceId ?? "")}`}
                        className={cn(
                          buttonVariants({ variant: "outline", size: "sm" }),
                          "gap-1",
                        )}
                      >
                        LLM-as-a-Judge
                        <ChevronRight className="size-3.5" />
                      </Link>
                    </div>
                  </div>
                  {evalRunsQ.isLoading ? (
                    <p className="text-xs text-muted-foreground">
                      Loading eval status…
                    </p>
                  ) : evalRunsQ.isError ? (
                    <p className="text-xs text-destructive">
                      {(evalRunsQ.error as Error).message}
                    </p>
                  ) : evalRuns.length === 0 ? (
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      No judge runs yet. Run eval above, then open{" "}
                      <Link
                        href={`/evals/llm-as-a-judge?trace=${encodeURIComponent(selectedTraceId ?? "")}`}
                        className="font-medium text-foreground underline underline-offset-2"
                      >
                        LLM-as-a-Judge
                      </Link>{" "}
                      for reasoning, score, and prompt/context improvements.
                    </p>
                  ) : (
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      Latest run:{" "}
                      <span className="font-medium text-foreground">
                        {evalRuns[0].status}
                      </span>
                      {evalRuns[0].score != null ? (
                        <>
                          {" "}
                          · score{" "}
                          <span className="text-foreground">{evalRuns[0].score}</span>
                        </>
                      ) : null}
                      {evalRuns[0].label ? (
                        <>
                          {" "}
                          ·{" "}
                          <span className="text-foreground">{evalRuns[0].label}</span>
                        </>
                      ) : null}
                      {evalRuns[0].created_at ? (
                        <> · {formatDateTime(evalRuns[0].created_at)}</>
                      ) : null}
                      . Full details in{" "}
                      <Link
                        href={`/evals/llm-as-a-judge?trace=${encodeURIComponent(selectedTraceId ?? "")}`}
                        className="font-medium text-foreground underline underline-offset-2"
                      >
                        LLM-as-a-Judge
                      </Link>
                      .
                    </p>
                  )}
                </div>

                {!selectedSpan ? (
                  <div className="text-sm text-muted-foreground">
                    Select a span to inspect.
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-base font-semibold">
                        {selectedSpan.name || "Span"}
                      </h3>
                      <Badge variant="secondary">{selectedSpan.status}</Badge>
                    </div>
                    <KeyValue
                      label="Span ID"
                      value={selectedSpan.span_id}
                      mono
                    />
                    <KeyValue label="Model" value={selectedSpan.model || "—"} />
                    <KeyValue
                      label="Latency"
                      value={fmtMs(selectedSpan.latency_ms)}
                    />
                    <KeyValue
                      label="Tokens"
                      value={fmtNum(selectedSpan.total_tokens)}
                    />
                    <KeyValue
                      label="Cost"
                      value={fmtUsd(selectedSpan.cost_usd)}
                    />

                    <TextBlock title="Input" text={selectedSpan.prompt ?? ""} />
                    <TextBlock
                      title="Output"
                      text={selectedSpan.completion ?? ""}
                    />
                    <JsonBlock title="Context" value={selectedSpan.context} />
                    <JsonBlock
                      title="Attributes"
                      value={selectedSpan.attributes}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}

function EvalStatusCell({
  status,
  score,
  label,
}: {
  status?: string | null;
  score?: number | null;
  label?: string | null;
}) {
  const s = (status || "pending").toLowerCase();
  const variant =
    s === "failed"
      ? "destructive"
      : s === "completed" || s === "running" || s === "queued"
        ? "secondary"
        : "outline";
  const short =
    s === "completed"
      ? "Done"
      : s === "pending"
        ? "Pending"
        : s === "queued"
          ? "Queued"
          : s === "running"
            ? "Running"
            : s === "skipped"
              ? "Skipped"
              : s === "failed"
                ? "Failed"
                : s;
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <Badge className="w-fit shrink-0" variant={variant}>
        {short}
      </Badge>
      {s === "completed" && (score != null || (label && label.length > 0)) ? (
        <span
          className="truncate text-[11px] text-muted-foreground"
          title={[score, label].filter(Boolean).join(" · ")}
        >
          {score != null ? String(score) : ""}
          {score != null && label ? " · " : ""}
          {label ?? ""}
        </span>
      ) : null}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="text-lg font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}

function SpanTreeNode({
  span,
  depth,
  childrenIndex,
  selectedSpanId,
  onSelectSpan,
}: {
  span: TraceSpan;
  depth: number;
  childrenIndex: Map<string, TraceSpan[]>;
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
}) {
  const kids = childrenIndex.get(span.span_id) ?? [];
  const selected = selectedSpanId === span.span_id;

  return (
    <div>
      <button
        type="button"
        onClick={() => onSelectSpan(span.span_id)}
        className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm ${
          selected ? "bg-secondary" : "hover:bg-accent"
        }`}
        style={{ marginLeft: `${depth * 10}px` }}
      >
        <div className="min-w-0">
          <div className="truncate">{span.name || "span"}</div>
          <div className="truncate font-mono text-[11px] text-muted-foreground">
            {span.span_id}
          </div>
        </div>
        <div className="text-xs text-muted-foreground">
          {fmtMs(span.latency_ms)}
        </div>
      </button>
      {kids.length > 0 ? (
        <div className="mt-1 space-y-1">
          {kids.map((k) => (
            <SpanTreeNode
              key={k.span_id}
              span={k}
              depth={depth + 1}
              childrenIndex={childrenIndex}
              selectedSpanId={selectedSpanId}
              onSelectSpan={onSelectSpan}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function buildChildrenIndex(spans: TraceSpan[]) {
  const map = new Map<string, TraceSpan[]>();
  for (const s of spans) {
    if (!s.parent_span_id) continue;
    const list = map.get(s.parent_span_id) ?? [];
    list.push(s);
    map.set(s.parent_span_id, list);
  }
  return map;
}

function KeyValue({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className={mono ? "font-mono text-xs" : "text-sm"}>{value}</div>
    </div>
  );
}

function TextBlock({ title, text }: { title: string; text: string }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <pre className="overflow-auto whitespace-pre-wrap wrap-break-word text-sm">
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
        <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <pre className="overflow-auto whitespace-pre-wrap wrap-break-word font-mono text-xs">
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
