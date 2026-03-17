-- Airflow DAG: analytics_warehouse_etl
-- Task: load_fact_sessions
-- Schedule: daily @ 09:00 UTC

CREATE TABLE IF NOT EXISTS analytics.fact_sessions (
    session_key         BIGINT       NOT NULL,
    session_id          VARCHAR(100) NOT NULL,
    customer_key        BIGINT       REFERENCES analytics.dim_customers(customer_key),
    channel_key         BIGINT       REFERENCES analytics.dim_channels(channel_key),
    session_date_key    INT          REFERENCES analytics.dim_dates(date_key),
    landing_page        VARCHAR(500),
    exit_page           VARCHAR(500),
    page_views          INT          DEFAULT 0,
    duration_seconds    INT,
    is_bounce           BOOLEAN      DEFAULT FALSE,
    converted           BOOLEAN      DEFAULT FALSE,
    device_type         VARCHAR(30),
    browser             VARCHAR(50),
    created_at          TIMESTAMP    DEFAULT GETDATE(),
    PRIMARY KEY (session_key)
);
