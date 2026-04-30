"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { createClient } from "@/lib/supabase";

interface Session {
  id: string;
  question: string;
  status: string;
  created_at: string;
}

const FREE_LIMIT = 3;

async function fetchSessions(token: string): Promise<Session[]> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/research/sessions`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default function DashboardPage() {
  const router = useRouter();
  const [userEmail, setUserEmail] = useState<string>("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [isPro, setIsPro] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(async ({ data }) => {
      if (!data.user) {
        router.push("/auth/login");
        return;
      }
      setUserEmail(data.user.email ?? "");

      const { data: sessionData } = await supabase.auth.getSession();
      const token = sessionData.session?.access_token ?? "";
      const fetched = await fetchSessions(token);
      setSessions(fetched);
      setLoading(false);
    });
  }, [router]);

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/auth/login");
  }

  async function handleUpgrade() {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token ?? "";

    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/billing/checkout`,
      { method: "POST", headers: { Authorization: `Bearer ${token}` } },
    );
    if (res.ok) {
      const { checkout_url } = await res.json();
      window.location.href = checkout_url;
    }
  }

  const reportsUsed = sessions.length;
  const atLimit = !isPro && reportsUsed >= FREE_LIMIT;

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <Button variant="outline" onClick={handleSignOut}>
            Sign out
          </Button>
        </div>

        {userEmail && (
          <p className="text-sm text-gray-600">Signed in as {userEmail}</p>
        )}

        {/* Usage meter */}
        <Card>
          <CardHeader>
            <CardTitle>Usage this month</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {isPro ? (
              <p className="text-sm font-medium text-green-700">
                Pro plan — unlimited reports
              </p>
            ) : (
              <>
                <div className="flex justify-between text-sm">
                  <span>
                    {reportsUsed} of {FREE_LIMIT} free reports used
                  </span>
                  <span className="text-gray-500">
                    {Math.max(FREE_LIMIT - reportsUsed, 0)} remaining
                  </span>
                </div>
                <Progress value={reportsUsed} max={FREE_LIMIT} />
                {atLimit && (
                  <p className="text-sm text-amber-700">
                    You&apos;ve reached your free limit.
                  </p>
                )}
              </>
            )}

            {!isPro && (
              <Button onClick={handleUpgrade} variant="default" size="sm">
                Upgrade to Pro — $29/month
              </Button>
            )}
          </CardContent>
        </Card>

        {/* Report history */}
        <Card>
          <CardHeader>
            <CardTitle>Research reports</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-gray-500">Loading…</p>
            ) : sessions.length === 0 ? (
              <p className="text-sm text-gray-500">
                No reports yet.{" "}
                <Link href="/" className="text-blue-600 hover:underline">
                  Start your first research session
                </Link>
              </p>
            ) : (
              <ul className="divide-y">
                {sessions.map((s) => (
                  <li key={s.id} className="py-3 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium line-clamp-1">{s.question}</p>
                      <p className="text-xs text-gray-500">
                        {new Date(s.created_at).toLocaleDateString()} · {s.status}
                      </p>
                    </div>
                    {s.status === "completed" && (
                      <Link
                        href={`/dashboard/report/${s.id}`}
                        className="text-sm text-blue-600 hover:underline ml-4 shrink-0"
                      >
                        View report
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
