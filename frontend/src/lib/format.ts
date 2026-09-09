export function formatDateTime(iso: string | undefined | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const datePart = d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  const timePart = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
  return `${datePart}, ${timePart}`;
}

export function formatDate(iso: string | undefined | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatRelative(iso: string | undefined | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const diffMs = d.getTime() - Date.now();
  const diffDays = Math.round(diffMs / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Tomorrow";
  if (diffDays === -1) return "Yesterday";
  if (diffDays > 1) return `In ${diffDays} days`;
  return `${Math.abs(diffDays)} days ago`;
}

export const STATUS_COLORS: Record<string, string> = {
  // Lead statuses
  NEW: "bg-slate-100 text-slate-700 border-slate-200",
  QUALIFIED: "bg-blue-50 text-blue-700 border-blue-200",
  EMAIL_DRAFTED: "bg-violet-50 text-violet-700 border-violet-200",
  APPROVED: "bg-indigo-50 text-indigo-700 border-indigo-200",
  QUEUED: "bg-amber-50 text-amber-700 border-amber-200",
  CONTACTED: "bg-cyan-50 text-cyan-700 border-cyan-200",
  REPLIED: "bg-emerald-50 text-emerald-700 border-emerald-200",
  FOLLOW_UP_DUE: "bg-orange-50 text-orange-700 border-orange-200",
  FOLLOW_UP_SENT: "bg-teal-50 text-teal-700 border-teal-200",
  IN_CONVERSATION: "bg-sky-50 text-sky-700 border-sky-200",
  MEETING_REQUESTED: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
  MEETING_SCHEDULED: "bg-purple-50 text-purple-700 border-purple-200",
  MEETING_COMPLETED: "bg-purple-100 text-purple-800 border-purple-300",
  PROPOSAL_SENT: "bg-pink-50 text-pink-700 border-pink-200",
  INTERESTED: "bg-green-50 text-green-700 border-green-200",
  NOT_INTERESTED: "bg-red-50 text-red-700 border-red-200",
  BOUNCED: "bg-rose-100 text-rose-800 border-rose-300",
  NO_RESPONSE: "bg-gray-100 text-gray-600 border-gray-200",
  SUPPRESSED: "bg-zinc-200 text-zinc-700 border-zinc-300",
  WON: "bg-green-100 text-green-800 border-green-300",
  LOST: "bg-red-100 text-red-800 border-red-300",
  CLOSED: "bg-slate-200 text-slate-700 border-slate-300",
  // Queue statuses
  PENDING: "bg-amber-50 text-amber-700 border-amber-200",
  PROCESSING: "bg-blue-50 text-blue-700 border-blue-200",
  SENT: "bg-emerald-50 text-emerald-700 border-emerald-200",
  RETRY: "bg-orange-50 text-orange-700 border-orange-200",
  FAILED: "bg-red-50 text-red-700 border-red-200",
  CANCELLED: "bg-gray-100 text-gray-600 border-gray-200",
  SKIPPED: "bg-zinc-100 text-zinc-600 border-zinc-200",
  // Follow-up
  DRAFT: "bg-slate-100 text-slate-700 border-slate-200",
  SCHEDULED: "bg-blue-50 text-blue-700 border-blue-200",
  DUE: "bg-orange-50 text-orange-700 border-orange-200",
  // Reply types
  REQUEST_FOR_DETAILS: "bg-blue-50 text-blue-700 border-blue-200",
  MEETING_REQUEST: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
  POSITIVE: "bg-green-50 text-green-700 border-green-200",
  NEUTRAL: "bg-gray-100 text-gray-600 border-gray-200",
  ASK_LATER: "bg-amber-50 text-amber-700 border-amber-200",
  OUT_OF_OFFICE: "bg-slate-100 text-slate-600 border-slate-200",
  BOUNCE: "bg-rose-100 text-rose-800 border-rose-300",
  UNSUBSCRIBE: "bg-zinc-200 text-zinc-700 border-zinc-300",
  UNKNOWN: "bg-gray-100 text-gray-500 border-gray-200",
  // Priority
  LOW: "bg-slate-100 text-slate-600 border-slate-200",
  MEDIUM: "bg-amber-50 text-amber-700 border-amber-200",
  HIGH: "bg-orange-50 text-orange-700 border-orange-200",
  URGENT: "bg-red-50 text-red-700 border-red-200",
};

export function statusColor(status: string | undefined | null): string {
  if (!status) return "bg-gray-100 text-gray-500 border-gray-200";
  return STATUS_COLORS[status] || "bg-gray-100 text-gray-600 border-gray-200";
}

export function humanize(value: string | undefined | null): string {
  if (!value) return "—";
  return value
    .split("_")
    .map((w) => w.charAt(0) + w.slice(1).toLowerCase())
    .join(" ");
}

export function toCsv(rows: Record<string, unknown>[]): string {
  if (rows.length === 0) return "";
  const headers = Object.keys(rows[0]);
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    if (s.includes(",") || s.includes('"') || s.includes("\n")) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  };
  const lines = [headers.join(",")];
  for (const row of rows) {
    lines.push(headers.map((h) => escape(row[h])).join(","));
  }
  return lines.join("\n");
}

export function downloadCsv(filename: string, rows: Record<string, unknown>[]): void {
  const csv = toCsv(rows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
