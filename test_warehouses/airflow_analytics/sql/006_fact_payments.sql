-- Airflow DAG: analytics_warehouse_etl
-- Task: load_fact_payments
-- Schedule: daily @ 08:00 UTC

CREATE TABLE IF NOT EXISTS analytics.fact_payments (
    payment_key         BIGINT       NOT NULL,
    order_key           BIGINT       REFERENCES analytics.fact_orders(order_key),
    customer_key        BIGINT       REFERENCES analytics.dim_customers(customer_key),
    payment_date_key    INT          REFERENCES analytics.dim_dates(date_key),
    payment_method      VARCHAR(50)  NOT NULL,
    amount              DECIMAL(12,2) NOT NULL,
    currency            VARCHAR(3)   DEFAULT 'USD',
    status              VARCHAR(30),
    reference_id        VARCHAR(100),
    created_at          TIMESTAMP    DEFAULT GETDATE(),
    PRIMARY KEY (payment_key)
);
