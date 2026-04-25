import TraceStream from "@/components/TraceStream";

interface ResearchPageProps {
  params: {
    sessionId: string;
  };
}

export default function ResearchPage({ params }: ResearchPageProps) {
  return (
    <main className="flex min-h-screen flex-col items-center p-8">
      <div className="w-full max-w-3xl flex flex-col gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900">
            Research in progress
          </h1>
          <p className="text-zinc-400 text-xs font-mono mt-1">
            {params.sessionId}
          </p>
        </div>
        <TraceStream sessionId={params.sessionId} />
      </div>
    </main>
  );
}
