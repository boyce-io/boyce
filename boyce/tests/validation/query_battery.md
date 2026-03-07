# Boyce Validation Query Battery — Pagila Schema
**Used during Will's testing sprint, March 11-12, 2026.**

Database: Pagila (DVD rental store, 15 tables)
Connection: `postgresql://boyce:password@localhost:5433/pagila`

Key tables: `film`, `actor`, `film_actor`, `film_category`, `category`, `inventory`,
`store`, `staff`, `rental`, `payment`, `customer`, `address`, `city`, `country`, `language`

Key relationships:
- `rental` → `inventory` → `film` (what was rented)
- `rental` → `customer` (who rented)
- `payment` → `rental` → `customer` (revenue)
- `film` → `film_category` → `category` (genre)
- `customer` → `store` → `address` (location)
- `rental.return_date` is NULL for currently-checked-out items

---

## Category A — Structured Capability Tests

These test specific pipeline features. For each: run it, paste the SQL output into the log.

---

### A1 — Simple Aggregation
**What it tests:** Entity resolution, metric aggregation, temporal filter

**Prompt:**
```
Total rental revenue by customer for the last 90 days, top 10
```

**Expected SQL shape:**
```sql
SELECT c.customer_id, c.first_name || ' ' || c.last_name AS customer_name,
       SUM(p.amount) AS total_revenue
FROM customer c
JOIN payment p ON p.customer_id = c.customer_id
WHERE p.payment_date >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY c.customer_id, c.first_name, c.last_name
ORDER BY total_revenue DESC
LIMIT 10
```

**Pass criteria:** GROUP BY customer, SUM(amount), date filter present, LIMIT 10

**Log:**
```
SQL produced: [ paste here ]
Pass: [ YES / NO ]
Issues: _______________
```

---

### A2 — Multi-Join (Dijkstra Path Resolution)
**What it tests:** Semantic graph join-path selection across 3+ tables

**Prompt:**
```
Top 10 films by total rental count, with their category name
```

**Expected join path:** `film` → `film_category` → `category` (for genre) AND
`film` → `inventory` → `rental` (for counts)

**Expected SQL shape:**
```sql
SELECT f.title, cat.name AS category, COUNT(r.rental_id) AS rental_count
FROM film f
JOIN film_category fc ON fc.film_id = f.film_id
JOIN category cat ON cat.category_id = fc.category_id
JOIN inventory i ON i.film_id = f.film_id
JOIN rental r ON r.inventory_id = i.inventory_id
GROUP BY f.film_id, f.title, cat.name
ORDER BY rental_count DESC
LIMIT 10
```

**Pass criteria:** All 5 tables present, correct join keys, COUNT aggregation

**Log:**
```
SQL produced: [ paste here ]
Join path correct: [ YES / PARTIAL / NO ]
Issues: _______________
```

---

### A3 — NULL Trap Detection
**What it tests:** Safety layer fires on equality filter over NULL-containing column

`rental.return_date` is NULL for currently checked-out items (~5-8% of rows).

**Prompt:**
```
Show me all rentals where return_date is not null
```

Or alternatively:
```
Show customers who have returned their rentals
```

**Expected:** SQL is generated AND a `NULL_TRAP` warning appears in the response.

**Pass criteria:** Warning present in response. SQL still generated (warning doesn't block).

**Log:**
```
NULL_TRAP warning present: [ YES / NO ]
Warning message text: _______________
SQL still produced: [ YES / NO ]
```

---

### A4 — Schema Exploration (Non-SQL Intent)
**What it tests:** Intent routing — question about the schema, not a data query

**Prompt:**
```
What tables have financial data?
```

**Expected:** The response describes `payment`, `rental` (with rate), and possibly `film`
(replacement_cost, rental_rate) — no SQL generated, prose explanation.

**Alternate prompt (if first doesn't trigger intent routing):**
```
What fields are in the payment table?
```

**Pass criteria:** Returns schema description, NOT a SELECT statement

**Log:**
```
Response type: [ Schema description / SQL (wrong) / Error ]
Response useful: [ YES / SORT OF / NO ]
```

---

### A5 — Redshift Safety Lint
**What it tests:** Safety layer rewrites CONCAT() → `||` for Redshift dialect

**Prompt:**
```
Show customer full names and email addresses
```

**Setup:** Before asking, set dialect to `redshift` in the StructuredFilter if you're
using `build_sql` directly. For `ask_boyce`, set `BOYCE_DB_DIALECT=redshift` env var
or note the dialect in the question.

**Pass criteria:** SQL uses `first_name || ' ' || last_name`, NOT `CONCAT(first_name, ...)`

**Log:**
```
SQL uses || : [ YES / NO — used CONCAT instead ]
Any other Redshift issues flagged: _______________
```

---

## Category B — Real-World Conversational Prompts

These simulate what actual users type. Run on at least 2 surfaces.
Record verbatim what you typed and exactly what came back.

---

### Junior Data Analyst Persona
*(Limited SQL knowledge, conversational, vague)*

**B1.**
```
what are the finance tables?
```
Expected: prose description of payment, rental (financial fields), not SQL
```
Response: _______________
Useful: [ YES / SORT OF / NO ]
```

**B2.**
```
show me top customers
```
Expected: planner picks a metric (revenue or rentals), asks for clarification OR makes sensible assumption
```
Metric chosen: [ revenue / rental count / asked me / other: ___ ]
SQL correct: [ YES / NO ]
Response: _______________
```

**B3.**
```
monthly trend report
```
Expected: planner picks a metric, groups by month — should either ask "trend of what?" or make a reasonable assumption
```
What metric was chosen: _______________
Time grain correct (monthly): [ YES / NO ]
Response: _______________
```

**B4.**
```
how many films do we have?
```
Expected: `SELECT COUNT(*) FROM film` — simple, should be perfect
```
SQL: _______________
Correct: [ YES / NO ]
```

---

### Staff Data Engineer Persona
*(Domain-specific, complex, assumes context)*

**B5.**
```
how did rental patterns change across store locations over the past year?
```
Expected: joins `rental` → `inventory` → `store`, groups by `store_id` and month,
counts rentals, filters `rental_date >= now() - interval '1 year'`
```
Join path: _______________
Temporal grouping: [ correct / missing / wrong grain ]
SQL: _______________
```

**B6.**
```
what's the average rental duration by film category?
```
Expected: joins `rental` → `inventory` → `film` → `film_category` → `category`,
computes `AVG(return_date - rental_date)`, groups by `category.name`
```
Handles NULL return_date: [ YES — excluded or warned / NO — included nulls ]
SQL: _______________
```

**B7.**
```
which films have never been rented?
```
Expected: LEFT JOIN `film` → `inventory` → `rental`, WHERE `rental.rental_id IS NULL`
```
Uses LEFT JOIN anti-pattern: [ YES / NO ]
SQL: _______________
```

---

### Non-Technical Stakeholder Persona
*(Pure business language, no SQL knowledge)*

**B8.**
```
are we losing customers?
```
Expected: planner interprets as churn/retention — maybe customers who rented in
prior period but not recently. May ask for clarification. Should NOT crash.
```
Response type: [ Clarifying question / SQL attempt / Error ]
If SQL: metric chosen: _______________
Graceful: [ YES / NO ]
```

**B9.**
```
what's our best category?
```
Expected: "best" is ambiguous — planner should either ask "best by revenue or rentals?"
or make an assumption and state it
```
Assumption stated: [ YES / NO ]
Metric: _______________
SQL: _______________
```

**B10.**
```
compare this month to last month
```
Expected: some period-over-period query — picks a metric (revenue most likely),
groups by current month vs prior month
```
Metric chosen: _______________
Both periods in query: [ YES / NO ]
SQL: _______________
```

---

## Scoring Guide

After running the battery, tally:

| Category | Queries | Passed | Notes |
|----------|---------|--------|-------|
| A — Capability | 5 | ___ | |
| B — Conversational | 10 | ___ | |
| **Total** | **15** | ___ | |

**Version decision thresholds:**
- 14-15 pass → strong v1.0 candidate
- 11-13 pass → v1.0 with documented limitations, or 0.9.0
- 8-10 pass → planner needs work, 0.1.x iteration
- <8 pass → hold publish, diagnose planner

**Most important single test:** A3 (NULL trap). If the safety layer doesn't fire,
that is a blocker regardless of other scores.
