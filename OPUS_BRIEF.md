# Boyce — Opus Brief

> Strategic briefing for Opus (claude.ai) planning sessions.
> CC updates this at the end of every execution session.
> Will uploads this when starting a new Opus chat.
> **Last updated:** 2026-03-28

## Project Summary

Boyce is a privacy-first SQL compiler and open semantic protocol (SemanticSnapshot) exposed as an MCP server. MIT-licensed engine, monetizable experience layer (IDE extensions, hosted service). Named for Raymond F. Boyce, co-inventor of SQL. The thesis: AI agents are the primary consumers of developer tools, and the interface between agents and databases is a behavioral design problem, not just an engineering one. Open protocols win adoption; monetize the experience layer.

## Current State
- **Phase:** Phase 5 — Agentic Ingestion Sprint (in progress, sprint planning complete)
- **Status:** v0.1.0 on PyPI. 465 tests. Phase 4b benchmark complete. StructuredFilter v0.2.
- **Active work:** Agentic Ingestion Sprint — the ingestion layer is the product. Distribution (Phase 6) paused until sprint passes Directive #7 gate.

## Recent Decisions
- 2026-03-28: **Strategic reframe — Agentic Ingestion Sprint.** Phase 4 benchmark showed Boyce ties vanilla LLM on clean schemas. 10 parsers extract the same info as information_schema. The ingestion layer IS the product gap. Phase 5 replaced with full sprint: Haiku regression root cause → schema extensions → live database profiling → parser deepening → host-LLM classification → benchmark validation. Distribution paused.
- 2026-03-28: **Directive #7 precision update.** Recommended tier (GPT-4o class): match or beat vanilla on every category, advantage on 3+. Budget tier (Haiku): systematic regression is P1 bug, not ship blocker. Dirty fixture required in benchmark.
- 2026-03-28: **Priority order.** Live database profiling is critical path. Parser deepening is parallel breadth work. Profiling wins if conflicts arise.
- 2026-03-27 (Phase 4b): 9 bugs fixed. Benchmark v2: Mode A 3.5/4, row count 100%, EXPLAIN 100%. StructuredFilter v0.2 adds order_by, limit, expressions.

## Open Questions
- **Sprint 0 Branch A vs B:** Is Haiku regression caused by prompt/validation issues (fixable, sprint continues) or StructuredFilter cognitive tax (needs simplification pass before enrichment)? Diagnostic test defined in sprint plan.
- Non-terminal user TAM: does the market of non-CLI users change delivery surface priority?
- VS Code extension: free-only or free + pro tier from day one?
- Ingest architecture question ANSWERED (2026-03-28): deterministic parsing + live profiling + host-LLM semantic interpretation. The model-compensation layer stays thin but exists.

## Blocked Items
- will@boyce.io email: domain transfer in progress (Dynadot to Namecheap).
- boyce.io site: unblocked by publish, but site build not yet started.

## Cross-Project Dependencies
- Boyce publish DONE — no longer gates anything
- Behavioral Design Framework (from CM root MASTER.md) governs all agent-facing copy across Boyce and Arezzo
- Null Trap essay live at convergentmethods.com/boyce/null-trap/ — distribution is the bottleneck
- Arezzo Phase 4 will apply Boyce's response guidance framework

## HITL Queue
- **Distribution timing:** Will controls when and where to post (HN, Reddit, social, Slack channels)
- **USPTO trademark:** File "Boyce" under Class 009 (~$250 TEAS Plus). Will-executed, post-publish.
