"use client";
import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { api, fetcher } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState, ErrorState } from "@/components/shared/empty-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge, Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Textarea, Label } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toaster";
import { ConversationThread } from "@/components/inbox/conversation-thread";
import { formatDateTime, humanize } from "@/lib/format";
import type {
  LeadDetail, LeadStatus, EmailDraft, ActivityLogEntry, ConversationMessage,
} from "@/lib/types";
import {
  Globe, Sparkles, CalendarClock, RefreshCcw, ClipboardEdit, StickyNote,
  Check, X, Send, Pencil, Mail, MessageSquare, UserPlus,
  Activity as ActivityIcon, FileText, PhoneCall, Clock, Loader2,
} from "lucide-react";

const LEAD_STATUSES: LeadStatus[] = [
  "NEW", "QUALIFIED", "EMAIL_DRAFTED", "APPROVED", "QUEUED", "CONTACTED",
  "REPLIED", "FOLLOW_UP_DUE", "FOLLOW_UP_SENT", "IN_CONVERSATION",
  "MEETING_REQUESTED", "MEETING_SCHEDULED", "MEETING_COMPLETED", "PROPOSAL_SENT",
  "INTERESTED", "NOT_INTERESTED", "BOUNCED", "NO_RESPONSE", "SUPPRESSED",
  "WON", "LOST", "CLOSED",
];

const ACTIVITY_ICONS: Record<string, typeof ActivityIcon> = {
  EMAIL_SENT: Mail,
  EMAIL_DRAFTED: FileText,
  EMAIL_APPROVED: Check,
  EMAIL_REJECTED: X,
  EMAIL_QUEUED: Clock,
  REPLY_RECEIVED: MessageSquare,
  FOLLOW_UP_SCHEDULED: CalendarClock,
  FOLLOW_UP_SENT: Send,
  STATUS_CHANGED: RefreshCcw,
  NOTE_ADDED: StickyNote,
  CALL: PhoneCall,
  LEAD_CREATED: UserPlus,
};

export function LeadDetailClient({ id }: { id: string }) {
  const { push } = useToast();
  const { data: lead, error, isLoading, mutate } = useSWR<LeadDetail>(`/api/leads/${id}`, fetcher);

  const [statusOpen, setStatusOpen] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [generating, setGenerating] = useState(false);

  async function handleGenerateEmail() {
    setGenerating(true);
    try {
      await api.post(`/api/leads/${id}/generate-email`);
      push({ title: "Email generation started", variant: "success" });
      mutate();
    } catch (e) {
      push({ title: "Failed to generate email", description: (e as Error).message, variant: "error" });
    } finally {
      setGenerating(false);
    }
  }

  if (error) return <ErrorState message={error.message} />;
  if (isLoading || !lead) {
    return (
      <div>
        <PageHeader title="Lead" description="Loading…" />
      </div>
    );
  }

  const website = lead.company?.official_website;
  const location = [lead.company?.city || lead.job?.city, lead.company?.state || lead.job?.state]
    .filter(Boolean)
    .join(", ");

  return (
    <div>
      <PageHeader
        title={lead.company_name || lead.company?.company_name || "Lead"}
        description={lead.job_title || lead.job?.job_title}
      />

      <Card className="mb-4">
        <CardContent className="flex flex-col gap-4 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold text-slate-900">
                {lead.company_name || lead.company?.company_name || "—"}
              </h2>
              <p className="text-sm text-slate-500">{lead.job_title || lead.job?.job_title || "—"}</p>
              {location && <p className="text-xs text-slate-400">{location}</p>}
            </div>
            <div className="flex items-center gap-2">
              <Badge className="border-indigo-200 bg-indigo-50 text-indigo-700">
                Lead Score {lead.lead_score ?? 0}
              </Badge>
              <Badge className="border-violet-200 bg-violet-50 text-violet-700">
                Opportunity {lead.botivate_opportunity_score ?? 0}
              </Badge>
              <StatusBadge status={lead.status} />
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Dialog open={statusOpen} onOpenChange={setStatusOpen}>
              <DialogTrigger asChild>
                <Button type="button" variant="outline" size="sm">
                  <RefreshCcw className="h-4 w-4" /> Change Status
                </Button>
              </DialogTrigger>
              <DialogContent>
                <ChangeStatusForm
                  leadId={id}
                  currentStatus={lead.status}
                  onDone={() => {
                    setStatusOpen(false);
                    mutate();
                  }}
                />
              </DialogContent>
            </Dialog>

            <Dialog open={noteOpen} onOpenChange={setNoteOpen}>
              <DialogTrigger asChild>
                <Button type="button" variant="outline" size="sm">
                  <ClipboardEdit className="h-4 w-4" /> Add Note
                </Button>
              </DialogTrigger>
              <DialogContent>
                <AddNoteForm
                  leadId={id}
                  onDone={() => {
                    setNoteOpen(false);
                    mutate();
                  }}
                />
              </DialogContent>
            </Dialog>

            {website ? (
              <a href={website} target="_blank" rel="noopener noreferrer">
                <Button type="button" variant="outline" size="sm">
                  <Globe className="h-4 w-4" /> Open Website
                </Button>
              </a>
            ) : null}

            <Button type="button" variant="primary" size="sm" onClick={handleGenerateEmail} disabled={generating}>
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Generate Email
            </Button>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="email">Email</TabsTrigger>
          <TabsTrigger value="conversation">Conversation</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab lead={lead} />
        </TabsContent>

        <TabsContent value="email">
          <EmailTab drafts={lead.email_drafts || []} mutate={mutate} />
        </TabsContent>

        <TabsContent value="conversation">
          <ConversationTab leadId={id} />
        </TabsContent>

        <TabsContent value="activity">
          <ActivityTab activity={lead.activity || []} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ---------- Action forms ----------

function ChangeStatusForm({
  leadId,
  currentStatus,
  onDone,
}: {
  leadId: string;
  currentStatus: LeadStatus;
  onDone: () => void;
}) {
  const { push } = useToast();
  const [status, setStatus] = useState<LeadStatus>(currentStatus);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    setSubmitting(true);
    try {
      await api.patch(`/api/leads/${leadId}`, { status });
      push({ title: "Status updated", variant: "success" });
      onDone();
    } catch (e) {
      push({ title: "Failed to update status", description: (e as Error).message, variant: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <DialogHeader>
        <DialogTitle>Change Status</DialogTitle>
      </DialogHeader>
      <Select value={status} onValueChange={(v) => setStatus(v as LeadStatus)}>
        <SelectTrigger><SelectValue /></SelectTrigger>
        <SelectContent>
          {LEAD_STATUSES.map((s) => (
            <SelectItem key={s} value={s}>{humanize(s)}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <DialogFooter>
        <Button type="button" variant="primary" onClick={handleSubmit} disabled={submitting}>
          {submitting ? "Saving…" : "Save"}
        </Button>
      </DialogFooter>
    </div>
  );
}

function AddNoteForm({ leadId, onDone }: { leadId: string; onDone: () => void }) {
  const { push } = useToast();
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!note.trim()) return;
    setSubmitting(true);
    try {
      await api.post(`/api/leads/${leadId}/notes`, { note, created_by: "rnd@botivate.in" });
      push({ title: "Note added", variant: "success" });
      onDone();
    } catch (e) {
      push({ title: "Failed to add note", description: (e as Error).message, variant: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <DialogHeader>
        <DialogTitle>Add Note</DialogTitle>
      </DialogHeader>
      <Textarea rows={4} placeholder="Note…" value={note} onChange={(e) => setNote(e.target.value)} />
      <DialogFooter>
        <Button type="submit" variant="primary" disabled={submitting || !note.trim()}>
          {submitting ? "Saving…" : "Save Note"}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ---------- Tabs ----------

function OverviewTab({ lead }: { lead: LeadDetail }) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>Company</CardTitle></CardHeader>
        <CardContent className="space-y-1 text-sm text-slate-700">
          <p><span className="text-slate-400">Name:</span> {lead.company?.company_name || "—"}</p>
          <p><span className="text-slate-400">Industry:</span> {lead.company?.industry || "—"}</p>
          <p><span className="text-slate-400">Location:</span> {[lead.company?.city, lead.company?.state].filter(Boolean).join(", ") || "—"}</p>
          <p><span className="text-slate-400">Website:</span> {lead.company?.official_website || "—"}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Job</CardTitle></CardHeader>
        <CardContent className="space-y-1 text-sm text-slate-700">
          <p><span className="text-slate-400">Title:</span> {lead.job?.job_title || "—"}</p>
          <p><span className="text-slate-400">Source:</span> {lead.job?.source || lead.source || "—"}</p>
          <p><span className="text-slate-400">Location:</span> {[lead.job?.city, lead.job?.state].filter(Boolean).join(", ") || "—"}</p>
          <p><span className="text-slate-400">Posted:</span> {lead.job?.posted_date || "—"}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Contact</CardTitle></CardHeader>
        <CardContent className="space-y-1 text-sm text-slate-700">
          <p><span className="text-slate-400">Name:</span> {lead.contact?.contact_name || "—"}</p>
          <p><span className="text-slate-400">Designation:</span> {lead.contact?.designation || "—"}</p>
          <p><span className="text-slate-400">Email:</span> {lead.contact?.email || "—"}</p>
          <p><span className="text-slate-400">Phone:</span> {lead.contact?.phone || "—"}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Signals & Recommendation</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm text-slate-700">
          <p><span className="text-slate-400">Automation Signals:</span> {lead.automation_signals || "—"}</p>
          <p><span className="text-slate-400">Pain Points:</span> {lead.pain_points || "—"}</p>
          <p className="flex items-center gap-2">
            <span className="text-slate-400">Recommended Solution:</span>
            <StatusBadge status={lead.recommended_solution} />
          </p>
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader><CardTitle>Next Steps</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 gap-3 text-sm text-slate-700 sm:grid-cols-4">
          <p><span className="block text-slate-400">Next Action</span>{humanize(lead.next_action) || "—"}</p>
          <p><span className="block text-slate-400">Next Action Date</span>{formatDateTime(lead.next_action_date)}</p>
          <p><span className="block text-slate-400">Owner</span>{lead.owner || "—"}</p>
          <p className="flex flex-col gap-1"><span className="text-slate-400">Priority</span><StatusBadge status={lead.priority} /></p>
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader><CardTitle>Notes</CardTitle></CardHeader>
        <CardContent>
          {!lead.notes?.length ? (
            <EmptyState title="No notes yet" />
          ) : (
            <div className="space-y-2">
              {lead.notes.map((n) => (
                <div key={n.note_id} className="rounded-lg border border-slate-100 p-3 text-sm">
                  <p className="text-slate-700">{n.note}</p>
                  <p className="mt-1 text-xs text-slate-400">{n.created_by} · {formatDateTime(n.created_at)}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function EmailTab({ drafts, mutate }: { drafts: EmailDraft[]; mutate: () => void }) {
  if (!drafts.length) return <EmptyState title="No email drafts yet" description="Generate an email to get started." />;
  return (
    <div className="flex flex-col gap-3">
      {drafts.map((d) => (
        <EmailDraftCard key={d.email_id} draft={d} mutate={mutate} />
      ))}
    </div>
  );
}

function EmailDraftCard({ draft, mutate }: { draft: EmailDraft; mutate: () => void }) {
  const { push } = useToast();
  const [expanded, setExpanded] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [queueOpen, setQueueOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>, successMsg: string) {
    setBusy(true);
    try {
      await action();
      push({ title: successMsg, variant: "success" });
      mutate();
    } catch (e) {
      push({ title: "Action failed", description: (e as Error).message, variant: "error" });
    } finally {
      setBusy(false);
    }
  }

  const preview = draft.plain_text_body || "";
  const isLong = preview.length > 300;

  return (
    <Card>
      <CardContent className="p-5">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <StatusBadge status={draft.status} />
          <span className="text-xs text-slate-400">{formatDateTime(draft.created_at)}</span>
        </div>
        <p className="mb-1 text-sm font-semibold text-slate-900">{draft.subject}</p>
        <p className="mb-0.5 text-xs text-slate-500">From: {draft.sender_email || "(not set)"}</p>
        <p className="mb-2 text-xs text-slate-500">To: {draft.recipient_email}</p>
        <div className={`whitespace-pre-wrap rounded-lg border border-slate-100 bg-slate-50 p-3 text-sm text-slate-700 ${expanded ? "" : "max-h-32 overflow-hidden"}`}>
          {isLong && !expanded ? `${preview.slice(0, 300)}…` : preview}
        </div>
        {isLong && (
          <button
            type="button"
            className="mt-1 text-xs font-medium text-indigo-600 hover:underline"
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Show less" : "Show more"}
          </button>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          <Dialog open={editOpen} onOpenChange={setEditOpen}>
            <DialogTrigger asChild>
              <Button type="button" size="sm" variant="outline" disabled={busy}>
                <Pencil className="h-4 w-4" /> Edit
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <EmailEditForm
                draft={draft}
                onSubmit={async (payload) => {
                  await run(() => api.patch(`/api/emails/${draft.email_id}`, payload), "Email updated");
                  setEditOpen(false);
                }}
              />
            </DialogContent>
          </Dialog>

          <Button
            type="button"
            size="sm"
            variant="success"
            disabled={busy}
            onClick={() => run(() => api.post(`/api/emails/${draft.email_id}/approve`), "Email approved")}
          >
            <Check className="h-4 w-4" /> Approve
          </Button>

          <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
            <DialogTrigger asChild>
              <Button type="button" size="sm" variant="destructive" disabled={busy}>
                <X className="h-4 w-4" /> Reject
              </Button>
            </DialogTrigger>
            <DialogContent>
              <RejectForm
                onSubmit={async (reason) => {
                  await run(() => api.post(`/api/emails/${draft.email_id}/reject`, { reason }), "Email rejected");
                  setRejectOpen(false);
                }}
              />
            </DialogContent>
          </Dialog>

          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => run(() => api.post(`/api/emails/${draft.email_id}/regenerate`), "Email regenerated")}
          >
            <RefreshCcw className="h-4 w-4" /> Regenerate
          </Button>

          <Dialog open={queueOpen} onOpenChange={setQueueOpen}>
            <DialogTrigger asChild>
              <Button type="button" size="sm" variant="primary" disabled={busy}>
                <Send className="h-4 w-4" /> Queue
              </Button>
            </DialogTrigger>
            <DialogContent>
              <QueueForm
                onSubmit={async (payload) => {
                  await run(() => api.post(`/api/emails/${draft.email_id}/queue`, payload), "Email queued");
                  setQueueOpen(false);
                }}
              />
            </DialogContent>
          </Dialog>
        </div>
      </CardContent>
    </Card>
  );
}

function RejectForm({ onSubmit }: { onSubmit: (reason: string) => Promise<void> }) {
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  return (
    <div>
      <DialogHeader>
        <DialogTitle>Reject Email</DialogTitle>
        <DialogDescription>Optionally provide a reason.</DialogDescription>
      </DialogHeader>
      <Textarea rows={3} placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <DialogFooter>
        <Button
          type="button"
          variant="destructive"
          disabled={submitting}
          onClick={async () => {
            setSubmitting(true);
            await onSubmit(reason);
            setSubmitting(false);
          }}
        >
          Reject
        </Button>
      </DialogFooter>
    </div>
  );
}

function EmailEditForm({
  draft,
  onSubmit,
}: {
  draft: EmailDraft;
  onSubmit: (payload: {
    sender_email: string;
    recipient_email: string;
    subject: string;
    plain_text_body: string;
  }) => Promise<void>;
}) {
  const [senderEmail, setSenderEmail] = useState(draft.sender_email || "");
  const [recipientEmail, setRecipientEmail] = useState(draft.recipient_email || "");
  const [subject, setSubject] = useState(draft.subject || "");
  const [body, setBody] = useState(draft.plain_text_body || "");
  const [submitting, setSubmitting] = useState(false);

  return (
    <div>
      <DialogHeader>
        <DialogTitle>Edit Email</DialogTitle>
        <DialogDescription>
          Nothing is sent until you Approve and Queue. In test mode, the actual send is
          redirected to the configured test inbox regardless of the recipient shown here.
        </DialogDescription>
      </DialogHeader>
      <div className="flex flex-col gap-3">
        <div>
          <Label>From (sender)</Label>
          <Input value={senderEmail} onChange={(e) => setSenderEmail(e.target.value)} placeholder="sender@botivate.in" />
        </div>
        <div>
          <Label>To (recipient)</Label>
          <Input value={recipientEmail} onChange={(e) => setRecipientEmail(e.target.value)} placeholder="contact@company.com" />
        </div>
        <div>
          <Label>Subject</Label>
          <Input value={subject} onChange={(e) => setSubject(e.target.value)} />
        </div>
        <div>
          <Label>Body</Label>
          <Textarea rows={10} value={body} onChange={(e) => setBody(e.target.value)} />
        </div>
      </div>
      <DialogFooter>
        <Button
          type="button"
          variant="primary"
          disabled={submitting}
          onClick={async () => {
            setSubmitting(true);
            await onSubmit({
              sender_email: senderEmail,
              recipient_email: recipientEmail,
              subject,
              plain_text_body: body,
            });
            setSubmitting(false);
          }}
        >
          Save Changes
        </Button>
      </DialogFooter>
    </div>
  );
}

function QueueForm({
  onSubmit,
}: {
  onSubmit: (payload: { scheduled_at?: string; priority?: string }) => Promise<void>;
}) {
  const [scheduledAt, setScheduledAt] = useState("");
  const [priority, setPriority] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  return (
    <div>
      <DialogHeader>
        <DialogTitle>Queue Email</DialogTitle>
      </DialogHeader>
      <div className="flex flex-col gap-3">
        <div>
          <Label>Scheduled At (optional)</Label>
          <Input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} />
        </div>
        <div>
          <Label>Priority (optional)</Label>
          <Select value={priority || undefined} onValueChange={setPriority}>
            <SelectTrigger><SelectValue placeholder="Select priority" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="LOW">Low</SelectItem>
              <SelectItem value="MEDIUM">Medium</SelectItem>
              <SelectItem value="HIGH">High</SelectItem>
              <SelectItem value="URGENT">Urgent</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <DialogFooter>
        <Button
          type="button"
          variant="primary"
          disabled={submitting}
          onClick={async () => {
            setSubmitting(true);
            await onSubmit({
              ...(scheduledAt ? { scheduled_at: new Date(scheduledAt).toISOString() } : {}),
              ...(priority ? { priority } : {}),
            });
            setSubmitting(false);
          }}
        >
          Queue
        </Button>
      </DialogFooter>
    </div>
  );
}

function ConversationTab({ leadId }: { leadId: string }) {
  const { data, error, isLoading } = useSWR<ConversationMessage[] | { items?: ConversationMessage[] }>(
    `/api/conversations/${leadId}`,
    fetcher
  );

  if (error) return <ErrorState message={error.message} />;
  if (isLoading) return null;

  const messages: ConversationMessage[] = Array.isArray(data) ? data : data?.items || [];
  if (!messages.length) return <EmptyState title="No conversation yet" description="No messages have been exchanged for this lead." />;

  return <ConversationThread messages={messages} />;
}

function ActivityTab({ activity }: { activity: ActivityLogEntry[] }) {
  if (!activity.length) return <EmptyState title="No activity recorded yet" />;
  return (
    <div className="flex flex-col gap-0">
      {activity.map((a, idx) => {
        const Icon = ACTIVITY_ICONS[a.activity_type] || ActivityIcon;
        return (
          <div key={a.activity_id} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-indigo-600">
                <Icon className="h-4 w-4" />
              </span>
              {idx < activity.length - 1 && <span className="w-px flex-1 bg-slate-200" />}
            </div>
            <div className="pb-6">
              <p className="text-sm font-medium text-slate-800">{a.description}</p>
              <p className="text-xs text-slate-400">{formatDateTime(a.created_at)} · {a.created_by}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
