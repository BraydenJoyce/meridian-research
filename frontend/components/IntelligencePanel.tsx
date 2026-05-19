"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
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

const METRIC_TYPE_STYLES: Record<string, { bar: string; pill: string; pillText: string }> = {
  market_size: { bar: "bg-blue-500",    pill: "bg-blue-50",    pillText: "text-blue-600"    },
  growth_rate: { bar: "bg-emerald-500", pill: "bg-emerald-50", pillText: "text-emerald-600" },
  share:       { bar: "bg-amber-500",   pill: "bg-amber-50",   pillText: "text-amber-600"   },
  funding:     { bar: "bg-violet-500",  pill: "bg-violet-50",  pillText: "text-violet-600"  },
  headcount:   { bar: "bg-sky-500",     pill: "bg-sky-50",     pillText: "text-sky-600"     },
  ranking:     { bar: "bg-orange-500",  pill: "bg-orange-50",  pillText: "text-orange-600"  },
  other:       { bar: "bg-slate-300",   pill: "bg-slate-100",  pillText: "text-slate-500"   },
};

const PRIORITY_DOT: Record<string, string> = {
  high:   "bg-red-400",
  medium: "bg-amber-400",
  low:    "bg-emerald-400",
};

const PRIORITY_BADGE: Record<string, string> = {
  high:   "bg-red-50 text-red-600",
  medium: "bg-amber-50 text-amber-600",
  low:    "bg-emerald-50 text-emerald-600",
};

const CHART_TYPE_LABELS: Record<string, string> = {
  bar_chart:    "Bar",
  line_chart:   "Line",
  pie_chart:    "Pie",
  scatter_plot: "Scatter",
  table:        "Table",
  unknown:      "Chart",
};

function qualityGradient(score: number): string {
  if (score >= 0.8) return "from-emerald-50 to-white";
  if (score >= 0.5) return "from-amber-50 to-white";
  return "from-red-50 to-white";
}

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
      <div className="space-y-3">
        <div className="skeleton h-4 rounded-lg w-3/4" />
        <div className="skeleton h-4 rounded-lg w-1/2" />
        <div className="skeleton h-4 rounded-lg w-2/3" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {data.hypothesis && (
        <div>
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-3">
            Working Hypothesis
          </p>
          <blockquote className="border-l-[3px] border-indigo-500 pl-4 text-slate-700 italic text-[15px] leading-relaxed bg-indigo-50/50 py-2.5 pr-3 rounded-r-xl">
            {data.hypothesis}
          </blockquote>
        </div>
      )}

      {data.research_angles.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-3">
            Research Angles
          </p>
          <ul className="space-y-2">
            {data.research_angles.map((angle, i) => (
              <li key={i} className="flex items-start gap-3 text-sm text-slate-700">
                <span className="inline-flex w-5 h-5 rounded-full bg-indigo-600 text-white text-[10px] items-center justify-center flex-shrink-0 mt-0.5 font-semibold">
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
          <span className="bg-slate-100 rounded-lg px-3 py-1.5 text-xs text-slate-600">
            <span className="font-semibold text-slate-400 mr-1.5">Scope</span>
            {data.scope_note}
          </span>
        )}
        {data.assumed_audience && (
          <span className="bg-slate-100 rounded-lg px-3 py-1.5 text-xs text-slate-600">
            <span className="font-semibold text-slate-400 mr-1.5">Audience</span>
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
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="skeleton h-32 rounded-2xl" />
        ))}
      </div>
    );
  }

  if (metrics.length === 0) {
    return (
      <p className="text-sm text-slate-400 text-center py-10">
        No quantitative metrics were extracted from this research.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
      {metrics.map((m, i) => {
        const styles = METRIC_TYPE_STYLES[m.metric_type] ?? METRIC_TYPE_STYLES.other;
        return (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04, duration: 0.25 }}
            className="relative bg-white rounded-2xl p-4 overflow-hidden shadow-[0_1px_3px_rgba(0,0,0,0.07),0_6px_20px_rgba(0,0,0,0.04)] hover:shadow-[0_2px_6px_rgba(0,0,0,0.09),0_12px_28px_rgba(0,0,0,0.06)] transition-shadow"
          >
            {/* Left accent bar */}
            <div className={`absolute left-0 top-0 bottom-0 w-[3px] rounded-l-2xl ${styles.bar}`} />

            {/* Type pill — top right */}
            <div className="flex justify-end mb-1">
              <span className={`text-[9px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${styles.pill} ${styles.pillText}`}>
                {m.metric_type.replace(/_/g, " ")}
              </span>
            </div>

            {/* Value — hero number */}
            <p className="text-4xl font-bold text-slate-900 tracking-tight leading-none truncate">
              {m.value}
            </p>

            {/* Label */}
            <p className="text-xs font-semibold text-slate-600 mt-1.5 leading-snug">{m.label}</p>

            {/* Context */}
            {m.context && (
              <p className="text-xs text-slate-400 leading-relaxed mt-1.5 line-clamp-2">{m.context}</p>
            )}

            {/* Source */}
            {m.source_url && (
              <a
                href={m.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 text-[11px] text-indigo-500 hover:text-indigo-700 mt-2.5 transition-colors"
              >
                Source <ExternalLink className="w-2.5 h-2.5" />
              </a>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}

function ChartsTab({ gallery }: { gallery: ChartItem[] | null }) {
  if (gallery === null) {
    return (
      <div className="flex gap-3 overflow-hidden">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="skeleton h-52 w-64 flex-shrink-0 rounded-2xl" />
        ))}
      </div>
    );
  }

  if (gallery.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-3 text-slate-400">
        <TrendingUp className="w-8 h-8 opacity-30" />
        <p className="text-sm">No chart data was extracted from this research.</p>
      </div>
    );
  }

  return (
    <div className="relative">
      <div className="pointer-events-none absolute left-0 top-0 bottom-2 w-4 bg-gradient-to-r from-white to-transparent z-10" />
      <div className="pointer-events-none absolute right-0 top-0 bottom-2 w-10 bg-gradient-to-l from-white to-transparent z-10" />
      <div
        className="flex gap-3 overflow-x-auto pb-2"
        style={{ scrollbarWidth: "none", msOverflowStyle: "none" } as React.CSSProperties}
      >
        {gallery.map((chart, i) => (
          <a
            key={i}
            href={chart.source_url || chart.image_url}
            target="_blank"
            rel="noopener noreferrer"
            className="w-64 flex-shrink-0 bg-white rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.07),0_6px_20px_rgba(0,0,0,0.04)] hover:shadow-[0_2px_8px_rgba(0,0,0,0.10),0_12px_28px_rgba(0,0,0,0.07)] overflow-hidden transition-shadow group"
          >
            {/* Chart image */}
            {chart.image_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={chart.image_url}
                alt={chart.title ?? "Chart"}
                className="w-full h-32 object-cover"
              />
            )}
            <div className="p-4">
              <span className="inline-block bg-indigo-50 text-indigo-600 text-[10px] font-semibold px-2 py-0.5 rounded-full mb-2">
                {CHART_TYPE_LABELS[chart.chart_type] ?? "Chart"}
              </span>
              {chart.title && (
                <p className="text-xs font-semibold text-slate-800 line-clamp-2 leading-snug mb-1.5">
                  {chart.title}
                </p>
              )}
              {chart.key_insight && (
                <p className="text-xs text-slate-500 leading-relaxed line-clamp-3">
                  {chart.key_insight}
                </p>
              )}
            </div>
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
      <div className="space-y-3">
        <div className="skeleton h-20 rounded-2xl" />
        <div className="skeleton h-20 rounded-2xl" />
        <div className="skeleton h-20 rounded-2xl" />
      </div>
    );
  }

  const hasContent =
    data.recommendations.length > 0 ||
    data.follow_up_questions.length > 0 ||
    data.risk_flags.length > 0;

  if (!hasContent) {
    return (
      <p className="text-sm text-slate-400 text-center py-10">
        No strategic recommendations were generated.
      </p>
    );
  }

  return (
    <div className="space-y-7">
      {data.recommendations.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-3">
            Recommendations
          </p>
          <div className="space-y-2.5">
            {data.recommendations.map((r, i) => (
              <div
                key={i}
                className="bg-white rounded-2xl p-4 shadow-[0_1px_3px_rgba(0,0,0,0.06),0_4px_12px_rgba(0,0,0,0.04)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2.5 flex-1 min-w-0">
                    <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${PRIORITY_DOT[r.priority] ?? PRIORITY_DOT.medium}`} />
                    <p className="font-semibold text-slate-800 text-sm leading-snug">{r.action}</p>
                  </div>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold flex-shrink-0 uppercase tracking-wide ${PRIORITY_BADGE[r.priority] ?? PRIORITY_BADGE.medium}`}>
                    {r.priority}
                  </span>
                </div>
                {r.rationale && (
                  <p className="text-xs text-slate-500 mt-2 leading-relaxed pl-4">{r.rationale}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {data.follow_up_questions.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-3">
            Follow-up Research
          </p>
          <div className="space-y-2">
            {data.follow_up_questions.map((q, i) => (
              <button
                key={i}
                onClick={() => onFollowUpClick?.(q)}
                className="flex items-center gap-2.5 w-full text-left px-4 py-3 text-sm text-slate-700 rounded-xl bg-indigo-50/60 hover:bg-indigo-100/70 hover:text-indigo-700 transition-colors group"
              >
                <ArrowRight className="w-3.5 h-3.5 flex-shrink-0 text-indigo-400 group-hover:text-indigo-600 transition-colors" />
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {data.risk_flags.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-3">
            Risk Flags
          </p>
          <div className="space-y-2">
            {data.risk_flags.map((f, i) => (
              <div
                key={i}
                className="bg-amber-50/80 border border-amber-200/60 rounded-xl p-3.5 flex items-start gap-2.5"
              >
                <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-semibold text-slate-800 leading-snug">{f.claim}</p>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{f.concern}</p>
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
  const gradient = qualityGradient(data.quality_score);
  const Icon =
    data.quality_score >= 0.8 ? ShieldCheck : data.quality_score >= 0.5 ? Shield : ShieldAlert;

  return (
    <div className={`rounded-2xl bg-gradient-to-r ${gradient} shadow-[0_1px_3px_rgba(0,0,0,0.06),0_6px_20px_rgba(0,0,0,0.04)] px-5 py-4`}>
      <div className="flex items-center gap-4">
        {/* Icon + label + score */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <Icon className={`w-4 h-4 ${iconColor}`} />
          <span className="text-xs font-semibold text-slate-600">Quality signal</span>
        </div>

        {/* Score number */}
        <span className="text-2xl font-bold text-slate-900 tracking-tight leading-none flex-shrink-0">
          {pct}%
        </span>

        {/* Progress bar */}
        <div className="flex-1 min-w-0 h-1.5 bg-black/[0.06] rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${barColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>

        {/* Flags toggle */}
        {data.flagged_count > 0 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1 text-xs font-medium text-amber-600 hover:text-amber-700 flex-shrink-0 transition-colors"
          >
            <AlertTriangle className="w-3.5 h-3.5" />
            {data.flagged_count} {data.flagged_count === 1 ? "flag" : "flags"}
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        )}
      </div>

      {expanded && data.flagged_claims.length > 0 && (
        <div className="mt-3 pt-3 border-t border-black/[0.06] space-y-2">
          {data.flagged_claims.map((c, i) => (
            <div key={i} className="flex items-start gap-2 text-xs">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-slate-700">{c.claim}</span>
                {c.reason && <span className="text-slate-400 ml-1">— {c.reason}</span>}
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
    <div className="w-full space-y-3 animate-fade-in">
      <QualitySignal data={critiqueData} />

      <div className="bg-white rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.06),0_8px_24px_rgba(0,0,0,0.05)] overflow-hidden">
        {/* Underline tab bar */}
        <div className="flex border-b border-slate-100 overflow-x-auto" style={{ scrollbarWidth: "none" } as React.CSSProperties}>
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative flex items-center gap-1.5 px-5 py-3.5 text-sm font-medium whitespace-nowrap transition-colors flex-shrink-0 ${
                activeTab === tab.id
                  ? "text-slate-900"
                  : "text-slate-400 hover:text-slate-600"
              }`}
            >
              {tab.icon}
              {tab.label}
              {activeTab === tab.id && (
                <motion.div
                  layoutId="tab-indicator"
                  className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-600 rounded-full"
                  transition={{ type: "spring", stiffness: 500, damping: 40 }}
                />
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="p-5">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.18 }}
            >
              {activeTab === "frame"    && <ResearchFrameTab data={hypothesisData} />}
              {activeTab === "metrics"  && <KeyMetricsTab metrics={metricsData} />}
              {activeTab === "charts"   && <ChartsTab gallery={chartGallery} />}
              {activeTab === "strategy" && (
                <StrategicOutlookTab data={strategyData} onFollowUpClick={onFollowUpClick} />
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
