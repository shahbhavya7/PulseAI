"use client";

import { CalendarDays } from "lucide-react";
import { recentIsoWeeks } from "@/lib/format";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ALL_TIME = "__all__";

/** Dropdown of recent ISO weeks. "All time" shows unfiltered data. */
export function WeekSelector({
  value,
  onChange,
  includeAllTime = true,
}: {
  value: string;
  onChange: (week: string) => void;
  includeAllTime?: boolean;
}) {
  const weeks = recentIsoWeeks(12);
  return (
    <div className="flex items-center gap-2">
      <CalendarDays className="size-4 text-muted-foreground" />
      <Select
        value={value === "" ? ALL_TIME : value}
        onValueChange={(v) => onChange(v === ALL_TIME ? "" : v)}
      >
        <SelectTrigger className="w-[150px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {includeAllTime && <SelectItem value={ALL_TIME}>All time</SelectItem>}
          {weeks.map((w) => (
            <SelectItem key={w} value={w}>
              {w}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
