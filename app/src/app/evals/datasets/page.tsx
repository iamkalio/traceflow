"use client";

import * as React from "react";
import { Upload } from "lucide-react";

import { AppShell } from "@/components/shell/AppShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { ImportEvalDataDialog } from "@/components/evaluation/ImportEvalDataDialog";
import { formatDateTime, formatInt } from "@/lib/format";

type DatasetRow = {
  id: string;
  name: string;
  rows: number;
  source: string;
  status: string;
  updatedAt: string;
};

const MOCK: DatasetRow[] = [
  {
    id: "1",
    name: "march_safety_batch",
    rows: 12840,
    source: "upload",
    status: "ready",
    updatedAt: "2026-03-27T10:00:00Z",
  },
  {
    id: "2",
    name: "prod_traces_sample",
    rows: 500,
    source: "trace export",
    status: "indexing",
    updatedAt: "2026-03-26T09:15:00Z",
  },
];

export default function DatasetsPage() {
  const [importOpen, setImportOpen] = React.useState(false);
  const [selectedId, setSelectedId] = React.useState<string | null>(MOCK[0]?.id ?? null);
  const selected = MOCK.find((r) => r.id === selectedId) ?? null;

  return (
    <AppShell active="evals">
      <div className="px-6 py-5">
        <EvalPageHeader
          eyebrow="Evaluation"
          title="Datasets"
          description="Eval datasets and offline batches—CSV/TSV upload, future sheet connectors, and trace-derived sets."
          actions={
            <Button type="button" size="sm" variant="outline" className="gap-1.5" onClick={() => setImportOpen(true)}>
              <Upload className="size-3.5" />
              Import data
            </Button>
          }
        />

        <EvalSplit
          list={
            <Card className="rounded-none border-border/60">
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead className="w-[100px]">Rows</TableHead>
                      <TableHead className="w-[120px]">Source</TableHead>
                      <TableHead className="w-[110px]">Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {MOCK.map((r) => (
                      <TableRow
                        key={r.id}
                        className={selectedId === r.id ? "bg-secondary/60" : "cursor-pointer"}
                        onClick={() => setSelectedId(r.id)}
                      >
                        <TableCell className="font-medium">{r.name}</TableCell>
                        <TableCell>{formatInt(r.rows)}</TableCell>
                        <TableCell className="text-muted-foreground">{r.source}</TableCell>
                        <TableCell>
                          <Badge variant={r.status === "ready" ? "secondary" : "outline"}>{r.status}</Badge>
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
                <DetailRow label="Dataset" value={selected.name} />
                <DetailRow label="Rows" value={selected.rows.toLocaleString()} />
                <DetailRow label="Source" value={selected.source} />
                <DetailRow label="Status" value={selected.status} />
                <DetailRow label="Updated" value={formatDateTime(selected.updatedAt)} />
                <p className="text-xs text-muted-foreground">
                  Schema, column mapping, and version history will appear here when the dataset API is available.
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Select a dataset to view details.</p>
            )
          }
        />

        <ImportEvalDataDialog open={importOpen} onOpenChange={setImportOpen} />
      </div>
    </AppShell>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div>{value}</div>
    </div>
  );
}
