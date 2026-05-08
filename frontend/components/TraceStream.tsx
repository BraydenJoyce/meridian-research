"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CheckCircle, AlertCircle, Loader2, Radio, ChevronDown, ChevronUp } from "lucide-react";
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
    case "agent_started":
      return `${agent} started`;
    case "agent_completed":
      return `${agent} completed`;
    case "agent_failed":
      return `${agent} failed`;
    case "sub_task_started":
      return `Sub-task started: ${String(p.query ?? "")}`;
    case "sub_task_completed":
      return `Sub-task completed (${String(p.source_count ?? 0)} sources)`;
    case "source_fetched":
      return `Source fetched: ${String(p.title ?? p.url ?? "")}`;
    case "hypothesis_ready":
      return "Research frame ready";
    case "metrics_ready":
      return `Metrics extracted (${String(p.metric_count ?? 0)})`;
    case "chart_gallery_ready":
      return `Charts catalogued (${String(p.chart_count ?? 0)})`;
    case "strategy_ready":
      return `Strategic outlook ready (${String(p.recommendation_count ?? 0)} recommendations)`;
    case "report_complete":
      return "Report generated";
    case "report_critique":
      return `Fact-check complete (quality: ${Math.round(Number(p.quality_score ?? 1) * 100)}%)`;
    case "done":
      return event.status === "failed" ? "Research failed" : "Research complete";
    default:
      return event.event_type;
  }
}

function EventIcon({ event }: { event: StreamEvent }) {
  if (event.event_type === "agent_failed" || event.status === "failed")
    return <AlertCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0 mt-0.5" />;
  if (event.event_type === "agent_completed" || event.event_type === "done")
    return <CheckCircle className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0 mt-0.5" />;
  return <Radio className="w-3.5 h-3.5 text-indigo-400 flex-shrink-0 mt-0.5 animate-pulse" />;
}

export default function TraceStream({ sessionId }: TraceStreamProps) {
  const router = useRouter();
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [reportMarkdown, setReportMarkdown] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [traceOpen, setTraceOpen] = useState(true);

  // Intelligence panel — all data arrives via SSE
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
      try {
        parsed = JSON.parse(e.data) as StreamEvent;
      } catch {
        return;
      }

      setEvents((prev) => [...prev, parsed]);

      const p = (parsed.payload ?? {}) as Record<string, unknown>;

      if (parsed.event_type === "hypothesis_ready") {
        setHypothesisData(parsed.payload as unknown as HypothesisData);
      }

      if (parsed.event_type === "metrics_ready" && Array.isArray(p.metrics)) {
        setMetricsData(p.metrics as Metric[]);
      }

      if (parsed.event_type === "chart_gallery_ready" && Array.isArray(p.gallery)) {
        setChartGallery(p.gallery as ChartItem[]);
      }

      if (parsed.event_type === "strategy_ready" && Array.isArray(p.recommendations)) {
        setStrategyData({
          recommendations: p.recommendations as StrategyData["recommendations"],
          follow_up_questions: Array.isArray(p.follow_up_questions)
            ? (p.follow_up_questions as string[])
            : [],
          risk_flags: Array.isArray(p.risk_flags)
            ? (p.risk_flags as StrategyData["risk_flags"])
            : [],
        });
      }

      if (parsed.event_type === "report_critique") {
        setCritiqueData({
          quality_score: Number(p.quality_score ?? 1),
          flagged_count: Number(p.flagged_count ?? 0),
          flagged_claims: Array.isArray(p.flagged_claims)
            ? (p.flagged_claims as CritiqueData["flagged_claims"])
            : [],
        });
      }

      if (parsed.event_type === "report_complete") {
        const md = p.markdown;
        if (typeof md === "string") {
          setReportMarkdown(md);
        }
      }

      if (parsed.event_type === "done") {
        setDone(true);
        setTraceOpen(false); // auto-collapse when done
        es.close();
        // Ensure empty-state fallbacks for any agents that didn't produce data
        setMetricsData((prev) => prev ?? []);
        setChartGallery((prev) => prev ?? []);
        setStrategyData(
          (prev) => prev ?? { recommendations: [], follow_up_questions: [], risk_flags: [] }
        );
      }
    };

    es.onerror = () => {
      setConnected(false);
      es.close();
    };

    return () => {
      es.close();
    };
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  function handleFollowUpClick(question: string) {
    router.push(`/?q=${encodeURIComponent(question)}`);
  }

  return (
    <div className="flex flex-col gap-5 w-full animate-fade-in">
      {/* Connection states */}
      {!connected && events.length === 0 && (
        <div className="flex items-center gap-2.5 px-4 py-3 bg-white rounded-xl border border-slate-200 text-slate-500 text-sm shadow-sm">
          <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
          Connecting to research stream…
        </div>
      )}
      {connected && events.length === 0 && !done && (
        <div className="flex items-center gap-2.5 px-4 py-3 bg-white rounded-xl border border-slate-200 text-slate-500 text-sm shadow-sm">
          <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
          Initializing research pipeline…
        </div>
      )}

      {/* Event trace - collapsible */}
      {events.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <button
            onClick={() => setTraceOpen((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-3 border-b border-slate-100 hover:bg-slate-50 transition-colors"
          >
            <div className="flex items-center gap-2.5">
              {done ? (
                <CheckCircle className="w-4 h-4 text-emerald-500" />
              ) : (
                <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
              )}
              <span className="text-xs font-semibold text-slate-700">
                {done ? "Research complete" : "Research in progress"}
              </span>
              <span className="text-xs text-slate-400">({events.length} events)</span>
            </div>
            {traceOpen ? (
              <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            )}
          </button>

          {traceOpen && (
            <div className="max-h-72 overflow-y-auto">
              {events.map((event, i) => (
                <div
                  key={i}
                  className="flex items-start gap-3 px-4 py-2.5 border-b border-slate-50 last:border-0 hover:bg-slate-50/50"
                >
                  <EventIcon event={event} />
                  <span className="text-sm text-slate-700 leading-snug flex-1">
                    {formatEventLabel(event)}
                  </span>
                  {event.timestamp && (
                    <span className="text-xs text-slate-400 flex-shrink-0 font-mono">
                      {new Date(event.timestamp).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </span>
                  )}
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      )}

      {/* Intelligence panel and report */}
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
