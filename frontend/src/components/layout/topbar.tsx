"use client";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useRouter } from "next/navigation";
import { useState } from "react";

export function Topbar() {
  const router = useRouter();
  const [q, setQ] = useState("");

  function onSearch(e: React.FormEvent) {
    e.preventDefault();
    if (q.trim()) router.push(`/leads?search=${encodeURIComponent(q.trim())}`);
  }

  return (
    <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-6">
      <form onSubmit={onSearch} className="relative w-96 max-w-full">
        <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search company, email, job title, city, domain, thread ID…"
          className="pl-8"
        />
      </form>
      <div className="text-xs text-slate-400">Botivate Services LLP</div>
    </header>
  );
}
