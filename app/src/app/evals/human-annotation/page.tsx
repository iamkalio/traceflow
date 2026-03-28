"use client";

import * as React from "react";

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
import { formatDateTime } from "@/lib/format";

type AnnotationRow = {
  id: string;
  annotator: string;
  traceId: string;
  spanId: string;
  label: string;
  status: string;
  updatedAt: string;
};

const MOCK: AnnotationRow[] = [
  {
    id: "1",
    annotator: "you@example.com",
    traceId: "7c9e2f1a4b5083d6",
    spanId: "a1b2c3d4",
    label: "helpful",
    status: "approved",
    updatedAt: "2026-03-27T11:00:00Z",
  },
  {
    id: "2",
    annotator: "reviewer_2",
    traceId: "8d1a0e3c5f6294b7",
    spanId: "e5f6g7h8",
    label: "needs fix",
    status: "draft",
    updatedAt: "2026-03-26T18:30:00Z",
  },
];

export default function HumanAnnotationPage() {
  const [selectedId, setSelectedId] = React.useState<string | null>(MOCK[0]?.id ?? null);
  const selected = MOCK.find((r) => r.id === selectedId) ?? null;

  return (
    <AppShell active="evals">
      <div className="px-6 py-5">
        <EvalPageHeader
          eyebrow="Evaluation"
          title="Human Annotation"
          description="Human labels and review queues for traces and spans. Export or sync with annotation tools later."
        />

        <EvalSplit
          list={
            <Card className="rounded-none border-border/60">
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Annotator</TableHead>
                      <TableHead>Trace</TableHead>
                      <TableHead>Span</TableHead>
                      <TableHead>Label</TableHead>
                      <TableHead className="w-[100px]">Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {MOCK.map((r) => (
                      <TableRow
                        key={r.id}
                        className={selectedId === r.id ? "bg-secondary/60" : "cursor-pointer"}
                        onClick={() => setSelectedId(r.id)}
                      >
                        <TableCell className="max-w-[120px] truncate text-sm">{r.annotator}</TableCell>
                        <TableCell className="max-w-[140px] truncate font-mono text-xs">{r.traceId}</TableCell>
                        <TableCell className="font-mono text-xs">{r.spanId}</TableCell>
                        <TableCell>{r.label}</TableCell>
                        <TableCell>
                          <Badge variant={r.status === "approved" ? "secondary" : "outline"}>{r.status}</Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          }
          detail={
            selected ? (
              <div className="space-y-4 text-sm">
                <DetailRow label="Annotator" value={selected.annotator} />
                <DetailRow label="Trace ID" value={selected.traceId} mono />
                <DetailRow label="Span ID" value={selected.spanId} mono />
                <DetailRow label="Label" value={selected.label} />
                <DetailRow label="Status" value={selected.status} />
                <DetailRow label="Updated" value={formatDateTime(selected.updatedAt)} />
                <p className="text-xs text-muted-foreground">
                  Free-text notes and attachment metadata will show here when the workflow is connected.
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Select a row to view details.</p>
            )
          }
        />
      </div>
    </AppShell>
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
