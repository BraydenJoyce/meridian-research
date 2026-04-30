# Agent Parallelism Benchmark

Compares parallel (`asyncio.gather`) vs sequential execution of 4 mock agents, each simulating 0.3s of I/O-bound work.

| Agents | Sleep (s) | Parallel (ms) | Sequential (ms) | Speedup |
|--------|-----------|---------------|-----------------|----------|
| 4 | 0.30 | 313 | 1247 | 3.99x |

**Speedup: 3.99x** — parallel execution takes ~1 agent duration; sequential takes ~N agent durations.
