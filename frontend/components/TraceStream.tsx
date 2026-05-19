"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CheckCircle, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
import ReportViewer from "@/components/ReportViewer";
import IntelligencePanel, {
  type ChartItem,
  type CritiqueData,
  type HypothesisData,
  type Metric,
  type StrategyData,
} from "@/components/IntelligencePanel";

interface StreamEvent {
  event_type: string;
  agent_type?: string;
  sequence_number?: number;
  timestamp?: string;
  payload?: Record<string, unknown>;
  status?: string;
}

interface TraceStreamProps {
  sessionId: string;
}

const AGENT_LABELS: Record<string, string> = {
  planner: "Planner",
  web_search: "Web Search",
  cv_document: "CV Document",
  news: "News",
  structured_data: "Structured Data",
  etl: "ETL Pipeline",
  writer: "Writer",
  critic: "Critic",
  orchestrator: "Orchestrator",
  system: "System",
  hypothesis: "Hypothesis",
  metrics: "Metrics",
  chart_gallery: "Chart Gallery",
  strategist: "Strategist",
};

function formatEventLabel(event: StreamEvent): string {
  const agent = event.agent_type ? (AGENT_LABELS[event.agent_type] ?? event.agent_type) : "";
  const p = (event.payload ?? {}) as Record<string, unknown>;
  switch (event.event_type) {
    case "agent_started":     return `${agent} started`;
    case "agent_completed":   return `${agent} completed`;
    case "agent_failed":      return `${agent} failed`;
    case "sub_task_started":  return `Searching: ${String(p.query ?? "")}`;
    case "sub_task_completed":return `Sub-task done (${String(p.source_count ?? 0)} sources)`;
    case "source_fetched":    return `Fetched: ${String(p.title ?? p.url ?? "")}`;
    case "hypothesis_ready":  return "Research frame ready";
    case "metrics_ready":     return `Metrics extracted (${String(p.metric_count ?? 0)})`;
    case "chart_gallery_ready": return `Charts catalogued (${String(p.chart_count ?? 0)})`;
    case "strategy_ready":    return `Strategic outlook ready`;
    case "report_complete":   return "Report generated";
    case "report_critique":   return `Fact-check complete (${Math.round(Number(p.quality_score ?? 1) * 100)}% quality)`;
    case "done":              return event.status === "failed" ? "Research failed" : "Research complete";
    default:                  return event.event_type;
  }
}

function EventDot({ event }: { event: StreamEvent }) {
  if (event.event_type === "agent_failed" || event.status === "failed") {
    return (
      <span className="w-4 h-4 rounded-full border-2 border-red-400 bg-red-50 flex items-center justify-center flex-shrink-0">
        <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
      </span>
    );
  }
  if (event.event_type === "agent_completed" || event.event_type === "done") {
    return <CheckCircle className="w-4 h-4 text-emerald-500 flex-shrink-0" />;
  }
  return (
    <span className="w-4 h-4 rounded-full border-2 border-indigo-400 bg-indigo-50 flex items-center justify-center flex-shrink-0">
      <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
    </span>
  );
}

export default function TraceStream({ sessionId }: TraceStreamProps) {
  const router = useRouter();
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [reportMarkdown, setReportMarkdown] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [traceOpen, setTraceOpen] = useState(true);

  const [hypothesisData, setHypothesisData] = useState<HypothesisData | null>(null);
  const [metricsData, setMetricsData] = useState<Metric[] | null>(null);
  const [chartGallery, setChartGallery] = useState<ChartItem[] | null>(null);
  const [strategyData, setStrategyData] = useState<StrategyData | null>(null);
  const [critiqueData, setCritiqueData] = useState<CritiqueData | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const es = new EventSource(`${apiUrl}/api/research/${sessionId}/stream`);
    setConnected(true);

    es.onmessage = (e: MessageEvent<string>) => {
      let parsed: StreamEvent;
      try { parsed = JSON.parse(e.data) as StreamEvent; } catch { return; }

      setEvents((prev) => [...prev, parsed]);
      const p = (parsed.payload ?? {}) as Record<string, unknown>;

      if (parsed.event_type === "hypothesis_ready") setHypothesisData(parsed.payload as unknown as HypothesisData);
      if (parsed.event_type === "metrics_ready" && Array.isArray(p.metrics)) setMetricsData(p.metrics as Metric[]);
      if (parsed.event_type === "chart_gallery_ready" && Array.isArray(p.gallery)) setChartGallery(p.gallery as ChartItem[]);
      if (parsed.event_type === "strategy_ready" && Array.isArray(p.recommendations)) {
        setStrategyData({
          recommendations: p.recommendations as StrategyData["recommendations"],
          follow_up_questions: Array.isArray(p.follow_up_questions) ? (p.follow_up_questions as string[]) : [],
          risk_flags: Array.isArray(p.risk_flags) ? (p.risk_flags as StrategyData["risk_flags"]) : [],
        });
      }
      if (parsed.event_type === "report_critique") {
        setCritiqueData({
          quality_score: Number(p.quality_score ?? 1),
          flagged_count: Number(p.flagged_count ?? 0),
          flagged_claims: Array.isArray(p.flagged_claims) ? (p.flagged_claims as CritiqueData["flagged_claims"]) : [],
        });
      }
      if (parsed.event_type === "report_complete") {
        const md = p.markdown;
        if (typeof md === "string") setReportMarkdown(md);
      }
      if (parsed.event_type === "done") {
        setDone(true);
        setTraceOpen(false);
        es.close();
        setMetricsData((prev) => prev ?? []);
        setChartGallery((prev) => prev ?? []);
        setStrategyData((prev) => prev ?? { recommendations: [], follow_up_questions: [], risk_flags: [] });
      }
    };

    es.onerror = () => { setConnected(false); es.close(); };
    return () => es.close();
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  function handleFollowUpClick(question: string) {
    router.push(`/?q=${encodeURIComponent(question)}`);
  }

  return (
    <div className="flex flex-col gap-4 w-full animate-fade-in">
      {/* Connecting states */}
      {!connected && events.length === 0 && (
        <div className="flex items-center gap-3 px-5 py-4 bg-white rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.06)] text-slate-500 text-sm">
          <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
          Connecting to research stream…
        </div>
      )}
      {connected && events.length === 0 && !done && (
        <div className="flex items-center gap-3 px-5 py-4 bg-white rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.06)] text-slate-500 text-sm">
          <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
          Initializing research pipeline…
        </div>
      )}

      {/* Event timeline */}
      {events.length > 0 && (
        <div className="bg-white rounded-2xl shadow-[0_1px_3px_rgba(0,0,0,0.06),0_6px_20px_rgba(0,0,0,0.04)] overflow-hidden">
          {/* Header */}
          <button
            onClick={() => setTraceOpen((v) => !v)}
            className="w-full flex items-center justify-between px-5 py-3.5 border-b border-slate-100 hover:bg-slate-50/50 transition-colors"
          >
            <div className="flex items-center gap-3">
              {done ? (
                <CheckCircle className="w-4 h-4 text-emerald-500" />
              ) : (
                <span className="w-4 h-4 rounded-full border-2 border-indigo-400 flex items-center justify-center">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
                </span>
              )}
              <span className="text-xs font-semibold text-slate-700">
                {done ? "Research complete" : "Research in progress"}
              </span>
              <span className="text-xs text-slate-400 tabular-nums">{events.length} events</span>
            </div>
            {traceOpen
              ? <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
              : <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            }
          </button>

          {/* Timeline */}
          {traceOpen && (
            <div className="max-h-72 overflow-y-auto px-5 py-3">
              <div className="relative">
                {/* Vertical line */}
                <div className="absolute left-[7px] top-2 bottom-2 w-px bg-slate-100" />

                <div className="space-y-0">
                  {events.map((event, i) => (
                    <div key={i} className="flex items-start gap-3 py-1.5 relative">
                      <EventDot event={event} />
                      <div className="flex-1 flex items-baseline justify-between gap-2 min-w-0">
                        <span className="text-xs text-slate-600 leading-snug truncate">
                          {formatEventLabel(event)}
                        </span>
                        {event.timestamp && (
                          <span className="text-[10px] text-slate-400 flex-shrink-0 font-mono tabular-nums">
                            {new Date(event.timestamp).toLocaleTimeString([], {
                              hour: "2-digit", minute: "2-digit", second: "2-digit",
                            })}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      )}

      {/* Intelligence panel */}
      <IntelligencePanel
        hypothesisData={hypothesisData}
        metricsData={metricsData}
        chartGallery={chartGallery}
        strategyData={strategyData}
        critiqueData={critiqueData}
        onFollowUpClick={handleFollowUpClick}
      />

      {reportMarkdown && <ReportViewer markdown={reportMarkdown} />}
    </div>
  );
}
