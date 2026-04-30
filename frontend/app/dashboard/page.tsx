"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase";

interface UserInfo {
  email: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [reportsUsed, setReportsUsed] = useState(0);
  const FREE_LIMIT = 3;

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getUser().then(({ data }) => {
      if (!data.user) {
        router.push("/auth/login");
        return;
      }
      setUser({ email: data.user.email ?? "" });
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
    const token = data.session?.access_token;

    const res = await fetch("/api/billing/checkout", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const { checkout_url } = await res.json();
      window.location.href = checkout_url;
    }
  }

  const usagePercent = Math.min((reportsUsed / FREE_LIMIT) * 100, 100);

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <Button variant="outline" onClick={handleSignOut}>
            Sign out
          </Button>
        </div>

        {user && (
          <p className="text-sm text-gray-600">Signed in as {user.email}</p>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Usage this month</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between text-sm">
              <span>{reportsUsed} of {FREE_LIMIT} free reports used</span>
              <span className="text-gray-500">{FREE_LIMIT - reportsUsed} remaining</span>
            </div>
            <div
              role="progressbar"
              aria-valuenow={reportsUsed}
              aria-valuemin={0}
              aria-valuemax={FREE_LIMIT}
              className="h-2 w-full rounded-full bg-gray-200"
            >
              <div
                className="h-2 rounded-full bg-blue-500 transition-all"
                style={{ width: `${usagePercent}%` }}
              />
            </div>
            {reportsUsed >= FREE_LIMIT && (
              <div className="space-y-2">
                <p className="text-sm text-amber-700">
                  You&apos;ve reached your free tier limit.
                </p>
                <Button onClick={handleUpgrade} size="sm">
                  Upgrade to Pro — $29/month
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Research reports</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-gray-500">
              No reports yet.{" "}
              <a href="/" className="text-blue-600 hover:underline">
                Start your first research session
              </a>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
