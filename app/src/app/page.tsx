import Link from "next/link";
import { getServerSession } from "next-auth";
import { authOptions } from "@/server/auth";
import { redirect } from "next/navigation";
import { Play, ArrowRight, Activity, ShieldCheck, Zap } from "lucide-react";

export default async function LandingPage() {
  const session = await getServerSession(authOptions);

  if (session) {
    redirect("/traces");
  }

  return (
    <div className="min-h-screen bg-black text-slate-50 flex flex-col selection:bg-indigo-500/30">
      {/* Navigation */}
      <header className="sticky top-0 z-50 w-full border-b border-white/10 bg-black/50 backdrop-blur-md">
        <div className="container mx-auto flex h-14 items-center justify-between px-4">
          <div className="flex items-center gap-2 font-semibold text-lg tracking-tight">
            <Activity className="h-5 w-5 text-indigo-400" />
            <span>Traceflow</span>
          </div>
          <nav className="flex items-center gap-4 text-sm font-medium">
            <Link
              href="https://github.com/iamkalio/traceflow"
              target="_blank"
              rel="noreferrer"
              className="text-slate-400 hover:text-white transition-colors flex items-center gap-2"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-4 w-4"
              >
                <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
                <path d="M9 18c-4.51 2-5-2-7-2" />
              </svg>
              <span className="hidden sm:inline">Star on GitHub</span>
            </Link>
            <Link
              href="/api/auth/signin"
              className="rounded-md bg-white px-3 py-1.5 text-black hover:bg-slate-200 transition-colors"
            >
              Sign In
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 text-center py-24 sm:py-32">
        <div className="inline-flex items-center rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-sm font-medium text-indigo-300 mb-8">
          <span className="flex h-2 w-2 rounded-full bg-indigo-500 mr-2 animate-pulse"></span>
          Traceflow is now in public beta
        </div>
        
        <h1 className="max-w-4xl text-5xl font-extrabold tracking-tight sm:text-7xl lg:text-8xl mb-6 bg-gradient-to-br from-white to-slate-500 bg-clip-text text-transparent">
          Open Source LLM <br className="hidden sm:block" /> Engineering Platform
        </h1>
        
        <p className="max-w-2xl text-lg sm:text-xl text-slate-400 mb-10">
          Traces, evals, prompt management and metrics to debug and improve your LLM application. 
          Built for teams that need to move fast and stay reliable.
        </p>
        
        <div className="flex flex-col sm:flex-row items-center gap-4 w-full sm:w-auto">
          <Link
            href="/api/auth/signin"
            className="w-full sm:w-auto flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-8 py-3 text-sm font-semibold text-white hover:bg-indigo-500 transition-all shadow-[0_0_20px_rgba(79,70,229,0.3)]"
          >
            Start Building Free
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            href="https://github.com/iamkalio/traceflow"
            target="_blank"
            className="w-full sm:w-auto flex items-center justify-center gap-2 rounded-lg border border-white/20 bg-white/5 px-8 py-3 text-sm font-semibold text-white hover:bg-white/10 transition-all"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-4 w-4"
            >
              <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
              <path d="M9 18c-4.51 2-5-2-7-2" />
            </svg>
            View on GitHub
          </Link>
        </div>

        {/* Feature Highlights */}
        <div className="grid sm:grid-cols-3 gap-8 mt-24 max-w-5xl text-left">
          <div className="flex flex-col gap-3 p-6 rounded-2xl border border-white/10 bg-white/5">
            <div className="h-10 w-10 rounded-lg bg-indigo-500/20 flex items-center justify-center text-indigo-400">
              <Activity className="h-5 w-5" />
            </div>
            <h3 className="font-semibold text-lg text-white">Observability</h3>
            <p className="text-sm text-slate-400">
              Track every LLM call, token usage, and latency. Debug complex agent workflows with nested traces.
            </p>
          </div>
          <div className="flex flex-col gap-3 p-6 rounded-2xl border border-white/10 bg-white/5">
            <div className="h-10 w-10 rounded-lg bg-emerald-500/20 flex items-center justify-center text-emerald-400">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <h3 className="font-semibold text-lg text-white">Evaluations</h3>
            <p className="text-sm text-slate-400">
              Run LLM-as-a-judge evals to catch regressions before they hit production. Score groundedness and relevance.
            </p>
          </div>
          <div className="flex flex-col gap-3 p-6 rounded-2xl border border-white/10 bg-white/5">
            <div className="h-10 w-10 rounded-lg bg-amber-500/20 flex items-center justify-center text-amber-400">
              <Zap className="h-5 w-5" />
            </div>
            <h3 className="font-semibold text-lg text-white">Performance</h3>
            <p className="text-sm text-slate-400">
              Monitor costs and optimize prompt latency. Get actionable insights into your LLM spending.
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-white/10 py-8 text-center text-sm text-slate-500">
        <p>© {new Date().getFullYear()} Traceflow. Open source under MIT License.</p>
      </footer>
    </div>
  );
}
