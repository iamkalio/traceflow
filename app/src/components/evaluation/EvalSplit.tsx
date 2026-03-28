"use client";

import * as React from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** Master–detail: list/table on the left, details on the right (stacks on small screens). */
export function EvalSplit({
  list,
  detail,
  className,
}: {
  list: React.ReactNode;
  detail: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`grid min-h-[min(70vh,720px)] grid-cols-1 gap-0 lg:grid-cols-[minmax(0,1fr)_minmax(300px,400px)] lg:gap-4 ${className ?? ""}`}
    >
      <div className="min-h-0 min-w-0 overflow-hidden">{list}</div>
      <Card className="min-h-0 rounded-none border-border/60 lg:max-h-[min(70vh,720px)]">
        <CardHeader className="border-b border-border/50 py-3">
          <CardTitle className="text-sm font-medium">Details</CardTitle>
        </CardHeader>
        <CardContent className="max-h-[min(60vh,600px)] overflow-y-auto pt-4">{detail}</CardContent>
      </Card>
    </div>
  );
}

export function EvalPageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="text-xs uppercase tracking-wider text-muted-foreground">{eyebrow}</div>
        <h1 className="mt-1 text-xl font-semibold">{title}</h1>
        {description ? <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
