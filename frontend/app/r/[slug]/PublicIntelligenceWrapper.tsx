"use client";

import { useRouter } from "next/navigation";
import IntelligencePanel from "@/components/IntelligencePanel";
import type {
  HypothesisData,
  Metric,
  ChartItem,
  StrategyData,
  CritiqueData,
} from "@/components/IntelligencePanel";

interface Props {
  hypothesisData: HypothesisData | null;
  metricsData: Metric[] | null;
  chartGallery: ChartItem[] | null;
  strategyData: StrategyData | null;
  critiqueData: CritiqueData | null;
}

export default function PublicIntelligenceWrapper({
  hypothesisData,
  metricsData,
  chartGallery,
  strategyData,
  critiqueData,
}: Props) {
  const router = useRouter();

  function handleFollowUpClick(question: string) {
    const encoded = encodeURIComponent(question);
    router.push(`/auth/signup?q=${encoded}`);
  }

  return (
    <IntelligencePanel
      hypothesisData={hypothesisData}
      metricsData={metricsData}
      chartGallery={chartGallery}
      strategyData={strategyData}
      critiqueData={critiqueData}
      onFollowUpClick={handleFollowUpClick}
    />
  );
}
