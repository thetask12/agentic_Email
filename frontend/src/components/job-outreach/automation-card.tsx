"use client";
// Job Outreach module — Start/Stop card for the personal job-application
// automation (separate system from the Botivate outreach above it on the
// dashboard; see backend/app/job_outreach/ and root CLAUDE.md). Kept as its
// own component (not inlined into page.tsx) so it stays clearly separable
// from the rest of the dashboard.
import { useState } from "react";
import useSWR from "swr";
import { api, fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toaster";
import { Loader2, Play, Square } from "lucide-react";

interface JobOutreachStatus {
  running: boolean;
  emails_sent_today: number;
  daily_cap: number;
  emails_remaining_today: number;
  company_limit: number | null;
  companies_found_this_run: number;
}

export function JobOutreachAutomationCard() {
  const { push } = useToast();
  const { data, mutate, isLoading } = useSWR<JobOutreachStatus>(
    "/api/job-outreach/status",
    fetcher,
    { refreshInterval: 15000 }
  );
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  // Optional "companies to search" cap for a manual test run — blank means
  // unlimited (the normal continuous-loop behavior). Kept as a string so the
  // input can be empty without coercing to 0.
  const [companyLimitInput, setCompanyLimitInput] = useState("1");

  async function handleStart() {
    setStarting(true);
    try {
      const trimmed = companyLimitInput.trim();
      const maxCompanies = trimmed === "" ? null : Math.max(1, parseInt(trimmed, 10) || 1);
      const res = await api.post<JobOutreachStatus>("/api/job-outreach/start", {
        max_companies: maxCompanies,
      });
      mutate(res, { revalidate: false });
      push({
        title: "Automation started",
        description: maxCompanies
          ? `Will auto-stop after ${maxCompanies} compan${maxCompanies === 1 ? "y" : "ies"}.`
          : "Job search + outreach cycles will run continuously in the background.",
      });
    } catch (err) {
      push({
        title: "Failed to start automation",
        description: err instanceof Error ? err.message : String(err),
        variant: "error",
      });
    } finally {
      setStarting(false);
    }
  }

  async function handleStop() {
    setStopping(true);
    try {
      const res = await api.post<JobOutreachStatus>("/api/job-outreach/stop");
      mutate(res, { revalidate: false });
      push({
        title: "Automation stopped",
        description: "No new search cycles will start. Already-queued emails will still be sent.",
      });
    } catch (err) {
      push({
        title: "Failed to stop automation",
        description: err instanceof Error ? err.message : String(err),
        variant: "error",
      });
    } finally {
      setStopping(false);
    }
  }

  const running = data?.running ?? false;

  return (
    <Card className="mb-6 max-w-2xl">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Job Outreach Automation</CardTitle>
          {!isLoading && (
            <Badge className={running ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-600"}>
              {running ? "Running" : "Stopped"}
            </Badge>
          )}
        </div>
        <CardDescription>
          Personal job-application search — finds companies hiring for AI/Agentic AI roles and sends one application email each.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-400">Emails sent today</div>
            <div className="mt-0.5 font-semibold text-slate-900">{data?.emails_sent_today ?? 0}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-400">Daily cap</div>
            <div className="mt-0.5 font-semibold text-slate-900">{data?.daily_cap ?? "—"}</div>
          </div>
          {running && data?.company_limit ? (
            <div className="col-span-2">
              <div className="text-xs uppercase tracking-wide text-slate-400">This run</div>
              <div className="mt-0.5 font-semibold text-slate-900">
                {data.companies_found_this_run} / {data.company_limit} companies
              </div>
            </div>
          ) : null}
        </div>

        <div className="mb-3 flex items-end gap-3">
          <div>
            <label htmlFor="company-limit" className="text-xs uppercase tracking-wide text-slate-400">
              Companies to search
            </label>
            <input
              id="company-limit"
              type="number"
              min={1}
              placeholder="unlimited"
              value={companyLimitInput}
              onChange={(e) => setCompanyLimitInput(e.target.value)}
              disabled={running}
              className="mt-0.5 block w-32 rounded-md border border-slate-200 px-2 py-1.5 text-sm disabled:bg-slate-50 disabled:text-slate-400"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-3">
          <Button type="button" variant="primary" onClick={handleStart} disabled={starting || running}>
            {starting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Start Automation
          </Button>
          <Button type="button" variant="destructive" onClick={handleStop} disabled={stopping || !running}>
            {stopping ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
            Stop Automation
          </Button>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Leave &quot;Companies to search&quot; blank for continuous automation. Set a number (e.g. 1) for a
          quick test run that auto-stops itself once that many companies have been processed. Stop only
          prevents new search cycles from starting — emails already queued are still sent.
        </p>
      </CardContent>
    </Card>
  );
}
