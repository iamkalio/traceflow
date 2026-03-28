"use client";

import * as React from "react";
import { FileSpreadsheet, Link2, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function splitDelimitedRow(line: string, delimiter: "," | "\t") {
  if (delimiter === "\t") return line.split("\t").map((c) => c.trim());
  return line.split(",").map((c) => c.replace(/^"|"$/g, "").trim());
}

function peekDelimiter(firstLine: string): "," | "\t" {
  const tabs = (firstLine.match(/\t/g) ?? []).length;
  const commas = (firstLine.match(/,/g) ?? []).length;
  if (tabs > 0 && tabs >= commas) return "\t";
  return ",";
}

function parseDelimitedPreview(text: string, maxPreviewRows: number) {
  const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
  if (lines.length === 0) {
    return {
      delimiter: "," as const,
      headers: [] as string[],
      rows: [] as string[][],
      rowCount: 0,
    };
  }
  const delimiter = peekDelimiter(lines[0]);
  const headers = splitDelimitedRow(lines[0], delimiter);
  const body = lines.slice(1);
  const rowCount = body.length;
  const rows = body.slice(0, maxPreviewRows).map((ln) => splitDelimitedRow(ln, delimiter));
  return { delimiter, headers, rows, rowCount };
}

export function ImportEvalDataDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [uploadState, setUploadState] = React.useState<{
    name: string;
    headers: string[];
    rows: string[][];
    rowCount: number;
    delimiter: string;
  } | null>(null);

  const onPickFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (
      !lower.endsWith(".csv") &&
      !lower.endsWith(".tsv") &&
      file.type !== "text/csv" &&
      file.type !== "text/tab-separated-values"
    ) {
      setUploadState(null);
      return;
    }
    const text = await file.text();
    const { delimiter, headers, rows, rowCount } = parseDelimitedPreview(text, 8);
    setUploadState({
      name: file.name,
      headers,
      rows,
      rowCount,
      delimiter: delimiter === "\t" ? "tab" : "comma",
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Import eval data</DialogTitle>
          <DialogDescription>
            Connect an external source or upload a file. Preview is local to your browser; API-backed imports are not
            wired yet.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-6 px-6 pb-6">
          <section className="space-y-3">
            <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Connect third parties</div>
            <div className="flex flex-col gap-2">
              <Button type="button" variant="secondary" className="h-auto justify-start gap-3 py-3" disabled>
                <FileSpreadsheet className="size-4 shrink-0 opacity-70" />
                <span className="flex flex-1 flex-col items-start gap-0.5 text-left">
                  <span className="flex items-center gap-2 font-medium">
                    Google Sheets
                    <Badge variant="outline" className="text-[10px] font-normal">
                      Soon
                    </Badge>
                  </span>
                  <span className="text-xs font-normal text-muted-foreground">OAuth and pick a workbook range for eval rows.</span>
                </span>
              </Button>
              <Button type="button" variant="ghost" className="h-auto justify-start gap-3 border border-dashed border-border py-3" disabled>
                <Link2 className="size-4 shrink-0 opacity-70" />
                <span className="flex flex-1 flex-col items-start gap-0.5 text-left">
                  <span className="flex items-center gap-2 font-medium">
                    More integrations
                    <Badge variant="outline" className="text-[10px] font-normal">
                      Soon
                    </Badge>
                  </span>
                  <span className="text-xs font-normal text-muted-foreground">Airtable, Notion databases, and webhooks.</span>
                </span>
              </Button>
            </div>
          </section>

          <Separator />

          <section className="space-y-3">
            <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Local file</div>
            <p className="text-xs text-muted-foreground">CSV or TSV: one row per eval case. Headers in the first row.</p>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.tsv,text/csv,text/tab-separated-values"
              className="hidden"
              aria-label="Upload CSV or TSV file for eval data preview"
              onChange={onPickFile}
            />
            <Button type="button" variant="outline" className="w-full gap-2" onClick={() => fileRef.current?.click()}>
              <Upload className="size-3.5" />
              Upload CSV or TSV
            </Button>
          </section>

          {uploadState ? (
            <Card size="sm" className="border-border/80">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">{uploadState.name}</CardTitle>
                <p className="text-xs text-muted-foreground">
                  {uploadState.rowCount.toLocaleString()} data row{uploadState.rowCount === 1 ? "" : "s"} · delimiter:{" "}
                  {uploadState.delimiter}
                </p>
              </CardHeader>
              <CardContent className="pt-0">
                {uploadState.headers.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No columns detected.</p>
                ) : (
                  <div className="max-h-[240px] overflow-auto rounded-md border border-border/60">
                    <Table className="text-xs [&_th]:px-2 [&_td]:px-2">
                      <TableHeader>
                        <TableRow>
                          {uploadState.headers.map((h) => (
                            <TableHead key={h} className="max-w-[120px] truncate font-medium">
                              {h || "—"}
                            </TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {uploadState.rows.map((r, i) => (
                          <TableRow key={i}>
                            {uploadState.headers.map((_, j) => (
                              <TableCell key={j} className="max-w-[120px] truncate text-muted-foreground">
                                {r[j] ?? "—"}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
