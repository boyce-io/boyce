# Plan: Init Wizard Overhaul

**Status:** Ready for build
**Created:** 2026-03-16
**Model assignment:** Sonnet · medium (all build steps), Opus · high (final review)
**Depends on:** None — self-contained rewrite of `boyce/src/boyce/init_wizard.py`

---

## Problem

The setup wizard (`boyce-init`) is the first thing a new user runs. It currently:
- Uses jargon ("asyncpg DSN", "EXPLAIN pre-flight", "MCP host", "NL mode")
- Shows 6 hosts including 4 irrelevant ones with alarming "not found" status
- Asks an LLM config question whose answer is always "no" for MCP editors
- Writes bare `"command": "boyce"` which fails in any editor that doesn't inherit the user's venv PATH
- Gives vague post-setup guidance ("run boyce-scan \<path\>")
- Does nothing to help the user actually load data — the whole point of setup
- Uses plain `input()` with no interactive selection

A data analyst who knows SQL but hasn't configured connection strings recently will bail.

## Goal

After `boyce-init` completes, Boyce is **ready to use** — editor wired, database connected, schemas loaded. The user's first question in their editor should just work.

---

## Design Spec

### Three-step flow

```
Step 1 of 3 — Editor
Step 2 of 3 — Database
Step 3 of 3 — Data Sources
```

### Interactive mode (questionary)

If `questionary` is installed, the wizard uses arrow-key navigation, checkboxes, and inline text input. If not, it offers to install it:

```
For the best experience, Boyce uses interactive prompts.
Install now? [Y/n]:
Installing... ✓ Ready
```

Y is the default. One Enter installs. If N or install fails, falls back to numbered lists and `input()`. Never broken, always functional.

`questionary` is declared as an optional dependency: `pip install boyce[wizard]`.

### Step 1 — Editor (multi-select checkbox)

**questionary mode:**
```
Step 1 of 3 — Editor

  Which editors do you use?  (Space to toggle, Enter to confirm)

  ❯ ◉ Cursor           (detected)
    ◉ Claude Code       (detected)
    ○ Claude Desktop
    ○ VS Code
    ○ JetBrains / DataGrip
    ○ Windsurf
    ○ Something else
```

- Detected editors pre-checked. Enter accepts defaults (zero effort for common case).
- "Something else" → prints a generic JSON config snippet with instructions.
- All editors always shown — detected ones sorted to top with `(detected)` label.
- No "not found" anywhere. Undetected editors are simply unlabeled.

**Fallback mode:**
```
Which editors do you use?
  [1] Cursor            (detected)
  [2] Claude Code       (detected)
  [3] Claude Desktop
  [4] VS Code
  [5] JetBrains / DataGrip
  [6] Windsurf
  [7] Something else

Enter numbers (e.g. 1,2): 1,2
```

**Detection improvements:**
- Cursor: check `/Applications/Cursor.app` (macOS), `~/.cursor/` dir, `cursor` on PATH
- VS Code: check `/Applications/Visual Studio Code.app`, `code` on PATH, `~/.vscode/`
- Claude Code: check `.claude/` in CWD (existing), also `claude` on PATH
- JetBrains: check `.idea/` in CWD (existing), also common app paths
- Windsurf: check app path + `~/.codeium/` dir

### Step 2 — Database (field-by-field with test)

**Flow:**
```
Step 2 of 3 — Database

  Connect to your database for live queries and SQL validation.
  Press Enter to skip — you can always add this later.

  [1] Enter connection details
  [2] Paste a connection URL
  [3] Skip for now

  > 1

  Host [localhost]: analytics.company.com
  Port [5432]:
  Database: warehouse
  Username: analyst
  Password: ········

  Connecting... ✓ Connected (42 tables)
  Saved as "warehouse"

  Add another database? [y/N]:
```

**Field-by-field input:**
- Host default: `localhost` (shown in brackets, Enter accepts)
- Port default: `5432` (auto-adjusts to `5439` if host contains "redshift")
- Database, Username: required (no default)
- Password: `getpass.getpass()` — masked input

**Option 2 (paste URL):**
```
  Connection URL: postgresql://analyst:****@analytics.company.com:5432/warehouse
  Connecting... ✓ Connected (42 tables)
```

**Connection test:**
- Attempts asyncpg connection (if asyncpg installed) with 5-second timeout
- Reports human-readable errors:
  - "Could not reach host — is the database running?"
  - "Authentication failed — check your username and password"
  - "Database 'warehouse' not found on this server"
  - Success: "Connected (N tables)" — shows table count as proof
- If asyncpg not installed: skip test, print note: "Install asyncpg for connection testing: pip install boyce[postgres]"

**On failure:** "Try again? [Y/n]" — loops back with previous values pre-filled (only need to fix the broken field).

**Loop:** After each success: "Add another database? [y/N]"

### Step 3 — Data Sources (auto-discovery + manual)

**Flow:**
```
Step 3 of 3 — Data Sources

  Boyce can also learn your schema from files you already have:
    • dbt projects (models, sources, schema.yml)
    • LookML / Looker (views, explores, joins)
    • SQL files (DDL, CREATE TABLE, migrations)
    • ORM definitions (Django, SQLAlchemy, Prisma)
    • Data files (CSV, Parquet, SQLite)

  Search your computer for data sources? [Y/n]: y

  I'll look in:
    ~/repos  ~/projects  ~/code  ~/work  ~/src  ~/dev
  (Everything stays on your machine — nothing is sent anywhere.)

  Searching...

  Found 3 data sources:

    [1] ✓  ~/repos/looker-production       LookML (47 views, 12 explores)
    [2] ✓  ~/repos/analytics-dbt           dbt (31 models, 8 sources)
    [3]    ~/Desktop/old_export.csv         CSV (1 file)

  Ingest which? (1,2 / all / none) [1,2]:

  Ingesting...
    ✓ looker-production — 47 views, 89 joins
    ✓ analytics-dbt — 31 models, 44 joins

  Add more paths manually? [y/N]:
```

**Auto-discovery implementation:**

Search locations (curated, not recursive from `~`):
```python
SEARCH_ROOTS = [
    ~/repos, ~/projects, ~/code, ~/src, ~/work, ~/dev,
    ~/github, ~/git, ~/workspace,
    # Also: siblings of CWD parent
]
```
Only search roots that exist. Max depth: 3 levels from each root.

Search for **project root markers** (fast — not every file):

| Marker | Parser | What it means |
|---|---|---|
| `dbt_project.yml` | dbt | dbt project root |
| `*.lkml` or `*.lookml` (3+ files in a dir) | LookML | LookML repo |
| `schema.prisma` or `*.prisma` | Prisma | Prisma schema |
| `models.py` with `from django` | Django | Django models |
| `models.py` with `from sqlalchemy` | SQLAlchemy | SQLAlchemy models |
| `*.sql` (5+ files in a dir with CREATE TABLE) | DDL | SQL schema collection |
| `*.sqlite` / `*.db` (with SQLite header) | SQLite | SQLite database |
| `manifest.json` (with nodes+sources) | dbt manifest | Compiled dbt |

For each found project: run a lightweight scan (`scan_path` from `scan.py`) to get entity/field/join counts for the display. Don't fully ingest until the user selects.

**Pre-selection heuristic:**
- Git repos with recognized project structure → pre-checked (✓)
- Individual files in Desktop/Downloads → not pre-checked
- Anything with high parser confidence (>0.8) → pre-checked

**If nothing found:** "No data sources found in common locations. Enter a path to scan (or Enter to skip):" — falls through to manual, no dead end.

**If too many found (>10):** Show top 10 by confidence, grouped by type. "(+N more — type 'list' to see all)"

**Manual add (always offered after auto):**
```
  Add more paths manually? [y/N]: y
  Path: ~/work/client-schemas/warehouse.sql
  Scanning... ✓ DDL — 12 tables, 67 columns
  Saved as "warehouse"
  Add another? [y/N]:
```

### Summary screen

```
Done! Boyce is ready.
══════════════════════

  Editors:    Cursor ✓  Claude Code ✓
  Databases:  warehouse (42 tables)
  Sources:    looker-production (47 views), analytics-dbt (31 models)

  Next: Open your editor and try:
    "Use boyce to show me the database schema"
    "What tables have revenue data?"
```

- Editor names are specific (not "your MCP host")
- Shows concrete counts as proof that setup worked
- Gives exact prompts to try — copy-pasteable

### Command resolution fix

`_resolve_boyce_command()` must return the **full resolved path**, not bare `"boyce"`:

```python
def _resolve_boyce_command() -> str:
    found = shutil.which("boyce")
    if found:
        return found  # Full path, e.g. /Users/.../venv/bin/boyce
    bin_dir = Path(sys.executable).parent
    candidate = bin_dir / "boyce"
    if candidate.exists():
        return str(candidate)
    return "boyce"  # Last resort fallback
```

This is the critical bug fix — without it, every editor config is broken for venv installs.

---

## Implementation Steps

### Step 0 — Dependencies and scaffolding
**Sonnet · low**

- Add `wizard = ["questionary>=2.0"]` to `[project.optional-dependencies]` in `pyproject.toml`
- Reinstall: `uv pip install -e "boyce/[wizard]"`
- Verify import: `python -c "import questionary; print(questionary.__version__)"`

### Step 1 — Fix `_resolve_boyce_command()` (critical, standalone)
**Sonnet · low**

One-line fix: return `shutil.which("boyce")` instead of bare `"boyce"`. Also add fallback via `sys.executable` parent dir. This fix is independent and should be done first since it affects all configs the wizard writes.

### Step 2 — Rewrite `init_wizard.py` — core structure
**Sonnet · medium**

Rewrite `run_wizard()` as three-step flow. Keep all existing functions (`detect_hosts`, `generate_server_entry`, `merge_config`) — they work. Replace the interactive portion.

New internal structure:
```
run_wizard()
├── _ensure_questionary()          # offer to install, set HAS_QUESTIONARY
├── _step_editors(hosts)           # multi-select, returns list of MCPHost
├── _step_databases()              # field-by-field or paste, returns list of DSNs
├── _step_data_sources()           # auto-discover + manual, runs scan/ingest
├── _build_and_write_configs(...)  # generate entries, merge into each editor config
└── _print_summary(...)            # final status screen
```

**Key rules for the rewrite:**
- Every interactive prompt has a questionary path and a fallback path
- Fallback uses `input()` with the improved prompts (no jargon)
- LLM config question is GONE — never asked for MCP editors
- All user-facing text uses "editor" not "host"
- All user-facing text avoids: "asyncpg", "DSN", "EXPLAIN", "pre-flight", "MCP", "NL mode", "env var"

### Step 3 — Editor detection improvements
**Sonnet · medium**

Add detection for:
- macOS app bundles: `/Applications/Cursor.app`, `/Applications/Visual Studio Code.app`
- User config dirs: `~/.cursor/`, `~/.vscode/`
- PATH binaries: `cursor`, `code`
- Existing: `.claude/` (Claude Code), `.idea/` (JetBrains)

Update `_host_specs()` to include `detection_hints` for Cursor and VS Code.

### Step 4 — Database connection (Step 2 of wizard)
**Sonnet · medium**

New function `_step_databases()`:
- Field-by-field input with defaults (host=localhost, port=5432)
- Paste URL option (parse with urllib.parse to validate format)
- Password via `getpass.getpass()`
- Connection test via asyncpg (optional import, graceful skip)
- Retry loop on failure with pre-filled values
- "Add another?" loop
- Returns list of `(name, dsn)` tuples

Connection test implementation:
```python
async def _test_connection(dsn: str) -> tuple[bool, str]:
    """Test a database connection. Returns (success, message)."""
    try:
        import asyncpg
    except ImportError:
        return True, "Connection saved (install asyncpg to verify: pip install boyce[postgres])"
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=5.0)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
        )
        await conn.close()
        return True, f"Connected ({count} tables)"
    except asyncio.TimeoutError:
        return False, "Could not reach host — is the database running?"
    except asyncpg.InvalidAuthorizationSpecificationError:
        return False, "Authentication failed — check your username and password"
    except asyncpg.InvalidCatalogNameError as e:
        return False, f"Database not found: {e}"
    except Exception as e:
        return False, f"Connection failed: {e}"
```

### Step 5 — Data source auto-discovery (Step 3 of wizard)
**Sonnet · medium**

New module: `boyce/src/boyce/discovery.py` (keeps init_wizard.py focused on the wizard flow).

```python
def discover_sources(search_roots: list[Path], max_depth: int = 3) -> list[DiscoveredSource]:
    """
    Walk search_roots looking for project-root markers.
    Returns list of DiscoveredSource(path, parser_type, description, confidence, counts).
    """
```

Implementation:
1. Filter `search_roots` to those that exist
2. Walk each root up to `max_depth` levels
3. At each directory, check for project-root markers (fast — stat calls, not content reads):
   - `dbt_project.yml` → dbt project
   - 3+ `.lkml`/`.lookml` files → LookML repo
   - `schema.prisma` → Prisma project
   - `manage.py` + `models.py` → Django
   - 5+ `.sql` files → DDL collection
   - `manifest.json` → check content for dbt
   - `*.sqlite`/`*.db` → SQLite
4. For each found project, run a quick `scan_path()` to get counts
5. Sort by confidence, group by type
6. Return structured results for the wizard to display

Pre-selection logic:
```python
@dataclass
class DiscoveredSource:
    path: Path
    parser_type: str           # "dbt", "lookml", "ddl", etc.
    description: str           # "47 views, 12 explores"
    confidence: float
    counts: dict               # {"entities": 47, "fields": 312, "joins": 89}
    is_git_repo: bool
    pre_selected: bool         # True if confidence > 0.8 and is_git_repo
```

New function in wizard: `_step_data_sources()`:
1. Ask "Search your computer?" (Y/n)
2. If yes: show search locations, run `discover_sources()`, present as checkbox/list
3. Ingest selected sources via `scan_path()` + `_save_snapshots()`
4. Ask "Add more paths manually?" (y/N)
5. Manual loop: path input → `scan_path()` → save → "Add another?"

### Step 6 — "Something else" editor support
**Sonnet · low**

When user selects "Something else":
```
  Boyce uses the MCP (Model Context Protocol) standard.
  Most AI-enabled editors support it.

  Add this to your editor's MCP config file:

  {
    "mcpServers": {
      "boyce": {
        "command": "/path/to/boyce",
        "args": [],
        "env": { "BOYCE_DB_URL": "your-connection-url" }
      }
    }
  }

  Check your editor's documentation for where MCP servers are configured.
```

Print the actual resolved command path and any configured DB URLs.

### Step 7 — Update CLI smoke tests
**Sonnet · low**

Update `test_cli_smoke.py`:
- `boyce-init` non-interactive test still passes (stdin closed → graceful exit)
- Add import test for `init_wizard` module
- Add unit test for `_resolve_boyce_command()` returning full path

### Step 8 — Integration test
**Sonnet · medium**

End-to-end manual verification:
1. Uninstall questionary → run wizard → verify fallback works with numbered lists
2. Install questionary → run wizard → verify interactive mode
3. Check generated `.cursor/mcp.json` has full path in `command`
4. Check generated config has DB URL from field-by-field entry
5. Verify `_local_context/` has snapshots from data source step

---

## Files Modified

| File | Change |
|---|---|
| `boyce/pyproject.toml` | Add `wizard = ["questionary>=2.0"]` optional dep |
| `boyce/src/boyce/init_wizard.py` | Full rewrite — 3-step flow, questionary + fallback |
| `boyce/src/boyce/discovery.py` | NEW — data source auto-discovery logic |
| `boyce/tests/test_cli_smoke.py` | Update wizard smoke test, add command resolution test |

## Files NOT Modified

- `server.py`, `cli.py`, `scan.py`, `kernel.py`, `builder.py` — no changes
- Parser files — used as-is via registry
- `store.py` — used as-is for snapshot persistence

---

## Acceptance Criteria

1. `boyce-init` with questionary installed → interactive arrow-key/checkbox wizard
2. `boyce-init` without questionary → functional numbered-list fallback
3. Multi-editor selection works (configure Cursor + Claude Code in one run)
4. DB field-by-field input constructs valid DSN and tests connection
5. DB paste-URL option works
6. DB retry loop works on auth failure (pre-fills previous values)
7. Auto-discovery finds dbt/LookML/DDL projects in standard locations
8. Manual path entry scans and ingests correctly
9. Generated configs use full path to `boyce` binary (not bare command)
10. Summary screen shows everything configured with counts
11. All 289 existing tests still pass
12. CLI smoke tests updated and passing
