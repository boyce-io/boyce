-- Airflow DAG: analytics_warehouse_etl
-- Task: load_dim_dates
-- Schedule: monthly (first day)

CREATE TABLE IF NOT EXISTS analytics.dim_dates (
    date_key            INT          NOT NULL,
    full_date           DATE         NOT NULL,
    day_of_week         SMALLINT     NOT NULL,
    day_name            VARCHAR(10)  NOT NULL,
    day_of_month        SMALLINT     NOT NULL,
    day_of_year         SMALLINT     NOT NULL,
    week_of_year        SMALLINT     NOT NULL,
    month_number        SMALLINT     NOT NULL,
    month_name          VARCHAR(10)  NOT NULL,
    quarter             SMALLINT     NOT NULL,
    year                SMALLINT     NOT NULL,
    is_weekend          BOOLEAN      NOT NULL,
    is_holiday          BOOLEAN      DEFAULT FALSE,
    fiscal_quarter      SMALLINT,
    fiscal_year         SMALLINT,
    PRIMARY KEY (date_key)
);
