"""StructuredDataAgent: retrieves SEC EDGAR XBRL financial data (ADR-007)."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import structlog

from app.agents.base import AgentEvent, EventEmitter, ResearchAgent
from app.models.source import Source

logger = structlog.get_logger(__name__)

_EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
_EDGAR_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_USER_AGENT = "Meridian Research contact@meridianresearch.com"
_MAX_COMPANIES = 3
_MAX_FACTS = 5
_XBRL_METRICS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NetIncomeLoss",
    "EarningsPerShareBasic",
    "GrossProfit",
]


class StructuredDataAgent(ResearchAgent):
    """
    Fetches structured financial data from SEC EDGAR XBRL API.

    Non-fatal: all HTTP and parse errors are logged as warnings and return
    empty results. Never raises AgentFatalError.
    """

    def __init__(
        self,
        session_id: uuid.UUID,
        emitter: EventEmitter,
        db: Any,
    ) -> None:
        super().__init__(session_id, emitter)
        self._db = db

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="structured_data",
                event_type="agent_started",
                payload={"agent": "structured_data"},
            )
        )

        try:
            source_ids, companies = await self._fetch_and_store(
                input_data.get("question", "")
            )
        except Exception as exc:
            logger.warning(
                "edgar_agent_error", session_id=str(self.session_id), error=str(exc)
            )
            await self.emitter.emit(
                AgentEvent(
                    session_id=self.session_id,
                    agent_type="structured_data",
                    event_type="agent_failed",
                    payload={"agent": "structured_data", "error": str(exc)},
                )
            )
            return {"edgar_source_ids": [], "edgar_count": 0, "edgar_companies": []}

        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="structured_data",
                event_type="edgar_fetched",
                payload={
                    "agent": "structured_data",
                    "companies": companies,
                    "facts_count": len(source_ids),
                },
            )
        )
        await self.emitter.emit(
            AgentEvent(
                session_id=self.session_id,
                agent_type="structured_data",
                event_type="agent_completed",
                payload={"agent": "structured_data", "edgar_count": len(source_ids)},
            )
        )
        return {
            "edgar_source_ids": source_ids,
            "edgar_count": len(source_ids),
            "edgar_companies": companies,
        }

    async def _fetch_and_store(
        self, question: str
    ) -> tuple[list[uuid.UUID], list[str]]:
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), headers=headers) as client:
            ciks = await self._search_ciks(client, question)
            if not ciks:
                return [], []

            ciks = ciks[:_MAX_COMPANIES]
            tasks = [self._fetch_company_facts(client, cik) for cik in ciks]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        source_ids: list[uuid.UUID] = []
        companies: list[str] = []
        for cik, result in zip(ciks, results, strict=False):
            if isinstance(result, Exception):
                logger.warning("edgar_facts_error", cik=cik, error=str(result))
                continue
            if result is None:
                continue
            name, content = result
            companies.append(name)
            source = Source(
                session_id=self.session_id,
                url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
                sub_task_index=0,
                title=f"EDGAR: {name} financials",
                raw_content=content,
                source_type="edgar",
            )
            self._db.add(source)
            source_ids.append(source.id)

        if source_ids:
            await self._db.flush()

        return source_ids, companies

    async def _search_ciks(
        self, client: httpx.AsyncClient, question: str
    ) -> list[str]:
        try:
            resp = await client.get(
                _EDGAR_SEARCH_URL,
                params={
                    "q": question,
                    "dateRange": "custom",
                    "startdt": "2023-01-01",
                },
            )
            if resp.status_code != 200:
                logger.warning("edgar_search_error", status=resp.status_code)
                return []
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            ciks: list[str] = []
            seen: set[str] = set()
            for hit in hits:
                cik = str(hit.get("_source", {}).get("entity_id", "")).zfill(10)
                if cik and cik not in seen and cik != "0000000000":
                    seen.add(cik)
                    ciks.append(cik)
                    if len(ciks) >= _MAX_COMPANIES:
                        break
            return ciks
        except Exception as exc:
            logger.warning("edgar_search_exception", error=str(exc))
            return []

    async def _fetch_company_facts(
        self, client: httpx.AsyncClient, cik: str
    ) -> tuple[str, str] | None:
        url = _EDGAR_FACTS_URL.format(cik=cik)
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("edgar_facts_http_error", cik=cik, status=resp.status_code)
                return None
            data = resp.json()
            name = data.get("entityName", f"CIK {cik}")
            us_gaap = data.get("facts", {}).get("us-gaap", {})
            lines: list[str] = [f"Company: {name}"]
            facts_added = 0
            for metric in _XBRL_METRICS:
                if facts_added >= _MAX_FACTS:
                    break
                metric_data = us_gaap.get(metric, {})
                units = metric_data.get("units", {})
                usd_values = units.get("USD", units.get("shares", []))
                annual = [
                    v for v in usd_values
                    if v.get("form") in ("10-K", "10-Q") and v.get("val") is not None
                ]
                annual.sort(key=lambda x: x.get("end", ""), reverse=True)
                for entry in annual[:4]:
                    period = entry.get("end", "")
                    value = entry.get("val", 0)
                    if abs(value) >= 1_000_000:
                        value_str = f"${value / 1_000_000:.1f}M"
                    else:
                        value_str = str(value)
                    lines.append(f"Metric: {metric} | Period: {period} | Value: {value_str}")
                    facts_added += 1
                    if facts_added >= _MAX_FACTS:
                        break
            return name, "\n".join(lines)
        except Exception as exc:
            logger.warning("edgar_facts_exception", cik=cik, error=str(exc))
            return None
