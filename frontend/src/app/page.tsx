import { JobOutreachAutomationCard } from "@/components/job-outreach/automation-card";

// Single-screen dashboard: just the Job Outreach automation Start/Stop
// card. Every other old-system dashboard widget (search form, metrics,
// pipeline stats) was removed along with the rest of that system — see
// CLAUDE.md "History".
export default function DashboardPage() {
  return (
    <div>
      <h1 className="mb-6 text-lg font-semibold text-slate-900">Job Outreach</h1>
      <JobOutreachAutomationCard />
    </div>
  );
}
