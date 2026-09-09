import { Inbox } from "lucide-react";

export function EmptyState({ title = "No records yet", description }: { title?: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white py-16 text-center">
      <Inbox className="mb-3 h-8 w-8 text-slate-300" />
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {description && <p className="mt-1 max-w-sm text-xs text-slate-500">{description}</p>}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-red-200 bg-red-50 py-16 text-center">
      <p className="text-sm font-medium text-red-700">Could not load data</p>
      <p className="mt-1 max-w-sm text-xs text-red-500">{message}</p>
    </div>
  );
}
