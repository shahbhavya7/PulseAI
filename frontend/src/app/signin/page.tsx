"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Activity, AlertTriangle, Loader2, Mail } from "lucide-react";
import {
  ApiError,
  getProviders,
  loginEmail,
  loginUrl,
  registerEmail,
} from "@/lib/api";
import type { ProvidersResponse } from "@/lib/types";
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
  const { user, loading, refresh } = useAuth();
  const [options, setOptions] = useState<ProvidersResponse | null>(null);
  const oauthError = params.get("error");

  useEffect(() => {
    if (!loading && user) router.replace("/");
  }, [loading, user, router]);

  useEffect(() => {
    getProviders()
      .then(setOptions)
      .catch(() => setOptions({ providers: [], email: false }));
  }, []);

  const hasOAuth = (options?.providers.length ?? 0) > 0;
  const hasEmail = options?.email ?? false;

  return (
    <PageTransition className="flex min-h-[70vh] items-center justify-center">
      <div className="glass ring-accent w-full max-w-sm rounded-[var(--radius)] p-8">
        <div className="text-center">
          <span className="mx-auto mb-5 flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-[0_0_28px_-4px_hsl(var(--primary)/0.9)]">
            <Activity className="size-6" />
          </span>
          <h1 className="text-xl font-bold tracking-tight">Welcome to PulseAI</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Sign in to see your customer signal dashboard.
          </p>
        </div>

        {oauthError && (
          <div className="mt-5 flex items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-3 py-2 text-left text-xs text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{ERROR_COPY[oauthError] ?? "Sign-in failed. Please try again."}</span>
          </div>
        )}

        {options === null ? (
          <div className="flex justify-center py-6">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            {hasEmail && <EmailForm onSuccess={refresh} />}

            {hasEmail && hasOAuth && (
              <div className="flex items-center gap-3 text-[11px] uppercase tracking-wider text-muted-foreground/60">
                <span className="h-px flex-1 bg-white/10" />
                or
                <span className="h-px flex-1 bg-white/10" />
              </div>
            )}

            {options.providers.includes("google") && (
              <ProviderButton provider="google" label="Continue with Google">
                <GoogleIcon />
              </ProviderButton>
            )}
            {options.providers.includes("apple") && (
              <ProviderButton provider="apple" label="Continue with Apple">
                <AppleIcon />
              </ProviderButton>
            )}

            {!hasEmail && !hasOAuth && (
              <p className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-center text-xs text-muted-foreground">
                No sign-in methods are enabled. Configure Google/Apple or enable
                email sign-in in the backend&apos;s <code>.env</code>.
              </p>
            )}
          </div>
        )}

        <p className="mt-6 text-center text-[11px] leading-relaxed text-muted-foreground/70">
          We only use your name and email to identify your account.
        </p>
      </div>
    </PageTransition>
  );
}

function EmailForm({ onSuccess }: { onSuccess: () => Promise<void> }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") {
        await loginEmail(email, password);
      } else {
        await registerEmail(email, password, fullName || undefined);
      }
      await onSuccess(); // refresh /auth/me → the guard sends us to the dashboard
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      {mode === "register" && (
        <Input
          type="text"
          placeholder="Full name (optional)"
          value={fullName}
          onChange={setFullName}
          autoComplete="name"
        />
      )}
      <Input
        type="email"
        placeholder="Email"
        value={email}
        onChange={setEmail}
        autoComplete="email"
        required
      />
      <Input
        type="password"
        placeholder={mode === "register" ? "Password (min 8 chars)" : "Password"}
        value={password}
        onChange={setPassword}
        autoComplete={mode === "register" ? "new-password" : "current-password"}
        required
      />

      {error && <p className="text-xs text-destructive">{error}</p>}

      <button
        type="submit"
        disabled={busy}
        className="flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-all hover:brightness-110 active:scale-[0.98] disabled:opacity-50"
      >
        {busy ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Mail className="size-4" />
        )}
        {mode === "login" ? "Sign in" : "Create account"}
      </button>

      <p className="text-center text-xs text-muted-foreground">
        {mode === "login" ? "New here?" : "Already have an account?"}{" "}
        <button
          type="button"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError(null);
          }}
          className="font-semibold text-primary hover:underline"
        >
          {mode === "login" ? "Create an account" : "Sign in"}
        </button>
      </p>
    </form>
  );
}

function Input({
  type,
  placeholder,
  value,
  onChange,
  autoComplete,
  required,
}: {
  type: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  required?: boolean;
}) {
  return (
    <input
      type={type}
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      autoComplete={autoComplete}
      required={required}
      className="w-full rounded-xl border border-white/15 bg-white/[0.04] px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 outline-none transition-colors focus:border-primary/60 focus:ring-2 focus:ring-ring/40"
    />
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
