"use client";

/**
 * Central mapping from domain values to lucide icons + colour tokens, so a
 * category/severity looks identical everywhere (nav, badges, tiles, charts).
 */

import {
  Bug,
  CircleAlert,
  CircleHelp,
  Layers,
  Lightbulb,
  Signal,
  SignalHigh,
  SignalLow,
  SignalMedium,
  Copy,
  FileX2,
  Ban,
  type LucideIcon,
} from "lucide-react";

export const CATEGORY_ICON: Record<string, LucideIcon> = {
  bug: Bug,
  feature_request: Lightbulb,
  question: CircleHelp,
  incident: CircleAlert,
  other: Layers,
};

export const SEVERITY_ICON: Record<string, LucideIcon> = {
  low: SignalLow,
  medium: SignalMedium,
  high: SignalHigh,
  critical: Signal,
};

export const SKIP_REASON_ICON: Record<string, LucideIcon> = {
  duplicate: Copy,
  blank: Ban,
  empty_after_clean: FileX2,
};

/** The CSS colour token for a category or severity (matches globals.css). */
export function domainColor(key: string): string {
  return `var(--color-${key})`;
}
