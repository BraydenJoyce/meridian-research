"""Research session worker: parallel agent orchestration (ADR-007)."""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentEvent, AgentFatalError, EventEmitter
from app.agents.chart_gallery import ChartGalleryAgent
from app.agents.critic import CriticAgent
from app.agents.cv_document import CvDocumentAgent
from app.agents.hypothesis import HypothesisAgent
from app.agents.metrics import MetricsAgent
from app.agents.news import NewsAgent
from app.agents.strategist import StrategistAgent
from app.agents.structured_data import StructuredDataAgent
from app.agents.writer import WriterAgent

logger = structlog.get_logger(__name__)

_RESEARCH_TIMEOUT = 120.0
_CRITIC_TIMEOUT = 60.0
_STRATEGIST_TIMEOUT = 60.0

_RESEARCH_AGENT_NAMES = [
    "web_search",
    "cv_document",
    "news",
    "structured_data",
    "metrics",
]


async def run_research_session(
    session_id: uuid.UUID,
    question: str,
    sub_tasks: list[str],
    emitter: EventEmitter,
    db: AsyncSession,
    settings: Any,
    pro_mode: bool = False,
) -> dict[str, Any]:
    """
    Orchestrate the full research pipeline for a session.

    Pipeline:
      Planner (called before this function) →
      HypothesisAgent (sequential, fast) →
      WebSearchAgent (fatal if fails) →
      parallel [CvDocumentAgent, NewsAgent, StructuredDataAgent, MetricsAgent] →
      ChartGalleryAgent (deterministic, no LLM) →
      WriterAgent →
      parallel [CriticAgent, StrategistAgent]

    Non-fatal agent failures (CV, News, EDGAR, Metrics, Critic, Strategist) do not
    abort the session. WebSearch and Writer failures are fatal.
    """
    input_data = {"question": question, "sub_tasks": sub_tasks}

    # Phase 1: Hypothesis (fast, gives user immediate framing)
    await _run_hypothesis(session_id, emitter, db, input_data)

    # Phase 2: Web search (fatal if insufficient sources)
    web_results = await _run_web_search(session_id, emitter, db, input_data, settings, pro_mode)

    # Phase 3: Parallel enrichment — CV, News, EDGAR, Metrics
    cv_agent = CvDocumentAgent(
        session_id=session_id,
        emitter=emitter,
        db=db,
        modal_base_url=settings.modal_base_url,
        modal_api_secret=settings.modal_api_secret,
    )
    news_agent = NewsAgent(
        session_id=session_id,
        emitter=emitter,
        db=db,
        newsapi_key=getattr(settings, "newsapi_key", ""),
        gnews_key=getattr(settings, "gnews_key", ""),
    )
    edgar_agent = StructuredDataAgent(
        session_id=session_id,
        emitter=emitter,
        db=db,
    )
    metrics_agent = MetricsAgent(
        session_id=session_id,
        emitter=emitter,
        db=db,
    )

    enrichment_results = await _run_parallel_agents(
        [cv_agent, news_agent, edgar_agent, metrics_agent],
        ["cv_document", "news", "structured_data", "metrics"],
        input_data,
    )

    merged = _merge_results(web_results, enrichment_results)
    merged.update(input_data)

    # Phase 4: Chart gallery (deterministic, materialises CV output for frontend)
    chart_gallery_agent = ChartGalleryAgent(
        session_id=session_id,
        emitter=emitter,
        db=db,
    )
    try:
        gallery_result = await chart_gallery_agent.run({"chart_results": merged.get("chart_results", [])})
        merged["chart_gallery"] = gallery_result.get("chart_gallery", [])
    except Exception as exc:
        logger.warning("chart_gallery_agent_failed", session_id=str(session_id), error=str(exc))

    await emitter.emit(
        AgentEvent(
            session_id=session_id,
            agent_type="orchestrator",
            event_type="orchestration_summary",
            payload=merged.get("_meta", {}),
        )
    )

    # Phase 5: Writer (fatal if empty report)
    writer = WriterAgent(session_id=session_id, emitter=emitter, db=db)
    writer_result = await writer.run(merged)

    report_markdown = writer_result.get("report_markdown", "")
    metrics: list[dict[str, Any]] = merged.get("metrics", [])

    # Phase 6: Critic + Strategist in parallel
    critic_input = {"report_markdown": report_markdown, "sources": []}
    strategist_input = {
        "report_markdown": report_markdown,
        "question": question,
        "metrics": metrics,
    }

    await asyncio.gather(
        _run_critic(session_id, emitter, db, critic_input),
        _run_strategist(session_id, emitter, db, strategist_input),
        return_exceptions=True,
    )

    return writer_result


async def _run_hypothesis(
    session_id: uuid.UUID,
    emitter: EventEmitter,
    db: AsyncSession,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    agent = HypothesisAgent(session_id=session_id, emitter=emitter, db=db)
    try:
        return await asyncio.wait_for(agent.run(input_data), timeout=30.0)
    except TimeoutError:
        logger.warning("hypothesis_timeout", session_id=str(session_id))
        return {}
    except Exception as exc:
        logger.warning("hypothesis_error", session_id=str(session_id), error=str(exc))
        return {}


async def _run_web_search(
    session_id: uuid.UUID,
    emitter: EventEmitter,
    db: AsyncSession,
    input_data: dict[str, Any],
    settings: Any,
    pro_mode: bool = False,
) -> dict[str, Any]:
    from app.agents.web_search import WebSearchAgent

    agent = WebSearchAgent(
        session_id=session_id,
        emitter=emitter,
        db=db,
        tavily_api_key=settings.tavily_api_key,
        results_per_subtask=15 if pro_mode else 10,
    )
    try:
        return await asyncio.wait_for(agent.run(input_data), timeout=_RESEARCH_TIMEOUT)
    except TimeoutError as exc:
        raise AgentFatalError("WebSearchAgent timed out") from exc


async def _run_parallel_agents(
    agents: list[Any],
    names: list[str],
    input_data: dict[str, Any],
) -> list[dict[str, Any] | BaseException]:
    async def _run(agent: Any, name: str) -> dict[str, Any]:
        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(agent.run(input_data), timeout=_RESEARCH_TIMEOUT)
            logger.info("agent_timing", agent=name, elapsed_ms=int((time.monotonic() - t0) * 1000))
            return result
        except TimeoutError:
            logger.warning("agent_timeout", agent=name, timeout=_RESEARCH_TIMEOUT)
            return {}

    results = await asyncio.gather(
        *[_run(a, n) for a, n in zip(agents, names, strict=False)],
        return_exceptions=True,
    )
    return list(results)


def _merge_results(
    web_results: dict[str, Any],
    enrichment_results: list[dict[str, Any] | BaseException],
) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "chart_results": [],
        "news_source_ids": [],
        "edgar_source_ids": [],
        "metrics": [],
    }
    merged.update(web_results)

    agent_names = ["cv_document", "news", "structured_data", "metrics"]
    agents_succeeded = 1
    agents_failed = 0

    for name, result in zip(agent_names, enrichment_results, strict=False):
        if isinstance(result, BaseException):
            logger.warning("enrichment_agent_failed", agent=name, error=str(result))
            agents_failed += 1
        elif isinstance(result, dict):
            if name == "metrics":
                merged["metrics"] = result.get("metrics", [])
            else:
                merged.update(result)
            agents_succeeded += 1
        else:
            agents_failed += 1

    merged["_meta"] = {
        "agents_succeeded": agents_succeeded,
        "agents_failed": agents_failed,
        "total_sources": web_results.get("sources_count", 0),
        "chart_count": len(merged.get("chart_results", [])),
        "metric_count": len(merged.get("metrics", [])),
    }
    return merged


async def _run_critic(
    session_id: uuid.UUID,
    emitter: EventEmitter,
    db: AsyncSession,
    critic_input: dict[str, Any],
) -> dict[str, Any]:
    critic = CriticAgent(session_id=session_id, emitter=emitter, db=db)
    try:
        return await asyncio.wait_for(critic.run(critic_input), timeout=_CRITIC_TIMEOUT)
    except TimeoutError:
        logger.warning("critic_timeout", session_id=str(session_id))
        return {"quality_score": 1.0, "flagged_claims": []}
    except Exception as exc:
        logger.warning("critic_error", session_id=str(session_id), error=str(exc))
        return {"quality_score": 1.0, "flagged_claims": []}


async def _run_strategist(
    session_id: uuid.UUID,
    emitter: EventEmitter,
    db: AsyncSession,
    strategist_input: dict[str, Any],
) -> dict[str, Any]:
    strategist = StrategistAgent(session_id=session_id, emitter=emitter, db=db)
    try:
        return await asyncio.wait_for(strategist.run(strategist_input), timeout=_STRATEGIST_TIMEOUT)
    except TimeoutError:
        logger.warning("strategist_timeout", session_id=str(session_id))
        return {"recommendations": [], "follow_up_questions": [], "risk_flags": []}
    except Exception as exc:
        logger.warning("strategist_error", session_id=str(session_id), error=str(exc))
        return {"recommendations": [], "follow_up_questions": [], "risk_flags": []}
