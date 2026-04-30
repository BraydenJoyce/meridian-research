"""Research session worker: parallel agent orchestration (ADR-007)."""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentEvent, AgentFatalError, EventEmitter
from app.agents.critic import CriticAgent
from app.agents.cv_document import CvDocumentAgent
from app.agents.news import NewsAgent
from app.agents.structured_data import StructuredDataAgent
from app.agents.writer import WriterAgent

logger = structlog.get_logger(__name__)

_RESEARCH_TIMEOUT = 120.0
_CRITIC_TIMEOUT = 60.0

_RESEARCH_AGENT_NAMES = [
    "web_search",
    "cv_document",
    "news",
    "structured_data",
]


async def run_research_session(
    session_id: uuid.UUID,
    question: str,
    sub_tasks: list[str],
    emitter: EventEmitter,
    db: AsyncSession,
    settings: Any,
) -> dict[str, Any]:
    """
    Orchestrate the full research pipeline for a session.

    Runs WebSearchAgent, CvDocumentAgent, NewsAgent, StructuredDataAgent in parallel
    (ADR-007). Merges results into WriterAgent input. Runs CriticAgent after writer.
    Non-fatal agent failures (CV, News, EDGAR, Critic) do not abort the session.
    WebSearch failure is fatal.
    """
    input_data = {"question": question, "sub_tasks": sub_tasks}

    web_results = await _run_web_search(session_id, emitter, db, input_data, settings)

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

    enrichment_results = await _run_parallel_agents(
        [cv_agent, news_agent, edgar_agent],
        ["cv_document", "news", "structured_data"],
        input_data,
    )

    merged = _merge_results(web_results, enrichment_results)
    merged.update(input_data)

    await emitter.emit(
        AgentEvent(
            session_id=session_id,
            agent_type="orchestrator",
            event_type="orchestration_summary",
            payload=merged.get("_meta", {}),
        )
    )

    writer = WriterAgent(session_id=session_id, emitter=emitter, db=db)
    writer_result = await writer.run(merged)

    critic_input = {
        "report_markdown": writer_result.get("report_markdown", ""),
        "sources": [],
    }
    await _run_critic(session_id, emitter, db, critic_input)

    return writer_result


async def _run_web_search(
    session_id: uuid.UUID,
    emitter: EventEmitter,
    db: AsyncSession,
    input_data: dict[str, Any],
    settings: Any,
) -> dict[str, Any]:
    from app.agents.web_search import WebSearchAgent

    agent = WebSearchAgent(
        session_id=session_id,
        emitter=emitter,
        db=db,
        tavily_api_key=settings.tavily_api_key,
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
    }
    merged.update(web_results)

    agent_names = ["cv_document", "news", "structured_data"]
    agents_succeeded = 1
    agents_failed = 0

    for name, result in zip(agent_names, enrichment_results, strict=False):
        if isinstance(result, BaseException):
            logger.warning("enrichment_agent_failed", agent=name, error=str(result))
            agents_failed += 1
        elif isinstance(result, dict):
            merged.update(result)
            agents_succeeded += 1
        else:
            agents_failed += 1

    merged["_meta"] = {
        "agents_succeeded": agents_succeeded,
        "agents_failed": agents_failed,
        "total_sources": web_results.get("sources_count", 0),
        "chart_count": len(merged.get("chart_results", [])),
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
