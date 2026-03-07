#!/usr/bin/env bash
# Boyce — Quickstart
# Gets the MCP server installed and ready to paste into Claude Desktop or Cursor.
#
# Usage:
#   ./quickstart.sh
#   ./quickstart.sh --postgres    # also install asyncpg for live DB adapter

set -euo pipefail

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}  ✓${RESET}  $*"; }
info() { echo -e "${CYAN}  →${RESET}  $*"; }
warn() { echo -e "${YELLOW}  ⚠${RESET}  $*"; }
die()  { echo -e "${RED}  ✗  $*${RESET}" >&2; exit 1; }
header() { echo -e "\n${BOLD}$*${RESET}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POSTGRES_EXTRA=0
[[ "${1:-}" == "--postgres" ]] && POSTGRES_EXTRA=1

# ---------------------------------------------------------------------------
# Step 1 — Detect installer: uv preferred, then pip/python3
# ---------------------------------------------------------------------------
header "Step 1/4 — Checking installer"

INSTALL_CMD=""
PYTHON_CMD=""

if command -v uv &>/dev/null; then
    ok "Found uv $(uv --version 2>/dev/null | head -1)"
    INSTALL_CMD="uv pip install"
    # Resolve the python uv would use
    PYTHON_CMD="$(uv run python -c 'import sys; print(sys.executable)' 2>/dev/null || echo 'uv run python')"
else
    # Find a Python 3.10+ binary: prefer active venv, then local .venv, then
    # versioned system binaries (3.13 → 3.10), then the bare python3.
    _find_python() {
        local candidates=(
            "${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python3}"
            "$SCRIPT_DIR/.venv/bin/python3"
            python3.13 python3.12 python3.11 python3.10
            python3
        )
        for c in "${candidates[@]}"; do
            [[ -z "$c" ]] && continue
            if command -v "$c" &>/dev/null || [[ -x "$c" ]]; then
                local v
                v="$("$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" || continue
                local maj="${v%%.*}" min="${v#*.}"
                if [[ "$maj" -gt 3 ]] || [[ "$maj" -eq 3 && "$min" -ge 10 ]]; then
                    echo "$c"; return 0
                fi
            fi
        done
        return 1
    }

    PYTHON_CMD="$(_find_python)" || die "Python 3.10+ not found. Install uv (https://docs.astral.sh/uv/) or Python 3.10+."
    PY_VER="$($PYTHON_CMD -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    ok "Found Python $PY_VER at $PYTHON_CMD"
    INSTALL_CMD="$PYTHON_CMD -m pip install"
fi

# ---------------------------------------------------------------------------
# Step 2 — Write .env template (skip if file already exists)
# ---------------------------------------------------------------------------
header "Step 2/4 — Environment file"

ENV_FILE="$SCRIPT_DIR/.env"
ENV_TEMPLATE="$SCRIPT_DIR/.env.boyce"

cat > "$ENV_TEMPLATE" <<'EOF'
# Boyce — environment variables
# Copy this block into your MCP host config or source it before running the server.

# ── LLM Provider (required for ask_boyce) ──────────────────────────────
# Provider name understood by LiteLLM: "anthropic", "openai", "ollama", etc.
BOYCE_PROVIDER=anthropic
# Model ID as LiteLLM expects it (prefix not needed for major providers)
BOYCE_MODEL=claude-sonnet-4-6

# ── LLM Credentials — set whichever matches your provider ──────────────────
ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE
# OPENAI_API_KEY=sk-YOUR_KEY_HERE
# LITELLM_API_KEY=YOUR_KEY_HERE

# ── Live Database (optional) ───────────────────────────────────────────────
# asyncpg DSN — enables query_database, profile_data, and EXPLAIN pre-flight.
# Leave blank to run in schema-only mode (SQL generation still works).
# BOYCE_DB_URL=postgresql://user:pass@host:5432/mydb
# BOYCE_DB_URL=postgresql://user:pass@your-cluster.region.redshift.amazonaws.com:5439/mydb

# ── Tuning ─────────────────────────────────────────────────────────────────
# BOYCE_STATEMENT_TIMEOUT_MS=30000
EOF

ok "Template written → $ENV_TEMPLATE"

if [[ -f "$ENV_FILE" ]]; then
    warn ".env already exists — not overwriting. Review $ENV_TEMPLATE and merge manually."
else
    cp "$ENV_TEMPLATE" "$ENV_FILE"
    ok ".env created. Fill in your API key before connecting a host."
fi

# ---------------------------------------------------------------------------
# Step 3 — Install boyce
# ---------------------------------------------------------------------------
header "Step 3/4 — Installing boyce"

PROTO_DIR="$SCRIPT_DIR/boyce"
[[ -d "$PROTO_DIR" ]] || die "boyce/ directory not found at $PROTO_DIR"

if [[ "$POSTGRES_EXTRA" -eq 1 ]]; then
    info "Installing with [postgres] extra (asyncpg)"
    $INSTALL_CMD -e "$PROTO_DIR[postgres]"
else
    $INSTALL_CMD -e "$PROTO_DIR"
fi
ok "Package installed"

# ---------------------------------------------------------------------------
# Step 4 — Connection check (import + unit tests, no DB required)
# ---------------------------------------------------------------------------
header "Step 4/4 — Connection check"

info "Running verify_eyes.py (15 unit tests, ~4 seconds)..."

if $PYTHON_CMD "$PROTO_DIR/tests/verify_eyes.py" 2>&1; then
    ok "All checks passed"
else
    die "verify_eyes.py reported failures — check the output above."
fi

# ---------------------------------------------------------------------------
# Done — print MCP host config blocks
# ---------------------------------------------------------------------------
# Prefer the entry point we just installed (venv > system PATH > bare name)
_VENV_CMD="$SCRIPT_DIR/.venv/bin/boyce"
if [[ -x "$_VENV_CMD" ]]; then
    SERVER_CMD="$_VENV_CMD"
else
    SERVER_CMD="$(command -v boyce 2>/dev/null || echo 'boyce')"
fi

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}${BOLD}  Boyce is ready.${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  Edit ${CYAN}.env${RESET} to set your API key and (optionally) BOYCE_DB_URL."
echo ""
echo -e "${BOLD}  ── Claude Desktop ──────────────────────────────────────────────${RESET}"
echo -e "  ${CYAN}~/Library/Application Support/Claude/claude_desktop_config.json${RESET}"
echo ""
cat <<CLAUDEEOF
  {
    "mcpServers": {
      "boyce": {
        "command": "$SERVER_CMD",
        "env": {
          "BOYCE_PROVIDER": "anthropic",
          "BOYCE_MODEL": "claude-sonnet-4-6",
          "ANTHROPIC_API_KEY": "sk-ant-YOUR_KEY_HERE"
        }
      }
    }
  }
CLAUDEEOF
echo ""
echo -e "${BOLD}  ── Cursor (.cursor/mcp.json) ───────────────────────────────────${RESET}"
echo ""
cat <<CURSOREOF
  {
    "mcpServers": {
      "boyce": {
        "command": "$SERVER_CMD",
        "env": {
          "BOYCE_PROVIDER": "openai",
          "BOYCE_MODEL": "gpt-4o",
          "OPENAI_API_KEY": "sk-YOUR_KEY_HERE"
        }
      }
    }
  }
CURSOREOF
echo ""
echo -e "  Add ${CYAN}\"BOYCE_DB_URL\": \"postgresql://user:pass@host:5432/db\"${RESET}"
echo -e "  to either config block to enable live query and EXPLAIN validation."
echo ""
echo -e "  ${CYAN}Docs:${RESET} README.md"
echo -e "  ${CYAN}Tests:${RESET} python boyce/tests/verify_eyes.py"
echo ""
