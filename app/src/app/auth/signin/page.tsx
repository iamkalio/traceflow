"use client";

import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Activity } from "lucide-react";

function SignInContent() {
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") ?? "/traces";
  const error = searchParams.get("error");

  const ERROR_MESSAGES: Record<string, string> = {
    OAuthSignin: "Could not start the GitHub sign-in flow. Please try again.",
    OAuthCallback: "An error occurred during the GitHub callback. Please try again.",
    OAuthCreateAccount: "Could not create your account. Please try again.",
    Callback: "Sign-in callback failed. Please try again.",
    Default: "An unexpected error occurred. Please try again.",
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-black px-4 text-slate-50">
      <div className="w-full max-w-sm space-y-6">
        {/* Logo */}
        <div className="flex flex-col items-center gap-3">
          <div className="flex items-center gap-2">
            <Activity className="h-7 w-7 text-indigo-400" />
            <span className="text-2xl font-bold tracking-tight">Traceflow</span>
          </div>
          <p className="text-sm text-slate-400">Trace → Eval → Insight</p>
        </div>

        {/* Error banner */}
        {error ? (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            {ERROR_MESSAGES[error] ?? ERROR_MESSAGES.Default}
          </div>
        ) : null}

        {/* Card */}
        <div className="rounded-2xl border border-white/10 bg-white/5 px-6 py-8 space-y-4">
          <div className="text-center space-y-1">
            <h1 className="text-xl font-semibold text-white">Sign in to your account</h1>
            <p className="text-sm text-slate-400">
              Your GitHub ID is used as your tenant identifier to scope your traces and evaluations.
            </p>
          </div>

          <button
            onClick={() => signIn("github", { callbackUrl })}
            className="flex w-full items-center justify-center gap-3 rounded-lg border border-white/20 bg-white/5 px-4 py-2.5 text-sm font-medium text-white transition-all hover:bg-white/10 active:scale-[0.98]"
          >
            <GitHubIcon />
            Continue with GitHub
          </button>
        </div>

        <p className="text-center text-xs text-slate-600">
          By signing in you agree to our terms of service.
        </p>
      </div>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense>
      <SignInContent />
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
