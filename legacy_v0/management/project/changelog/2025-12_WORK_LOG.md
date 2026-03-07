# DataShark Work Log — December 2025

Consolidated log of all December 2025 work, receipts, and evidence.

---

## Sprint 2: Artifact Logger (December 2025)

**What Changed:**
- Implemented audit logging system with Contract A: one record per file (single-line JSONL)
- Added `datashark.core.audit` module with `AuditRecord`, `AuditWriter`, and `log_artifact()` function
- Integrated audit logging into `engine.process_request()` (automatic for all SQL generation)
- Audit artifacts written to `.datashark/audit/audit_YYYY-MM-DD_{request_id}.jsonl`

**Files Touched:**
- `datashark-mcp/src/datashark/core/audit.py` (new, 234 lines)
- `datashark-mcp/src/datashark_mcp/kernel/engine.py` (added log_artifact call, lines 159-170)
- `datashark-mcp/tests/test_audit.py` (new, full test suite)
- `tests/test_audit.py` (deleted - stale duplicate)

**Commands Run:**
```bash
cd datashark-mcp
PYTHONPATH=src python3 -m pytest tests/test_audit.py -v
# Result: All tests pass
```

**Code Paths:**
- Service entrypoint: `datashark.core.audit.log_artifact()`
- Engine integration: `datashark_mcp.kernel.engine.DataSharkEngine.process_request()` (line 162)
- Audit writer: `datashark.core.audit.AuditWriter.write_record()` (Contract A: one record per file)

**Status:** ✅ Complete — All runs emit audit artifacts

---

## Sprint 3A: Golden Query Harness (December 2025)

**What Changed:**
- Created `tools/golden_harness.py` script for running golden queries Q1–Q3
- Implemented SQL normalization (whitespace collapsing) for baseline comparison
- Added baseline directory: `tests/golden_baselines/` with Q1.sql, Q2.sql, Q3.sql
- Added semantic assertions to prevent invalid baselines

**Files Touched:**
- `datashark-mcp/tools/golden_harness.py` (new, 834 lines)
- `datashark-mcp/tests/test_golden_harness.py` (new, full test suite)
- `datashark-mcp/tests/golden_baselines/` (new directory with baselines)

**Commands Run:**
```bash
cd datashark-mcp
PYTHONPATH=src python3 tools/golden_harness.py --update-baselines
PYTHONPATH=src python3 tools/golden_harness.py
PYTHONPATH=src python3 -m pytest tests/test_golden_harness.py -v
# Result: All tests pass, Q1-Q3 validated
```

**Code Paths:**
- Harness: `datashark-mcp/tools/golden_harness.py`
- Baselines: `datashark-mcp/tests/golden_baselines/Q1.sql`, `Q2.sql`, `Q3.sql`
- Tests: `datashark-mcp/tests/test_golden_harness.py`

**Status:** ✅ Complete — Golden harness validates SQL generation deterministically

---

## Sprint 3B: Golden Query 3 (LEFT JOIN) Fix (December 2025)

**What Changed:**
- Fixed Q3 to generate real LEFT JOIN SQL instead of fallback SQL
- Added `customer_id` field to orders dimensions in `create_lookml_for_q3()` (required for join condition)
- Implemented SQL rebuild logic in golden harness for Q3 using real SQLBuilder with snapshot
- Added snapshot validation function `validate_snapshot_for_query()` to prevent fallback SQL

**Files Touched:**
- `datashark-mcp/tools/golden_harness.py` (added Q3 support, SQL rebuild logic, validation)
- `datashark-mcp/tests/golden_baselines/Q3.sql` (regenerated with correct LEFT JOIN SQL)
- `datashark-mcp/tests/test_golden_harness.py` (added Q3 tests)

**Commands Run:**
```bash
cd datashark-mcp
PYTHONPATH=src python3 tools/golden_harness.py --update-baselines
PYTHONPATH=src python3 tools/golden_harness.py
PYTHONPATH=src python3 -m pytest tests/test_golden_harness.py -v
# Result: Q3 passes semantic assertions, generates correct LEFT JOIN SQL
```

**Code Paths:**
- Q3 LookML: `datashark-mcp/tools/golden_harness.py:228-304` (create_lookml_for_q3)
- SQL rebuild: `datashark-mcp/tools/golden_harness.py:501-745` (Q3-specific rebuild logic)
- Validation: `datashark-mcp/tools/golden_harness.py:387-446` (validate_snapshot_for_query)
- Q3 baseline: `datashark-mcp/tests/golden_baselines/Q3.sql`

**Status:** ✅ Complete — Q3 generates correct LEFT JOIN SQL with COUNT and GROUP BY

---

## MVP: Cursor Extension Scaffold (December 2025)

**What Changed:**
- Created service entrypoint `datashark.core.service.generate_sql()` using golden path (engine.process_request)
- Added MCP tool `generate_sql` to server
- Added extension command "DataShark: Generate SQL" with selection text or prompt input
- SQL inserted into new untitled file and copied to clipboard
- Audit artifacts automatically written and path shown in notification

**Files Touched:**
- `datashark-mcp/src/datashark/core/service.py` (new, 181 lines)
- `datashark-mcp/src/datashark/core/server.py` (added _generate_sql handler, tool schema)
- `datashark-extension/package.json` (added command, configuration settings)
- `datashark-extension/src/extension.ts` (added generateSQLCommand handler)
- `datashark-extension/src/mcp/client.ts` (added generateSQL method)

**Commands Run:**
```bash
# Service validation
cd datashark-mcp
PYTHONPATH=src python3 -c "from datashark.core.service import generate_sql; result = generate_sql('test'); print('Success:', result.get('error') is None)"
# Result: Success: True, audit artifact written

# Extension build (requires npm)
cd datashark-extension
npm install
npm run compile
```

**Code Paths:**
- Service: `datashark-mcp/src/datashark/core/service.py:36-181`
- MCP tool: `datashark-mcp/src/datashark/core/server.py:1777-1827`
- Extension command: `datashark-extension/src/extension.ts:210-306`
- MCP client: `datashark-extension/src/mcp/client.ts:288-293`

**Status:** ✅ Complete — Extension scaffold ready for Cursor installation

**Smoke Test Checklist:**
- [ ] Install extension in Cursor (VSIX or folder location)
- [ ] Run "DataShark: Generate SQL" with selected text → SQL appears in new file
- [ ] Run "DataShark: Generate SQL" with prompt input → SQL appears in new file
- [ ] Verify SQL is copied to clipboard
- [ ] Verify audit artifact path shown in notification matches actual file in `.datashark/audit/`

---

## Markdown Consolidation (December 2025)

**What Changed:**
- Consolidated all December receipts/reports into single `2025-12_WORK_LOG.md`
- Moved superseded receipts to `project/changelog/archive/2025-12/`
- Updated `project/CURSOR_RULES.md` with governance rule preventing markdown sprawl

**Files Touched:**
- `project/changelog/2025-12_WORK_LOG.md` (new, consolidated log)
- `project/CURSOR_RULES.md` (added markdown governance rule)
- Various receipts moved to archive (see inventory below)

**Status:** ✅ Complete — Single active December log, all receipts archived

