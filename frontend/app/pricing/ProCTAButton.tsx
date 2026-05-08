"use client";

export default function ProCTAButton() {
  async function handleUpgrade() {
    const { createClient } = await import("@/lib/supabase");
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (!token) { window.location.href = "/auth/signup"; return; }
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const res = await fetch(`${apiUrl}/api/billing/checkout`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) { const { checkout_url } = await res.json(); window.location.href = checkout_url; }
  }

  return (
    <button
      onClick={handleUpgrade}
      className="block w-full text-center px-4 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
    >
      Get started with Pro
    </button>
  );
}
