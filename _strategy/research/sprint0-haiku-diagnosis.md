# Sprint 0 — Haiku Regression Root Cause

**Date:** 2026-03-28
**Model:** anthropic/claude-haiku-4-5-20251001
**Database:** Pagila (29 tables, 171 fields)
**Raw data:** `sprint0-diagnosis.json`

---

## Branch Determination: **A** — Fixable within existing architecture

The Haiku regression is caused by metric/dimension confusion in the planner
prompt, NOT by the StructuredFilter abstraction itself. Simplifying the
abstraction made scores worse (2.50), not better. The fix is localized to
prompt engineering and validation logic.

---

## Evidence

### Aggregate Comparison

| Metric | Full StructuredFilter (A) | Stripped (C) | Vanilla (B) |
|---|---|---|---|
| Row count accuracy | 92% | 25% | 100% |
| Top result accuracy | 67% | 42% | 92% |
| **Join correctness** | **83%** | **83%** | 92% |
| EXPLAIN verified | 100% | 100% | 100% |
| **Avg score (0-4)** | **3.42** | **2.50** | **3.83** |

**Branch B would predict:** Stripped > Full, approaching Vanilla.
**Actual result:** Stripped < Full. Stripped is the worst of all three modes.

### Why stripped scores lower

The stripped prompt removes metrics/dimensions/order_by/limit. Without
aggregation, all GROUP BY queries return flat row sets (Q01: 1000 rows instead
of 5). This tanks row_count and top_result scores. The stripped version
cannot express the query intent for 8 of 12 queries.

### The critical metric: join correctness

Join correctness measures entity selection — did the LLM pick the right
tables? This is the one dimension unaffected by the aggregation removal.

**Result: 83% for both Full and Stripped.** Identical.

Simplifying the prompt did NOT improve entity selection. The same entities
were chosen in both modes. Q03 picked the `sales_by_film_category` view
in both. Q06 selected all 4 correct tables in both. The entity selection
errors are not caused by StructuredFilter complexity.

### Per-query field selection comparison

The stripped prompt DID improve raw field selection — but this improvement
is invisible without aggregation to leverage it:

| Query | Full (A) field/metric error | Stripped (C) fields selected | Improvement? |
|---|---|---|---|
| Q02 | `customer_id` as dimension (missing names) | `customer_id, rental_id, first_name, last_name` | **Yes** — got names |
| Q03 | Used `sales_by_film_category` view | Same view | No |
| Q05 | `actor_id` as metric field (wrong COUNT) | `actor_id, first_name, last_name, film_id` | **Yes** — got film_id |
| Q06 | No dimensions (scalar COUNT) | `country, customer_id` | **Yes** — got country |

When Haiku is asked for flat "fields" it picks the right columns. When asked
to categorize them into metrics (what to aggregate) vs dimensions (what to
group by), it makes specific errors:
- Picks join keys as dimensions instead of display columns (Q02)
- Picks the wrong column for aggregation (Q05: `actor_id` vs `film_id`)
- Omits dimensions entirely for "by X" queries (Q06: no `country` dimension)

---

## Per-Query Detail

### Q02: Top 5 customers by total rentals (Full 3/4, Stripped 2/4, Vanilla 4/4)

**Full mode failure:** Haiku selected `customer_id` as the dimension and
`rental_id` with COUNT_DISTINCT as the metric. The SQL groups by `customer_id`
without selecting `first_name`/`last_name`. The top result check expects
`first_name: "ELEANOR"` — not found.

**Stripped mode:** Selected `customer_id, rental_id, first_name, last_name` as
fields. All the right columns are present. But without aggregation, returned
16,044 rows (one per rental) instead of 5 grouped rows.

**Diagnosis:** Haiku understands which columns are relevant. It fails when asked
to split them into "what to count" vs "what to display." This is a
metrics/dimensions prompt comprehension issue.

### Q03: Revenue by film category, top 5 (Full 3/4, Stripped 2/4, Vanilla 4/4)

**Both modes:** Selected `sales_by_film_category` (a Pagila view) instead of
the 5 base tables (category, film_category, inventory, rental, payment).

**Vanilla mode:** Correctly used base tables with a 5-table join chain.

**Diagnosis:** Entity selection error. Haiku prefers the shortcut view. This is
independent of StructuredFilter complexity — same choice in both modes. The view
exists in the schema context and Haiku takes the path of least resistance. This
is a prompt/context issue (the view shouldn't be presented, or should be
deprioritized).

### Q05: Actors in most films, top 5 (Full 3/4, Stripped 2/4, Vanilla 4/4)

**Full mode failure:** Haiku set `actor_id` as the metric field with
COUNT_DISTINCT. The resulting SQL: `COUNT(DISTINCT actor.actor_id)` — which is
always 1 per grouped actor. Should have been `COUNT(film_actor.film_id)`.

**Stripped mode:** Selected `actor_id, first_name, last_name, film_id`. Correct
fields including `film_id` (the column that should be counted).

**Vanilla mode:** Wrote `COUNT(fa.film_id) AS film_count`. Correct.

**Diagnosis:** Haiku correctly identifies `film_id` as the relevant column when
asked generically. When asked to construct a metric with `{name, field,
aggregation_type}`, it puts the grouping identifier (`actor_id`) in the metric
field slot instead of the counting target (`film_id`). This is a prompt/example
issue — the planner prompt needs clearer examples distinguishing "what to count"
from "what to count by."

### Q06: Countries with most customers, top 5 (Full 2/4, Stripped 2/4, Vanilla 4/4)

**Full mode failure:** Haiku selected all 4 correct entities and constructed the
join chain correctly. But produced zero dimensions — no `country` in GROUP BY.
The SQL is a scalar `COUNT(DISTINCT customer.customer_id)` returning 1 row.

**Stripped mode:** Selected `country, customer_id` as fields. Both correct.
Without aggregation, returned 599 flat rows (all customers with country).

**Vanilla mode:** Wrote `GROUP BY c.country ORDER BY customer_count DESC LIMIT 5`.

**Diagnosis:** Haiku understands the query involves `country` (selected it as a
field) but doesn't recognize it needs to be a dimension (GROUP BY target) in the
StructuredFilter. The "dimensions" concept is not well-enough illustrated in the
planner prompt for Haiku-class models. The model knows what it wants but can't
express it through the structured format.

---

## Root Cause Summary

The regression has three distinct causes, all within the planner layer:

1. **Metrics/dimensions confusion** (Q02, Q05, Q06): Haiku struggles to
   categorize columns into the right StructuredFilter slots. It picks good
   columns but puts them in wrong places — join keys as dimensions, grouping
   targets as metric fields, or omits dimensions entirely.

2. **View shortcutting** (Q03): Haiku selects convenience views over base
   tables. This is an entity selection issue in the schema context, not a
   StructuredFilter issue.

3. **Absent in vanilla:** All four regressions disappear when Haiku writes
   SQL directly, confirming the issue is in the translation to StructuredFilter,
   not in Haiku's SQL understanding.

---

## Recommended Fixes (for Sprint 3 or planner iteration)

These are observations, not Sprint 0 implementations:

1. **Prompt examples for metrics/dimensions:** Add 2-3 worked examples to the
   planner prompt showing the distinction: "When the query says 'by country',
   country is a dimension. When it says 'count of X', X is the metric field."

2. **Validation guardrail:** If `aggregation_required=True` and `dimensions=[]`,
   flag as suspicious. For "top N by X" queries, X should always appear as a
   dimension.

3. **View deprioritization:** Either exclude views from the schema context
   presented to the planner, or add a rule: "Prefer base tables over views."

4. **Adaptive complexity (Sprint 3 consideration):** Haiku-class models could
   receive a simpler prompt surface. The data shows Haiku picks better raw
   fields than structured metrics/dimensions. A two-pass approach — get fields
   first, then classify into metrics/dimensions — might help budget-tier models.

---

## Sprint continuation

**Branch A confirmed.** The sprint continues as planned. Sprint 1a (schema
extensions) and Sprint 2 (profiling engine) proceed unchanged. Sprint 3 should
consider the adaptive prompt complexity finding when designing the
classification loop for budget-tier models.
