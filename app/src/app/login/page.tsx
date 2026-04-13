"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { TRACEFLOW_API_URL } from "@/lib/env";

const ERROR_MESSAGES: Record<string, string> = {
  oauth_not_configured: "GitHub OAuth is not configured on the server. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.",
  token_exchange_failed: "Failed to exchange GitHub OAuth code. Please try again.",
  github_user_fetch_failed: "Could not fetch your GitHub profile. Please try again.",
  missing_code: "GitHub did not return an authorisation code. Please try again.",
};

function LoginContent() {
  const searchParams = useSearchParams();
  const error = searchParams.get("error");

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-linear-to-br from-emerald-400 to-cyan-400" />
          <div className="text-center">
            <h1 className="text-2xl font-semibold tracking-tight">Traceflow</h1>
            <p className="mt-1 text-sm text-muted-foreground">Trace → Eval → Insight</p>
          </div>
        </div>

        {error ? (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {ERROR_MESSAGES[error] ?? `Sign-in error: ${error}`}
          </div>
        ) : null}

        <a
          href={`${TRACEFLOW_API_URL}/auth/github`}
          className="flex w-full items-center justify-center gap-3 rounded-md border border-border bg-card px-4 py-2.5 text-sm font-medium transition-colors hover:bg-muted"
        >
          <GitHubIcon />
          Sign in with GitHub
        </a>

        <p className="text-center text-xs text-muted-foreground">
          Your GitHub ID is used as your tenant identifier to scope traces and evaluations.
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginContent />
    </Suspense>
  );
}

function GitHubIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
    </svg>
  );
}
