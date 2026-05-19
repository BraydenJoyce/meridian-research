"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, CheckCircle, Loader2 } from "lucide-react";
import { createClient } from "@/lib/supabase";

export default function ResetPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const supabase = createClient();
      const { error: authError } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/auth/update-password`,
      });
      if (authError) setError(authError.message);
      else setSuccess(true);
    } catch {
      setError("An unexpected error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex">
      {/* Left panel */}
      <div className="hidden lg:flex lg:w-[42%] bg-[#080810] flex-col justify-between p-12 relative overflow-hidden flex-shrink-0">
        <div
          className="pointer-events-none absolute bottom-0 left-0 w-[500px] h-[500px]"
          style={{ background: "radial-gradient(ellipse at bottom left, rgba(99,102,241,0.15) 0%, transparent 60%)" }}
        />
        <Link href="/" className="flex items-center gap-2.5 relative z-10">
          <span className="inline-flex items-center justify-center w-7 h-7 rounded-[7px] bg-gradient-to-br from-indigo-500 to-violet-600 text-white text-sm font-bold">M</span>
          <span className="text-white font-semibold text-[16px] tracking-tight">Meridian</span>
        </Link>
        <div className="relative z-10">
          <h2 className="text-3xl font-bold text-white tracking-tight leading-snug">
            We&apos;ll get you back in
          </h2>
          <p className="text-white/45 mt-2 text-sm leading-relaxed">
            Enter your email and we&apos;ll send a secure reset link.
          </p>
        </div>
        <p className="text-xs text-white/20 relative z-10">© {new Date().getFullYear()} Meridian Research</p>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 bg-white">
        <div className="w-full max-w-sm animate-fade-up">
          <Link href="/" className="lg:hidden flex items-center gap-2 mb-8">
            <span className="w-6 h-6 rounded-[6px] bg-gradient-to-br from-indigo-500 to-violet-600 text-white text-xs font-bold flex items-center justify-center">M</span>
            <span className="font-semibold text-slate-900">Meridian</span>
          </Link>

          {success ? (
            <div className="flex flex-col items-center text-center gap-4 py-8">
              <div className="w-14 h-14 rounded-2xl bg-emerald-50 flex items-center justify-center">
                <CheckCircle className="w-7 h-7 text-emerald-600" />
              </div>
              <div>
                <p className="text-lg font-bold text-slate-900">Check your email</p>
                <p role="status" className="text-sm text-slate-500 mt-1.5">
                  We sent a reset link to <strong>{email}</strong>.
                </p>
              </div>
              <Link
                href="/auth/login"
                className="flex items-center gap-1 text-sm text-indigo-600 hover:text-indigo-700 transition-colors mt-2"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                Back to sign in
              </Link>
            </div>
          ) : (
            <>
              <div className="mb-8">
                <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Reset your password</h1>
                <p className="text-sm text-slate-400 mt-1">We&apos;ll send you a secure reset link</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5">
                <div className="space-y-1.5">
                  <label htmlFor="email" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Email</label>
                  <input
                    id="email" type="email" placeholder="you@example.com"
                    value={email} onChange={(e) => setEmail(e.target.value)}
                    required aria-label="Email"
                    className="w-full border-b-2 border-slate-200 focus:border-indigo-500 bg-transparent px-0 py-2 text-[15px] text-slate-900 placeholder:text-slate-300 outline-none transition-colors"
                  />
                </div>

                {error && (
                  <div role="alert" className="flex items-start gap-2 text-sm text-red-600">
                    <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    {error}
                  </div>
                )}

                <button
                  type="submit" disabled={loading}
                  className="w-full flex items-center justify-center gap-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl px-4 py-3 text-sm font-semibold transition-colors disabled:opacity-60 disabled:cursor-not-allowed mt-2"
                >
                  {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                  {loading ? "Sending…" : "Send reset link"}
                </button>
              </form>

              <div className="mt-8 pt-6 border-t border-slate-100 text-center">
                <Link
                  href="/auth/login"
                  className="flex items-center justify-center gap-1 text-sm text-slate-400 hover:text-indigo-600 transition-colors"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  Back to sign in
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
