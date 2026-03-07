#!/usr/bin/env bash
# Clone external test warehouse repos for parser validation.
# Run from the test_warehouses/ directory.
# Small fixtures (jaffle_shop, thelook_lookml, northwind_ddl, wide_world_importers_ddl)
# are committed directly — no setup needed.

set -euo pipefail
cd "$(dirname "$0")"

clone_or_update() {
    local name="$1"
    local url="$2"

    if [ -d "$name" ]; then
        echo "Updating $name..."
        git -C "$name" pull --ff-only 2>/dev/null || echo "  (pull failed, using existing checkout)"
    else
        echo "Cloning $name..."
        git clone --depth 1 "$url" "$name"
    fi
}

echo "=== Setting up test warehouses ==="
echo ""

clone_or_update "mattermost" "https://github.com/mattermost/mattermost-data-warehouse.git"
clone_or_update "dagster_platform" "https://github.com/dagster-io/dagster-open-platform.git"

echo ""
echo "=== Done ==="
echo "Committed fixtures (no setup needed):"
echo "  jaffle_shop/              — dbt project, 3 tables, seed CSVs"
echo "  jaffle_shop_duckdb/       — DuckDB variant of Jaffle Shop"
echo "  thelook_lookml/           — LookML views + explores, 5 entities, 6 joins"
echo "  northwind_ddl/            — Classic retail DDL (T-SQL, 14 tables)"
echo "  wide_world_importers_ddl/ — Star schema DW DDL (T-SQL, 17 tables)"
echo ""
echo "Cloned fixtures (git-ignored):"
echo "  mattermost/               — Enterprise dbt + Airflow (Snowflake)"
echo "  dagster_platform/         — SaaS analytics platform (Dagster + dbt)"
