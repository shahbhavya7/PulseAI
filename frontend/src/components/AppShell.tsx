"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { AuthGuard } from "@/components/AuthGuard";
import { TopNav } from "@/components/TopNav";

/** The authenticated app frame: floating nav + guarded content. The sign-in
 *  route renders bare (no nav), everything else is behind the guard. */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const bare = pathname === "/signin";

  return (
    <div className="relative z-10 min-h-screen">
      {!bare && <TopNav />}
      <main className="mx-auto w-full max-w-6xl px-4 pb-10 pt-6 md:px-8">
        <AuthGuard>{children}</AuthGuard>
      </main>
    </div>
  );
}
