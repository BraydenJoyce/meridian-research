import type { Metadata } from "next";
import { Zap } from "lucide-react";
import ReportViewer from "@/components/ReportViewer";
import type {
  HypothesisData,
  Metric,
  ChartItem,
  StrategyData,
  CritiqueData,
} from "@/components/IntelligencePanel";
import PublicIntelligenceWrapper from "./PublicIntelligenceWrapper";

// ── Types ─────────────────────────────────────────────────────────────────────

interface FlaggedClaim {
  claim: string;
  reason: string;
}

interface PublicSession {
  question: string;
  report_markdown: string | null;
  metrics_json: { metrics: Metric[] } | null;
  hypothesis_json: HypothesisData | null;
  strategy_json: StrategyData | null;
  critique_json: { quality_score: number; flagged_claims: FlaggedClaim[] } | null;
  chart_gallery_json: { gallery: ChartItem[]; chart_count: number } | null;
  created_at: string;
}

// ── Data fetching ─────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function getPublicSession(slug: string): Promise<PublicSession | null> {
  const res = await fetch(`${API_BASE}/api/research/public/${slug}`, {
    next: { revalidate: 3600 },
  });
  if (!res.ok) return null;
  return res.json();
}

// ── Metadata ──────────────────────────────────────────────────────────────────

export async function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Promise<Metadata> {
  const session = await getPublicSession(params.slug);
  if (!session) return { title: "Report not found — Meridian" };
  return {
    title: `${session.question} — Meridian Research`,
    description: `AI-powered market intelligence: ${session.question.slice(0, 150)}`,
    openGraph: {
      title: session.question,
      description: "AI-powered market intelligence report",
      type: "article",
    },
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function PublicReportPage({
  params,
}: {
  params: { slug: string };
}) {
  const session = await getPublicSession(params.slug);

  if (!session) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-slate-900 mb-2">Report not found</h1>
          <p className="text-slate-500 mb-6">
            This report may have been unpublished or the link is incorrect.
          </p>
          <a
            href="/auth/signup"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            Run your own research free
          </a>
        </div>
      </div>
    );
  }

  // Build typed props for IntelligencePanel from the API's JSON columns
  const metricsData: Metric[] | null = session.metrics_json?.metrics ?? null;
  const hypothesisData: HypothesisData | null = session.hypothesis_json ?? null;
  const strategyData: StrategyData | null = session.strategy_json ?? null;
  const chartGallery: ChartItem[] | null =
    session.chart_gallery_json?.gallery ?? null;
  const critiqueData: CritiqueData | null = session.critique_json
    ? {
        quality_score: session.critique_json.quality_score,
        flagged_count: session.critique_json.flagged_claims.length,
        flagged_claims: session.critique_json.flagged_claims,
      }
    : null;

  const hasIntelligence =
    hypothesisData !== null ||
    metricsData !== null ||
    chartGallery !== null ||
    strategyData !== null ||
    critiqueData !== null;

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Branded header */}
      <header className="sticky top-0 z-40 bg-white/80 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <a href="/" className="flex items-center gap-2 font-bold text-slate-900">
            <span className="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex-shrink-0">
              <Zap className="w-4 h-4 text-white" />
            </span>
            Meridian
          </a>
          <a
            href="/auth/signup"
            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            Run your own research free →
          </a>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        {/* Report title + date */}
        <div>
          <p className="text-xs font-semibold text-indigo-600 uppercase tracking-wide mb-1">
            Intelligence Report
          </p>
          <h1 className="text-2xl font-bold text-slate-900 leading-snug">
            {session.question}
          </h1>
          <p className="text-xs text-slate-400 mt-1.5">{formatDate(session.created_at)}</p>
        </div>

        {/* Intelligence panel (client component wrapper) */}
        {hasIntelligence && (
          <PublicIntelligenceWrapper
            hypothesisData={hypothesisData}
            metricsData={metricsData}
            chartGallery={chartGallery}
            strategyData={strategyData}
            critiqueData={critiqueData}
          />
        )}

        {/* Report body */}
        {session.report_markdown ? (
          <ReportViewer markdown={session.report_markdown} />
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm px-8 py-12 text-center">
            <p className="text-slate-400 text-sm">Report content is not available.</p>
          </div>
        )}

        {/* Bottom CTA banner */}
        <div className="bg-indigo-50 border border-indigo-200 rounded-2xl p-8 text-center mt-8">
          <h2 className="text-xl font-bold text-slate-900 mb-2">
            Run your own market research
          </h2>
          <p className="text-slate-600 mb-4 max-w-md mx-auto">
            3 free reports per month. No credit card required.
          </p>
          <a
            href="/auth/signup"
            className="inline-flex items-center gap-2 px-6 py-3 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-700 transition-colors"
          >
            Get started free
          </a>
        </div>
      </main>
    </div>
  );
}
