"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createClient } from "@/lib/supabase";
import {
  AlertCircle,
  ArrowLeft,
  ChevronDown,
  Download,
  Loader2,
  RotateCcw,
  Share2,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ResearchSession {
  id: string;
  question: string;
  status: string;
  created_at: string;
  report_markdown?: string;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function ReportSkeleton() {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden animate-pulse">
      {/* Skeleton header */}
      <div className="px-8 py-6 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white space-y-3">
        <div className="h-3 w-28 bg-slate-200 rounded-full" />
        <div className="h-6 w-3/4 bg-slate-200 rounded-full" />
        <div className="h-3 w-36 bg-slate-200 rounded-full" />
      </div>
      {/* Skeleton body */}
      <div className="px-8 py-6 space-y-4">
        <div className="h-3 bg-slate-100 rounded-full w-full" />
        <div className="h-3 bg-slate-100 rounded-full w-5/6" />
        <div className="h-3 bg-slate-100 rounded-full w-4/6" />
        <div className="h-3 bg-slate-100 rounded-full w-full mt-6" />
        <div className="h-3 bg-slate-100 rounded-full w-3/4" />
        <div className="h-3 bg-slate-100 rounded-full w-5/6" />
        <div className="h-3 bg-slate-100 rounded-full w-2/3" />
      </div>
    </div>
  );
}

export default function ReportPage() {
  const params = useParams();
  const router = useRouter();
  const id = params?.id as string;

  const [session, setSession] = useState<ResearchSession | null>(null);
  const [markdown, setMarkdown] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  // Feature C: Share state
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [isSharing, setIsSharing] = useState(false);
  const [showShareModal, setShowShareModal] = useState(false);

  // Feature E: Export dropdown state
  const [exportOpen, setExportOpen] = useState(false);
  const [docxError, setDocxError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    const supabase = createClient();
    supabase.auth.getSession().then(async ({ data }) => {
      const token = data.session?.access_token;
      if (!token) {
        router.push("/auth/login");
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/api/research/${id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          setError("Report not found.");
          setLoading(false);
          return;
        }
        const sessionData: ResearchSession = await res.json();
        setSession(sessionData);
        setMarkdown(
          sessionData.report_markdown ?? "Report is still being generated…"
        );
      } catch {
        setError("Failed to load report.");
      } finally {
        setLoading(false);
      }
    });
  }, [id, router]);

  async function handleDownloadPdf() {
    setDownloading(true);
    try {
      const supabase = createClient();
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token ?? "";

      const res = await fetch(`${API_BASE}/api/research/${id}/export`, {
        headers: { Authorization: `Bearer ${token}`, Accept: "application/pdf" },
      });

      if (!res.ok) {
        setError("PDF export failed.");
        return;
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "report.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }

  // Feature C: Share handler
  async function handleShare() {
    if (shareUrl) {
      setShowShareModal(true);
      return;
    }
    setIsSharing(true);
    try {
      const supabase = createClient();
      const { data: sessionData } = await supabase.auth.getSession();
      const token = sessionData.session?.access_token;
      if (!token) return;
      const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${apiUrl}/api/research/${id}/share`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json() as { public_url: string; public_slug: string };
        setShareUrl(data.public_url);
        setShowShareModal(true);
      }
    } finally {
      setIsSharing(false);
    }
  }

  // Feature E: DOCX download handler
  async function handleDownloadDocx() {
    setExportOpen(false);
    setDocxError(null);
    const supabase = createClient();
    const { data: sessionData } = await supabase.auth.getSession();
    const token = sessionData.session?.access_token;
    if (!token) return;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const res = await fetch(`${apiUrl}/api/research/${id}/export/docx`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.status === 403) {
      setDocxError("DOCX export requires a Pro plan. Upgrade at /pricing.");
      return;
    }
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "report.docx";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] bg-slate-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 space-y-6">

        {/* Top bar */}
        <div className="flex items-center justify-between">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </Link>
          {markdown && !loading && (
            <div className="flex items-center gap-2">
              {/* Feature F: Re-run button */}
              {session?.question && (
                <Link
                  href={`/?q=${encodeURIComponent(session.question)}`}
                  className="inline-flex items-center gap-1.5 bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
                >
                  <RotateCcw className="w-4 h-4" />
                  Re-run
                </Link>
              )}

              {/* Feature C: Share button */}
              <button
                onClick={handleShare}
                disabled={isSharing || !markdown}
                className="inline-flex items-center gap-1.5 bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
              >
                <Share2 className="w-4 h-4" />
                {isSharing ? "Sharing…" : shareUrl ? "Shared ✓" : "Share"}
              </button>

              {/* Feature E: Export dropdown */}
              <div className="relative">
                <button
                  onClick={() => setExportOpen((v) => !v)}
                  disabled={!markdown}
                  className="inline-flex items-center gap-1.5 bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
                >
                  {downloading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Download className="w-4 h-4" />
                  )}
                  Export
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                </button>
                {exportOpen && (
                  <div className="absolute right-0 top-full mt-1 bg-white border border-slate-200 rounded-xl shadow-lg py-1 z-20 min-w-[160px]">
                    <button
                      onClick={() => { handleDownloadPdf(); setExportOpen(false); }}
                      className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                    >
                      PDF (.pdf)
                    </button>
                    <button
                      onClick={handleDownloadDocx}
                      className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center justify-between"
                    >
                      Word (.docx)
                      <span className="text-[10px] bg-indigo-100 text-indigo-600 px-1.5 py-0.5 rounded-full font-semibold ml-2">Pro</span>
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Feature E: DOCX error message */}
        {docxError && (
          <div className="mx-auto max-w-5xl px-4 mt-2">
            <p className="text-sm text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2">
              {docxError} <a href="/pricing" className="underline">View plans</a>
            </p>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div
            role="alert"
            className="flex items-start gap-3 bg-red-50 border border-red-200 rounded-xl px-5 py-4"
          >
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Loading skeleton */}
        {loading && <ReportSkeleton />}

        {/* Report card */}
        {!loading && !error && (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
            {/* Report header */}
            <div className="px-8 py-6 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
              <p className="text-xs font-semibold text-indigo-600 uppercase tracking-wide mb-2">
                Intelligence Report
              </p>
              <h1 className="text-xl font-bold text-slate-900 leading-snug">
                {session?.question ?? "Research Report"}
              </h1>
              {session?.created_at && (
                <p className="text-xs text-slate-400 mt-2">
                  {formatDate(session.created_at)}
                </p>
              )}
            </div>

            {/* Report content */}
            <div className="px-8 py-6">
              <article>
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    h2: ({ children, ...props }) => (
                      <h2
                        className="text-xl font-bold text-slate-900 mt-8 mb-3 pb-2 border-b border-slate-100"
                        {...props}
                      >
                        {children}
                      </h2>
                    ),
                    h3: ({ children, ...props }) => (
                      <h3
                        className="text-base font-semibold text-slate-800 mt-5 mb-2"
                        {...props}
                      >
                        {children}
                      </h3>
                    ),
                    p: ({ children, ...props }) => (
                      <p
                        className="text-slate-700 leading-relaxed mb-4 text-[15px]"
                        {...props}
                      >
                        {children}
                      </p>
                    ),
                    a: ({ href, children, ...props }) => (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-600 underline underline-offset-2 hover:text-indigo-700 decoration-indigo-300 inline-flex items-center gap-0.5"
                        {...props}
                      >
                        {children}
                      </a>
                    ),
                    ul: ({ children, ...props }) => (
                      <ul
                        className="list-disc list-outside ml-5 mb-4 space-y-1.5"
                        {...props}
                      >
                        {children}
                      </ul>
                    ),
                    li: ({ children, ...props }) => (
                      <li
                        className="text-slate-700 leading-relaxed text-[15px]"
                        {...props}
                      >
                        {children}
                      </li>
                    ),
                    blockquote: ({ children, ...props }) => (
                      <blockquote
                        className="border-l-4 border-indigo-200 pl-4 text-slate-600 italic my-4"
                        {...props}
                      >
                        {children}
                      </blockquote>
                    ),
                    table: ({ children, ...props }) => (
                      <div className="overflow-x-auto mb-4">
                        <table
                          className="w-full border-collapse"
                          {...props}
                        >
                          {children}
                        </table>
                      </div>
                    ),
                    th: ({ children, ...props }) => (
                      <th
                        className="bg-slate-50 px-4 py-2 text-left text-xs font-semibold text-slate-600 border border-slate-200"
                        {...props}
                      >
                        {children}
                      </th>
                    ),
                    td: ({ children, ...props }) => (
                      <td
                        className="px-4 py-2 text-sm text-slate-700 border border-slate-200"
                        {...props}
                      >
                        {children}
                      </td>
                    ),
                  }}
                >
                  {markdown}
                </ReactMarkdown>
              </article>
            </div>
          </div>
        )}
      </div>

      {/* Feature C: Share modal */}
      {showShareModal && shareUrl && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setShowShareModal(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-xl p-6 max-w-md w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-semibold text-slate-900 mb-1">Report shared</h3>
            <p className="text-sm text-slate-500 mb-4">
              Anyone with this link can view the full report — no login required.
            </p>
            <div className="flex gap-2">
              <input
                readOnly
                value={shareUrl}
                className="flex-1 text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-700 font-mono"
              />
              <button
                onClick={() => { navigator.clipboard.writeText(shareUrl); }}
                className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors flex-shrink-0"
              >
                Copy
              </button>
            </div>
            <button
              onClick={() => setShowShareModal(false)}
              className="mt-4 text-xs text-slate-400 hover:text-slate-600 w-full text-center"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
