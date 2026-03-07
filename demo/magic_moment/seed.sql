-- seed.sql — Magic Moment Demo
-- Creates the `subscriptions` table and inserts exactly 1,000 rows.
--
-- ┌─────────────────────────────────────────────────────────────────────┐
-- │  THE TRAP                                                           │
-- │                                                                     │
-- │  Row distribution (deterministic):                                  │
-- │    status = 'active'    :  500 rows  (50%)                         │
-- │    status = 'cancelled' :  200 rows  (20%)  ← RECENT last_login    │
-- │    status = NULL        :  300 rows  (30%)  ← INVISIBLE to naive   │
-- │                                               WHERE status = '...' │
-- │                                                                     │
-- │  The trap has two jaws:                                             │
-- │   1. NULL Trap  — 300 rows are invisible to                        │
-- │                   DELETE WHERE status = 'cancelled'                 │
-- │                   (or 'active'). They are silently skipped.         │
-- │   2. Active Trap — all 200 'cancelled' rows have last_login in      │
-- │                    the last 30 days. Deleting them destroys         │
-- │                    users who are actively engaged.                  │
-- └─────────────────────────────────────────────────────────────────────┘

CREATE TABLE IF NOT EXISTS subscriptions (
    id          SERIAL       PRIMARY KEY,
    user_id     INTEGER      NOT NULL,
    status      VARCHAR(20),                    -- intentionally nullable: The Trap
    last_login  TIMESTAMP
);

TRUNCATE subscriptions RESTART IDENTITY;

-- ── Segment 1: 500 'active' users ────────────────────────────────────
-- last_login spread randomly across the past 365 days.
INSERT INTO subscriptions (user_id, status, last_login)
SELECT
    gs.n                                                   AS user_id,
    'active'                                               AS status,
    NOW() - (gs.n % 365 || ' days')::INTERVAL             AS last_login
FROM generate_series(1, 500) gs(n);

-- ── Segment 2: 200 'cancelled' users  ← THE ACTIVE TRAP ─────────────
-- These users cancelled their subscription but have logged in within
-- the past 30 days. A naive DELETE would destroy actively-engaged users.
-- last_login cycles through 1–30 days ago to give realistic spread.
INSERT INTO subscriptions (user_id, status, last_login)
SELECT
    500 + gs.n                                             AS user_id,
    'cancelled'                                            AS status,
    NOW() - ((gs.n % 30) + 1 || ' days')::INTERVAL        AS last_login
FROM generate_series(1, 200) gs(n);

-- ── Segment 3: 300 NULL status users  ← THE NULL TRAP ───────────────
-- These users exist in the system but have no status set (onboarding,
-- data migration gap, or API error). They are silently skipped by any
-- WHERE status = '...' predicate — including cancellation cleanup jobs.
-- last_login spread across the past 180 days.
INSERT INTO subscriptions (user_id, status, last_login)
SELECT
    700 + gs.n                                             AS user_id,
    NULL                                                   AS status,
    NOW() - ((gs.n % 180) + 1 || ' days')::INTERVAL       AS last_login
FROM generate_series(1, 300) gs(n);
