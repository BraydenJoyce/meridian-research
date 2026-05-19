"use client";

import { useRouter } from "next/navigation";

const TEMPLATES = [
  { label: "Competitive Analysis", query: "What are the competitive dynamics in the enterprise SaaS market and which players are gaining share in 2025?" },
  { label: "Market Sizing", query: "What is the total addressable market for AI-powered legal tech software globally and what is the growth trajectory?" },
  { label: "Due Diligence", query: "Conduct a due diligence analysis of Stripe including competitive position, financial health signals, and key risks." },
  { label: "Tech Landscape", query: "What is the current landscape of vector database providers and how do they compare on performance, pricing, and enterprise adoption?" },
  { label: "GTM Strategy", query: "What go-to-market strategies are most effective for B2B infrastructure software targeting mid-market companies in 2025?" },
  { label: "Supply Chain Risk", query: "What are the key supply chain risks for semiconductor manufacturers and how are leading companies mitigating them?" },
  { label: "Regulatory Watch", query: "What regulatory changes are expected in EU AI legislation in 2025 and how will they affect enterprise AI adoption?" },
  { label: "M&A Targets", query: "Which cybersecurity companies under $500M market cap are the most likely M&A targets for large strategic acquirers in 2025?" },
];

export default function TemplateGrid() {
  const router = useRouter();

  return (
    <div
      className="flex gap-2 overflow-x-auto pb-1"
      style={{ scrollbarWidth: "none", msOverflowStyle: "none" } as React.CSSProperties}
    >
      {TEMPLATES.map((t) => (
        <button
          key={t.label}
          onClick={() => router.push(`/?q=${encodeURIComponent(t.query)}`)}
          className="flex-shrink-0 px-3 py-1.5 rounded-full border border-white/[0.12] bg-white/[0.06] text-white/55 hover:bg-white/[0.12] hover:text-white/85 text-xs whitespace-nowrap transition-colors"
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
