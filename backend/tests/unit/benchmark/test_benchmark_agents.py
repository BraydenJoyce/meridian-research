"""Tests for benchmark_agents parallel vs sequential timing (t-036)."""
from __future__ import annotations

import pytest

from app.benchmark.benchmark_agents import MockAgent, _format_table, run_parallel, run_sequential


@pytest.mark.asyncio
async def test_parallel_faster_than_sequential() -> None:
    agents = [MockAgent(sleep_seconds=0.05) for _ in range(4)]
    input_data = {"question": "benchmark"}

    _, parallel_ms = await run_parallel(agents, input_data)
    _, sequential_ms = await run_sequential(agents, input_data)

    assert parallel_ms < sequential_ms, (
        f"Parallel ({parallel_ms:.0f}ms) should be faster than sequential ({sequential_ms:.0f}ms)"
    )


@pytest.mark.asyncio
async def test_speedup_at_least_3x() -> None:
    agents = [MockAgent(sleep_seconds=0.05) for _ in range(4)]
    input_data = {"question": "benchmark"}

    _, parallel_ms = await run_parallel(agents, input_data)
    _, sequential_ms = await run_sequential(agents, input_data)

    speedup = sequential_ms / parallel_ms if parallel_ms > 0 else 0.0
    assert speedup >= 3.0, f"Expected speedup >= 3x, got {speedup:.2f}x"


def test_benchmark_output_contains_speedup_table() -> None:
    result = {
        "agent_count": 4,
        "sleep_seconds": 0.05,
        "parallel_ms": 55.0,
        "sequential_ms": 210.0,
        "speedup_factor": 3.81,
    }
    table = _format_table(result)

    assert "| Agents |" in table
    assert "3.81x" in table
    assert "4" in table
