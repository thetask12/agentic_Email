import * as React from "react";
import { cn } from "@/lib/utils";
import { statusColor, humanize } from "@/lib/format";

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        className
      )}
      {...props}
    />
  );
}

export function StatusBadge({ status, className }: { status: string | undefined | null; className?: string }) {
  return <Badge className={cn(statusColor(status), className)}>{humanize(status)}</Badge>;
}
