# Boyce — Opus Brief

> Strategic briefing for Opus (claude.ai) planning sessions.
> CC updates this at the end of every execution session.
> Will uploads this when starting a new Opus chat.
> **Last updated:** 2026-03-27

## Project Summary

Boyce is a privacy-first SQL compiler and open semantic protocol (SemanticSnapshot) exposed as an MCP server. MIT-licensed engine, monetizable experience layer (IDE extensions, hosted service). Named for Raymond F. Boyce, co-inventor of SQL. The thesis: AI agents are the primary consumers of developer tools, and the interface between agents and databases is a behavioral design problem, not just an engineering one. Open protocols win adoption; monetize the experience layer.

## Current State
- **Phase:** Phase 3 — Platform Expansion (pre-distribution)
- **Status:** v0.1.0 published to PyPI (2026-03-24). Terminology refresh complete (2026-03-24). Roadmap resequenced (2026-03-27). 438 tests, 24 CLI smoke checks.
- **Active work:** Platform Expansion (Codex support), then Preliminary Benchmark, then Agentic Ingestion Light — all before distribution.

## Recent Decisions
- 2026-03-27: Roadmap resequenced — Phases 3-5 (Platform Expansion, Preliminary Benchmark, Agentic Ingestion Light) execute before distribution. Phase 10 split into light (pre-distribution) and full (pre-v1.0.0). Rationale: stronger launch copy with 7 platforms, benchmark numbers, and agentic ingestion in feature list.
- 2026-03-24: Terminology refresh — Eyes/Brain/Nervous System → SQL Compiler/Database Inspector/Query Verification. "Advertising layer" → "Response Guidance." Function + test renames. LLM-optimized naming for dual human/agent audience.
- 2026-03-24: Published v0.1.0 to PyPI. GitHub release tagged. UV_PUBLISH_TOKEN in .zshrc.
- 2026-03-24: Cursor cross-platform test passed (6/6). Init wizard fix: platform-specific restart instructions.

## Open Questions
- Ingest architecture: deterministic parsing alone may not handle real-world schema diversity. LLM-assisted semantic interpretation may be needed. Evaluate after Tier 2 testing.
- Non-terminal user TAM: does the market of non-CLI users change delivery surface priority?
- VS Code extension: free-only or free + pro tier from day one?

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
