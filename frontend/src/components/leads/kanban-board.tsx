"use client";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { formatRelative, humanize } from "@/lib/format";
import type { Lead, LeadStatus } from "@/lib/types";

// Assumption: the product's Kanban columns are a simplified view over the full
// LeadStatus lifecycle. Statuses not explicitly called out in the task spec
// are folded into the nearest sensible column:
//   - EMAIL_DRAFTED, APPROVED, QUEUED -> Contacted (email is in-flight but not sent/replied yet)
//   - FOLLOW_UP_DUE, FOLLOW_UP_SENT, IN_CONVERSATION -> Replied (there's been engagement/outreach follow-through)
//   - NOT_INTERESTED, BOUNCED, NO_RESPONSE, SUPPRESSED, CLOSED -> Lost
const KANBAN_COLUMNS: { key: string; label: string; statuses: LeadStatus[] }[] = [
  { key: "new", label: "New", statuses: ["NEW"] },
  { key: "qualified", label: "Qualified", statuses: ["QUALIFIED"] },
  { key: "contacted", label: "Contacted", statuses: ["EMAIL_DRAFTED", "APPROVED", "QUEUED", "CONTACTED"] },
  { key: "replied", label: "Replied", statuses: ["REPLIED", "FOLLOW_UP_DUE", "FOLLOW_UP_SENT", "IN_CONVERSATION"] },
  { key: "interested", label: "Interested", statuses: ["INTERESTED"] },
  { key: "meeting", label: "Meeting", statuses: ["MEETING_REQUESTED", "MEETING_SCHEDULED", "MEETING_COMPLETED"] },
  { key: "proposal", label: "Proposal", statuses: ["PROPOSAL_SENT"] },
  { key: "won", label: "Won", statuses: ["WON"] },
  { key: "lost", label: "Lost", statuses: ["LOST", "NOT_INTERESTED", "BOUNCED", "NO_RESPONSE", "SUPPRESSED", "CLOSED"] },
];

export function KanbanBoard({ leads }: { leads: Lead[] }) {
  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {KANBAN_COLUMNS.map((col) => {
        const colLeads = leads.filter((l) => col.statuses.includes(l.status));
        return (
          <div key={col.key} className="flex w-72 shrink-0 flex-col rounded-xl border border-slate-200 bg-slate-50">
            <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
              <h3 className="text-sm font-semibold text-slate-800">{col.label}</h3>
              <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-600">
                {colLeads.length}
              </span>
            </div>
            <div className="flex max-h-[70vh] flex-col gap-2 overflow-y-auto p-2">
              {colLeads.length === 0 ? (
                <p className="p-3 text-center text-xs text-slate-400">No leads</p>
              ) : (
                colLeads.map((lead) => (
                  <Link key={lead.lead_id} href={`/leads/${lead.lead_id}`}>
                    <Card className="cursor-pointer p-3 hover:border-indigo-300 hover:shadow-md">
                      <p className="text-sm font-medium text-slate-900">{lead.company_name || "—"}</p>
                      <p className="mt-0.5 text-xs text-slate-500">{lead.job_title || "—"}</p>
                      <div className="mt-2 flex items-center justify-between">
                        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
                          Score {lead.lead_score ?? 0}
                        </span>
                        <span className="text-xs text-slate-400">{formatRelative(lead.last_activity_at)}</span>
                      </div>
                      {lead.next_action && (
                        <p className="mt-1.5 truncate text-xs text-slate-500">
                          Next: {humanize(lead.next_action)}
                        </p>
                      )}
                    </Card>
                  </Link>
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
