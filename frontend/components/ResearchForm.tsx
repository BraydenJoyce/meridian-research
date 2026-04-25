"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

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
  const [question, setQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);

    if (question.trim().length < MIN_LENGTH) {
      setError(`Question must be at least ${MIN_LENGTH} characters.`);
      return;
    }

    setIsSubmitting(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const response = await fetch(`${apiUrl}/api/research/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });

      if (!response.ok) {
        const body = (await response.json()) as ApiErrorResponse;
        setError(body.detail ?? "Something went wrong. Please try again.");
        return;
      }

      const data = (await response.json()) as CreateResearchResponse;
      router.push(`/research/${data.session_id}`);
    } catch {
      setError("Network error. Please check your connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const charCount = question.length;
  const isOverLimit = charCount > MAX_LENGTH;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 w-full max-w-2xl">
      <div className="flex flex-col gap-2">
        <label
          htmlFor="research-question"
          className="text-sm font-medium text-zinc-700"
        >
          Research question
        </label>
        <Textarea
          id="research-question"
          placeholder="e.g. What are the competitive dynamics in the B2B SaaS CRM market in 2026?"
          value={question}
          onChange={(e) => {
            setQuestion(e.target.value);
            if (error) setError(null);
          }}
          rows={5}
          maxLength={MAX_LENGTH}
          aria-describedby={error ? "question-error" : "char-count"}
          aria-invalid={error !== null}
          className={error ? "border-red-500 focus-visible:ring-red-500" : ""}
          disabled={isSubmitting}
        />
        <div className="flex justify-between items-center">
          {error ? (
            <p id="question-error" className="text-sm text-red-600" role="alert">
              {error}
            </p>
          ) : (
            <span />
          )}
          <p
            id="char-count"
            className={`text-xs ml-auto ${
              isOverLimit ? "text-red-600" : "text-zinc-400"
            }`}
          >
            {charCount} / {MAX_LENGTH}
          </p>
        </div>
      </div>

      <Button
        type="submit"
        disabled={isSubmitting || isOverLimit}
        className="self-start"
      >
        {isSubmitting ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            <span>Researching…</span>
          </>
        ) : (
          "Start research"
        )}
      </Button>
    </form>
  );
}
