"""
DataShark MCP CLI

Primary entrypoint for running the MCP server over stdio.
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="datashark", add_help=True)
    ap.add_argument(
        "--version",
        action="store_true",
        help="Print version information and exit.",
    )
    args = ap.parse_args(argv)

    if args.version:
        # Keep version reporting local and non-invasive.
        try:
            from datashark_mcp import __version__ as v  # type: ignore
        except Exception:
            v = "unknown"
        print(v)
        return 0

    # Default behavior: run MCP server (stdio JSON-RPC).
    from datashark.core.server import main as server_main

    server_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



