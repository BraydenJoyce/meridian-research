"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Loader2, Search } from "lucide-react";
import { createClient } from "@/lib/supabase";

const MIN_LENGTH = 10;
const MAX_LENGTH = 2000;

interface CreateResearchResponse {
  session_id: string;
  status: string;
  stream_url: string;
}

interface ApiErrorResponse {
  error: string;
  detail: string;
}

export function ResearchForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [question, setQuestion] = useState(searchParams.get("q") ?? "");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Keep textarea in sync if the URL param changes (e.g., follow-up question clicked)
  useEffect(() => {
    const q = searchParams.get("q");
    if (q) setQuestion(q);
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (question.trim().length < MIN_LENGTH) {
      setError(`Question must be at least ${MIN_LENGTH} characters.`);
      return;
    }

    setIsSubmitting(true);

    try {
      const supabase = createClient();
      const { data: sessionData } = await supabase.auth.getSession();
      const token = sessionData.session?.access_token;

      if (!token) {
        setError("You must be logged in to start a research session.");
        setIsSubmitting(false);
        return;
      }

      const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const response = await fetch(`${apiUrl}/api/research/create`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question: question.trim() }),
      });

      if (!response.ok) {
        const body = (await response.json()) as ApiErrorResponse;
        setError(body.detail ?? "Something went wrong. Please try again.");
        return;
      }

      const data = (await response.json()) as CreateResearchResponse;
      router.push(`/research/${data.session_id}?q=${encodeURIComponent(question.trim())}`);
    } catch {
      setError("Network error. Please check your connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const charCount = question.length;
  const isOverLimit = charCount > MAX_LENGTH;

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <div
        className={`bg-white rounded-xl border shadow-sm overflow-hidden transition-colors ${
          error
            ? "border-red-300"
            : "border-slate-200 focus-within:border-indigo-400 focus-within:shadow-md"
        }`}
      >
        <textarea
          placeholder="e.g. What are the competitive dynamics in the B2B SaaS CRM market in 2025, and which players are taking share?"
          value={question}
          onChange={(e) => {
            setQuestion(e.target.value);
            if (error) setError(null);
          }}
          rows={4}
          disabled={isSubmitting}
          className="w-full p-4 text-[15px] text-slate-900 placeholder:text-slate-400 leading-relaxed resize-none focus:outline-none bg-transparent"
          aria-label="Research question"
        />
        <div className="px-4 py-3 bg-slate-50/80 border-t border-slate-100 flex items-center justify-between gap-3">
          <span className={`text-xs font-medium ${isOverLimit ? "text-red-500" : "text-slate-400"}`}>
            {charCount.toLocaleString()} / {MAX_LENGTH.toLocaleString()}
          </span>
          <button
            type="submit"
            disabled={isSubmitting || isOverLimit || question.trim().length < MIN_LENGTH}
            className="inline-flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
          >
            {isSubmitting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            {isSubmitting ? "Starting…" : "Research"}
          </button>
        </div>
      </div>
      {error && (
        <div className="flex items-start gap-2 mt-2.5 text-sm text-red-600">
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          {error}
        </div>
      )}
    </form>
  );
}
