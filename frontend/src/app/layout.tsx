import type { Metadata } from "next";
import Link from "next/link";
import { NavLink } from "@/components/NavLink";
import "./globals.css";

export const metadata: Metadata = {
  title: "PulseAI — Customer Signal Dashboard",
  description: "Upload customer tickets, see what matters this week.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <div className="flex min-h-screen">
          {/* Sidebar */}
          <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-border bg-surface px-4 py-6 md:flex">
            <Link href="/" className="mb-8 flex items-center gap-2.5 px-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-lg">
                💠
              </span>
              <span className="text-base font-bold tracking-tight">PulseAI</span>
            </Link>
            <nav className="flex flex-col gap-1">
              <NavLink href="/" icon="📊">
                Overview
              </NavLink>
              <NavLink href="/tickets" icon="🎫">
                Tickets
              </NavLink>
              <NavLink href="/upload" icon="⬆️">
                Upload
              </NavLink>
            </nav>
            <p className="mt-auto px-2 text-xs leading-relaxed text-muted">
              Customer ticket triage, summarised weekly.
            </p>
          </aside>

          {/* Mobile top nav */}
          <div className="flex w-full flex-col">
            <header className="flex items-center gap-4 border-b border-border bg-surface px-4 py-3 md:hidden">
              <span className="text-base font-bold">💠 PulseAI</span>
              <nav className="flex gap-3 text-sm text-muted">
                <Link href="/">Overview</Link>
                <Link href="/tickets">Tickets</Link>
                <Link href="/upload">Upload</Link>
              </nav>
            </header>
            <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:px-8">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
