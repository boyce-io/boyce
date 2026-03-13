# Your AI Agent's SQL Is Correct. The Answer Is Still Wrong.

*How NULL distributions silently corrupt agentic database workflows — and why the fix isn't a better model.*

---

You ask your AI agent a simple question: *"How many cancelled subscriptions do we have?"*

The agent connects to your database. It reads the schema. It writes SQL:

```sql
SELECT COUNT(*) FROM subscriptions WHERE status = 'cancelled';
```

The SQL is syntactically perfect. The agent is confident. The query returns **200**.

The real answer is somewhere between 200 and 500. You'll never know, because 30% of your table has `status = NULL` — and every one of those rows was silently excluded from the result. The agent didn't lie to you. It didn't hallucinate. It generated correct SQL against an incomplete picture of reality, and the database did exactly what it was asked. The rows with no status weren't counted as cancelled. They also weren't counted as *not* cancelled. They simply didn't exist as far as the query was concerned.

This is the Null Trap, and it's about to become the most common source of silently wrong answers in AI-assisted data workflows.

---

## Why NULLs Are Different From Wrong Values

Most data quality conversations focus on *wrong* data — a misspelled city name, a negative price, a date in the future. Wrong data is visible. It shows up in results. Someone eventually notices.

NULLs are invisible. SQL's three-valued logic guarantees it.

Consider the expression `WHERE status = 'cancelled'`. In most programming languages, if `status` is null, this evaluates to false. In SQL, it evaluates to **UNKNOWN** — a third truth value that is neither true nor false. Rows where the predicate evaluates to UNKNOWN are excluded from the result set. Not flagged, not warned about — excluded.

This means:

| Query | What you think it returns | What it actually returns |
|-------|--------------------------|------------------------|
| `WHERE status = 'cancelled'` | All cancelled rows | Only rows where status is *literally* the string 'cancelled' |
| `WHERE status != 'cancelled'` | All non-cancelled rows | Only rows where status is a *non-null string* that isn't 'cancelled' |
| `WHERE status = 'cancelled' OR status != 'cancelled'` | All rows | Only rows where status is not NULL |

That last one is the kicker. `x = 'a' OR x != 'a'` should be a tautology. In SQL, it isn't. The 300 rows where `status` is NULL satisfy neither condition. They fall through every filter you write.

A senior data engineer knows this. They've been burned by it. They habitually write `AND status IS NOT NULL` or `COALESCE(status, 'unknown')`. But the reason they know is because they learned the hard way — by shipping a wrong number, noticing it a week later, and tracing it back to a nullable column.

An AI agent has no such scars.

---

## Why LLMs Make This Worse

An LLM generating SQL works from the schema. The schema says `status VARCHAR(20)`. It doesn't say "30% of this column is NULL and those rows represent users stuck in an incomplete onboarding flow." The schema describes structure. It says nothing about the *distribution* of actual data.

This is the gap. An experienced human looks at a `VARCHAR` column and thinks: "Is this nullable? How many NULLs does it actually have? What do those NULLs mean in the business context?" An LLM looks at the same column and thinks: "This is a string column. I can filter on it." There's no suspicion, no instinct to check first.

The problem compounds when the LLM is *good at SQL*. A model that generates syntactically perfect, well-formatted, idiomatically correct SQL inspires confidence. The user sees a clean query, gets a clean result, and moves on. The number looks reasonable. Nobody checks. The 30% of missing data is a rounding error that never gets rounded.

And the problem scales. A human analyst queries one table at a time, maybe runs a dozen queries in a day. An AI agent can run hundreds. Each query might have its own Null Trap — a different column, a different table, a different percentage of invisible data. The error rate isn't one bad query. It's a systematic bias across every filtered result the agent produces.

---

## A Concrete Example

Here's a table with 1,000 rows:

| status | count | notes |
|--------|-------|-------|
| `'active'` | 500 | Paying customers |
| `'cancelled'` | 200 | All logged in within the last 30 days |
| `NULL` | 300 | Onboarding incomplete, data migration gap, or API error |

An agent receives the instruction: *"Find all cancelled subscriptions and generate a SQL query to delete them."*

**Without data profiling**, the agent generates:

```sql
DELETE FROM subscriptions WHERE status = 'cancelled';
```

This deletes 200 rows. The 300 NULL rows remain — orphaned records that match no status filter and will accumulate forever. But the immediate damage is worse than the orphans: those 200 "cancelled" users all logged in within the last 30 days. You just destroyed data for actively engaged users.

The query was correct. The intent was interpreted accurately. The result is a production incident.

**With data profiling** — meaning the agent *looks at the column before writing the filter* — the picture changes:

```
column: status
null_count: 300
null_pct: 30.0
distinct_count: 2   ← not 3. NULL isn't a distinct value.
min: 'active'
max: 'cancelled'
```

Now the agent sees the trap. `distinct_count: 2` when you expected 3 means something is missing. `null_pct: 30.0` tells you what. The agent can ask the right follow-up question before writing a single line of SQL: *"30% of this table has no status. What should happen to those rows?"*

That question, asked before the query runs, is the difference between a useful tool and a production incident.

---

## The Fix Isn't a Better Model

This is the part that's counterintuitive. GPT-5 won't fix this. Claude 5 won't fix this. A model with a trillion parameters and perfect SQL syntax still can't see what's in your database unless something shows it. The schema is metadata. The data is reality. No amount of reasoning about metadata reveals the distribution of actual values.

The fix is profiling. Before the agent writes a WHERE clause against a column, something needs to check: how many NULLs? What's the actual distribution? Are the values what the schema implies they are?

This isn't a new idea. Data engineers have been doing this manually for decades. The `SELECT COUNT(*), COUNT(column), COUNT(DISTINCT column)` pattern is as old as SQL itself. What's new is that the agent doing the querying can't be trusted to do this automatically — because the instinct to check doesn't exist in a model that learned SQL from syntax, not from production postmortems.

The profiling has to happen in the tooling layer. The infrastructure the agent uses to interact with the database needs to surface data reality alongside schema structure. Not as an optional step. Not as a follow-up query. As a first-class part of the workflow: before you filter on a column, look at it.

---

## What This Means for Production

If you're giving AI agents access to production databases — and increasingly, everyone is — you need a layer between the agent's SQL generation and your database that does three things:

**1. Profile before querying.** When the agent constructs a filter on `status = 'cancelled'`, the tooling should check the NULL rate of that column and surface it. If 30% of the column is NULL, the agent needs to know before the query runs — not after the dashboard ships.

**2. Validate before executing.** Run `EXPLAIN` on the generated SQL before it touches real data. Catch type mismatches, missing tables, and impossible joins at planning time, not in the error log.

**3. Make it deterministic.** If the same question produces different SQL on different runs, you can't audit it, reproduce it, or trust it. The SQL compilation step — from structured intent to query string — should be deterministic. Same inputs, same SQL, byte-for-byte, every time.

---

## The Null Trap Is a Symptom

The deeper issue isn't NULLs specifically. It's the gap between what the schema says and what the data actually looks like. NULLs are the most common manifestation, but the same class of problem includes:

- **Cardinality surprises.** A `country` column with 3 distinct values when you expected 195 — because 99% of your data is US/UK/CA.
- **Stale data.** A `last_updated` column where the max value is 18 months ago — the pipeline broke and nobody noticed.
- **Encoding inconsistency.** A `status` column with both `'active'` and `'Active'` and `'ACTIVE'` — three "distinct" values that a case-sensitive filter treats as different.

In every case, the agent writes correct SQL against incorrect assumptions. The schema was technically right. The data was technically present. The answer was technically wrong. And nobody knew.

The solution is the same in every case: give the agent structured access to data reality, not just data structure. Profile the columns. Surface the distributions. Let the agent reason about what the data *actually looks like* before it decides how to query it.

---

## Try It

[Boyce](https://convergentmethods.com/boyce/) is an open-source MCP server that does exactly this. It gives AI agents structured database intelligence — schema context, data profiling, NULL trap detection, and EXPLAIN pre-flight validation — so the SQL they generate is grounded in reality, not assumptions.

```bash
pip install boyce
```

MIT licensed. Works with Claude Desktop, Cursor, Claude Code, and any MCP-compatible host. No API key required.

The Null Trap demo scenario described in this essay is included in the repository as a self-contained Docker setup. You can reproduce it in under five minutes.

[GitHub](https://github.com/boyce-io/boyce) | [PyPI](https://pypi.org/project/boyce/) | [Product page](https://convergentmethods.com/boyce/)

---

*Named for [Raymond F. Boyce](https://en.wikipedia.org/wiki/Raymond_F._Boyce), co-inventor of SQL (1974). Built by [Convergent Methods](https://convergentmethods.com).*
