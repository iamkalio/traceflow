"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { AppShell } from "@/components/shell/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  EVAL_LOCAL_KEY_QUERY_KEY,
  getEvalProviderConfiguredLocal,
} from "@/lib/api";
import { clearStoredOpenAIKey, setStoredOpenAIKey } from "@/lib/openaiKey";

export default function SettingsPage() {
  const qc = useQueryClient();
  const [apiKey, setApiKey] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const settingsQ = useQuery({
    queryKey: EVAL_LOCAL_KEY_QUERY_KEY,
    queryFn: () => getEvalProviderConfiguredLocal(),
  });

  async function onSave() {
    setErr(null);
    setSaving(true);
    try {
      setStoredOpenAIKey(apiKey.trim());
      setApiKey("");
      await qc.invalidateQueries({ queryKey: EVAL_LOCAL_KEY_QUERY_KEY });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function onRemove() {
    setErr(null);
    clearStoredOpenAIKey();
    setApiKey("");
    await qc.invalidateQueries({ queryKey: EVAL_LOCAL_KEY_QUERY_KEY });
  }

  const configured = settingsQ.data?.configured ?? false;

  return (
    <AppShell active="settings">
      <div className="px-6 py-5">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">
          Settings
        </div>
        <h1 className="mt-1 text-xl font-semibold">Evaluation Provider</h1>

        <Card className="mt-6 rounded-none border-border/60 ring-0">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Bring your own key</span>
              <span className="text-xs text-muted-foreground">
                Status: {configured ? "Saved in this browser" : "Not set"}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="text-muted-foreground">
              Your OpenAI API key is stored only in this browser (localStorage).
              It is sent to the Traceflow API in the{" "}
              <code className="text-xs">X-OpenAI-API-Key</code> header when you
              run an eval — the server does not save it.
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-…"
                className="max-w-[520px]"
              />
              <Button onClick={onSave} disabled={saving || !apiKey.trim()}>
                {saving ? "Saving…" : "Save in browser"}
              </Button>
              {configured ? (
                <Button type="button" variant="outline" onClick={onRemove}>
                  Remove key
                </Button>
              ) : null}
            </div>

            {err ? <div className="text-sm text-destructive">{err}</div> : null}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
