"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/components/AuthProvider";

/** Wraps protected content: while the session is loading it shows a spinner;
 *  once resolved, an unauthenticated user is redirected to /signin. The sign-in
 *  route itself is exempt (rendered directly). */
export function AuthGuard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isSignIn = pathname === "/signin";

  useEffect(() => {
    if (!loading && !user && !isSignIn) {
      router.replace("/signin");
    }
  }, [loading, user, isSignIn, router]);

  // The sign-in page renders regardless of auth state.
  if (isSignIn) return <>{children}</>;

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="size-6 animate-spin text-primary" />
      </div>
    );
  }

  if (!user) {
    // Redirect is in-flight; render nothing to avoid a flash of protected UI.
    return null;
  }

  return <>{children}</>;
}
