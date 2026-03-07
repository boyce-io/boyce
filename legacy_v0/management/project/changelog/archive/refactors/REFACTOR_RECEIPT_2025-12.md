# Refactor Receipt — December 2025

## 1. Changed Files

### Created:
- `_management_documents/CURSOR_INIT_PACKET.md`
- `project/changelog/2025-12_sprint_archive.md`

### Modified:
- `_management_documents/PROJECT_SUMMARY.md`
- `project/CURSOR_RULES.md`
- `project/02_TASKS.md`
- `scripts/audit_doc_sync.py`
- `scripts/context_verify.py`

### Deleted:
- `_management_documents/CONTEXT_BOOTSTRAP.md`
- `_management_documents/_CHAT_BOOT_SCRIPT.txt`

## 2. Critical Excerpts

### 2.1 CURSOR_RULES whitelist + changelog exception

```markdown
## 0. Canonical Document Whitelist (LOCKED)
The following are the only documents allowed to define project goals, scope, phases, or status:

- `_management_documents/CURSOR_INIT_PACKET.md`
- `_management_documents/PROJECT_SUMMARY.md`
- `project/00_MASTER_STRATEGY.md`
- `project/01_ARCHITECTURE.md`
- `project/02_TASKS.md`
- `project/CURSOR_RULES.md` (this file)

**Note:** `CURSOR_INIT_PACKET.md` is an operational initializer (procedure + pointers), not a canonical narrative spec.

**Archive Exception:** `project/changelog/*.md` files are allowed as historical archives (non-governance, history only). These files do not define project goals, scope, phases, or status.

No other markdown files may exist as parallel narratives, contracts, rules, or governance.
```

### 2.2 CURSOR_INIT_PACKET.md (full contents)

```markdown
# Cursor Initialization Packet

Drop this file into Cursor to initialize the assistant with project context and execution protocols.

## Canonical Document Read Order

Read these files in order before starting any work:

1. `project/CURSOR_RULES.md` — Operating rules and canonical whitelist
2. `project/00_MASTER_STRATEGY.md` — Phase definitions and scope (authoritative)
3. `project/01_ARCHITECTURE.md` — Architecture and contracts
4. `project/02_TASKS.md` — Task queue and execution state
5. `_management_documents/PROJECT_SUMMARY.md` — Executive overview and context anchors

## Execution Protocol

- Obey whitelist + governance rules from `project/CURSOR_RULES.md`
- Keep Phase 1/Phase 2 boundaries intact (defined in `project/00_MASTER_STRATEGY.md`)
- Do not create new governance docs without explicit instruction
- Always cite file paths when claiming something exists

## Default Working Behavior

- Locate ACTIVE TASK in `project/02_TASKS.md` and work only on that unless instructed otherwise
- For any new outputs, prefer putting them in the smallest appropriate existing location

## Verification Checklist (End of Work)

- Update `project/02_TASKS.md` status if work completed
- Update `_management_documents/PROJECT_SUMMARY.md` only if the change materially affects executive status
- Ensure no new doc drift (no stale references)
```

### 2.3 PROJECT_SUMMARY "Context Anchors" section

```markdown
## Context Anchors (Agent + Human Quick Map)

- **Spec:** `project/00_MASTER_STRATEGY.md`
- **Architecture:** `project/01_ARCHITECTURE.md`
- **Execution State:** `project/02_TASKS.md`
- **Governance:** `project/CURSOR_RULES.md`
- **Cursor Init Packet:** `_management_documents/CURSOR_INIT_PACKET.md`
```

### 2.4 02_TASKS archive pointer + ACTIVE/NEXT headers

```markdown
## PHASE REALIGNMENT NOTICE (Authoritative)
Phase definitions and scope live only in `project/00_MASTER_STRATEGY.md` ("Phase Definitions"). This file is an execution queue; do not restate phase scope here.

**Older completed work archived to `project/changelog/2025-12_sprint_archive.md`**

## HOLIDAY SPRINT QUEUE (Phase 1 Consolidation)

**Execution Period:** Next 2 weeks  
**Single Source of Truth:** This section is the authoritative execution roadmap for holiday progress.

- [x] **Sprint 1: Join-Path Resolver.** Refactor `SQLBuilder` to use `JoinDef` from the snapshot to ensure deterministic SQL JOIN clauses. ✅ **Complete**
  - **Note:** Must support Many-to-Many junction tables (Gap 2.1) to unblock Golden Query 4.
- [x] **Audit Remediation:** Fixed Gap 1.1 (SQLBuilder uses snapshot.joins), Gap 3.3 & 3.4 (DATE_TRUNC implemented), Risk 4.1 (Clean Room purge). ✅ **Complete**
- [ ] **Sprint 2: Artifact Logger.** Implement the system to capture the `Input -> Snapshot -> SQL` audit trail for every run.
- [ ] **Sprint 3: GoldenHarness.** Create the verification script that runs queries and compares result hashes against the baseline.
- [ ] **Sprint 4: Schema-Reality Check.** Ensure the `LookerAdapter` validates snapshots against the local database catalog.
  - **Note:** Include mandatory Entity.grain validation (Gap 2.4) to prevent double-counting in multi-table aggregations.
- [x] **Sprint 5: Golden Query 2.** (Monthly Revenue & Category Filtering). ✅ **Complete** — SQL generation verified with DATE_TRUNC and 3-table join.

**ACTIVE TASK:** Sprint 5 complete. Ready for Sprint 2 (Artifact Logger) or Sprint 6 (Golden Query 3).

## NEXT

- [ ] **Sprint 6: Golden Query 3.** (Left Join & Zero-Value Detection).
- [ ] **Sprint 7: Golden Query 4.** (Multi-Hop Join & Geographic Grain).
- [ ] **Sprint 8: Golden Query 5.** (Complex Boolean & Exclusion Logic).
- [ ] **Sprint 9: Dialect Stability.** Implement a cross-dialect diff tool for Postgres/DuckDB validation.
- [ ] **Sprint 12-14: Final Integration & IP Audit.**
```

## 3. Drift Checks

### 3.1 Search for deleted filenames

**CONTEXT_BOOTSTRAP.md:**
NONE

**_CHAT_BOOT_SCRIPT.txt:**
NONE

### 3.2 Markdown inventory

**project/:**
- `project/00_MASTER_STRATEGY.md`
- `project/01_ARCHITECTURE.md`
- `project/02_TASKS.md`
- `project/CURSOR_RULES.md`
- `project/EXECUTIVE_AUDIT_DEC_2024.md`

**_management_documents/:**
- `_management_documents/CURSOR_INIT_PACKET.md`
- `_management_documents/PROJECT_SUMMARY.md`

**project/changelog/:**
- `project/changelog/2025-12_sprint_archive.md`

