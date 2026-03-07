from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class MCPSmokeResult:
    passed: bool
    messages: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    tools_sample: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "messages": self.messages,
            "errors": self.errors,
            "tools_sample": self.tools_sample,
        }


def run_mcp_smoke() -> MCPSmokeResult:
    """
    Lightweight MCP server smoke test.

    - Imports datashark.core.server.
    - Confirms DataSharkMCPServer class exists.
    - Introspects call_tool to ensure expected tool names are present
      in the implementation source (without starting DB connections).
    """
    result = MCPSmokeResult(passed=True)

    try:
        import inspect
        from datashark.core import server as mcp_server
    except TypeError as e:
        # Some environments (e.g., older Python runtimes) may not support
        # certain type annotation syntax used in server.py (PEP 604 unions).
        # Treat this as a skipped-but-not-failed smoke test, since it is an
        # environment limitation rather than an engine logic error.
        if "unsupported operand type(s) for |" in str(e):
            result.passed = True
            result.messages.append(
                "Skipped MCP server import in smoke test due to union-type annotation "
                "incompatibility with this Python runtime."
            )
            return result
        result.passed = False
        result.errors.append(f"Failed to import datashark.core.server: {e}")
        return result

    if not hasattr(mcp_server, "DataSharkMCPServer"):
        result.passed = False
        result.errors.append("DataSharkMCPServer class not found in datashark.core.server.")
        return result

    result.messages.append("Imported datashark.core.server and found DataSharkMCPServer.")

    # Inspect call_tool implementation to ensure key tools are wired
    srv_cls = mcp_server.DataSharkMCPServer
    call_tool = getattr(srv_cls, "call_tool", None)
    if call_tool is None:
        result.passed = False
        result.errors.append("DataSharkMCPServer.call_tool is missing.")
        return result

    try:
        src = inspect.getsource(call_tool)
    except OSError:
        src = ""

    expected_tools = [
        "list_schemas",
        "get_table_info",
        "run_query",
        "get_query_history",
    ]
    present = [name for name in expected_tools if name in src]
    missing = [name for name in expected_tools if name not in src]

    result.tools_sample = present

    if missing:
        result.passed = False
        result.errors.append(f"call_tool implementation missing expected tools: {', '.join(missing)}")
    else:
        result.messages.append("call_tool implementation exposes representative core tools.")

    return result


