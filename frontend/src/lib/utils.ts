import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn's class combiner: merges conditional classes and dedupes Tailwind
 *  utilities so the last one wins (e.g. `p-2` + `p-4` → `p-4`). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
