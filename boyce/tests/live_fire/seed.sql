-- seed.sql — Live Fire test fixture
-- Creates the `employees` table and inserts three rows.
-- Run idempotently: truncates before inserting.

CREATE TABLE IF NOT EXISTS employees (
    id                  SERIAL       PRIMARY KEY,
    name                VARCHAR(50)  NOT NULL,
    department          VARCHAR(50)  NOT NULL,
    status              VARCHAR(20)  NOT NULL,
    projects_completed  INTEGER      NOT NULL DEFAULT 0
);

TRUNCATE employees RESTART IDENTITY;

INSERT INTO employees (name, department, status, projects_completed) VALUES
    ('Alice',  'Engineering', 'Active',    12),
    ('Bob',    'Marketing',   'Inactive',   4),
    ('Carol',  'Engineering', 'Active',     8);
