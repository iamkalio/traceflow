"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut } from "next-auth/react";
import { Activity, BarChart3, ClipboardPen, Database, Lightbulb, Settings, LogOut } from "lucide-react";

import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export function AppShell({
  children,
  active,
}: {
  children: React.ReactNode;
  active: "traces" | "evals" | "insights" | "settings";
}) {
  const pathname = usePathname() ?? "";

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-[1600px]">
        <div className="grid grid-cols-[260px_1fr]">
          <aside className="min-h-screen border-r bg-card/30 px-4 py-5">
            <div className="flex items-center gap-2 px-2 pb-4">
              <div className="h-8 w-8 rounded-lg bg-linear-to-br from-emerald-400 to-cyan-400" />
              <div className="leading-tight">
                <div className="text-sm font-semibold tracking-wide">Traceflow</div>
                <div className="text-xs text-muted-foreground">Trace → Eval → Insight</div>
              </div>
            </div>
            <Separator className="mb-3" />

            <nav className="space-y-1">
              <NavItem href="/traces" active={active === "traces"} icon={<Activity className="size-4" />}>
                Tracing
              </NavItem>

              <NavItem href="/insights" active={active === "insights"} icon={<BarChart3 className="size-4" />}>
                Insights
              </NavItem>

              <div className="pt-2">
                <div className="px-2 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  Evaluation
                </div>
                <div className="space-y-0.5">
                  <EvalSubLink href="/evals/llm-as-a-judge" pathname={pathname} icon={<Lightbulb className="size-4" />}>
                    LLM-as-a-Judge
                  </EvalSubLink>
                  <EvalSubLink
                    href="/evals/human-annotation"
                    pathname={pathname}
                    icon={<ClipboardPen className="size-4" />}
                  >
                    Human Annotation
                  </EvalSubLink>
                  <EvalSubLink href="/evals/datasets" pathname={pathname} icon={<Database className="size-4" />}>
                    Datasets
                  </EvalSubLink>
                </div>
              </div>

              <div className="pt-2">
                <NavItem href="/settings" active={active === "settings"} icon={<Settings className="size-4" />}>
                  Settings
                </NavItem>
              </div>

              <div className="pt-8">
                <button
                  onClick={() => signOut({ callbackUrl: '/' })}
                  className={cn(
                    buttonVariants({ variant: "ghost" }),
                    "w-full justify-start gap-2 font-medium text-muted-foreground hover:text-foreground"
                  )}
                >
                  <LogOut className="size-4" />
                  <span>Sign Out</span>
                </button>
              </div>
            </nav>
          </aside>

          <main className="min-h-screen bg-background">{children}</main>
        </div>
      </div>
    </div>
  );
}

function NavItem({
  href,
  active,
  icon,
  children,
}: {
  href: string;
  active: boolean;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        buttonVariants({ variant: active ? "secondary" : "ghost" }),
        "w-full justify-start gap-2",
        active ? "font-semibold" : "font-medium",
      )}
    >
      {icon}
      <span>{children}</span>
    </Link>
  );
}

function EvalSubLink({
  href,
  pathname,
  icon,
  children,
}: {
  href: string;
  pathname: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  const active = pathname === href || pathname.startsWith(`${href}/`);

  return (
    <Link
      href={href}
      className={cn(
        buttonVariants({ variant: active ? "secondary" : "ghost" }),
        "h-9 w-full justify-start gap-2 px-2 text-[13px]",
        active ? "font-semibold" : "font-medium",
      )}
    >
      {icon}
      <span className="truncate">{children}</span>
    </Link>
  );
}
