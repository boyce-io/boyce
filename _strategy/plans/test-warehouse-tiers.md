# Plan: Test Warehouse Tier System
**Status:** Planned — Stage 6 post-publish
**Created:** 2026-03-17
**Depends on:** PyPI publish complete

## Goal
A structured test warehouse hierarchy that validates Boyce against increasingly
realistic database environments. Tier 2 feeds the benchmark program directly.

---

## Tier Definitions

### Tier 1 — CI / Smoke (exists)
- **What:** Pagila (15 tables), committed fixtures, verify_eyes.py
- **Where:** `tests/validation/docker-compose.yml` (Pagila), `test_warehouses/` fixtures
- **Use:** Fast CI, smoke tests, regression. 316 tests in ~10s.
- **Status:** OPERATIONAL

### Tier 2 — Messy / Medium (to build)
- **What:** ~50-200 tables with realistic data quality problems:
  - Columns with 10-50% NULL rates (NULL trap triggers)
  - Naming collisions across schemas (e.g., `orders.status` vs `shipments.status`)
  - Inconsistent data types (varchar dates, numeric strings)
  - Stale timestamps (last_updated months old)
  - Mixed naming conventions (camelCase + snake_case + spaces)
  - Orphaned foreign keys (FK points to nonexistent rows)
  - Wide tables (50+ columns, most unused)
- **Where:** `test_warehouses/tier2/` — setup script + Docker Compose, data NOT committed
- **Use:** Benchmark program, parser stress test, NULL trap validation
- **Priority:** HIGH — this is the benchmark foundation

### Tier 3 — Production Scale (future)
- **What:** Hundreds of tables, deep join graphs, production-scale complexity
- **Candidates:** TPC-DS, Adventureworks full, or synthetic generator
- **Where:** External, pulled on demand via setup script
- **Use:** Performance testing, join resolution at scale
- **Priority:** LOW — after benchmark program proves the methodology

---

## Open Questions
- **Tier 2 source:** Synthetic (generated to trigger known failure modes) vs. real open
  dataset (Adventureworks, Chinook extended)? Synthetic gives control over failure
  modes but feels artificial. Real dataset is credible for benchmarks but may not
  hit all edge cases. Recommendation: synthetic core with realistic table/column names.
- **Tier 2 storage:** Docker Compose with seed SQL (like Pagila) is the proven pattern.
  Setup script runs `docker compose up`, seeds data, ready to test.

## Acceptance Criteria
- [ ] Tier 2 Docker Compose + seed SQL operational
- [ ] `test_warehouses/tier2/setup.sh` — one command to stand up the warehouse
- [ ] At least 50 tables with documented data quality problems
- [ ] NULL trap fires on at least 5 different columns
- [ ] Naming collision triggers at least 2 disambiguation scenarios
- [ ] Benchmark harness can target Tier 2 via config
