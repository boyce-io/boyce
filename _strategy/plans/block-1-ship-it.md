# Plan: Block 1 — Ship It
**Status:** Active — Phase A complete, Phase B testing complete (24 bugs fixed), platform tests + publish remaining
**Created:** 2026-02-28
**Updated:** 2026-03-16
**Depends on:** Block 0 (naming) — COMPLETE

## Goal
Published on PyPI, deployed on a real warehouse, discoverable by agents and developers.
`pip install boyce` → working semantic protocol + safety layer in under 5 minutes.

**Hard requirement:** Will personally tests all surfaces before anything is published.

---

## Phase A — Engineering [COMPLETE as of 2026-03-07]

All engineering work done. 316 tests green. No open items.

---

## Phase B — Testing Sprint [ACTIVE]

**Testing complete. Platform integration + publish gates remaining.**

### Completed
- [x] Integration guides written (Claude Desktop, Cursor, Claude Code, Cline, Continue.dev)
- [x] Docker Compose for Pagila operational
- [x] Validation query battery + testing runbook
- [x] Prior-name scrub (CEO directive 2026-03-11)
- [x] Semantic review pass (zero findings)
- [x] MCP integration testing: 7 sessions, 24 bugs found and fixed
- [x] Opus refactor: `_resolve_field_ref()` extracted, -94 lines
- [x] Live DB round-trip (Pagila Docker): ingest → query → profile
- [x] Clean venv install: `pip install -e boyce/` → all imports + CLI work
- [x] NULL trap demo: both dangers fire, all assertions pass
- [x] Init wizard overhaul: 3-step interactive, discovery system, 27 tests
- [x] CLI convention: `boyce init` / `boyce scan` subcommands
- [x] Support readiness: issue templates, FAQ, troubleshooting
- [x] Email references updated to will@convergentmethods.com

Full session-by-session testing log: `_strategy/history/testing-sprint-log.md`

### Remaining Gates
- [ ] Cursor cross-platform test (must-have for publish gate)
- [ ] VS Code cross-platform (stretch)
- [ ] Version decision + PyPI publish

**Gate:** Will has personally tested all surfaces. Real queries produce correct results.

---

## Phase C — Amplification [AFTER PUBLISH]

- [ ] MCP directory submissions (Smithery, PulseMCP, mcp.so, Glama)
- [ ] Integration guides published as public docs
- [ ] Local LLM setup guide (Ollama/vLLM)
- [ ] Content: Story 1 (adoption/IC) — clean README, 30-second demo
- [ ] Content: Story 2 (trust/C-suite) — Null Trap technical essay
- [ ] With/without Boyce comparison table for README + boyce.io
- [ ] VS Code extension (Block 1b) — deprioritized, scaffold preserved

---

## Acceptance Criteria
- [x] Phase A: all engineering complete, 316 tests green
- [x] Phase B: query battery — 24 bugs resolved, all clean
- [ ] Phase B: Will has tested Claude Code + Cursor (must-have), VS Code (stretch)
- [ ] Phase B: version decision
- [ ] Phase B: `pip install boyce` from PyPI works in clean env
- [ ] Phase C: Null Trap essay published to 3+ channels
- [ ] Phase C: listed on 2+ MCP directories

## Risks
- Planner may produce poor SQL on complex Pagila joins — surfaces during Phase B; fix or document
- Version decision may push to "iterate" — Friday flex day absorbs this
- Null Trap essay reception is unpredictable — have follow-up content ideas ready
