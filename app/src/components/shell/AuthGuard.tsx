"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";
import { getAuthToken } from "@/lib/api";

const PUBLIC_PATHS = ["/login", "/auth/callback"];

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname() ?? "";
  const [checked, setChecked] = React.useState(false);

  React.useEffect(() => {
    const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
    if (isPublic) {
      setChecked(true);
      return;
    }
    const token = getAuthToken();
    if (!token) {
      router.replace("/login");
    } else {
      setChecked(true);
    }
  }, [pathname, router]);

  if (!checked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  return <>{children}</>;
}
