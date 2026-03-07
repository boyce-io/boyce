#!/bin/bash
# Boyce validation environment setup
# Downloads Pagila SQL and starts the Docker database.
# Run once before your first testing session.
#
# Usage:
#   cd boyce/tests/validation/
#   ./setup.sh
#
# After setup:
#   docker compose up -d          # start (subsequent sessions)
#   docker compose down           # stop
#   docker compose down -v        # stop + wipe data (force re-seed)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INIT_DIR="$SCRIPT_DIR/init"

echo "Boyce validation setup"
echo "======================"

# --- Download Pagila SQL files if not already present ---

PAGILA_BASE="https://raw.githubusercontent.com/devrimgunduz/pagila/master"

if [[ ! -f "$INIT_DIR/01_pagila_schema.sql" ]]; then
    echo "Downloading Pagila schema..."
    curl -fsSL "$PAGILA_BASE/pagila-schema.sql" -o "$INIT_DIR/01_pagila_schema.sql"
    echo "  OK: 01_pagila_schema.sql"
else
    echo "  Skipped: 01_pagila_schema.sql already present"
fi

if [[ ! -f "$INIT_DIR/02_pagila_data.sql" ]]; then
    echo "Downloading Pagila data..."
    curl -fsSL "$PAGILA_BASE/pagila-data.sql" -o "$INIT_DIR/02_pagila_data.sql"
    echo "  OK: 02_pagila_data.sql"
else
    echo "  Skipped: 02_pagila_data.sql already present"
fi

# --- Start Docker ---

echo ""
echo "Starting Pagila database..."
cd "$SCRIPT_DIR"
docker compose up -d

echo ""
echo "Waiting for Postgres to be ready..."
for i in $(seq 1 30); do
    if docker compose exec pagila pg_isready -U boyce -d pagila -q 2>/dev/null; then
        echo "  Ready."
        break
    fi
    sleep 1
done

echo ""
echo "Connection string:"
echo "  postgresql://boyce:password@localhost:5433/pagila"
echo ""
echo "To stop:     docker compose down"
echo "To wipe:     docker compose down -v  (re-runs seed on next start)"
echo "To connect:  psql postgresql://boyce:password@localhost:5433/pagila"
