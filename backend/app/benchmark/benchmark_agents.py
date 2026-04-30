"""Benchmark: parallel vs sequential agent execution timing (ADR-007)."""
from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

from app.agents.base import AgentEvent, EventEmitter, ResearchAgent


class _NullEmitter(EventEmitter):
    async def emit(self, event: AgentEvent) -> None:
        pass


class MockAgent(ResearchAgent):
    """Simulates an agent with a configurable sleep to model real latency."""

    def __init__(self, sleep_seconds: float = 0.5, name: str = "mock") -> None:
        super().__init__(uuid.uuid4(), _NullEmitter())
        self._sleep = sleep_seconds
        self._name = name

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(self._sleep)
        return {"agent": self._name, "elapsed": self._sleep}


async def run_parallel(
    agents: list[MockAgent], input_data: dict[str, Any]
) -> tuple[list[dict[str, Any]], float]:
    t0 = time.monotonic()
    results = await asyncio.gather(*[a.run(input_data) for a in agents])
    elapsed_ms = (time.monotonic() - t0) * 1000
    return list(results), elapsed_ms


async def run_sequential(
    agents: list[MockAgent], input_data: dict[str, Any]
) -> tuple[list[dict[str, Any]], float]:
    t0 = time.monotonic()
    results = [await a.run(input_data) for a in agents]
    elapsed_ms = (time.monotonic() - t0) * 1000
    return results, elapsed_ms


async def _benchmark(
    agent_count: int = 4, sleep_seconds: float = 0.3
) -> dict[str, float]:
    agents = [
        MockAgent(sleep_seconds=sleep_seconds, name=f"agent_{i}")
        for i in range(agent_count)
    ]
    input_data: dict[str, Any] = {"question": "benchmark"}

    _, parallel_ms = await run_parallel(agents, input_data)
    _, sequential_ms = await run_sequential(agents, input_data)
    speedup = sequential_ms / parallel_ms if parallel_ms > 0 else 0.0

    return {
        "agent_count": agent_count,
        "sleep_seconds": sleep_seconds,
        "parallel_ms": parallel_ms,
        "sequential_ms": sequential_ms,
        "speedup_factor": speedup,
    }


def _format_table(result: dict[str, float]) -> str:
    return (
        "| Agents | Sleep (s) | Parallel (ms) | Sequential (ms) | Speedup |\n"
        "|--------|-----------|---------------|-----------------|----------|\n"
        f"| {int(result['agent_count'])} | {result['sleep_seconds']:.2f} "
        f"| {result['parallel_ms']:.0f} | {result['sequential_ms']:.0f} "
        f"| {result['speedup_factor']:.2f}x |\n"
    )


def main() -> None:
    result = asyncio.run(_benchmark(agent_count=4, sleep_seconds=0.3))

    table = _format_table(result)
    print("\n## Agent Parallelism Benchmark\n")
    print(table)
    print(f"Speedup: {result['speedup_factor']:.2f}x with {int(result['agent_count'])} agents\n")

    md = (
        "# Agent Parallelism Benchmark\n\n"
        "Compares parallel (`asyncio.gather`) vs sequential execution of 4 mock agents, "
        "each simulating 0.3s of I/O-bound work.\n\n"
        f"{table}\n"
        f"**Speedup: {result['speedup_factor']:.2f}x** — "
        "parallel execution takes ~1 agent duration; sequential takes ~N agent durations.\n"
    )

    out = Path(__file__).parents[3] / "benchmark_agents.md"
    out.write_text(md, encoding="utf-8")
    print(f"Results written to {out}")


if __name__ == "__main__":
    main()
