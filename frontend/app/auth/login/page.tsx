"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2, Search, ShieldCheck, Zap } from "lucide-react";
import { createClient } from "@/lib/supabase";

const VALUE_PROPS = [
  { icon: Search, text: "50+ sources searched in parallel — web, news, and EDGAR filings" },
  { icon: ShieldCheck, text: "Every claim fact-checked before delivery" },
  { icon: Zap, text: "Full intelligence brief in under 3 minutes" },
];

function AuthLeft({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="hidden lg:flex lg:w-[42%] bg-[#080810] flex-col justify-between p-12 relative overflow-hidden flex-shrink-0">
      {/* Ambient glow */}
      <div
        className="pointer-events-none absolute bottom-0 left-0 w-[500px] h-[500px]"
        style={{ background: "radial-gradient(ellipse at bottom left, rgba(99,102,241,0.15) 0%, transparent 60%)" }}
      />
      {/* Logo */}
      <Link href="/" className="flex items-center gap-2.5 relative z-10">
        <span className="inline-flex items-center justify-center w-7 h-7 rounded-[7px] bg-gradient-to-br from-indigo-500 to-violet-600 text-white text-sm font-bold">
          M
        </span>
        <span className="text-white font-semibold text-[16px] tracking-tight">Meridian</span>
      </Link>

      {/* Headline + value props */}
      <div className="relative z-10 space-y-8">
        <div>
          <h2 className="text-3xl font-bold text-white tracking-tight leading-snug">{title}</h2>
          <p className="text-white/45 mt-2 text-sm leading-relaxed">{subtitle}</p>
        </div>
        <ul className="space-y-4">
          {VALUE_PROPS.map(({ icon: Icon, text }, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="w-6 h-6 rounded-full bg-indigo-500/15 border border-indigo-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                <Icon className="w-3 h-3 text-indigo-400" />
              </span>
              <span className="text-sm text-white/55 leading-relaxed">{text}</span>
            </li>
          ))}
        </ul>
      </div>

      <p className="text-xs text-white/20 relative z-10">© {new Date().getFullYear()} Meridian Research</p>
    </div>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const supabase = createClient();
      const { error: authError } = await supabase.auth.signInWithPassword({ email, password });
      if (authError) setError(authError.message);
      else router.push("/dashboard");
    } catch {
      setError("An unexpected error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex">
      <AuthLeft
        title="Market intelligence at your fingertips"
        subtitle="Trusted by analysts, investors, and operators who move fast."
      />

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 bg-white">
        <div className="w-full max-w-sm animate-fade-up">
          {/* Mobile logo */}
          <Link href="/" className="lg:hidden flex items-center gap-2 mb-8">
            <span className="w-6 h-6 rounded-[6px] bg-gradient-to-br from-indigo-500 to-violet-600 text-white text-xs font-bold flex items-center justify-center">M</span>
            <span className="font-semibold text-slate-900">Meridian</span>
          </Link>

          <div className="mb-8">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Welcome back</h1>
            <p className="text-sm text-slate-400 mt-1">Sign in to your account</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <label htmlFor="email" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Email
              </label>
              <input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                aria-label="Email"
                className="w-full border-b-2 border-slate-200 focus:border-indigo-500 bg-transparent px-0 py-2 text-[15px] text-slate-900 placeholder:text-slate-300 outline-none transition-colors"
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="password" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                Password
              </label>
              <input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                aria-label="Password"
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
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl px-4 py-3 text-sm font-semibold transition-colors disabled:opacity-60 disabled:cursor-not-allowed mt-2"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="mt-8 pt-6 border-t border-slate-100 flex flex-col items-center gap-2 text-sm text-slate-500">
            <Link href="/auth/reset-password" className="text-slate-400 hover:text-indigo-600 transition-colors">
              Forgot password?
            </Link>
            <p>
              Don&apos;t have an account?{" "}
              <Link href="/auth/signup" className="text-indigo-600 hover:text-indigo-700 font-semibold">
                Sign up free
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
