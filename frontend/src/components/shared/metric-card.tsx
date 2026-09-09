import Link from "next/link";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export function MetricCard({
  label,
  value,
  href,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: number | string;
  href?: string;
  icon?: LucideIcon;
  tone?: "default" | "success" | "warning" | "danger";
}) {
  const toneClasses: Record<string, string> = {
    default: "text-slate-900",
    success: "text-emerald-600",
    warning: "text-amber-600",
    danger: "text-red-600",
  };
  const content = (
    <Card className="p-4 transition-shadow hover:shadow-md">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
        {Icon && <Icon className="h-4 w-4 text-slate-300" />}
      </div>
      <p className={cn("mt-2 text-2xl font-semibold", toneClasses[tone])}>{value}</p>
    </Card>
  );
  return href ? <Link href={href}>{content}</Link> : content;
}
