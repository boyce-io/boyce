# Your AI Agent's SQL Is Correct. The Answer Is Still Wrong.

*How NULL distributions silently corrupt agentic database workflows — and why the fix isn't a better model.*

---

You ask your AI agent a simple question: *"How many cancelled subscriptions do we have?"*

The agent connects to your database. It reads the schema. It writes SQL:

```sql
SELECT COUNT(*) FROM subscriptions WHERE status = 'cancelled';
```

The SQL is syntactically perfect. The agent is confident. The query returns **200**.

The real answer might be as high as 500. You'll never know, because 30% of your table has `status = NULL` — and every one of those rows was silently excluded. The agent didn't lie to you. It didn't hallucinate. It generated correct SQL against an incomplete picture of reality, and the database did exactly what it was asked. The rows with no status weren't counted as cancelled. They also weren't counted as *not* cancelled. They simply didn't exist as far as the query was concerned.

This is the **Null Trap**. It's one of the many bits of embedded knowledge in the daily workflow of a data engineer, data scientist, or data analyst. What's changed is that AI agents now run hundreds of queries a day against your data, autonomously, with no human reviewing the results. A senior engineer gets a number back and thinks "let me sanity check that." An agent gets a number back and puts it in your dashboard. The Null Trap went from an occasional human mistake to a systematic bias across every filtered result an agent produces.

---

## Why NULLs Are Different From Wrong Values

Most data quality conversations focus on *wrong* data — a misspelled city name, a negative price, a date in the future. Wrong data is visible. It shows up in results. Someone eventually notices.

NULLs are invisible. SQL's three-valued logic guarantees it.

`WHERE status = 'cancelled'` — in most programming languages, if `status` is null, this evaluates to false. In SQL, it evaluates to **UNKNOWN**. A third truth value that is neither true nor false. Rows where the predicate evaluates to UNKNOWN are excluded from the result set. Not flagged. Not warned about. Excluded.

| Query | What you think it returns | What it actually returns |
|-------|--------------------------|------------------------|
| `WHERE status = 'cancelled'` | All cancelled rows | Only rows where status is *literally* the string 'cancelled' |
| `WHERE status != 'cancelled'` | All non-cancelled rows | Only rows where status is a *non-null string* that isn't 'cancelled' |
| `WHERE status = 'cancelled' OR status != 'cancelled'` | All rows | Only rows where status is not NULL |

That last one. `x = 'a' OR x != 'a'` should be a tautology. In SQL, it isn't. The 300 rows where `status` is NULL satisfy neither condition. They fall through every filter you write.

A senior data engineer knows this. They've been burned by it. They habitually write `AND status IS NOT NULL` or `COALESCE(status, 'unknown')`. But the reason they know is because they shipped a wrong number, noticed it a week later, and traced it back to a nullable column.

An AI agent has no such scars.

---

## Why LLMs Make This Worse

An LLM generating SQL works from the schema. The schema says `status VARCHAR(20)`. It doesn't say "30% of this column is NULL and those rows represent users stuck in an incomplete onboarding flow." The schema describes structure. It says nothing about the *distribution* of actual data.

An experienced human looks at a `VARCHAR` column and thinks: "Is this nullable? How many NULLs does it actually have? What do those NULLs *mean*?" An LLM looks at the same column and thinks: "This is a string column. I can filter on it."

The problem compounds when the LLM is *good at SQL*. A model that generates syntactically perfect, well-formatted, idiomatically correct SQL inspires confidence. The user sees a clean query, gets a clean result, and moves on. The number looks reasonable. Nobody checks.

---

## A Concrete Example

Here's a table with 1,000 rows:

| status | count | notes |
|--------|-------|-------|
| `'active'` | 500 | Paying customers |
| `'cancelled'` | 200 | Explicitly cancelled |
| `NULL` | 300 | Onboarding incomplete, data migration gap, or API error |

An agent receives the question: *"How many cancelled subscriptions do we have?"*

**Without data profiling**, the agent generates:

```sql
SELECT COUNT(*) FROM subscriptions WHERE status = 'cancelled';
```

Returns 200. Clean number. Looks right. Except 300 rows — 30% of the table — were invisible to the query. Some of those NULLs might be cancelled users whose status never got written. Some might be active users stuck in a broken onboarding flow. The agent can't distinguish and didn't try. It answered a question about your data while ignoring almost a third of it.

**With data profiling** — meaning the agent *looks at the column before writing the filter* — the picture changes:

```
column: status
null_count: 300
null_pct: 30.0
distinct_count: 2   ← not 3. NULL isn't a distinct value.
min: 'active'
max: 'cancelled'
```

Now the agent sees the trap. `distinct_count: 2` when you expected 3 means something is missing. `null_pct: 30.0` tells you what. The agent asks the right follow-up question before writing a single line of SQL: *"30% of this table has no status. Should those rows be included in the count?"*

Asking this question **before** the query runs is the difference between a useful tool and a wrong answer that nobody catches.

---

## The Fix Isn't a Better Model

The next GPT Codex won't fix this. The next Claude Opus won't fix this. Smarter models can reason better about what data they see, but a model can't see what the infrastructure doesn't show it. The schema is metadata. The data is reality. No amount of reasoning about metadata reveals the distribution of actual values.

The fix is profiling. Before the agent writes a `WHERE` clause against a column, something needs to check questions like:

- How many NULLs are in this column?
- What's the actual distribution?
- Are the values actually what the schema implies they are?

Data engineers have been doing this manually for decades. `SELECT COUNT(*), COUNT(column), COUNT(DISTINCT column)` is as old as SQL itself. What's new is that the agent doing the querying doesn't have the instinct to check — because it learned SQL from syntax, not from production postmortems.

The profiling has to happen in the tooling layer. Not as an optional step. Not as a follow-up query the model might or might not think to run. As infrastructure: before you filter on a column, look at it.

---

## What This Means for Production

If you're giving AI agents access to production databases — and increasingly, everyone is — you need a layer between the agent and your data that does three things:

**1. Profile before querying.** When the agent constructs a filter on `status = 'cancelled'`, the tooling checks the NULL rate of that column and surfaces it. If 30% of the column is NULL, the agent knows before the query runs — not after the dashboard ships.

**2. Validate before executing.** Run `EXPLAIN` on the generated SQL before it touches real data. Catch type mismatches, missing tables, and impossible joins at planning time, not in the error log.

**3. Make it deterministic.** If the same question produces different SQL on different runs, you can't audit it, reproduce it, or trust it. The SQL compilation step — from structured intent to query string — should be deterministic. Same inputs, same SQL, every time.

---

## NULLs Are the Most Common Trap. They're Not the Only One.

The deeper issue is the gap between what the schema says and what the data actually looks like. NULLs are the most common case, but the same structural problem shows up as cardinality surprises (a `country` column with 3 distinct values when you expected 195), stale data (a `last_updated` max of 18 months ago because the pipeline broke), and encoding drift (`'active'` vs `'Active'` vs `'ACTIVE'` — three values a case-sensitive filter treats as different).

Same pattern every time: correct SQL, incorrect assumptions, wrong answer. Nobody knew.

---

## Try It

[Boyce](https://convergentmethods.com/boyce/) is an open-source MCP server that sits between your AI agent and your database. When an agent asks to query a table, Boyce profiles the relevant columns first — NULL rates, distinct values, distributions — and hands that context to the agent alongside the schema. The agent sees the trap before it writes the query, not after.

Here's what that looks like in practice. Agent asks *"how many cancelled subscriptions?"* — Boyce profiles the `status` column, surfaces the 30% NULL rate, and the agent asks you what to do about it before generating SQL. No wrong answer ships. No silent exclusion.

```bash
pip install boyce
```

MIT licensed. Works with Claude Desktop, Cursor, Claude Code, and any MCP-compatible host. No API key required.

The Null Trap scenario from this essay is included in the repo as a self-contained Docker setup. Reproduce it in under five minutes.

[GitHub](https://github.com/boyce-io/boyce) | [PyPI](https://pypi.org/project/boyce/) | [Product page](https://convergentmethods.com/boyce/)

---

*Named for [Raymond F. Boyce](https://en.wikipedia.org/wiki/Raymond_F._Boyce), co-inventor of SQL (1974). Built by [Convergent Methods](https://convergentmethods.com).*
