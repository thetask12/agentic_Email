import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { TestModeBanner } from "./test-mode-banner";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-slate-50">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TestModeBanner />
        <Topbar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
