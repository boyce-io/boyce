# Plan: Client Reference Strip
**Status:** Planned — execute before any public push or repo transfer
**Priority:** Absolute requirement. No exceptions.
**Created:** 2026-03-06

---

## Directive

No reference to any specific client, employer, or private business relationship may exist
in any committed file, git history, published package, or memory file associated with Boyce.
This is a permanent, non-negotiable policy.

---

## Current Exposure Assessment

### In Current Working Tree (Committed Files)

All working tree references have been cleaned. Files that were edited during Phase 1:

| File | What was changed |
|------|-----------------|
| `.gitignore` | Section comment generalized |
| `_management_documents/2026-03-06_sprint_planning_session.md` | All deployment references generalized |
| `_management_documents/SESSION_BRIEFING_2026-03-04.md` | Deployment plan references generalized |
| `_management_documents/2026-02-28 - DataShark Product Brainstorming.md` | Brainstorming note generalized |
| `_strategy/plans/block-1-ship-it.md` | Step 4 title, body, acceptance criteria, risks generalized |
| `_strategy/plans/block-2-protocol-and-parsers.md` | Prerequisite generalized |
| `_strategy/plans/block-3-governance-and-ecosystem.md` | Prerequisite generalized |
| `_strategy/plans/block-4-ecosystem-and-adoption.md` | Prerequisite generalized |
| `_strategy/MASTER.md` | Checklist item generalized |
| `legacy_v0/management/project/changelog/archive/EXECUTIVE_AUDIT_DEC_2024.md` | Audit item generalized |
| `legacy_v0/scripts/setup/set_credentials.sh` | Production hostname, username, database name redacted |

### In Git History (Deleted Files / Old Versions)

- LookML files containing client-specific entity name prefixes
- Previous versions of strategy docs and brainstorming files
- Credential setup scripts with production hostnames
- Old snapshot JSON files with client-specific table references

**Action required (Phase 4):** Use `git filter-repo --replace-text` to rewrite history.

### In Memory Files (Local, Not Committed)

| File | Status |
|------|--------|
| `MEMORY.md` | Cleaned — deployment reference generalized |

### Not in Git (Local Only — No Action Required for Repo)

- Session transcripts in `.claude/projects/` — extensive, but these are local JSONL files
  that are never committed. No repo action needed, but be aware they exist locally.

---

## Execution Plan

### Phase 1: Clean Working Tree (Sonnet)

For every file listed above:
- Remove or replace all references with generic language
- "Deploy on production warehouse" or "validate against a live database" — no client names
- The planning session doc (`2026-03-06_sprint_planning_session.md`) should be rewritten
  with all references removed and testing approach updated to open-source databases
- The credential script in legacy should have the hostname fully redacted

### Phase 2: Clean Memory Files (Sonnet)

- Update `MEMORY.md` to remove the reference
- Verify no other memory files contain references

### Phase 3: Install Pre-Commit Hook (Sonnet)

Create `.git/hooks/pre-commit`:
- Reads from `.claude/sensitive_terms.txt` (gitignored)
- Scans all staged files for any term in the list (case-insensitive)
- Blocks commit with clear error message showing file + line + matched term
- Extensible: any future sensitive term added to the patterns file

Create `.claude/sensitive_terms.txt` (gitignored):
- Contains the client name and any related identifiers (hostnames, entity prefixes, etc.)

Update `.gitignore`:
- Add `.claude/sensitive_terms.txt`

Update `quickstart.sh`:
- Copy the pre-commit hook into `.git/hooks/` during dev setup

### Phase 4: Rewrite Git History (Sonnet — Will approves before execution)

**Tool:** `git filter-repo --replace-text`

Create a replacements file mapping every variant to redacted text:
- The client name (all cases) -> `[REDACTED]`
- Production hostnames -> `[REDACTED]`
- Entity name prefixes from LookML files -> `[REDACTED]`

Run `git filter-repo --replace-text replacements.txt` on the private repo.

**Important:** This rewrites ALL commit hashes. After running:
- The remote must be force-pushed (one-time exception to the force-push deny rule)
- Any local clones must be re-cloned
- This is a one-way operation — do it once, do it right

**Alternative (simpler, if public repo is separate):**
If the `boyce-io/boyce` public repo starts as a fresh repo (no history from the private
ConvergentMethods repo), then Phase 4 is optional for the private repo. The public repo
would start clean with an initial commit from the current (cleaned) state. The private
repo retains its history — which is fine since it stays private under ConvergentMethods.

**Recommendation:** Do both. Clean the private repo history AND start the public repo fresh.
Belt and suspenders. The private repo might someday be transferred or opened, and history
rewrites cost nothing after Phase 1-3 are done.

### Phase 5: Verify (Sonnet)

After all phases:
```bash
# Should return zero results
grep -ri "[CLIENT_NAME]" --include="*.md" --include="*.py" --include="*.sh" --include="*.json" .
git log --all -p | grep -i "[CLIENT_NAME]" | wc -l
```

---

## Ongoing Policy

1. **Pre-commit hook** catches all future attempts automatically
2. **No client names in any planning document, strategy doc, code comment, or test fixture**
3. **No client-specific test infrastructure** — all testing uses open-source databases
4. **Private testing** of production deployments happens on Will's separate machine, outside this repo
5. **Memory files** must never reference specific clients — use generic terms only
6. **This policy applies to all repos** under ConvergentMethods and boyce-io orgs

---

## Model Assignment

| Phase | Model | Rationale |
|-------|-------|-----------|
| Phase 1: Clean working tree | Sonnet 4.6 | Mechanical find-and-replace |
| Phase 2: Clean memory | Sonnet 4.6 | Trivial |
| Phase 3: Pre-commit hook | Sonnet 4.6 | Shell scripting |
| Phase 4: Git history rewrite | Sonnet 4.6 | Mechanical, but Will approves before execution |
| Phase 5: Verify | Sonnet 4.6 | Automated check |
