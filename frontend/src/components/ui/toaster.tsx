"use client";
import * as React from "react";
import { cn } from "@/lib/utils";
import { CheckCircle2, XCircle, Info } from "lucide-react";

type Toast = { id: number; title: string; description?: string; variant?: "success" | "error" | "info" };

const ToastContext = React.createContext<{ push: (t: Omit<Toast, "id">) => void } | null>(null);

export function ToasterProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);

  const push = React.useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { ...t, id }]);
    setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), 4500);
  }, []);

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "flex w-80 items-start gap-2 rounded-lg border bg-white p-3 shadow-lg",
              t.variant === "success" && "border-emerald-200",
              t.variant === "error" && "border-red-200",
              (!t.variant || t.variant === "info") && "border-slate-200"
            )}
          >
            {t.variant === "success" && <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-600" />}
            {t.variant === "error" && <XCircle className="mt-0.5 h-4 w-4 text-red-600" />}
            {(!t.variant || t.variant === "info") && <Info className="mt-0.5 h-4 w-4 text-slate-500" />}
            <div>
              <p className="text-sm font-medium text-slate-900">{t.title}</p>
              {t.description && <p className="text-xs text-slate-500">{t.description}</p>}
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToasterProvider");
  return ctx;
}
