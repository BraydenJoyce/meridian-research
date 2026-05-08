"use client";
import { useRouter } from "next/navigation";

const TEMPLATES = [
  { icon: "⚔️", category: "Competitive Analysis", query: "What are the competitive dynamics in [market] and which players are gaining share in 2025?" },
  { icon: "📐", category: "Market Sizing", query: "What is the total addressable market for [sector] and what are the key growth drivers through 2027?" },
  { icon: "🔍", category: "Due Diligence", query: "Provide a comprehensive due diligence report on [company] including financials, leadership, competitive position, and risks." },
  { icon: "💻", category: "Tech Landscape", query: "What is the current technology landscape for [domain] and which vendors are leading in 2025?" },
  { icon: "🚀", category: "GTM Strategy", query: "What go-to-market strategies are working best in [market segment] in 2025 and what channels are driving growth?" },
  { icon: "⛓️", category: "Supply Chain Risk", query: "What are the key supply chain risks and vulnerabilities in the [industry] sector and how are leading companies responding?" },
  { icon: "📋", category: "Regulatory Environment", query: "What is the current regulatory environment for [sector] and what policy changes are expected in 2025-2026?" },
  { icon: "🎯", category: "M&A Target Analysis", query: "Identify the most attractive M&A targets in [industry] and analyze their strategic fit, valuation, and acquisition readiness." },
];

export default function TemplateGrid() {
  const router = useRouter();
  return (
    <div className="w-full max-w-2xl">
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Or start with a template</p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        {TEMPLATES.map((t) => (
          <button
            key={t.category}
            onClick={() => router.push(`/?q=${encodeURIComponent(t.query)}`)}
            className="rounded-xl border border-slate-200 bg-white hover:border-indigo-300 hover:shadow-sm p-3 text-left transition-all cursor-pointer group"
          >
            <span className="text-xl">{t.icon}</span>
            <p className="mt-2 text-xs font-semibold text-slate-700 group-hover:text-indigo-600 transition-colors leading-tight">{t.category}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
