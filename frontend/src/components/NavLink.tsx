"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Top-nav link that highlights when its route is active. The active pill glides
 *  horizontally between items via a shared framer-motion layoutId. `icon` is a
 *  rendered element so it passes cleanly from the layout. On narrow widths the
 *  label is hidden (icon-only) via `labelClassName`. */
export function NavLink({
  href,
  icon,
  children,
  labelClassName = "",
}: {
  href: string;
  icon: ReactNode;
  children: string;
  labelClassName?: string;
}) {
  const pathname = usePathname();
  const active = pathname === href || (href !== "/" && pathname.startsWith(href));

  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      title={children}
      className={cn(
        "group relative flex items-center gap-2 rounded-full px-3.5 py-2 text-sm font-medium transition-colors",
        active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {active && (
        <motion.span
          layoutId="nav-active"
          transition={{ type: "spring", stiffness: 420, damping: 34 }}
          className="absolute inset-0 rounded-full border border-primary/40 bg-primary/15 shadow-[0_0_20px_-4px_hsl(var(--primary)/0.6)]"
        />
      )}
      <span
        className={cn(
          "relative shrink-0 transition-colors [&_svg]:size-4",
          active ? "text-primary" : "group-hover:text-foreground",
        )}
      >
        {icon}
      </span>
      <span className={cn("relative", labelClassName)}>{children}</span>
    </Link>
  );
}
