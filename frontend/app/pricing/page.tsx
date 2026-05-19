import Link from "next/link";
import ProCTAButton from "./ProCTAButton";
import { Check, Minus } from "lucide-react";

const TIERS = [
  {
    name: "Free",
    price: "$0",
    period: "forever",
    description: "Get started with 3 full intelligence briefs.",
    features: [
      "3 reports / month",
      "3 sub-tasks per query",
      "10 sources per sub-task",
      "PDF export",
      "Public link sharing",
    ],
    cta: "free",
    popular: false,
  },
  {
    name: "Pro",
    price: "$29",
    period: "per month",
    description: "Deeper research, more sources, unlimited briefs.",
    features: [
      "Unlimited reports",
      "5 sub-tasks per query",
      "15 sources per sub-task",
      "DOCX + PDF export",
      "Public link sharing",
      "Priority processing",
    ],
    cta: "pro",
    popular: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "For teams that need integrations, SSO, and SLAs.",
    features: [
      "Everything in Pro",
      "Custom integrations",
      "SSO / SAML",
      "Dedicated support",
      "SLA guarantee",
    ],
    cta: "enterprise",
    popular: false,
  },
];

const COMPARISON_ROWS = [
  { label: "Reports",           free: "3 / month",   pro: "Unlimited",   enterprise: "Unlimited" },
  { label: "Sub-tasks / query", free: "3",            pro: "5",           enterprise: "Custom" },
  { label: "Sources / query",   free: "30",           pro: "75",          enterprise: "Custom" },
  { label: "PDF export",        free: true,           pro: true,          enterprise: true },
  { label: "DOCX export",       free: false,          pro: true,          enterprise: true },
  { label: "Public sharing",    free: true,           pro: true,          enterprise: true },
  { label: "Priority queue",    free: false,          pro: true,          enterprise: true },
  { label: "SSO / SAML",        free: false,          pro: false,         enterprise: true },
  { label: "SLA",               free: false,          pro: false,         enterprise: true },
];

function Cell({ value }: { value: boolean | string }) {
  if (typeof value === "boolean") {
    return value ? (
      <Check className="w-4 h-4 text-emerald-500 mx-auto" />
    ) : (
      <Minus className="w-4 h-4 text-slate-200 mx-auto" />
    );
  }
  return <span className="text-sm text-slate-700 font-medium">{value}</span>;
}

export default function PricingPage() {
  return (
    <main className="min-h-[calc(100vh-3.5rem)] bg-slate-50/60">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16 space-y-16">

        {/* Header */}
        <div className="text-center max-w-xl mx-auto">
          <h1 className="text-4xl font-bold tracking-tight text-slate-900 mb-4">
            Simple, transparent pricing
          </h1>
          <p className="text-slate-500 text-lg leading-relaxed">
            Start free. Upgrade when you need more depth.
          </p>
        </div>

        {/* Tier cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          {TIERS.map((tier) => (
            <div
              key={tier.name}
              className={`relative rounded-2xl p-7 flex flex-col ${
                tier.popular
                  ? "bg-[#080810] text-white shadow-[0_4px_24px_rgba(0,0,0,0.2)]"
                  : "bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.04)]"
              }`}
            >
              {tier.popular && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-500 text-white text-[11px] font-semibold px-3 py-0.5 rounded-full shadow-lg">
                  Most popular
                </span>
              )}

              <div className="mb-6">
                <p className={`text-xs font-semibold uppercase tracking-widest mb-3 ${tier.popular ? "text-indigo-400" : "text-slate-400"}`}>
                  {tier.name}
                </p>
                <div className="flex items-baseline gap-1.5 mb-2">
                  <span className={`text-4xl font-bold tracking-tight ${tier.popular ? "text-white" : "text-slate-900"}`}>
                    {tier.price}
                  </span>
                  {tier.period && (
                    <span className={`text-sm ${tier.popular ? "text-white/40" : "text-slate-400"}`}>
                      {tier.period}
                    </span>
                  )}
                </div>
                <p className={`text-sm leading-relaxed ${tier.popular ? "text-white/50" : "text-slate-500"}`}>
                  {tier.description}
                </p>
              </div>

              <ul className="space-y-2.5 mb-8 flex-1">
                {tier.features.map((f) => (
                  <li key={f} className="flex items-center gap-2.5">
                    <Check className={`w-4 h-4 flex-shrink-0 ${tier.popular ? "text-indigo-400" : "text-emerald-500"}`} />
                    <span className={`text-sm ${tier.popular ? "text-white/70" : "text-slate-600"}`}>{f}</span>
                  </li>
                ))}
              </ul>

              {tier.cta === "free" && (
                <Link
                  href="/auth/signup"
                  className="w-full text-center py-2.5 rounded-xl border border-slate-200 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                >
                  Get started free
                </Link>
              )}
              {tier.cta === "pro" && <ProCTAButton />}
              {tier.cta === "enterprise" && (
                <a
                  href="mailto:sales@meridian.so"
                  className="w-full text-center py-2.5 rounded-xl border border-white/10 text-sm font-semibold text-white/70 hover:text-white hover:border-white/20 transition-colors"
                >
                  Contact sales
                </a>
              )}
            </div>
          ))}
        </div>

        {/* Comparison table */}
        <div>
          <h2 className="text-xl font-bold text-slate-900 mb-6 text-center">Full comparison</h2>
          <div className="bg-white rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.04)] overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="px-6 py-4 text-left text-xs font-semibold text-slate-400 uppercase tracking-wide">Feature</th>
                  {TIERS.map((t) => (
                    <th key={t.name} className="px-4 py-4 text-center text-xs font-semibold text-slate-700 uppercase tracking-wide">
                      {t.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {COMPARISON_ROWS.map((row) => (
                  <tr key={row.label} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-6 py-3.5 text-sm text-slate-600">{row.label}</td>
                    <td className="px-4 py-3.5 text-center"><Cell value={row.free} /></td>
                    <td className="px-4 py-3.5 text-center bg-indigo-50/30"><Cell value={row.pro} /></td>
                    <td className="px-4 py-3.5 text-center"><Cell value={row.enterprise} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </main>
  );
}
