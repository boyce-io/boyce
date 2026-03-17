-- Airflow DAG: analytics_warehouse_etl
-- Task: load_fact_order_items
-- Schedule: daily @ 07:30 UTC (after fact_orders)

CREATE TABLE IF NOT EXISTS analytics.fact_order_items (
    order_item_key      BIGINT       NOT NULL,
    order_key           BIGINT       REFERENCES analytics.fact_orders(order_key),
    product_key         BIGINT       REFERENCES analytics.dim_products(product_key),
    quantity            INT          NOT NULL,
    unit_price          DECIMAL(10,2) NOT NULL,
    discount_pct        DECIMAL(5,2)  DEFAULT 0,
    line_total          DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_item_key)
);
