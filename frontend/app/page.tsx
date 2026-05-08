import { ResearchForm } from "@/components/ResearchForm";
import TemplateGrid from "@/components/TemplateGrid";
import { BarChart2, Globe, ShieldCheck, Zap } from "lucide-react";

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
    <main className="min-h-[calc(100vh-3.5rem)] flex flex-col">
      {/* Hero */}
      <section className="relative flex-1 flex flex-col items-center justify-center px-4 pt-20 pb-16 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-50/60 via-white to-violet-50/40 pointer-events-none" />
        <div className="absolute top-20 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-indigo-400/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 flex flex-col items-center text-center max-w-3xl mx-auto">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold mb-6">
            <Zap className="w-3 h-3" />
            AI-Powered Intelligence
          </span>

          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-slate-900 leading-tight mb-4">
            Research that thinks{" "}
            <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
              ahead of the market
            </span>
          </h1>

          <p className="text-lg text-slate-500 max-w-xl mb-10 leading-relaxed">
            Ask any business question. Meridian searches 50+ sources, extracts data, and delivers a
            cited intelligence report — in under 3 minutes.
          </p>

          <div className="w-full max-w-2xl">
            <ResearchForm />
          </div>

          <div className="w-full max-w-2xl mt-6">
            <TemplateGrid />
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="border-t border-slate-100 bg-white px-4 py-12">
        <div className="max-w-4xl mx-auto grid grid-cols-1 sm:grid-cols-3 gap-8">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600 flex-shrink-0">
                <Icon className="w-4 h-4" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800 mb-1">{title}</p>
                <p className="text-sm text-slate-500 leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
