"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users } from "lucide-react";
import { cn } from "@/lib/utils";

// Per user request: a deliberately simple two-page flow — search from the
// Dashboard, review everything in the Leads list/detail. Every other page
// (Search Runs, Sources, Jobs, Companies, Outreach, Follow-ups, Inbox,
// Email Queue, Campaigns, Analytics, Activity, Settings) was removed
// outright, not just hidden from nav.
const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/leads", label: "Leads", icon: Users },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex">
      <div className="flex h-14 items-center gap-2 border-b border-slate-100 px-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-indigo-600 text-xs font-bold text-white">B</div>
        <span className="text-sm font-semibold text-slate-900">Botivate Outreach</span>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {NAV.map((item) => {
          const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
