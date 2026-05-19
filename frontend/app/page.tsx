import { Suspense } from "react";
import { ResearchForm } from "@/components/ResearchForm";
import TemplateGrid from "@/components/TemplateGrid";
import { BarChart2, Globe, ShieldCheck } from "lucide-react";

const FEATURES = [
  {
    icon: Globe,
    title: "50+ live sources",
    desc: "Web, news, EDGAR filings, and chart extraction working in parallel.",
  },
  {
    icon: BarChart2,
    title: "Structured intelligence",
    desc: "Metrics, hypotheses, recommendations, and risk flags — not just a text summary.",
  },
  {
    icon: ShieldCheck,
    title: "Fact-checked output",
    desc: "Every claim is verified against source material before delivery.",
  },
];

export default function HomePage() {
  return (
    <main className="flex flex-col">
      {/* ── Dark hero ─────────────────────────────────────────────────────── */}
      <section className="grain relative min-h-[calc(100vh-3.5rem)] flex flex-col items-center justify-center px-4 pt-16 pb-20 overflow-hidden bg-[#080810]">
        {/* Ambient glow */}
        <div
          className="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[600px] rounded-full"
          style={{
            background:
              "radial-gradient(ellipse at center, rgba(99,102,241,0.18) 0%, rgba(139,92,246,0.08) 45%, transparent 70%)",
          }}
        />

        <div className="relative z-10 flex flex-col items-center text-center max-w-3xl mx-auto">
          {/* Headline */}
          <h1
            className="font-bold tracking-[-0.03em] text-white leading-[1.06] mb-5 animate-fade-up"
            style={{ fontSize: "clamp(42px, 6vw, 68px)" }}
          >
            The intelligence layer
            <br />
            <span className="text-indigo-400">for market leaders</span>
          </h1>

          {/* Sub-headline */}
          <p
            className="text-white/50 text-lg max-w-lg leading-relaxed mb-10 animate-fade-up"
            style={{ animationDelay: "60ms" }}
          >
            Ask any business question. Meridian searches 50+ sources, extracts
            structured data, and delivers a cited intelligence brief — in under
            3 minutes.
          </p>

          {/* Search form */}
          <div
            className="w-full max-w-2xl animate-fade-up"
            style={{ animationDelay: "120ms" }}
          >
            <Suspense fallback={null}>
              <ResearchForm variant="dark" />
            </Suspense>
          </div>

          {/* Template pills */}
          <div
            className="w-full max-w-2xl mt-4 animate-fade-up"
            style={{ animationDelay: "180ms" }}
          >
            <TemplateGrid />
          </div>
        </div>
      </section>

      {/* ── Features strip ───────────────────────────────────────────────── */}
      <section className="bg-[#0d0d1c] border-t border-white/[0.06] px-4 py-14">
        <div className="max-w-4xl mx-auto grid grid-cols-1 sm:grid-cols-3 gap-8">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="flex items-start gap-3">
              <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 flex-shrink-0">
                <Icon className="w-4 h-4" />
              </div>
              <div>
                <p className="text-sm font-semibold text-white/80 mb-1">{title}</p>
                <p className="text-sm text-white/35 leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
