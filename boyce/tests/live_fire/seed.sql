-- seed.sql — Live Fire test fixture
-- Creates the `agents` table and inserts three rows.
-- Run idempotently: truncates before inserting.

CREATE TABLE IF NOT EXISTS agents (
    id          SERIAL       PRIMARY KEY,
    codename    VARCHAR(50)  NOT NULL,
    status      VARCHAR(20)  NOT NULL,
    kill_count  INTEGER      NOT NULL DEFAULT 0
);

TRUNCATE agents RESTART IDENTITY;

INSERT INTO agents (codename, status, kill_count) VALUES
    ('007',    'Active',   50),
    ('Vesper', 'Inactive',  3),
    ('Nomi',   'Active',   17);
