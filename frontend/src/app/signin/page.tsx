"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Activity, AlertTriangle, Loader2 } from "lucide-react";
import { getProviders, loginUrl } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { GoogleIcon, AppleIcon } from "@/components/BrandIcons";
import { PageTransition } from "@/components/motion";

const ERROR_COPY: Record<string, string> = {
  access_denied: "You cancelled the sign-in. No problem — try again when ready.",
  provider_unavailable: "That sign-in provider isn't configured on the server.",
  missing_claims: "The provider didn't share an email, so we can't sign you in.",
  oauth_failed: "Sign-in didn't complete. Please try again.",
};

export default function SignInPage() {
  return (
    <Suspense fallback={null}>
      <SignInView />
    </Suspense>
  );
}

function SignInView() {
  const params = useSearchParams();
  const router = useRouter();
  const { user, loading } = useAuth();
  const [providers, setProviders] = useState<string[] | null>(null);
  const error = params.get("error");

  // Already signed in → go to the dashboard.
  useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [loading, user, router]);

  useEffect(() => {
    getProviders()
      .then((r) => setProviders(r.providers))
      .catch(() => setProviders([]));
  }, []);

  return (
    <PageTransition className="flex min-h-[70vh] items-center justify-center">
      <div className="glass ring-accent w-full max-w-sm rounded-[var(--radius)] p-8 text-center">
        <span className="mx-auto mb-5 flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-[0_0_28px_-4px_hsl(var(--primary)/0.9)]">
          <Activity className="size-6" />
        </span>
        <h1 className="text-xl font-bold tracking-tight">Welcome to PulseAI</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Sign in to see your customer signal dashboard.
        </p>

        {error && (
          <div className="mt-5 flex items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-3 py-2 text-left text-xs text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{ERROR_COPY[error] ?? "Sign-in failed. Please try again."}</span>
          </div>
        )}

        <div className="mt-6 space-y-3">
          {providers === null ? (
            <div className="flex justify-center py-4">
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            </div>
          ) : providers.length === 0 ? (
            <p className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-xs text-muted-foreground">
              No sign-in providers are configured yet. Set the Google (and/or
              Apple) credentials in the backend&apos;s <code>.env</code>.
            </p>
          ) : (
            <>
              {providers.includes("google") && (
                <ProviderButton provider="google" label="Continue with Google">
                  <GoogleIcon />
                </ProviderButton>
              )}
              {providers.includes("apple") && (
                <ProviderButton provider="apple" label="Continue with Apple">
                  <AppleIcon />
                </ProviderButton>
              )}
            </>
          )}
        </div>

        <p className="mt-6 text-[11px] leading-relaxed text-muted-foreground/70">
          We only use your name and email to identify your account.
        </p>
      </div>
    </PageTransition>
  );
}

function ProviderButton({
  provider,
  label,
  children,
}: {
  provider: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <a
      href={loginUrl(provider)}
      className="flex w-full items-center justify-center gap-3 rounded-full border border-white/15 bg-white/[0.05] px-4 py-2.5 text-sm font-semibold text-foreground transition-all hover:border-primary/50 hover:bg-white/[0.09] active:scale-[0.98]"
    >
      <span className="flex size-5 items-center justify-center">{children}</span>
      {label}
    </a>
  );
}
