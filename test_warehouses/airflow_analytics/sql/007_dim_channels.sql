-- Airflow DAG: analytics_warehouse_etl
-- Task: load_dim_channels
-- Schedule: weekly (Monday)

CREATE TABLE IF NOT EXISTS analytics.dim_channels (
    channel_key         BIGINT       NOT NULL,
    channel_id          VARCHAR(50)  NOT NULL,
    channel_name        VARCHAR(100) NOT NULL,
    channel_type        VARCHAR(50),
    medium              VARCHAR(50),
    source              VARCHAR(100),
    is_paid             BOOLEAN      DEFAULT FALSE,
    cost_per_click      DECIMAL(8,4),
    created_at          TIMESTAMP    DEFAULT GETDATE(),
    PRIMARY KEY (channel_key)
);
