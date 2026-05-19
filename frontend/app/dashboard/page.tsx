"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase";
import {
  ArrowRight,
  FileText,
  Loader2,
  Plus,
  RotateCcw,
  Sparkles,
  TrendingUp,
} from "lucide-react";

interface Session {
  id: string;
  question: string;
  status: string;
  created_at: string;
}

const FREE_LIMIT = 3;
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function StatusBadge({ status }: { status: string }) {
  if (status === "completed")
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700">
        Completed
      </span>
    );
  if (status === "running")
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-50 text-indigo-700">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
        Running
      </span>
    );
  if (status === "failed")
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-red-50 text-red-700">
        Failed
      </span>
    );
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-500">
      Queued
    </span>
  );
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function DashboardPage() {
  const router = useRouter();
  const [userEmail, setUserEmail] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [isPro, setIsPro] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(async ({ data }) => {
      if (!data.user) { router.push("/auth/login"); return; }
      setUserEmail(data.user.email ?? "");
      const { data: sessionData } = await supabase.auth.getSession();
      const token = sessionData.session?.access_token ?? "";
      try {
        const res = await fetch(`${API_BASE}/api/research/sessions`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) setSessions(await res.json());
      } catch {}
      setLoading(false);
    });
  }, [router]);

  async function handleSignOut() {
    await createClient().auth.signOut();
    router.push("/auth/login");
  }

  async function handleUpgrade() {
    const { data } = await createClient().auth.getSession();
    const token = data.session?.access_token ?? "";
    const res = await fetch(`${API_BASE}/api/billing/checkout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const { checkout_url } = await res.json();
      window.location.href = checkout_url;
    }
  }

  const reportsUsed = sessions.length;
  const usagePct = Math.min((reportsUsed / FREE_LIMIT) * 100, 100);
  const atLimit = !isPro && reportsUsed >= FREE_LIMIT;

  return (
    <div className="min-h-[calc(100vh-3.5rem)] bg-slate-50/70">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10 space-y-8">

        {/* Page header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-[28px] font-bold text-slate-900 tracking-tight">Dashboard</h1>
            {userEmail && (
              <p className="text-sm text-slate-400 mt-0.5">{userEmail}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-xl transition-colors"
            >
              <Plus className="w-4 h-4" />
              New research
            </Link>
            <button
              onClick={handleSignOut}
              className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 hover:bg-white rounded-xl border border-slate-200 transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {/* Reports */}
          <div className="bg-white rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.04)] p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Reports this month</span>
              <FileText className="w-4 h-4 text-slate-300" />
            </div>
            <p className="text-5xl font-bold text-slate-900 tracking-tight leading-none">{reportsUsed}</p>
            <p className="text-xs text-slate-400 mt-2">
              {isPro ? "Unlimited — Pro plan" : `of ${FREE_LIMIT} free`}
            </p>
          </div>

          {/* Completed */}
          <div className="bg-white rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.04)] p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Completed</span>
              <TrendingUp className="w-4 h-4 text-slate-300" />
            </div>
            <p className="text-5xl font-bold text-slate-900 tracking-tight leading-none">
              {sessions.filter((s) => s.status === "completed").length}
            </p>
            <p className="text-xs text-slate-400 mt-2">intelligence reports</p>
          </div>

          {/* Plan */}
          <div className={`rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.04)] p-6 ${
            atLimit ? "bg-amber-50" : "bg-white"
          }`}>
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Plan</span>
              <Sparkles className="w-4 h-4 text-slate-300" />
            </div>
            {isPro ? (
              <p className="text-sm font-semibold text-emerald-700 leading-none">Pro — unlimited</p>
            ) : (
              <>
                <div className="mb-4">
                  <div className="flex justify-between text-xs text-slate-400 mb-2">
                    <span>{reportsUsed} used</span>
                    <span>{Math.max(FREE_LIMIT - reportsUsed, 0)} left</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${atLimit ? "bg-amber-500" : "bg-indigo-600"}`}
                      style={{ width: `${usagePct}%` }}
                    />
                  </div>
                </div>
                <button
                  onClick={handleUpgrade}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
                >
                  Upgrade to Pro — $29/mo
                  <ArrowRight className="w-3 h-3" />
                </button>
              </>
            )}
          </div>
        </div>

        {/* Sessions list */}
        <div className="bg-white rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.04)] overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Research Reports</h2>
            <span className="text-xs text-slate-400 tabular-nums">{sessions.length} total</span>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20 text-slate-400 gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Loading reports…</span>
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center px-4">
              <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                <FileText className="w-6 h-6 text-slate-300" />
              </div>
              <p className="text-sm font-semibold text-slate-700 mb-1">No reports yet</p>
              <p className="text-sm text-slate-400 mb-6">Your research reports will appear here</p>
              <Link
                href="/"
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-xl transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                Start your first research
              </Link>
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {sessions.map((s, i) => (
                <li
                  key={s.id}
                  className="px-6 py-4 flex items-center gap-4 hover:bg-slate-50/70 transition-colors animate-fade-up"
                  style={{ animationDelay: `${i * 35}ms` }}
                >
                  <div className="w-8 h-8 rounded-xl bg-indigo-50 flex items-center justify-center flex-shrink-0">
                    <FileText className="w-4 h-4 text-indigo-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">{s.question}</p>
                    <p className="text-xs text-slate-400 mt-0.5 tabular-nums">{formatDate(s.created_at)}</p>
                  </div>
                  <StatusBadge status={s.status} />
                  <div className="flex items-center gap-3 flex-shrink-0">
                    {s.status === "completed" && (
                      <Link
                        href={`/dashboard/report/${s.id}`}
                        className="text-xs font-medium text-indigo-600 hover:text-indigo-700 flex items-center gap-1 transition-colors"
                      >
                        View <ArrowRight className="w-3 h-3" />
                      </Link>
                    )}
                    {s.status === "running" && (
                      <Link
                        href={`/research/${s.id}`}
                        className="text-xs font-medium text-indigo-600 hover:text-indigo-700 flex items-center gap-1 transition-colors"
                      >
                        Watch <ArrowRight className="w-3 h-3" />
                      </Link>
                    )}
                    <Link
                      href={`/?q=${encodeURIComponent(s.question)}`}
                      className="text-xs text-slate-400 hover:text-indigo-600 flex items-center gap-1 transition-colors"
                    >
                      <RotateCcw className="w-3 h-3" />
                      Re-run
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
