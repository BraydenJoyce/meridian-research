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

interface ResearchFormProps {
  variant?: "dark" | "light";
}

export function ResearchForm({ variant = "light" }: ResearchFormProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [question, setQuestion] = useState(searchParams.get("q") ?? "");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const dark = variant === "dark";

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
        className={`rounded-2xl overflow-hidden transition-all ${
          dark
            ? "bg-white/[0.07] backdrop-blur-xl border border-white/[0.12] shadow-2xl focus-within:border-white/25"
            : `bg-white border shadow-sm ${
                error
                  ? "border-red-300"
                  : "border-slate-200 focus-within:border-indigo-400 focus-within:shadow-md"
              }`
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
          className={`w-full p-4 text-[15px] leading-relaxed resize-none focus:outline-none bg-transparent ${
            dark
              ? "text-white placeholder:text-white/25"
              : "text-slate-900 placeholder:text-slate-400"
          }`}
          aria-label="Research question"
        />
        <div
          className={`px-4 py-3 border-t flex items-center justify-between gap-3 ${
            dark
              ? "bg-white/[0.04] border-white/[0.08]"
              : "bg-slate-50/80 border-slate-100"
          }`}
        >
          <span
            className={`text-xs font-medium ${
              isOverLimit
                ? "text-red-400"
                : dark
                ? "text-white/30"
                : "text-slate-400"
            }`}
          >
            {charCount.toLocaleString()} / {MAX_LENGTH.toLocaleString()}
          </span>
          <button
            type="submit"
            disabled={isSubmitting || isOverLimit || question.trim().length < MIN_LENGTH}
            className={`inline-flex items-center gap-2 px-5 py-2 text-sm font-medium rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0 ${
              dark
                ? "bg-indigo-500 hover:bg-indigo-400 text-white"
                : "bg-indigo-600 hover:bg-indigo-700 text-white"
            }`}
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
        <div
          className={`flex items-start gap-2 mt-2.5 text-sm ${
            dark ? "text-red-400" : "text-red-600"
          }`}
        >
          <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          {error}
        </div>
      )}
    </form>
  );
}
