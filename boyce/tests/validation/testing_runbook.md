# Boyce Testing Runbook
**Will's testing sprint — Wednesday March 11 + Thursday March 12, 2026**

This is your checklist. Work through it in order. Log failures as you go.
Claude Code is live alongside you — paste any error and it gets fixed.

---

## Before You Start (5 minutes)

```bash
# 1. Start Pagila
cd /Users/willwright/ConvergentMethods/Products/Boyce/boyce/tests/validation
./setup.sh
# Wait for "Ready." — takes ~30 seconds first time

# 2. Verify Boyce is installed
boyce --help

# 3. Open this runbook alongside your MCP host
```

---

## Wednesday Morning — Integration (2 hours target)

Work through each host. Stop and paste errors to Claude Code immediately — don't move
to the next host until the current one is working or confirmed broken with a root cause.

### Host 1: Claude Desktop

- [ ] Config written (`~/Library/Application Support/Claude/claude_desktop_config.json`)
- [ ] Claude Desktop restarted
- [ ] Tools icon visible in chat input (hammer icon)
- [ ] Called `get_schema` — returned entities?
- [ ] Asked plain-English question — got SQL back?

**Log (fill in):**
```
get_schema result: [ OK / ERROR: _______ ]
plain-English test: "______________________________"
SQL output:
  [ correct / garbage / error: _______ ]
```

---

### Host 2: Cursor

- [ ] `.cursor/mcp.json` created in project root
- [ ] Cursor window reloaded
- [ ] Boyce tools appear in Cursor chat
- [ ] `get_schema` works
- [ ] `build_sql` produces SQL from a StructuredFilter

**Log:**
```
get_schema result: [ OK / ERROR: _______ ]
build_sql test StructuredFilter: <paste what you sent>
SQL output: [ correct / garbage / error: _______ ]
```

---

### Host 3: Claude Code

- [ ] `.claude/settings.json` updated with mcpServers config
- [ ] New Claude Code session started
- [ ] Boyce tools available
- [ ] `get_schema` works
- [ ] Claude Code can chain `get_schema` → `build_sql` autonomously

**Log:**
```
get_schema result: [ OK / ERROR: _______ ]
autonomous chain test: [ worked / failed: _______ ]
```

---

### Host 4: Cline (VS Code)

- [ ] Cline installed from Marketplace
- [ ] MCP server config added
- [ ] Boyce shows as connected in Cline's MCP panel
- [ ] `get_schema` works in Cline chat
- [ ] SQL generation works

**Log:**
```
Connected: [ YES / NO ]
get_schema: [ OK / ERROR: _______ ]
```

---

### Host 5: Continue.dev (VS Code)

- [ ] `~/.continue/config.yaml` updated
- [ ] Continue reloaded
- [ ] Boyce tools accessible
- [ ] Basic query works

**Log:**
```
Connected: [ YES / NO ]
Basic query: [ OK / ERROR: _______ ]
```

---

## Wednesday Afternoon — Query Battery

Run these queries on **every host that passed the morning integration check**.
Use the Pagila database (15 tables, DVD rental schema) for all queries.

For each query: note the host, the exact prompt you typed, and the SQL returned.
Claude Code reviews flagged results in real time.

---

### Category A — Structured Capability Tests

**A1. Simple aggregation**
```
Prompt: "Total revenue by customer, last 90 days"
Expected: GROUP BY customer, SUM(amount), date filter on payment_date
```
- [ ] Claude Desktop: [ SQL correct / issues: _______ ]
- [ ] Cursor: [ SQL correct / issues: _______ ]
- [ ] Claude Code: [ SQL correct / issues: _______ ]

---

**A2. Multi-join (Dijkstra path resolution)**
```
Prompt: "Show me the top 10 films by total rental count, with their category"
Expected: film → inventory → rental (join path), COUNT(rental_id), GROUP BY film
Note: requires 3+ table join — this tests the semantic graph
```
- [ ] SQL includes correct join path? [ YES / NO ]
- [ ] Result makes sense? [ YES / NO ]
- [ ] Which host produced the best output? _______

---

**A3. NULL trap scenario**
```
Prompt: "Show me rentals where return_date is NULL" (or any equality filter on a NULL-heavy column)
Expected: boyce fires NULL_TRAP warning in response
```
- [ ] NULL_TRAP warning appears in response? [ YES / NO ]
- [ ] SQL still generated? [ YES / NO ]
- [ ] Warning message is intelligible? [ YES / NO ]

---

**A4. Schema exploration (non-SQL)**
```
Prompt: "What tables have financial data?" or "What does the payment table contain?"
Expected: get_schema response, prose explanation — NOT a SQL query
```
- [ ] Intent routing worked (didn't try to generate SQL)? [ YES / NO ]
- [ ] Response was useful? [ YES / NO ]

---

**A5. Dialect check (Redshift safety lint)**
```
Prompt: "Show me customer names concatenated with their email"
Expected: uses || not CONCAT() — boyce safety layer enforces this for Redshift dialect
```
- [ ] SQL uses `||` not `CONCAT()`? [ YES / NO ]
- [ ] (Set dialect to redshift in StructuredFilter to trigger lint)

---

### Category B — Real-World Conversational Prompts

These are messy, ambiguous, human prompts. The goal is to see how the planner handles
natural language that isn't cleanly structured. Record exactly what you typed and
exactly what came back.

**Junior data analyst persona** (limited SQL knowledge, vague):

- [ ] "what are the finance tables?"
  - Response: _______________________________
  - Useful? [ YES / SORT OF / NO ]

- [ ] "show me top customers"
  - Response: _______________________________
  - Top by what? Did boyce ask for clarification or make an assumption?

- [ ] "monthly trend report"
  - Response: _______________________________
  - Did it pick a sensible metric and time grain?

---

**Staff data engineer persona** (domain-specific, complex):

- [ ] "how did rental patterns change across store locations over the past year?"
  - Response: _______________________________
  - Did it join store → inventory → rental? Did it handle temporal grouping?

- [ ] "reconcile revenue between payments and rental counts"
  - Response: _______________________________
  - Did it produce two comparable queries or a single reconciliation?

---

**Non-technical stakeholder persona** (pure business language):

- [ ] "are we losing customers?"
  - Response: _______________________________
  - Did it interpret this as churn/retention? What metric did it pick?

- [ ] "what's our best category?"
  - Response: _______________________________
  - Best by revenue? By rentals? Did it ask?

- [ ] "compare this month to last"
  - Response: _______________________________
  - Did it produce a period-over-period comparison?

---

## Wednesday End-of-Day Log

Before closing your laptop, fill this in:

```
Hosts working:        [ list ]
Hosts broken:         [ list + root cause ]
Category A failures:  [ list ]
Category B surprises: [ anything unexpected, good or bad ]
Planner quality:      [ strong / acceptable / needs work — one sentence ]
Biggest issue found:  _______________________________
Fixed live today:     [ list ]
Still open:           [ list — Claude Code addresses overnight ]
```

---

## Thursday Morning — Retest + Decision

- [ ] All overnight fixes retested
- [ ] Any remaining Category B queries completed
- [ ] NULL trap demo verified: `demo/magic_moment/verify_demo.py` passes

**Thursday afternoon — version decision:**

Ask yourself honestly:
1. Do I trust this to return correct SQL on real business questions?
2. Did the planner handle ambiguity gracefully (ask for clarification or make a sensible assumption)?
3. Would I be comfortable if 100 people installed this today?

```
Version decision: [ v1.0 — ship it / v0.x — iterate / hold — specific blocker: _______ ]
Decision made by: Will Wright
Date: Thursday March 12, 2026
```

If go: `cd boyce && python -m build && uv publish`

---

## Failure Log Template

Use this for each failure found:

```
Host:        _______
Query:       "_______________________________"
Expected:    _______
Got:         _______
Severity:    [ blocker / degraded / minor ]
Fixed:       [ YES / NO / deferred ]
Fix:         _______
```

---

## Notes

- Port 5433 is Pagila (15 tables, DVD rental)
- Port 5432 is live_fire (bare Postgres, used by live_fire tests)
- Don't use 5432 for manual testing — use 5433
- If Docker is slow: `docker compose logs -f pagila` to see what's happening
- Connection string: `postgresql://boyce:password@localhost:5433/pagila`
