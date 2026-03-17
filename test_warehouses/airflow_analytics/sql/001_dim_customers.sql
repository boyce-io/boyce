-- Airflow DAG: analytics_warehouse_etl
-- Task: load_dim_customers
-- Schedule: daily @ 06:00 UTC

CREATE TABLE IF NOT EXISTS analytics.dim_customers (
    customer_key        BIGINT       NOT NULL,
    customer_id         VARCHAR(50)  NOT NULL,
    first_name          VARCHAR(100),
    last_name           VARCHAR(100),
    email               VARCHAR(255),
    phone               VARCHAR(50),
    city                VARCHAR(100),
    state               VARCHAR(50),
    country             VARCHAR(100),
    signup_date         DATE,
    customer_segment    VARCHAR(50),
    lifetime_value      DECIMAL(12,2),
    is_active           BOOLEAN      DEFAULT TRUE,
    created_at          TIMESTAMP    DEFAULT GETDATE(),
    updated_at          TIMESTAMP    DEFAULT GETDATE(),
    PRIMARY KEY (customer_key)
);
