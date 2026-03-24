# RELEASING.md — Boyce Publish Runbook

**Purpose:** Step-by-step checklist for publishing a Boyce release.
Run top-to-bottom. Do not skip steps. Each step has a verification.

---

## Pre-Publish Gate (must all be true)

- [x] Cursor cross-platform test PASSED ✓ 2026-03-23 (6/6 clean — ingest, schema, Mode C→A funnel, NULL trap bypass, joins, Redshift lint)
- [x] All tests pass: `python -m pytest boyce/tests/ -v` (438 pass, 6 skip) ✓ 2026-03-23
- [x] CLI smoke checks pass: `python -m pytest boyce/tests/test_cli_smoke.py -v` ✓ 2026-03-23
- [x] Clean venv install works: `uv venv /tmp/boyce-release && uv pip install -e boyce/ && /tmp/boyce-release/bin/boyce --help` ✓ 2026-03-23
- [x] Version number decided: 0.1.0 ✓ 2026-03-23 (first public release, API may evolve; 1.0.0 reserved for SemanticSnapshot spec stabilization)
- [x] `git status` is clean on main branch ✓ 2026-03-23
- [x] No open PRs that should be merged first ✓ 2026-03-23

---

## Step 1: Set Version

Edit `boyce/src/boyce/__init__.py` (or wherever `__version__` lives):
```bash
# Verify current version
grep -r "__version__" boyce/src/boyce/
# Update to release version
vim boyce/src/boyce/__init__.py
```

Edit `boyce/pyproject.toml`:
```bash
vim boyce/pyproject.toml
# Update: version = "X.Y.Z"
```

**Verify:** `grep version boyce/pyproject.toml` shows the correct version.

---

## Step 2: Final Test Run

```bash
cd /Users/willwright/ConvergentMethods/products/Boyce
python -m pytest boyce/tests/ -v
python -m pytest boyce/tests/test_cli_smoke.py -v
```

**Verify:** All pass. Do not proceed if any fail.

---

## Step 3: Build Package

```bash
cd boyce/
uv build
```

**Verify:** `ls dist/` shows `boyce-X.Y.Z.tar.gz` and `boyce-X.Y.Z-py3-none-any.whl`

---

## Step 4: Test Package Install (clean env)

```bash
uv venv /tmp/boyce-publish-test
uv pip install --python /tmp/boyce-publish-test/bin/python dist/boyce-X.Y.Z-py3-none-any.whl
/tmp/boyce-publish-test/bin/boyce --help
/tmp/boyce-publish-test/bin/python -c "from boyce import process_request, SemanticSnapshot; print('OK')"
```

**Verify:** CLI starts, public imports work.

---

## Step 5: Publish to PyPI

```bash
cd boyce/
uv publish
# Will prompt for PyPI credentials (or use token via TWINE_PASSWORD)
```

**Verify:**
```bash
pip install boyce==X.Y.Z  # from a fresh terminal
boyce --help
```
Also check: https://pypi.org/project/boyce/ — page renders, description looks correct.

---

## Step 6: Git Tag + Push

```bash
cd /Users/willwright/ConvergentMethods/products/Boyce
git add -A
git commit -m "release: Boyce vX.Y.Z — first public release

Deterministic SQL compiler and semantic protocol for agentic database workflows.
8 MCP tools, 10 source parsers, NULL trap detection, EXPLAIN pre-flight.
MIT licensed."

git tag -a vX.Y.Z -m "Boyce vX.Y.Z — first public release"
git push origin main --tags
```

**Verify:** `git log --oneline -1` shows the release commit. Tag visible on GitHub.

---

## Step 7: GitHub Release

Go to: https://github.com/boyce-io/boyce/releases/new

- **Tag:** vX.Y.Z (select existing tag)
- **Title:** Boyce vX.Y.Z — First Public Release
- **Body:** (paste release notes — draft separately or use template below)
- **Attach:** the `.tar.gz` and `.whl` from `dist/` (optional — PyPI is the primary)
- **Mark as latest release**

**Verify:** Release page is live, links work.

---

## Step 8: Phase C Stage 1 — Distribution (same day)

### MCP Directory Submissions
Content is pre-drafted in `_strategy/mcp-directory-submissions.md`. Submit to all four:

- [ ] **Smithery** — https://smithery.ai/submit
- [ ] **PulseMCP** — https://pulsemcp.com/submit
- [ ] **mcp.so** — https://mcp.so (Add Server)
- [ ] **Glama** — https://glama.ai/mcp/servers

### JetBrains ACP Registry
- [ ] Submit using canonical content adapted to ACP format

### Note submission dates below:
- Smithery: __________
- PulseMCP: __________
- mcp.so: __________
- Glama: __________
- JetBrains ACP: __________

---

## Step 9: Verify All Publish Surfaces

Cross-reference with `ASSETS.md` publish surfaces table:

| Surface | URL | Updated? |
|---------|-----|----------|
| PyPI | https://pypi.org/project/boyce/ | [ ] |
| GitHub README | https://github.com/boyce-io/boyce | [ ] |
| Product page | https://convergentmethods.com/boyce/ | [ ] |
| Agent docs (index) | https://convergentmethods.com/boyce/llms.txt | [ ] |
| Agent docs (full) | https://convergentmethods.com/boyce/llms-full.txt | [ ] |
| CM root page | https://convergentmethods.com | [ ] |
| CM agent index | https://convergentmethods.com/llms.txt | [ ] |

**Version must be consistent across all surfaces.**

If any surface references a stale version or has outdated content, fix it now.

---

## Step 10: Update Plan Docs

```bash
# In _strategy/MASTER.md:
# - Mark Phase B as COMPLETE
# - Update "Current phase" to Phase C
# - Check off Phase C Stage 1 items
# - Update "Last updated" date

# In root ConvergentMethods/MASTER.md:
# - Update Boyce status line
```

**Verify:** `git diff` shows only the expected status changes. Commit and push.

---

## Post-Publish (next 48 hours)

These are Phase C Stages 2-3. Not blocking, but do them while momentum is fresh:

- [ ] **Agent SEO baseline** — run test queries across Claude, GPT, Gemini (Stage 2)
- [ ] **Content review pass** — all 8 surfaces, manually (Stage 3)
- [ ] **Celebrate** — you shipped a product

---

## Release Notes Template

```markdown
# Boyce vX.Y.Z — First Public Release

Deterministic SQL compiler and semantic protocol for agentic database workflows.

## Install

```
pip install boyce
```

## What's In This Release

- **8 MCP tools:** `ingest_source`, `ingest_definition`, `get_schema`, `ask_boyce`, `validate_sql`, `query_database`, `profile_data`, `check_health`
- **10 source parsers:** dbt manifest, dbt project, LookML, raw DDL, SQLite, Django, SQLAlchemy, Prisma, CSV, Parquet
- **Deterministic SQL kernel:** Same inputs → same SQL, byte-for-byte, every time. Zero LLM in the compiler.
- **NULL Trap detection:** Profiles equality-filtered columns for NULL hazards before the query runs.
- **EXPLAIN pre-flight:** Every generated query is validated against the database before returning.
- **Redshift safety linting:** Catches Redshift 1.0 incompatibilities at compile time.
- **Dijkstra join resolution:** Optimal join paths via weighted semantic graph.
- **Multi-dialect SQL:** Redshift, Postgres, DuckDB, BigQuery.
- **Zero-config for MCP hosts:** Works with Claude Code, Cursor, VS Code, DataGrip, and any MCP-compatible editor — no API key needed.
- **Setup wizard:** `boyce init` auto-detects your editor, database, and data sources.
- **Auto-discovery:** `boyce scan ./` finds and ingests your project's schema sources.

## Quick Start

```bash
pip install boyce
boyce init          # configure your editor + database
boyce scan ./       # auto-detect and ingest schema sources
boyce ask "total revenue by customer segment"
```

## Links

- **Docs:** https://convergentmethods.com/boyce/
- **GitHub:** https://github.com/boyce-io/boyce
- **The Null Trap:** https://convergentmethods.com/boyce/null-trap/

## License

MIT. The engine is free forever. No paywalls. No open-core bait-and-switch.

Named for [Raymond F. Boyce](https://en.wikipedia.org/wiki/Raymond_F._Boyce), co-inventor of SQL (1974).
```
