import { ResearchForm } from "@/components/ResearchForm";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="w-full max-w-2xl flex flex-col gap-8">
        <div className="flex flex-col gap-2">
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900">
            Meridian Research
          </h1>
          <p className="text-zinc-500">
            Submit a business question and get a cited intelligence report in minutes.
          </p>
        </div>
        <ResearchForm />
      </div>
    </main>
  );
}
