interface ResearchPageProps {
  params: {
    sessionId: string;
  };
}

export default function ResearchPage({ params }: ResearchPageProps) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="w-full max-w-3xl flex flex-col gap-4">
        <h1 className="text-2xl font-bold tracking-tight text-zinc-900">
          Research in progress
        </h1>
        <p className="text-zinc-500 text-sm font-mono">
          Session: {params.sessionId}
        </p>
        <p className="text-zinc-400 text-sm">
          Live trace stream coming soon.
        </p>
      </div>
    </main>
  );
}
