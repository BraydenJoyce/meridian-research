"use client";

import { useState } from "react";
import {
  Lightbulb,
  BarChart2,
  TrendingUp,
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  ShieldCheck,
  ShieldAlert,
  Shield,
} from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

export interface HypothesisData {
  hypothesis: string;
  research_angles: string[];
  scope_note: string;
  assumed_audience: string;
}

export interface Metric {
  label: string;
  value: string;
  context: string;
  source_url: string;
  metric_type: string;
}

export interface ChartItem {
  image_url: string;
  source_url: string;
  chart_type: string;
  title: string | null;
  key_insight: string;
  series_count: number;
  x_axis: string | null;
  y_axis: string | null;
  series: unknown[];
}

export interface Recommendation {
  action: string;
  rationale: string;
  priority: "high" | "medium" | "low";
}

export interface RiskFlag {
  claim: string;
  concern: string;
}

export interface StrategyData {
  recommendations: Recommendation[];
  follow_up_questions: string[];
  risk_flags: RiskFlag[];
}

export interface CritiqueData {
  quality_score: number;
  flagged_count: number;
  flagged_claims: Array<{ claim: string; reason: string }>;
}

export interface IntelligencePanelProps {
  hypothesisData: HypothesisData | null;
  metricsData: Metric[] | null;
  chartGallery: ChartItem[] | null;
  strategyData: StrategyData | null;
  critiqueData: CritiqueData | null;
  onFollowUpClick?: (question: string) => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const METRIC_TYPE_STYLES: Record<string, { dot: string; label: string; bg: string }> = {
  market_size: { dot: "bg-blue-500",    label: "text-blue-600",    bg: "bg-blue-50"    },
  growth_rate: { dot: "bg-emerald-500", label: "text-emerald-600", bg: "bg-emerald-50" },
  share:       { dot: "bg-amber-500",   label: "text-amber-600",   bg: "bg-amber-50"   },
  funding:     { dot: "bg-violet-500",  label: "text-violet-600",  bg: "bg-violet-50"  },
  headcount:   { dot: "bg-sky-500",     label: "text-sky-600",     bg: "bg-sky-50"     },
  ranking:     { dot: "bg-orange-500",  label: "text-orange-600",  bg: "bg-orange-50"  },
  other:       { dot: "bg-slate-400",   label: "text-slate-500",   bg: "bg-slate-50"   },
};

const PRIORITY_BORDER: Record<string, string> = {
  high:   "border-l-4 border-red-400",
  medium: "border-l-4 border-amber-400",
  low:    "border-l-4 border-emerald-400",
};

const PRIORITY_BADGE: Record<string, string> = {
  high:   "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low:    "bg-emerald-100 text-emerald-700",
};

const CHART_TYPE_LABELS: Record<string, string> = {
  bar_chart:    "Bar",
  line_chart:   "Line",
  pie_chart:    "Pie",
  scatter_plot: "Scatter",
  table:        "Table",
  unknown:      "Chart",
};

function qualityBarColor(score: number): string {
  if (score >= 0.8) return "bg-emerald-500";
  if (score >= 0.5) return "bg-amber-400";
  return "bg-red-500";
}

function qualityIconColor(score: number): string {
  if (score >= 0.8) return "text-emerald-600";
  if (score >= 0.5) return "text-amber-500";
  return "text-red-500";
}

function qualityTextColor(score: number): string {
  if (score >= 0.8) return "text-emerald-700";
  if (score >= 0.5) return "text-amber-700";
  return "text-red-700";
}

// ── Tab definitions ───────────────────────────────────────────────────────────

type TabId = "frame" | "metrics" | "charts" | "strategy";

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "frame",    label: "Research Frame",    icon: <Lightbulb className="w-3.5 h-3.5" /> },
  { id: "metrics",  label: "Key Metrics",       icon: <BarChart2 className="w-3.5 h-3.5" /> },
  { id: "charts",   label: "Charts",            icon: <TrendingUp className="w-3.5 h-3.5" /> },
  { id: "strategy", label: "Strategic Outlook", icon: <ArrowRight className="w-3.5 h-3.5" /> },
];

// ── Sub-components ────────────────────────────────────────────────────────────

function ResearchFrameTab({ data }: { data: HypothesisData | null }) {
  if (!data || (!data.hypothesis && data.research_angles.length === 0)) {
    return (
      <div className="space-y-3 animate-pulse">
        <div className="h-4 bg-slate-200 rounded w-3/4" />
        <div className="h-4 bg-slate-200 rounded w-1/2" />
        <div className="h-4 bg-slate-200 rounded w-2/3" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {data.hypothesis && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Working Hypothesis
          </p>
          <blockquote className="border-l-[3px] border-indigo-500 pl-4 text-slate-800 italic text-sm leading-relaxed bg-indigo-50/40 py-2 rounded-r-lg">
            {data.hypothesis}
          </blockquote>
        </div>
      )}

      {data.research_angles.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Research Angles
          </p>
          <ul className="space-y-2">
            {data.research_angles.map((angle, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm text-slate-700">
                <span className="inline-flex w-5 h-5 rounded-full bg-indigo-600 text-white text-xs items-center justify-center flex-shrink-0 mt-0.5 font-medium">
                  {i + 1}
                </span>
                {angle}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {data.scope_note && (
          <span className="bg-slate-100 rounded-lg px-3 py-1.5 text-xs text-slate-700">
            <span className="font-semibold text-slate-500 mr-1">Scope:</span>
            {data.scope_note}
          </span>
        )}
        {data.assumed_audience && (
          <span className="bg-slate-100 rounded-lg px-3 py-1.5 text-xs text-slate-700">
            <span className="font-semibold text-slate-500 mr-1">Audience:</span>
            {data.assumed_audience}
          </span>
        )}
      </div>
    </div>
  );
}

function KeyMetricsTab({ metrics }: { metrics: Metric[] | null }) {
  if (metrics === null) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 animate-pulse">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="h-28 bg-slate-100 rounded-xl" />
        ))}
      </div>
    );
  }

  if (metrics.length === 0) {
    return (
      <p className="text-sm text-slate-500 text-center py-8">
        No quantitative metrics were extracted from this research.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
      {metrics.map((m, i) => {
        const styles = METRIC_TYPE_STYLES[m.metric_type] ?? METRIC_TYPE_STYLES.other;
        return (
          <div
            key={i}
            className="bg-white border border-slate-200 rounded-xl p-4 hover:border-indigo-300 hover:shadow-sm transition-all"
          >
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${styles.dot}`} />
              <span className={`text-[10px] font-semibold uppercase tracking-wide ${styles.label}`}>
                {m.metric_type.replace(/_/g, " ")}
              </span>
            </div>
            <p className="text-2xl font-bold text-slate-900 mt-1 leading-none truncate">{m.value}</p>
            <p className="text-xs font-semibold text-slate-700 mt-0.5 leading-snug">{m.label}</p>
            {m.context && (
              <p className="text-xs text-slate-500 leading-relaxed mt-1.5 line-clamp-2">{m.context}</p>
            )}
            {m.source_url && (
              <a
                href={m.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 text-xs text-indigo-500 hover:text-indigo-700 mt-2 transition-colors"
              >
                Source <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ChartsTab({ gallery }: { gallery: ChartItem[] | null }) {
  if (gallery === null) {
    return (
      <div className="flex gap-3 animate-pulse overflow-hidden">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-40 w-52 flex-shrink-0 bg-slate-100 rounded-xl" />
        ))}
      </div>
    );
  }

  if (gallery.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-3 text-slate-400">
        <TrendingUp className="w-8 h-8 opacity-40" />
        <p className="text-sm text-slate-500">No chart data was extracted from this research.</p>
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Left fade */}
      <div className="pointer-events-none absolute left-0 top-0 bottom-2 w-4 bg-gradient-to-r from-white to-transparent z-10" />
      {/* Right fade */}
      <div className="pointer-events-none absolute right-0 top-0 bottom-2 w-8 bg-gradient-to-l from-white to-transparent z-10" />
      <div
        className="flex gap-3 overflow-x-auto pb-2"
        style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
      >
        {gallery.map((chart, i) => (
          <a
            key={i}
            href={chart.source_url || chart.image_url}
            target="_blank"
            rel="noopener noreferrer"
            className="w-52 flex-shrink-0 bg-white border border-slate-200 rounded-xl p-4 hover:border-indigo-300 hover:shadow-md transition-all cursor-pointer"
          >
            <span className="inline-block bg-indigo-50 text-indigo-600 text-[10px] font-semibold px-2 py-0.5 rounded-full">
              {CHART_TYPE_LABELS[chart.chart_type] ?? "Chart"}
            </span>
            {chart.title && (
              <p className="text-xs font-semibold text-slate-800 mt-2 line-clamp-2 leading-snug">
                {chart.title}
              </p>
            )}
            {chart.key_insight && (
              <p className="text-xs text-slate-500 leading-relaxed mt-1.5 line-clamp-3">
                {chart.key_insight}
              </p>
            )}
            {(chart.x_axis || chart.y_axis) && (
              <p className="text-[10px] text-slate-400 mt-2 flex gap-1">
                {[chart.x_axis, chart.y_axis].filter(Boolean).join(" · ")}
              </p>
            )}
          </a>
        ))}
      </div>
    </div>
  );
}

function StrategicOutlookTab({
  data,
  onFollowUpClick,
}: {
  data: StrategyData | null;
  onFollowUpClick?: (q: string) => void;
}) {
  if (data === null) {
    return (
      <div className="space-y-3 animate-pulse">
        <div className="h-16 bg-slate-100 rounded-xl" />
        <div className="h-16 bg-slate-100 rounded-xl" />
        <div className="h-16 bg-slate-100 rounded-xl" />
      </div>
    );
  }

  const hasContent =
    data.recommendations.length > 0 ||
    data.follow_up_questions.length > 0 ||
    data.risk_flags.length > 0;

  if (!hasContent) {
    return (
      <p className="text-sm text-slate-500 text-center py-8">
        No strategic recommendations were generated.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {data.recommendations.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2.5">
            Recommendations
          </p>
          <div className="space-y-2.5">
            {data.recommendations.map((r, i) => (
              <div
                key={i}
                className={`rounded-xl bg-white border border-slate-200 pl-4 pr-4 py-3.5 ${PRIORITY_BORDER[r.priority] ?? PRIORITY_BORDER.medium}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold text-slate-800 text-sm leading-snug">{r.action}</p>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-semibold flex-shrink-0 uppercase tracking-wide ${PRIORITY_BADGE[r.priority] ?? PRIORITY_BADGE.medium}`}
                  >
                    {r.priority}
                  </span>
                </div>
                {r.rationale && (
                  <p className="text-xs text-slate-500 mt-1 leading-relaxed">{r.rationale}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {data.follow_up_questions.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2.5">
            Follow-up Research
          </p>
          <div className="space-y-2">
            {data.follow_up_questions.map((q, i) => (
              <button
                key={i}
                onClick={() => onFollowUpClick?.(q)}
                className="flex items-center gap-2 w-full text-left px-4 py-3 text-sm text-slate-700 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/30 hover:text-indigo-700 transition-all group"
              >
                <ArrowRight className="w-3.5 h-3.5 flex-shrink-0 text-slate-400 group-hover:text-indigo-500 transition-colors" />
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {data.risk_flags.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2.5">
            Risk Flags
          </p>
          <div className="space-y-2">
            {data.risk_flags.map((f, i) => (
              <div
                key={i}
                className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 flex items-start gap-2.5"
              >
                <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-semibold text-slate-800 leading-snug">{f.claim}</p>
                  <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">{f.concern}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function QualitySignal({ data }: { data: CritiqueData | null }) {
  const [expanded, setExpanded] = useState(false);

  if (!data) return null;

  const pct = Math.round(data.quality_score * 100);
  const barColor = qualityBarColor(data.quality_score);
  const iconColor = qualityIconColor(data.quality_score);
  const textColor = qualityTextColor(data.quality_score);
  const Icon =
    data.quality_score >= 0.8
      ? ShieldCheck
      : data.quality_score >= 0.5
      ? Shield
      : ShieldAlert;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm px-5 py-3.5">
      {/* Main row */}
      <div className="flex items-center gap-4">
        {/* Left: icon + label + score */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <Icon className={`w-4 h-4 ${iconColor}`} />
          <span className="text-xs font-semibold text-slate-600">Quality signal</span>
          <span className={`text-xs font-bold ${textColor}`}>{pct}%</span>
        </div>

        {/* Center: slim progress bar */}
        <div className="flex-1 min-w-0 h-1 bg-slate-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${barColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>

        {/* Right: expandable flagged claims button */}
        {data.flagged_count > 0 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1 text-xs font-medium text-amber-600 hover:text-amber-700 flex-shrink-0 transition-colors"
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            {data.flagged_count} {data.flagged_count === 1 ? "flag" : "flags"}
            {expanded ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        )}
      </div>

      {/* Expanded flagged claims */}
      {expanded && data.flagged_claims.length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-100 space-y-2">
          {data.flagged_claims.map((c, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-slate-700">{c.claim}</span>
                {c.reason && (
                  <span className="text-slate-400 ml-1">— {c.reason}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function IntelligencePanel({
  hypothesisData,
  metricsData,
  chartGallery,
  strategyData,
  critiqueData,
  onFollowUpClick,
}: IntelligencePanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>("frame");

  const hasAnyData =
    hypothesisData !== null ||
    metricsData !== null ||
    chartGallery !== null ||
    strategyData !== null ||
    critiqueData !== null;

  if (!hasAnyData) return null;

  return (
    <div className="w-full space-y-4 animate-fade-in">
      <QualitySignal data={critiqueData} />

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {/* Pill tab bar */}
        <div className="px-4 pt-4 pb-0">
          <div className="flex items-center gap-1 p-1 bg-slate-100 rounded-xl">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  activeTab === tab.id
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Tab content */}
        <div className="p-4 pt-3">
          {activeTab === "frame" && <ResearchFrameTab data={hypothesisData} />}
          {activeTab === "metrics" && <KeyMetricsTab metrics={metricsData} />}
          {activeTab === "charts" && <ChartsTab gallery={chartGallery} />}
          {activeTab === "strategy" && (
            <StrategicOutlookTab data={strategyData} onFollowUpClick={onFollowUpClick} />
          )}
        </div>
      </div>
    </div>
  );
}
