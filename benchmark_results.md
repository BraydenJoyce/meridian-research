# Pipeline Benchmark Results

**Total time:** 19.983 seconds
**Assert < 60 s:** PASS

## Per-Stage Breakdown

| Stage | Time (s) | Records |
|---|---|---|
| ingest | 3.454 | 1000 ingested |
| deduplicate | 13.100 | 694 after dedup |
| score | 3.032 | 694 after scoring |
| extract_entities | 0.366 | 36 entities |
| index | 0.031 | 694 chunks indexed |

## Summary Statistics

- **Sources ingested:** 1000
- **Sources after dedup:** 694
- **Sources after scoring:** 694
- **Entities extracted:** 36
- **Chunks indexed:** 694
- **Dedup rate:** 30.6% duplicates removed
