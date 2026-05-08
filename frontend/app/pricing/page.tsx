import Link from "next/link";
import ProCTAButton from "./ProCTAButton";

const FREE_FEATURES = [
  "3 research reports/month",
  "3 sub-tasks per query",
  "10 sources per sub-task",
  "PDF export",
  "Public sharing",
];

const PRO_FEATURES = [
  "Unlimited reports",
  "5 sub-tasks per query",
  "15 sources per sub-task",
  "DOCX export",
  "PDF export",
  "Public sharing",
  "Priority processing",
];

const ENTERPRISE_FEATURES = [
  "Everything in Pro",
  "Custom integrations",
  "SSO / SAML",
  "Dedicated support",
  "SLA",
];

const TABLE_ROWS = [
  { label: "Monthly reports",           free: "3",   pro: "Unlimited", enterprise: "Unlimited" },
  { label: "Research depth (sub-tasks)", free: "3",   pro: "5",         enterprise: "5+" },
  { label: "Sources per query",          free: "10",  pro: "15",        enterprise: "15+" },
  { label: "DOCX export",               free: false, pro: true,        enterprise: true },
  { label: "Public sharing",            free: true,  pro: true,        enterprise: true },
  { label: "PDF export",                free: true,  pro: true,        enterprise: true },
  { label: "Priority queue",            free: false, pro: true,        enterprise: true },
];

function Check() {
  return <span className="text-emerald-600 font-bold text-base">&#10003;</span>;
}

function Dash() {
  return <span className="text-slate-300 font-bold text-base">&#8212;</span>;
}

function CellValue({ value }: { value: boolean | string }) {
  if (value === true) return <Check />;
  if (value === false) return <Dash />;
  return <span className="text-sm font-medium text-slate-700">{value}</span>;
}

export default function PricingPage() {
  return (
    <main className="min-h-[calc(100vh-3.5rem)] bg-slate-50">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-16 space-y-12">

        {/* Hero */}
        <div className="text-center space-y-4">
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-slate-900">
            Simple, transparent pricing
          </h1>
          <p className="text-lg text-slate-500 max-w-xl mx-auto leading-relaxed">
            Start free and scale as your research needs grow. No hidden fees, no surprises.
          </p>
        </div>

        {/* Tier cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">

          {/* Free */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-7 flex flex-col gap-5">
            <div>
              <p className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-1">Free</p>
              <div className="flex items-end gap-1">
                <span className="text-4xl font-bold text-slate-900">$0</span>
                <span className="text-slate-400 text-sm mb-1">/month</span>
              </div>
            </div>
            <ul className="space-y-2.5 flex-1">
              {FREE_FEATURES.map((f) => (
                <li key={f} className="flex items-center gap-2 text-sm text-slate-600">
                  <Check />
                  {f}
                </li>
              ))}
            </ul>
            <Link
              href="/auth/signup"
              className="block text-center px-4 py-2.5 rounded-lg border border-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Get started free
            </Link>
          </div>

          {/* Pro — highlighted */}
          <div className="bg-white rounded-xl border-2 border-indigo-500 shadow-lg shadow-indigo-100 p-7 flex flex-col gap-5 relative">
            <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-600 text-white text-xs font-semibold px-3 py-1 rounded-full">
              Most popular
            </span>
            <div>
              <p className="text-sm font-semibold text-indigo-600 uppercase tracking-wide mb-1">Pro</p>
              <div className="flex items-end gap-1">
                <span className="text-4xl font-bold text-slate-900">$29</span>
                <span className="text-slate-400 text-sm mb-1">/month</span>
              </div>
            </div>
            <ul className="space-y-2.5 flex-1">
              {PRO_FEATURES.map((f) => (
                <li key={f} className="flex items-center gap-2 text-sm text-slate-600">
                  <Check />
                  {f}
                </li>
              ))}
            </ul>
            <ProCTAButton />
          </div>

          {/* Enterprise */}
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-7 flex flex-col gap-5">
            <div>
              <p className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-1">Enterprise</p>
              <div className="flex items-end gap-1">
                <span className="text-4xl font-bold text-slate-900">Custom</span>
              </div>
            </div>
            <ul className="space-y-2.5 flex-1">
              {ENTERPRISE_FEATURES.map((f) => (
                <li key={f} className="flex items-center gap-2 text-sm text-slate-600">
                  <Check />
                  {f}
                </li>
              ))}
            </ul>
            <a
              href="mailto:hello@meridian.so"
              className="block text-center px-4 py-2.5 rounded-lg border border-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Contact sales
            </a>
          </div>
        </div>

        {/* Feature comparison table */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100">
            <h2 className="text-sm font-semibold text-slate-900">Feature comparison</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-1/2">Feature</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Free</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-indigo-600 uppercase tracking-wide">Pro</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Enterprise</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {TABLE_ROWS.map((row) => (
                  <tr key={row.label} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-3.5 text-sm text-slate-700 font-medium">{row.label}</td>
                    <td className="px-4 py-3.5 text-center"><CellValue value={row.free} /></td>
                    <td className="px-4 py-3.5 text-center"><CellValue value={row.pro} /></td>
                    <td className="px-4 py-3.5 text-center"><CellValue value={row.enterprise} /></td>
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
