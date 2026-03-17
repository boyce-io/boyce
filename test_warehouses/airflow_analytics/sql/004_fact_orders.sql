-- Airflow DAG: analytics_warehouse_etl
-- Task: load_fact_orders
-- Schedule: daily @ 07:00 UTC (after dimensions)

CREATE TABLE IF NOT EXISTS analytics.fact_orders (
    order_key           BIGINT       NOT NULL,
    order_id            VARCHAR(50)  NOT NULL,
    customer_key        BIGINT       REFERENCES analytics.dim_customers(customer_key),
    order_date_key      INT          REFERENCES analytics.dim_dates(date_key),
    ship_date_key       INT          REFERENCES analytics.dim_dates(date_key),
    status              VARCHAR(30),
    shipping_method     VARCHAR(50),
    subtotal            DECIMAL(12,2),
    discount_amount     DECIMAL(10,2)  DEFAULT 0,
    tax_amount          DECIMAL(10,2)  DEFAULT 0,
    total_amount        DECIMAL(12,2),
    item_count          INT,
    created_at          TIMESTAMP    DEFAULT GETDATE(),
    PRIMARY KEY (order_key)
);
