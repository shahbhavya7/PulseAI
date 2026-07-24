"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  Activity,
  LayoutDashboard,
  LogOut,
  MessagesSquare,
  Ticket,
  UploadCloud,
} from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/button";

/**
 * Floating glass top navbar. Sticky, inset from all edges (detached bar hovering
 * over the aurora), rounded, and using the SAME `.glass-strong` treatment as the
 * cards so it merges with the glass system. Slides/fades down on mount.
 *
 * Brand left · nav links center-left · (room for actions) right. On narrow
 * widths the link labels collapse, leaving icon-only pills.
 */
export function TopNav() {
  const { user, signOut } = useAuth();
  const initial = (user?.full_name || user?.email || "?").trim().charAt(0).toUpperCase();

  return (
    <motion.header
      initial={{ opacity: 0, y: -24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
      className="sticky top-4 z-30 mx-auto w-full max-w-6xl px-4"
    >
      <nav className="glass-strong flex items-center gap-2 rounded-full py-2 pl-3 pr-2 sm:gap-4 sm:pl-4">
        {/* Brand */}
        <Link href="/" className="flex shrink-0 items-center gap-2.5 pr-1">
          <span className="flex size-8 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-[0_0_24px_-4px_hsl(var(--primary)/0.9)]">
            <Activity className="size-5" />
          </span>
          <span className="hidden text-base font-bold tracking-tight sm:inline">
            PulseAI
          </span>
        </Link>

        {/* Nav links — labels hide on narrow widths (icon-only pills). */}
        <div className="flex items-center gap-1">
          <NavLink href="/" icon={<LayoutDashboard />} labelClassName="hidden sm:inline">
            Overview
          </NavLink>
          <NavLink href="/tickets" icon={<Ticket />} labelClassName="hidden sm:inline">
            Tickets
          </NavLink>
          <NavLink href="/chat" icon={<MessagesSquare />} labelClassName="hidden sm:inline">
            Chat
          </NavLink>
          <NavLink href="/upload" icon={<UploadCloud />} labelClassName="hidden sm:inline">
            Upload
          </NavLink>
        </div>

        {/* Actions slot (right-aligned): who's signed in + sign out. */}
        <div className="ml-auto flex items-center gap-2 pr-1">
          {user && (
            <>
              <span
                className="flex size-8 items-center justify-center rounded-full bg-primary/15 text-sm font-semibold text-primary"
                title={user.email}
              >
                {initial}
              </span>
              <span className="hidden max-w-[10rem] truncate text-xs text-muted-foreground lg:inline">
                {user.full_name || user.email}
              </span>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => void signOut()}
                title="Sign out"
                aria-label="Sign out"
              >
                <LogOut className="size-4" />
              </Button>
            </>
          )}
        </div>
      </nav>
    </motion.header>
  );
}
