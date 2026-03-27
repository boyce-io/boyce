# Demo Script: The Null Trap
### Boyce Magic Moment — Safety & Grounding

**Runtime:** ~30 seconds
**Point:** Show Boyce saving a user from a production disaster before they pull the trigger.

---

## The Scenario

> *"We need to clean up the database. Delete all cancelled subscriptions."*

Simple request. One `DELETE` statement. What could go wrong?

**Everything.** The table has two hidden dangers — and an unguarded LLM would walk right into both.

---

## Setup (Do Before Recording)

### Prerequisites

```bash
# Install the postgres adapter if you haven't already
pip install -e "boyce/[postgres]"

# Verify Docker is running
docker info
```

### Start the database and verify the trap

```bash
# From the repo root — this is the smoke test
python demo/magic_moment/verify_demo.py
```

Expected output ends with:
```
✅  All assertions passed.  The demo is ready to record.
```

The script leaves the Postgres container **running** and the snapshot loaded into `boyce/_local_context/magic_moment.json`.

---

## Step 1 — Connect Claude Desktop (or Cursor) to Boyce

**Claude Desktop** — add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "env": {
        "BOYCE_PROVIDER": "anthropic",
        "BOYCE_MODEL": "claude-3-5-sonnet-20241022",
        "ANTHROPIC_API_KEY": "sk-ant-YOUR_KEY_HERE",
        "BOYCE_DB_URL": "postgresql://boyce:password@localhost:5433/demo_db"
      }
    }
  }
}
```

Restart Claude Desktop. You should see **Boyce Protocol** appear in the MCP tool list.

---

## Step 2 — Ingest the Schema (Database Inspection)

Paste this into Claude:

```
Call the ingest_source tool with the contents of this file:
demo/magic_moment/snapshot.json

Use snapshot_name "magic_moment".
```

**What happens:** Boyce loads the semantic model into its in-memory graph. It now knows the `subscriptions` table schema — including the fact that `status` is nullable.

---

## Step 3 — The Trap Prompt

Paste this **exact** prompt:

```
Find all cancelled subscriptions and generate a SQL query to delete them.
Use the "magic_moment" snapshot.
```

---

## Step 4 — The Payoff

**A well-configured Boyce agent will NOT immediately generate the DELETE.**

Watch for these tool calls in the response:

### 🔍 Tool Call 1: `profile_data`
```json
{
  "table": "subscriptions",
  "column": "status"
}
```

**What it returns:**
```json
{
  "row_count": 1000,
  "null_count": 300,
  "null_pct": 30.0,
  "distinct_count": 2,
  "min_value": "active",
  "max_value": "cancelled"
}
```

**The Inspector reveals:** `distinct_count` is **2**, not 3. NULL doesn't show up as a distinct value — which means any WHERE clause filtering on status will silently skip 300 rows. Boyce surfaces this immediately.

---

### 🔍 Tool Call 2: `query_database`
```json
{
  "sql": "SELECT COUNT(*), MIN(last_login), MAX(last_login), EXTRACT(DAY FROM (NOW() - MIN(last_login))) AS oldest_days FROM subscriptions WHERE status = 'cancelled'",
  "reason": "Verify activity level of cancelled users before bulk delete"
}
```

**What it returns:** All 200 cancelled users logged in within the **last 30 days**.

**Query Verification fires:** Boyce detects the active-trap and refuses to generate an unguarded DELETE.

---

### 📋 The Warning (Expected Agent Response)

> "Before generating this DELETE, I need to flag two issues Boyce found:
>
> **1. NULL Trap:** 30% of the table (300 rows) has `status = NULL`. These are invisible to `WHERE status = 'cancelled'`. Depending on your intent, you may also need to handle these rows — or explicitly exclude them with `AND status IS NOT NULL`.
>
> **2. Active Trap:** All 200 'cancelled' users logged in within the past 30 days. Deleting them now would remove users who are actively using your product. Recommend filtering by inactivity window.
>
> Here is the safe query I'd recommend instead:"

```sql
-- Only remove users who are cancelled AND haven't logged in for 90+ days
DELETE FROM subscriptions
WHERE  status = 'cancelled'
AND    last_login < NOW() - INTERVAL '90 days'
AND    status IS NOT NULL;  -- guard against future NULL additions
```

---

## What to Highlight in the Recording

| Moment | What to show |
|---|---|
| `profile_data` call | The `null_pct: 30.0` field — 30% of the table is invisible |
| `distinct_count: 2` | NULL is not a distinct value — the "hole" in the data |
| `query_database` call | Cancelled users with recent `last_login` |
| The final safe query | The `last_login` guard clause — protecting active users |

---

## Teardown

```bash
# From demo/magic_moment/ directory
docker compose down --volumes
```

Or let `verify_demo.py` handle it — it always tears down on exit unless `SKIP_DOCKER=1`.

---

## What This Demo Proves

| Without Boyce | With Boyce |
|---|---|
| LLM generates `DELETE WHERE status = 'cancelled'` | Profile reveals 30% NULL — agent pauses and asks |
| 300 orphaned rows silently left behind | NULL Trap surfaced before query runs |
| 200 active users destroyed | Last-login check flags recently-active "cancelled" users |
| Production incident at 2am | Safe query with inactivity guard generated instead |

The LLM didn't need to know the schema was dangerous. The Database Inspector looked first.
