"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle, AlertCircle, Loader2, Radio } from "lucide-react";
import ReportViewer from "@/components/ReportViewer";

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
  etl: "ETL Pipeline",
  writer: "Writer",
  system: "System",
};

function formatEventLabel(event: StreamEvent): string {
  const agent = event.agent_type ? (AGENT_LABELS[event.agent_type] ?? event.agent_type) : "";
  switch (event.event_type) {
    case "agent_started":
      return `${agent} started`;
    case "agent_completed":
      return `${agent} completed`;
    case "agent_failed":
      return `${agent} failed`;
    case "sub_task_started":
      return `Sub-task started: ${String((event.payload as Record<string, unknown>)?.query ?? "")}`;
    case "sub_task_completed":
      return `Sub-task completed (${String((event.payload as Record<string, unknown>)?.source_count ?? 0)} sources)`;
    case "source_fetched":
      return `Source fetched: ${String((event.payload as Record<string, unknown>)?.title ?? (event.payload as Record<string, unknown>)?.url ?? "")}`;
    case "report_complete":
      return "Report generated";
    case "done":
      return event.status === "failed" ? "Research failed" : "Research complete";
    default:
      return event.event_type;
  }
}

function EventIcon({ event }: { event: StreamEvent }) {
  if (event.event_type === "agent_failed" || event.status === "failed") {
    return <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />;
  }
  if (event.event_type === "agent_completed" || event.event_type === "done") {
    return <CheckCircle className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />;
  }
  return <Radio className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />;
}

export default function TraceStream({ sessionId }: TraceStreamProps) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [reportMarkdown, setReportMarkdown] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const es = new EventSource(`/api/research/${sessionId}/stream`);
    setConnected(true);

    es.onmessage = (e: MessageEvent<string>) => {
      let parsed: StreamEvent;
      try {
        parsed = JSON.parse(e.data) as StreamEvent;
      } catch {
        return;
      }

      setEvents((prev) => [...prev, parsed]);

      if (parsed.event_type === "report_complete") {
        const md = (parsed.payload as Record<string, unknown>)?.markdown;
        if (typeof md === "string") {
          setReportMarkdown(md);
        }
      }

      if (parsed.event_type === "done") {
        setDone(true);
        es.close();
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

  return (
    <div className="flex flex-col gap-6 w-full">
      {!connected && events.length === 0 && (
        <div className="flex items-center gap-2 text-zinc-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Connecting to research stream…</span>
        </div>
      )}

      {events.length > 0 && (
        <div className="flex flex-col gap-2 rounded-lg border border-zinc-200 bg-zinc-50 p-4 max-h-96 overflow-y-auto">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-1">
            Research Trace
          </p>
          {events.map((event, i) => (
            <div key={i} className="flex items-start gap-2 text-sm">
              <EventIcon event={event} />
              <span className="text-zinc-700 leading-tight">{formatEventLabel(event)}</span>
              {event.timestamp && (
                <span className="ml-auto text-zinc-400 text-xs flex-shrink-0">
                  {new Date(event.timestamp).toLocaleTimeString()}
                </span>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      {!done && connected && events.length === 0 && (
        <div className="flex items-center gap-2 text-zinc-500 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Waiting for first event…</span>
        </div>
      )}

      {reportMarkdown && <ReportViewer markdown={reportMarkdown} />}
    </div>
  );
}
