"use client";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { AlertTriangle } from "lucide-react";
import type { DashboardData } from "@/lib/types";

export function TestModeBanner() {
  const { data } = useSWR<DashboardData>("/api/dashboard", fetcher, { refreshInterval: 60000 });
  if (!data?.email_test_mode) return null;
  return (
    <div className="flex items-center justify-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-xs font-medium text-amber-800">
      <AlertTriangle className="h-3.5 w-3.5" />
      TEST MODE ENABLED — all outgoing emails are redirected to the configured test address. No real companies will be contacted.
    </div>
  );
}
