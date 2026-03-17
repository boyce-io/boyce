-- Airflow DAG: analytics_warehouse_etl
-- Task: load_dim_products
-- Schedule: daily @ 06:00 UTC

CREATE TABLE IF NOT EXISTS analytics.dim_products (
    product_key         BIGINT       NOT NULL,
    product_id          VARCHAR(50)  NOT NULL,
    product_name        VARCHAR(255) NOT NULL,
    category            VARCHAR(100),
    subcategory         VARCHAR(100),
    brand               VARCHAR(100),
    unit_price          DECIMAL(10,2),
    unit_cost           DECIMAL(10,2),
    weight_kg           DECIMAL(8,3),
    is_discontinued     BOOLEAN      DEFAULT FALSE,
    supplier_id         VARCHAR(50),
    created_at          TIMESTAMP    DEFAULT GETDATE(),
    updated_at          TIMESTAMP    DEFAULT GETDATE(),
    PRIMARY KEY (product_key)
);
