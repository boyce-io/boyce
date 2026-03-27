# Plan: Agent Adoption Docs Sync
**Status:** Ready for execution
**Created:** 2026-03-19
**Model:** Sonnet 4.6 · high
**Depends on:** Response response guidance layer (COMPLETE), behavioral design framework in `../../MASTER.md` (COMPLETE)

## Goal

Rewrite all public-facing agent docs to reflect the current Boyce tool
surface and behavioral design framework. When an agent reads llms.txt or
llms-full.txt, it should receive the same behavioral hooks we deploy in
tool descriptions and responses: loss aversion, reciprocity, authority
framing, and clear workflow directives.

**Hard requirement:** Every piece of public copy must follow the Behavioral
Design Framework documented in the root `MASTER.md` under Cross-Cutting
Rules. Read that section before writing anything.

---

## Context

Over 2026-03-17 to 2026-03-19, the Boyce MCP tool surface was rewritten
across three marketing surfaces based on a behavioral psychology framework.
The code-level work is done (346 tests passing). But the public docs still
describe the pre-rewrite Boyce:

- `query_database` is listed as "read-only SELECT execution" — no mention
  of NULL risk scan or EXPLAIN pre-flight
- No mention of the response response guidance layer (`next_step`, `present_to_user`,
  `data_reality`)
- Tool descriptions in docs don't match the two-register guidance structure now
  in server.py
- No behavioral hooks in the docs themselves (loss aversion, authority framing)

---

## Files to Modify

All files are in `sites/convergentmethods/boyce/`:

### 1. `llms.txt` — Agent-readable overview (~50 lines)

This is the FIRST surface an agent reads. It must:

- Use loss-aversion framing in the opening: what agents are missing without
  Boyce (not what Boyce offers)
- Update the MCP Tools section to match current tool descriptions in server.py
- Specifically update `query_database`: "Execute read-only SELECT with NULL
  risk scan and EXPLAIN pre-flight on every query"
- Add a "Response Format" line: "All tool responses include a `next_step`
  directive and contextual safety metadata (`present_to_user`, `data_reality`)
  when material issues are detected."
- Keep it under 60 lines. This is a summary, not the full reference.

**Source of truth for current tool descriptions:**
`boyce/src/boyce/server.py` — read the docstring of each `@mcp.tool()` function.

### 2. `llms-full.txt` — Complete agent reference (~300 lines)

This is the deep reference. It must:

- Include the full response schema for every tool, including the guidance
  fields (`next_step`, `present_to_user`, `data_reality`)
- Document the `next_step` patterns per tool (see table in
  `products/Boyce/CLAUDE.md` under "Response Guidance Layer")
- Document `data_reality` behavior: when it fires, what it contains, why
- Document `present_to_user` behavior: when it fires, loss-aversion framing
- Update all tool parameter docs to match current server.py signatures
  (e.g., `query_database` now takes `snapshot_name`)
- Use authority framing: "Validated against 3 safety dimensions: NULL traps,
  EXPLAIN pre-flight, dialect compatibility"

**Source of truth:** `boyce/src/boyce/server.py` — every tool's docstring,
`_build_response_guidance()`, and the per-tool next_step map.

### 3. `index.html` — Product page

Smaller updates:
- MCP Tools table: `query_database` row already updated. Verify all 7 rows
  match current descriptions.
- Consider adding a brief "Response Intelligence" section or bullet under
  "What Boyce Does" that mentions the response guidance layer in human terms:
  "Every query response includes contextual safety findings and explicit
  next-step guidance — your agent always knows what Boyce found and what
  to do next."

---

## Verbiage Rules (from MASTER.md)

These are binding. Follow them exactly:

1. **Loss aversion first.** Lead with what's missing/wrong, not what Boyce
   offers. "This query excluded 30% of rows" before "ask_boyce handles
   NULL values."
2. **Directive language, never hedging.** "Pass this SQL to query_database"
   not "consider using query_database."
3. **Authority stacking with specific numbers.** "3 safety dimensions" >
   "multiple checks" > "validated."
4. **No noise.** Don't describe `present_to_user` as "always present" — it
   only fires when material. Say that explicitly.
5. **No AI slop.** No "revolutionize your workflow." Clean, technical, credible.

---

## How to Execute

1. Read `../../MASTER.md` Cross-Cutting Rules → "Behavioral Design Framework"
2. Read `boyce/src/boyce/server.py`:
   - Each `@mcp.tool()` function's docstring (current descriptions)
   - `_build_response_guidance()` (response schema + next_step map)
   - `FastMCP` constructor `instructions=` parameter (preamble text)
3. Read `products/Boyce/CLAUDE.md` → "Response Guidance Layer" section
4. Rewrite `llms.txt` (short version first)
5. Rewrite `llms-full.txt` (complete reference)
6. Update `index.html` MCP Tools table + any needed additions
7. Verify: read the rewritten files and confirm every behavioral hook from
   MASTER.md is present

---

## Verification

- [ ] llms.txt uses loss-aversion framing in opening
- [ ] llms.txt mentions `next_step`, `present_to_user`, `data_reality`
- [ ] llms.txt `query_database` description includes safety pre-flight
- [ ] llms-full.txt documents full response schema with guidance fields
- [ ] llms-full.txt includes per-tool next_step patterns
- [ ] llms-full.txt tool parameters match server.py signatures
- [ ] index.html MCP Tools table matches current descriptions
- [ ] No AI slop in any file
- [ ] All files under their target line counts

---

## Do NOT

- Modify server.py or any Python code. This is a docs-only task.
- Create new files beyond the three listed above.
- Change the site's CSS, layout, or structure.
- Add emojis to the docs.
- Guess at tool behavior — read server.py for ground truth.
