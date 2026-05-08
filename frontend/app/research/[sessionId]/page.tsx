import TraceStream from "@/components/TraceStream";

interface ResearchPageProps {
  params: { sessionId: string };
  searchParams: { q?: string };
}

export default function ResearchPage({ params, searchParams }: ResearchPageProps) {
  const question = searchParams.q ? decodeURIComponent(searchParams.q) : null;

  return (
    <main className="min-h-[calc(100vh-3.5rem)] bg-slate-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        {/* Header */}
        <div className="mb-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-medium mb-3">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
            Research in progress
          </div>
          {question ? (
            <h1 className="text-xl font-bold text-slate-900 leading-snug max-w-2xl">{question}</h1>
          ) : (
            <h1 className="text-xl font-bold text-slate-900">Researching…</h1>
          )}
        </div>
        <TraceStream sessionId={params.sessionId} />
      </div>
    </main>
  );
}
