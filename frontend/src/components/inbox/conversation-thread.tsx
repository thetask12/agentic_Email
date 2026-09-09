"use client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toaster";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Copy } from "lucide-react";
import type { ConversationMessage } from "@/lib/types";

export function ConversationThread({ messages }: { messages: ConversationMessage[] }) {
  const { push } = useToast();

  async function copySuggested(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      push({ title: "Copied", variant: "success" });
    } catch {
      push({ title: "Could not copy", variant: "error" });
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {messages.map((m, idx) => {
        const outbound = m.direction === "OUTBOUND";
        return (
          <div key={m.message_id || idx} className={cn("flex", outbound ? "justify-end" : "justify-start")}>
            <Card
              className={cn(
                "max-w-2xl p-4",
                outbound ? "border-indigo-200 bg-indigo-50" : "border-slate-200 bg-slate-50"
              )}
            >
              <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium text-slate-500">
                  {outbound ? "Sent" : "Received"} · {formatDateTime(m.timestamp)}
                </span>
                <div className="flex items-center gap-1.5">
                  {m.reply_type && <StatusBadge status={m.reply_type} />}
                  {m.sentiment && <StatusBadge status={m.sentiment} />}
                </div>
              </div>
              {m.subject && <p className="mb-1 text-sm font-semibold text-slate-900">{m.subject}</p>}
              <p className="whitespace-pre-wrap text-sm text-slate-700">{m.body}</p>
              {m.ai_summary && (
                <p className="mt-2 text-xs italic text-slate-500">Summary: {m.ai_summary}</p>
              )}
              {m.suggested_response && (
                <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Suggested Response
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => copySuggested(m.suggested_response as string)}
                    >
                      <Copy className="h-3.5 w-3.5" /> Copy
                    </Button>
                  </div>
                  <p className="whitespace-pre-wrap text-sm text-slate-700">{m.suggested_response}</p>
                </div>
              )}
            </Card>
          </div>
        );
      })}
    </div>
  );
}
