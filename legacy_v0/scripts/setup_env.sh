#!/bin/bash
# Phase 1 Ground Truth Environment Setup
# Sets up local database with public 'thelook_ecommerce' dataset

set -e

echo "🔧 Setting up Phase 1 Ground Truth Environment..."

# Check for macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "⚠️  Warning: This script is designed for macOS"
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is required but not installed"
    exit 1
fi

# Check for Homebrew (common on macOS)
if ! command -v brew &> /dev/null; then
    echo "⚠️  Warning: Homebrew not found. You may need to install PostgreSQL or DuckDB manually"
    echo "   Install Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
fi

# Choose database: Postgres (default) or DuckDB
DB_TYPE="${1:-postgres}"

if [ "$DB_TYPE" = "postgres" ]; then
    echo "📦 Setting up PostgreSQL..."
    
    # Check if PostgreSQL is installed
    if ! command -v psql &> /dev/null; then
        echo "📥 Installing PostgreSQL via Homebrew..."
        brew install postgresql@14 || brew install postgresql
        brew services start postgresql@14 || brew services start postgresql
    fi
    
    # Create database
    DB_NAME="thelook_ecommerce"
    echo "🗄️  Creating database: $DB_NAME"
    
    # Check if database exists
    if psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
        echo "   Database $DB_NAME already exists"
    else
        createdb "$DB_NAME" || echo "   Note: Database creation may require manual setup"
    fi
    
    echo "✅ PostgreSQL setup complete"
    echo "   Database: $DB_NAME"
    echo "   Connection: psql -d $DB_NAME"
    echo ""
    echo "📥 Next steps:"
    echo "   1. Download thelook_ecommerce dataset schema and data"
    echo "   2. Import schema: psql -d $DB_NAME < thelook_schema.sql"
    echo "   3. Import data: psql -d $DB_NAME < thelook_data.sql"
    echo ""
    echo "   Dataset source: https://console.cloud.google.com/marketplace/product/bigquery-public-data/thelook-ecommerce"
    
elif [ "$DB_TYPE" = "duckdb" ]; then
    echo "📦 Setting up DuckDB..."
    
    # Create virtual environment if it doesn't exist
    if [ ! -d ".venv" ]; then
        echo "🐍 Creating Python virtual environment..."
        python3 -m venv .venv
    fi
    
    source .venv/bin/activate
    
    # Install DuckDB
    echo "📥 Installing DuckDB Python package..."
    pip install -q duckdb
    
    # Create database file
    DB_FILE="data/thelook_ecommerce.duckdb"
    mkdir -p data
    
    echo "🗄️  Creating DuckDB database: $DB_FILE"
    python3 << EOF
import duckdb
conn = duckdb.connect('$DB_FILE')
print("✅ DuckDB database created at $DB_FILE")
conn.close()
EOF
    
    echo "✅ DuckDB setup complete"
    echo "   Database file: $DB_FILE"
    echo ""
    echo "📥 Next steps:"
    echo "   1. Download thelook_ecommerce dataset"
    echo "   2. Import using DuckDB Python API or SQL"
    echo ""
    echo "   Dataset source: https://console.cloud.google.com/marketplace/product/bigquery-public-data/thelook-ecommerce"
    
else
    echo "❌ Error: Unknown database type: $DB_TYPE"
    echo "   Supported: postgres, duckdb"
    exit 1
fi

echo ""
echo "🎯 Phase 1 Ground Truth Environment ready!"
echo "   Run: python3 tools/db_inspector.py to inspect the schema"


