# Plan: Block 1b — VS Code Extension
**Status:** Scaffold complete — Steps 1-4 built, compiles clean
**Created:** 2026-03-06
**Updated:** 2026-03-11
**Timeline:** Immediately after Block 1 core (PyPI publish, essay, directories)
**Depends on:** HTTP API (`boyce serve --http`) — already built and tested

## Goal
Ship a VS Code extension to the marketplace that gives 30M+ VS Code users a GUI interface
to Boyce. This is the first delivery surface beyond MCP hosts and CLI, and the first
monetization vehicle. The extension is a thin TypeScript wrapper over the HTTP API — Boyce
handles all LLM and SQL logic internally.

## Strategic Context

### Why VS Code First
- 30M+ monthly active users — largest IDE install base by far
- Marketplace distribution is built in (no sideloading)
- VS Code users expect free + paid tiers — natural monetization surface
- The HTTP API surface (`boyce serve --http`) is already operational
- Legacy v0 reference implementation (preserved in git history) was used as scaffold reference

### Monetization Strategy
The core engine is MIT forever. IDE extensions are the experience layer where monetization lives.

| Layer | License | Monetization |
|-------|---------|-------------|
| **Protocol** (SemanticSnapshot spec) | MIT forever | None — adoption IS the return |
| **Core library** (kernel, parsers, safety, MCP server) | MIT forever | None — this is what gets adopted |
| **CLI tools** (boyce-scan, boyce-init, boyce ask) | MIT forever | None — onboarding funnel |
| **IDE extensions** (VS Code, JetBrains) | Free tier + Pro | Pro features: visual schema explorer, query history, team snapshot sharing |
| **Hosted service** (future) | SaaS | Managed Boyce — zero self-hosting, SSO, audit dashboard |

Pattern: Docker (engine free, Desktop paid), Terraform (CLI free, Cloud paid), Grafana (server free, Cloud paid).

---

## Architecture

The extension does NOT embed LLM logic. It calls the Boyce HTTP API.

```
VS Code Extension (TypeScript)
    │
    │  HTTP calls to localhost:8741
    │
    ▼
boyce serve --http
    │
    ├── /chat    → intent routing (schema/sql/profile/path)
    ├── /ask     → NL → SQL pipeline
    ├── /schema  → get_schema
    ├── /build-sql → deterministic SQL from StructuredFilter
    ├── /query   → execute read-only SELECT
    ├── /profile → column profiling
    └── /ingest  → ingest sources
```

The user configures their LLM API key once via `boyce-init`. The extension never touches it.

### Two LLM Roles (critical distinction)
1. **The Host LLM** — in MCP hosts (Claude Code, Cursor), the host LLM routes to Boyce tools. VS Code has no native LLM, so this role doesn't exist.
2. **Boyce's Internal LLM** — configured via `BOYCE_PROVIDER` + `BOYCE_MODEL`. The `/chat` and `/ask` endpoints use this internally. The extension just sends text and gets responses.

The extension is a thin GUI. All intelligence lives in Boyce.

---

## Legacy Reference

The v0 extension (~700 LOC, now in git history only) provided these reusable patterns:

| Component | File | Reusable? |
|-----------|------|-----------|
| Main entry point | `src/extension.ts` | Structure yes, API calls no (old protocol) |
| Schema tree browser | `src/providers/schemaTreeProvider.ts` | UI pattern yes |
| SQL editor provider | `src/providers/sqlEditorProvider.ts` | UI pattern yes |
| Completions | `src/providers/completionProvider.ts` | UI pattern yes |
| Results panel | `src/panels/resultsPanel.ts` | UI pattern yes |
| Query console | `src/panels/queryConsolePanel.ts` | UI pattern yes |
| Credential storage | `src/settings/credentialManager.ts` | Reusable |
| MCP client | `src/mcp/client.ts` | Replace with HTTP client |
| Query history | `src/utils/queryHistory.ts` | Reusable |

The UI patterns and panel layouts are reusable. The API layer needs to be rewritten to call
the HTTP API instead of the old MCP/LSP protocol.

---

## Implementation Steps

### Step 1: Scaffold Extension [DONE — 2026-03-11]
- [x] Manual scaffold: `package.json`, `tsconfig.json`, `.vscodeignore`, `.gitignore`
- [x] Extension activates on: workspace contains `.boyce/config.json`, or user runs `Boyce: Connect`
- [x] Publisher: `convergent-methods`
- [x] Activity bar with database icon, 5 commands, keybindings (`Cmd+Enter` runs SQL)
- [x] Configuration: `boyce.serverUrl`, `boyce.autoStart`, `boyce.defaultDialect`, `boyce.snapshotName`
- [x] Compiles clean (`tsc`, zero errors)
- Built in: **Opus 4.6** (scaffold + HTTP client + panels in one pass, had tokens to burn)

### Step 2: HTTP Client Layer [DONE — 2026-03-11]
- [x] `BoyceClient` class in `src/client.ts` — typed methods for all 8 HTTP endpoints (7 MCP tools + `/health`)
- [x] `BoyceProcess` class in `src/process.ts` — auto-starts `boyce serve --http` as child process
- [x] Health check on activation (`GET /health`), polls until healthy (10s timeout)
- [x] Bearer token auth from `.boyce/config.json` or `BOYCE_HTTP_TOKEN` env var
- [x] Graceful shutdown: SIGTERM → 3s grace → SIGKILL on extension deactivate

### Step 3: Chat Panel (Primary UI) [SCAFFOLDED — 2026-03-11]
- [x] Webview panel: text input → `/chat` endpoint → rendered response
- [x] "Run SQL" button on responses containing SQL → calls `/query` → shows results
- [x] Message history maintained in-memory
- [x] Enter to send, Shift+Enter for newline, loading indicator
- [ ] SQL syntax highlighting in responses (currently plain text in code blocks)
- [ ] Query history persistence (local storage or file-based)
- [ ] Response rendering polish (tables, profiling stats)

### Step 4: Schema Tree View [SCAFFOLDED — 2026-03-11]
- [x] TreeView provider in sidebar: entities → fields → data types
- [x] Type-aware icons (number, string, boolean, date, JSON, etc.)
- [x] FK annotations in tooltips
- [x] Graceful handling when server not running ("Boyce server not running" message)
- [ ] Click entity → context menu actions (preview data, generate SELECT)
- [ ] Join visualization (edges between entities)

### Step 5: SQL Editor Integration
- CodeLens on `.sql` files: "Run with Boyce" → `/query` endpoint
- Diagnostics provider: lint SQL via Boyce safety layer (future)
- Completions from schema (table names, column names) — future pro feature
- Cursor model: **Sonnet 4.6**

### Step 6: Setup Wizard
- On first activation (no `.boyce/config.json` found):
  - Prompt to install `boyce` via pip/uv if not found
  - Run `boyce-init` equivalent: configure LLM provider + API key
  - Scan workspace for parseable sources
  - Store config in `.boyce/config.json`
- Cursor model: **Sonnet 4.6**

### Step 7: Marketplace Publish
- Package as `.vsix`
- Publish to VS Code Marketplace (free tier)
- README with screenshots, quick-start, "pip install boyce" prerequisite
- Executor: Will directly (marketplace account)

---

## Free vs. Pro Feature Split (Future)

| Feature | Free | Pro |
|---------|------|-----|
| Chat panel (NL → SQL) | Yes | Yes |
| Schema tree view | Yes | Yes |
| Run queries | Yes | Yes |
| Query history | Last 50 | Unlimited |
| Visual schema explorer (graph view) | No | Yes |
| Team snapshot sharing | No | Yes |
| Multi-database profiles | 1 | Unlimited |
| SQL completions from schema | No | Yes |

Pro pricing TBD. Start free-only for adoption; add pro tier after organic usage establishes demand.

---

## Acceptance Criteria
- [ ] Extension installs from VS Code Marketplace
- [ ] Chat panel sends NL queries and renders SQL responses
- [ ] Schema tree shows entities and fields from ingested snapshots
- [ ] "Run SQL" executes queries and shows results in a table
- [ ] Auto-starts `boyce serve --http` when not running
- [ ] Setup wizard guides first-time users through `boyce-init` equivalent
- [ ] Works without any LLM for schema browsing / manual SQL execution
- [ ] Works with BOYCE_PROVIDER configured for NL → SQL via `/chat`

## Risks / Open Questions
- **Child process management**: Auto-starting `boyce serve --http` as a subprocess needs
  graceful shutdown on extension deactivate. May need a process manager or pidfile.
- **Auth flow**: `.boyce/config.json` Bearer token works for local use. Team/remote scenarios
  need a different auth model (future).
- **Marketplace review**: VS Code marketplace has review times. Plan for 1-3 day delay on
  first publish.
- **Pro tier timing**: Ship free-only first. Don't build payment infrastructure until there's
  organic demand signal (download count, GitHub stars, user feedback).
