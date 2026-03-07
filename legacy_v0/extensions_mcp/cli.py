from __future__ import annotations

import sys
from pathlib import Path

MCP_SRC = Path(__file__).resolve().parent / "src"
if str(MCP_SRC) not in sys.path:
    sys.path.insert(0, str(MCP_SRC))

from datashark_mcp.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
