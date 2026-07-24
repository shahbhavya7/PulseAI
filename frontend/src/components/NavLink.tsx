"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/** Sidebar link that highlights when its route is active. */
export function NavLink({
  href,
  icon,
  children,
}: {
  href: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const active = pathname === href || (href !== "/" && pathname.startsWith(href));
  return (
    <Link
      href={href}
      className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
        active
          ? "bg-accent-soft text-text"
          : "text-muted hover:bg-surface-2 hover:text-text"
      }`}
    >
      <span className="text-base" aria-hidden>
        {icon}
      </span>
      {children}
    </Link>
  );
}
