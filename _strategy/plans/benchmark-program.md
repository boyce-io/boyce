# Plan: Benchmark Program — With Boyce vs. Without Boyce
**Status:** Planned — Stage 7 post-publish
**Created:** 2026-03-17
**Depends on:** Tier 2 test warehouse operational (Stage 6)

## Goal
Published, reproducible benchmark showing measurable improvement when Boyce is
present in an agentic database workflow. Results appear on README, product page,
and PyPI. This is the primary marketing asset for adoption.

---

## What We Measure

| Metric | Definition | How measured |
|--------|-----------|-------------|
| SQL accuracy | Does the generated SQL return the correct result set? | Compare against ground-truth SQL output |
| Token consumption | Total tokens used in the NL→SQL pipeline | Platform-specific token counting |
| Error rate | Queries that produce invalid SQL or runtime errors | EXPLAIN pre-flight + execution |
| NULL trap detection | Queries where NULL distribution would corrupt results | Ground truth: known NULL-heavy columns |
| Join correctness | Correct join path chosen (no Cartesian, no hallucinated joins) | Compare against known-correct join graph |

## Ground-Truth Query Set

20-50 queries against the Tier 2 warehouse, spanning:
- Simple aggregation (single table, single metric)
- Multi-join (3+ tables, Dijkstra path required)
- NULL-trap-prone (equality filter on high-NULL column)
- Ambiguous naming (column name exists in multiple tables)
- Temporal filters (date ranges, DATE_TRUNC)
- Mixed grain (aggregation + detail in same query intent)

Each query has:
- Natural language prompt
- Known-correct SQL (hand-verified)
- Expected result set (or row count + spot checks)
- Known failure mode without Boyce (what goes wrong and why)

## Platform Matrix

| Platform | Config | Status |
|----------|--------|--------|
| Claude Code | `.claude/settings.json` MCP | v0.1 mandatory |
| Cursor | `.cursor/mcp.json` | v0.1 mandatory |
| Codex | `~/.codex/config.toml` | v0.1 mandatory |
| VS Code (native MCP) | `.vscode/mcp.json` | v0.1 stretch |
| DataGrip | AI Assistant MCP settings | v0.2 |

## Harness Design

Plug-and-play: adding a new platform = adding a config file, not writing new test code.

```
test_warehouses/benchmarks/
├── ground_truth/          # query definitions + expected results
│   ├── 001_simple_agg.yml
│   ├── 002_multi_join.yml
│   └── ...
├── platforms/             # per-platform config
│   ├── claude_code.yml
│   ├── cursor.yml
│   └── codex.yml
├── results/               # timestamped benchmark runs
│   └── 2026-03-XX/
├── run_benchmark.py       # orchestrator
└── report.py              # generates comparison table
```

## Output Format

The comparison table — clean, scannable, goes on README + product page + PyPI:

```
                    With Boyce    Without Boyce
SQL Accuracy        XX%           XX%
NULL Traps Caught   XX/XX         0/XX
Token Usage         XX avg        XX avg
Error Rate          XX%           XX%
Join Correctness    XX%           XX%
```

Platform-specific breakdowns available in the full report.

## Acceptance Criteria
- [ ] Ground-truth query set: minimum 20 queries, hand-verified SQL + results
- [ ] Benchmark harness runs against Tier 2 warehouse
- [ ] At least 3 platforms tested (CC, Cursor, Codex)
- [ ] Comparison table generated automatically from results
- [ ] Results published on README, convergentmethods.com/boyce/, PyPI description
- [ ] Benchmark is reproducible: anyone can clone, run setup, run benchmark

## Sequencing Note
This is Block 2 work, not Block 1. It depends on the Tier 2 test warehouse
existing (Stage 6) and is the first major post-publish engineering deliverable.
Do not attempt to squeeze this into the publish timeline.
