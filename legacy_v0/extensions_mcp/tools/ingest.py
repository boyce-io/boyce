import sys
from pathlib import Path

# Ensure source-based execution works when called via subprocess without PYTHONPATH.
REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_SRC = Path(__file__).resolve().parents[1] / "src"
for p in (str(REPO_ROOT), str(MCP_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)
from datashark.core.tools import ingest

if __name__ == "__main__":
    sys.exit(ingest.main())


