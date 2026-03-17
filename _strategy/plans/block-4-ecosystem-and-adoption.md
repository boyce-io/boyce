# Plan: Block 4 — Ecosystem & Adoption
**Status:** Pending
**Created:** 2026-02-28
**Timeline:** Days 36-45 after name is locked
**Depends on:** Block 3 (Data Quality) — quality profiling operational, protocol v0.2 published

## Goal
The product transitions from "impressive open-source tool" to "infrastructure people depend on."
Entity intelligence, pipeline parser coverage, and published content create compounding adoption
signals. External producers of SemanticSnapshot begin to appear — even if they don't realize
that's what they're doing (via `scan` CLI).

## Prerequisites
- Block 3 complete: protocol v0.2 with QualityProfile, drift detection operational
- Null Trap essay generating organic traffic
- At least one real-world deployment providing feedback

---

## Implementation Steps

### Step 1: Entity Priority Score
- Add `priority_score: Optional[float]` to `Entity` in `types.py`
- Compute at ingest time from:
  - FK centrality (number of incoming/outgoing FK relationships)
  - Field count (proxy for table importance)
  - Join fanout (number of entities reachable within 2 hops)
- Used by future smart ingestion: high-priority entities get deeper treatment
- File: `types.py`, `graph.py` (centrality computation)
- Cursor model: **Sonnet 4.6 Thinking** (graph algorithm, needs reasoning)

### Step 2: Airflow DAG Parser
- Parse Airflow DAG Python files using AST
- Extract: SQL statements embedded in operators (PostgresOperator, BigQueryOperator, etc.)
- Parse extracted SQL for table references → entities, column references → fields
- File: `parsers/airflow.py`
- Cursor model: **Sonnet 4.6 Thinking** (AST + SQL extraction)

### Step 3: Technical Content Series
- Essay 2: "Why Deterministic SQL Matters for Agent Safety" — the case for
  separating LLM intent from SQL generation
- Essay 3: "The SemanticSnapshot Standard" — introducing the protocol spec,
  why it matters, how to adopt it
- Essay 4: "Building a Parser for Boyce" — community contribution guide,
  doubles as a tutorial
- Each essay includes working code examples
- Executor: Will writes; Claude Code reviews technical accuracy

### Step 4: Adoption Outreach
- Identify 5-10 NL-to-SQL tools that could adopt StructuredFilter as their IR
- Open issues / PRs on their repos showing how to integrate
- Write a "Why adopt SemanticSnapshot" one-pager for tool authors
- Engage with dbt community, data engineering communities, MCP community
- **Prerequisite reality check:** This only works after the quality profiling and content
  establish credibility. Don't cold-outreach until you have external users validating the spec.
- Executor: Will directly (relationship building)

---

## Acceptance Criteria
- [ ] Entity `priority_score` computed at ingest time
- [ ] Airflow DAG parser implemented and tested
- [ ] At least 2 technical essays published beyond the Null Trap
- [ ] At least one external tool produces or consumes SemanticSnapshot format
- [ ] All tests pass (existing + new tests)

## The 18-Month View
After Block 4, the product has:
- A published protocol spec (v0.2) with quality, policy, and provenance dimensions
- 10+ parsers covering most common database toolchains
- An auto-discovery CLI for frictionless onboarding
- Data quality as a first-class protocol feature
- Drift detection for ongoing monitoring
- A deterministic kernel that survives the Bitter Lesson
- A safety layer that no model can replace
- Published content driving organic adoption

The NL→SQL planner is still useful but is explicitly positioned as scaffolding —
the demo that gets people in the door. The protocol, kernel, safety layer, and
governance features are the product. These survive regardless of how capable
models become at SQL generation.

## Note on Protocol Bootstrapping
Every run of `boyce scan ./` produces a SemanticSnapshot. Every user who runs
the scan CLI is an "adopter" of the format — even if they never think of themselves
that way. The scan CLI is the sneaky bootstrapping mechanism for protocol adoption.
External producers emerge organically from utility, not from outreach.
