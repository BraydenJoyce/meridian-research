"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase";
import { LayoutDashboard, LogOut, Plus } from "lucide-react";

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(({ data }) => {
      setEmail(data.user?.email ?? null);
      setReady(true);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_, session) => {
      setEmail(session?.user?.email ?? null);
    });
    return () => subscription.unsubscribe();
  }, []);

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/auth/login");
  }

  const initials = email ? email.slice(0, 2).toUpperCase() : "";
  const isAuthPage = pathname?.startsWith("/auth");

  if (pathname?.startsWith("/r/")) return null;

  return (
    <header className="sticky top-0 z-40 h-14 bg-[#080810]/95 backdrop-blur-xl border-b border-white/[0.07]">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 flex items-center justify-between h-full">

        {/* Wordmark */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-[6px] bg-gradient-to-br from-indigo-500 to-violet-600 text-white text-xs font-bold tracking-tight select-none">
            M
          </span>
          <span className="text-white font-semibold text-[15px] tracking-tight">
            Meridian
          </span>
        </Link>

        {/* Nav actions */}
        {ready && !isAuthPage && (
          <nav className="flex items-center gap-0.5">
            {email ? (
              <>
                <Link
                  href="/dashboard"
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-white/50 hover:text-white/90 rounded-lg transition-colors"
                >
                  <LayoutDashboard className="w-3.5 h-3.5" />
                  Dashboard
                </Link>
                <Link
                  href="/"
                  className="flex items-center gap-1.5 ml-2 px-3.5 py-1.5 bg-white text-slate-900 hover:bg-white/90 text-sm font-medium rounded-full transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                  New research
                </Link>
                <button
                  onClick={handleSignOut}
                  title={`Signed in as ${email}`}
                  className="flex items-center gap-2 ml-2 px-2.5 py-1.5 text-white/40 hover:text-white/80 rounded-lg transition-colors"
                >
                  <span className="w-6 h-6 rounded-full bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 text-[10px] font-semibold flex items-center justify-center">
                    {initials}
                  </span>
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </>
            ) : (
              <>
                <Link
                  href="/pricing"
                  className="px-3 py-1.5 text-sm text-white/50 hover:text-white/90 rounded-lg transition-colors"
                >
                  Pricing
                </Link>
                <Link
                  href="/auth/login"
                  className="px-3 py-1.5 text-sm text-white/50 hover:text-white/90 rounded-lg transition-colors"
                >
                  Sign in
                </Link>
                <Link
                  href="/auth/signup"
                  className="ml-2 px-3.5 py-1.5 text-sm bg-white text-slate-900 hover:bg-white/90 font-medium rounded-full transition-colors"
                >
                  Sign up
                </Link>
              </>
            )}
          </nav>
        )}
      </div>
    </header>
  );
}
