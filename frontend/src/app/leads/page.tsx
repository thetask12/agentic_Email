"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import { fetcher, qs } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, ErrorState } from "@/components/shared/empty-state";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { KanbanBoard } from "@/components/leads/kanban-board";
import { downloadCsv, humanize, formatDate } from "@/lib/format";
import { INDIAN_STATES, JOB_SOURCES } from "@/lib/indian-states";
import type { Lead, LeadStatus, Priority, ListResponse } from "@/lib/types";
import { LayoutGrid, List as ListIcon, Download } from "lucide-react";

const LEAD_STATUSES: LeadStatus[] = [
  "NEW", "QUALIFIED", "EMAIL_DRAFTED", "APPROVED", "QUEUED", "CONTACTED",
  "REPLIED", "FOLLOW_UP_DUE", "FOLLOW_UP_SENT", "IN_CONVERSATION",
  "MEETING_REQUESTED", "MEETING_SCHEDULED", "MEETING_COMPLETED", "PROPOSAL_SENT",
  "INTERESTED", "NOT_INTERESTED", "BOUNCED", "NO_RESPONSE", "SUPPRESSED",
  "WON", "LOST", "CLOSED",
];

const PRIORITIES: Priority[] = ["LOW", "MEDIUM", "HIGH", "URGENT"];

type Filters = {
  state: string;
  city: string;
  source: string;
  job_title: string;
  company: string;
  status: string;
  priority: string;
  email_status: string;
  reply_status: string;
  search: string;
};

const EMPTY_FILTERS: Filters = {
  state: "", city: "", source: "", job_title: "", company: "",
  status: "", priority: "", email_status: "", reply_status: "",
  search: "",
};

export default function LeadsPage() {
  return (
    <Suspense fallback={null}>
      <LeadsPageInner />
    </Suspense>
  );
}

function LeadsPageInner() {
  const router = useRouter();
  const sp = useSearchParams();

  const [filters, setFilters] = useState<Filters>(() => ({
    state: sp.get("state") || "",
    city: sp.get("city") || "",
    source: sp.get("source") || "",
    job_title: sp.get("job_title") || "",
    company: sp.get("company") || "",
    status: sp.get("status") || "",
    priority: sp.get("priority") || "",
    email_status: sp.get("email_status") || "",
    reply_status: sp.get("reply_status") || "",
    search: sp.get("search") || "",
  }));
  const [minScore, setMinScore] = useState<string>("");
  const [view, setView] = useState<"table" | "kanban">("table");

  // Keep the URL in sync (shallow) so filters stay deep-linkable.
  useEffect(() => {
    const query = qs(filters);
    router.replace(`/leads${query}`, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  const queryString = useMemo(() => qs(filters), [filters]);
  const { data, error, isLoading } = useSWR<ListResponse<Lead>>(`/api/leads${queryString}`, fetcher);

  const items = data?.items || [];
  const filteredItems = useMemo(() => {
    const min = Number(minScore);
    if (!minScore || isNaN(min)) return items;
    return items.filter((l) => (l.lead_score ?? 0) >= min);
  }, [items, minScore]);

  function setFilter<K extends keyof Filters>(key: K, value: string) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  function handleExport() {
    const rows = filteredItems.map((l) => ({
      lead_id: l.lead_id,
      company_name: l.company_name,
      job_title: l.job_title,
      source: l.source,
      status: l.status,
      priority: l.priority,
      lead_score: l.lead_score,
      botivate_opportunity_score: l.botivate_opportunity_score,
      email_sent: l.email_sent,
      has_reply: l.has_reply,
      follow_up_count: l.follow_up_count,
      next_action: l.next_action,
      next_action_date: l.next_action_date,
      owner: l.owner,
      created_at: l.created_at,
      last_activity_at: l.last_activity_at,
    }));
    downloadCsv("leads.csv", rows);
  }

  return (
    <div>
      <PageHeader
        title="Leads"
        description={isLoading ? "Loading…" : `${filteredItems.length} of ${data?.total ?? 0} leads`}
        actions={
          <>
            <div className="flex items-center rounded-lg border border-slate-200 bg-white p-0.5">
              <Button
                type="button"
                size="sm"
                variant={view === "table" ? "secondary" : "ghost"}
                onClick={() => setView("table")}
              >
                <ListIcon className="h-4 w-4" /> Table
              </Button>
              <Button
                type="button"
                size="sm"
                variant={view === "kanban" ? "secondary" : "ghost"}
                onClick={() => setView("kanban")}
              >
                <LayoutGrid className="h-4 w-4" /> Kanban
              </Button>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={handleExport}>
              <Download className="h-4 w-4" /> Export CSV
            </Button>
          </>
        }
      />

      <Card className="mb-4">
        <CardContent className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          <Input
            placeholder="Search…"
            value={filters.search}
            onChange={(e) => setFilter("search", e.target.value)}
          />
          <Input
            placeholder="Company"
            value={filters.company}
            onChange={(e) => setFilter("company", e.target.value)}
          />
          <Input
            placeholder="Job title"
            value={filters.job_title}
            onChange={(e) => setFilter("job_title", e.target.value)}
          />
          <Input
            placeholder="City"
            value={filters.city}
            onChange={(e) => setFilter("city", e.target.value)}
          />

          <Select value={filters.state || undefined} onValueChange={(v) => setFilter("state", v)}>
            <SelectTrigger><SelectValue placeholder="State" /></SelectTrigger>
            <SelectContent>
              {INDIAN_STATES.map((s) => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={filters.source || undefined} onValueChange={(v) => setFilter("source", v)}>
            <SelectTrigger><SelectValue placeholder="Source" /></SelectTrigger>
            <SelectContent>
              {JOB_SOURCES.map((s) => (
                <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={filters.status || undefined} onValueChange={(v) => setFilter("status", v)}>
            <SelectTrigger><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              {LEAD_STATUSES.map((s) => (
                <SelectItem key={s} value={s}>{humanize(s)}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={filters.priority || undefined} onValueChange={(v) => setFilter("priority", v)}>
            <SelectTrigger><SelectValue placeholder="Priority" /></SelectTrigger>
            <SelectContent>
              {PRIORITIES.map((s) => (
                <SelectItem key={s} value={s}>{humanize(s)}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={filters.email_status || undefined} onValueChange={(v) => setFilter("email_status", v)}>
            <SelectTrigger><SelectValue placeholder="Email Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="SENT">Sent</SelectItem>
              <SelectItem value="NOT_SENT">Not Sent</SelectItem>
            </SelectContent>
          </Select>

          <Select value={filters.reply_status || undefined} onValueChange={(v) => setFilter("reply_status", v)}>
            <SelectTrigger><SelectValue placeholder="Reply Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="REPLIED">Replied</SelectItem>
              <SelectItem value="NOT_REPLIED">Not Replied</SelectItem>
            </SelectContent>
          </Select>

          <Input
            type="number"
            placeholder="Min lead score"
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
          />

          <Button type="button" variant="ghost" size="sm" onClick={() => { setFilters(EMPTY_FILTERS); setMinScore(""); }}>
            Clear filters
          </Button>
        </CardContent>
      </Card>

      {error ? (
        <ErrorState message={error.message} />
      ) : !isLoading && filteredItems.length === 0 ? (
        <EmptyState title="No leads found" description="Try adjusting your filters." />
      ) : view === "kanban" ? (
        <KanbanBoard leads={filteredItems} />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Company</TableHead>
              <TableHead>Job</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>State</TableHead>
              <TableHead>City</TableHead>
              <TableHead>Lead Score</TableHead>
              <TableHead>Opportunity Score</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Priority</TableHead>
              <TableHead>Email Sent</TableHead>
              <TableHead>Reply</TableHead>
              <TableHead>Next Action</TableHead>
              <TableHead>Next Action Date</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredItems.map((lead) => (
              <LeadRow key={lead.lead_id} lead={lead} />
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function LeadRow({ lead }: { lead: Lead }) {
  const router = useRouter();
  return (
    <TableRow className="cursor-pointer" onClick={() => router.push(`/leads/${lead.lead_id}`)}>
      <TableCell>
        <Link href={`/leads/${lead.lead_id}`} className="font-medium text-indigo-600 hover:underline" onClick={(e) => e.stopPropagation()}>
          {lead.company_name || "—"}
        </Link>
      </TableCell>
      <TableCell>{lead.job_title || "—"}</TableCell>
      <TableCell>{lead.source || "—"}</TableCell>
      <TableCell>{"—"}</TableCell>
      <TableCell>{"—"}</TableCell>
      <TableCell>{lead.lead_score ?? "—"}</TableCell>
      <TableCell>{lead.botivate_opportunity_score ?? "—"}</TableCell>
      <TableCell><StatusBadge status={lead.status} /></TableCell>
      <TableCell><StatusBadge status={lead.priority} /></TableCell>
      <TableCell>{lead.email_sent ? "Yes" : "No"}</TableCell>
      <TableCell>{lead.has_reply ? "Yes" : "No"}</TableCell>
      <TableCell>{lead.next_action ? humanize(lead.next_action) : "—"}</TableCell>
      <TableCell>{formatDate(lead.next_action_date)}</TableCell>
    </TableRow>
  );
}
