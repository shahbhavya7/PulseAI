"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Activity, LayoutDashboard, Ticket, UploadCloud } from "lucide-react";
import { NavLink } from "@/components/NavLink";

/**
 * Floating glass top navbar. Sticky, inset from all edges (detached bar hovering
 * over the aurora), rounded, and using the SAME `.glass-strong` treatment as the
 * cards so it merges with the glass system. Slides/fades down on mount.
 *
 * Brand left · nav links center-left · (room for actions) right. On narrow
 * widths the link labels collapse, leaving icon-only pills.
 */
export function TopNav() {
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
          <NavLink href="/upload" icon={<UploadCloud />} labelClassName="hidden sm:inline">
            Upload
          </NavLink>
        </div>

        {/* Actions slot (right-aligned). */}
        <p className="ml-auto hidden pr-2 text-xs text-muted-foreground lg:block">
          Customer ticket triage
        </p>
      </nav>
    </motion.header>
  );
}
