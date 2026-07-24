import { cn } from "@/lib/utils";

/** Shimmering placeholder (the `.skeleton` class carries the animation). */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("skeleton", className)} {...props} />;
}

export { Skeleton };
