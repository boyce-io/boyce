"""
Boyce HTTP API — REST interface for all MCP tools.

Exposes Boyce as a JSON REST API that any HTTP client can call:
VS Code extensions, web dashboards, scripts, cron jobs.

Endpoints:
    POST /schema       → get_schema
    POST /build-sql    → build_sql
    POST /ask          → ask_boyce
    POST /chat         → intent classification + routing
    POST /query        → query_database
    POST /profile      → profile_data
    POST /ingest       → ingest_source
    GET  /health       → {"status": "ok", "version": "..."}

Auth:
    Bearer token required on all endpoints except /health.
    Token source (first match wins):
        1. BOYCE_HTTP_TOKEN environment variable
        2. .boyce/config.json in the working directory
        3. Auto-generated on startup (printed to stderr, session-only)

Start:
    boyce serve --http --port 8741
    uvicorn boyce.http_api:app --port 8741  (if you pre-generate the app)
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any, Optional

try:
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    _STARLETTE_AVAILABLE = True
except ImportError:
    _STARLETTE_AVAILABLE = False

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(".boyce") / "config.json"


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------


def _load_or_create_token() -> str:
    """
    Resolve the bearer token for HTTP API auth.

    Order of precedence:
    1. BOYCE_HTTP_TOKEN env var
    2. token stored in .boyce/config.json
    3. Generate a new random token, persist it, print to stderr
    """
    env_token = os.environ.get("BOYCE_HTTP_TOKEN", "")
    if env_token:
        return env_token

    if _CONFIG_PATH.exists():
        try:
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            tok = data.get("http_token", "")
            if tok:
                return tok
        except (json.JSONDecodeError, OSError):
            pass

    # Generate and persist
    token = secrets.token_urlsafe(32)
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if _CONFIG_PATH.exists():
        try:
            existing = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    existing["http_token"] = token
    _CONFIG_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    logger.warning("Generated new HTTP token (also saved to .boyce/config.json):")
    logger.warning("  BOYCE_HTTP_TOKEN=%s", token)
    return token


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests missing a valid Bearer token (except /health)."""

    def __init__(self, app: Any, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.url.path == "/health":
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != self._token:
            return JSONResponse(
                {"error": {"code": 401, "message": "Unauthorized — provide a valid Bearer token"}},
                status_code=401,
            )
        return await call_next(request)


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


async def _json_body(request: Request) -> dict:
    """Parse JSON body; return empty dict on failure."""
    try:
        return await request.json()
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


async def health(request: Request) -> JSONResponse:
    from . import __version__ as _ver  # noqa: PLC0415 — lazy
    return JSONResponse({"status": "ok", "version": _ver})


async def route_schema(request: Request) -> JSONResponse:
    from .server import get_schema  # noqa: PLC0415
    body = await _json_body(request)
    snapshot_name = body.get("snapshot_name", "default")
    result = json.loads(get_schema(snapshot_name))
    status = 400 if "error" in result else 200
    return JSONResponse(result, status_code=status)


async def route_build_sql(request: Request) -> JSONResponse:
    from .server import build_sql  # noqa: PLC0415
    body = await _json_body(request)
    structured_filter = body.get("structured_filter", {})
    snapshot_name = body.get("snapshot_name", "default")
    dialect = body.get("dialect", "redshift")
    result = json.loads(await build_sql(structured_filter, snapshot_name, dialect))
    status = 400 if "error" in result else 200
    return JSONResponse(result, status_code=status)


async def route_ask(request: Request) -> JSONResponse:
    from .server import ask_boyce  # noqa: PLC0415
    body = await _json_body(request)
    query = body.get("query", body.get("natural_language_query", ""))
    snapshot_name = body.get("snapshot_name", "default")
    dialect = body.get("dialect", "redshift")
    result = json.loads(await ask_boyce(query, snapshot_name, dialect))
    status = 400 if "error" in result else 200
    return JSONResponse(result, status_code=status)


async def route_chat(request: Request) -> JSONResponse:
    """
    Conversational endpoint — routes all messages through ask_boyce.

    Returns a text response shaped for display, not just raw SQL.

    Request body:
        {"message": "...", "snapshot_name": "default", "dialect": "redshift"}

    Response:
        {"reply": "...", "tool_used": "ask_boyce", "data": {...}}
    """
    from .server import ask_boyce  # noqa: PLC0415

    body = await _json_body(request)
    message = body.get("message", "")
    snapshot_name = body.get("snapshot_name", "default")
    dialect = body.get("dialect", "redshift")

    if not message:
        return JSONResponse(
            {"error": {"code": 400, "message": "'message' is required"}},
            status_code=400,
        )

    raw = await ask_boyce(
        natural_language_query=message,
        snapshot_name=snapshot_name,
        dialect=dialect,
    )
    data = json.loads(raw)

    if "error" in data:
        return JSONResponse(data, status_code=400)

    # Mode C: schema guidance — no LLM credentials configured
    if data.get("mode") == "schema_guidance":
        entities = data.get("relevant_entities", [])
        entity_lines = []
        for ent in entities:
            field_names = [f["name"] for f in ent.get("fields", [])]
            preview = ", ".join(field_names[:5])
            if len(field_names) > 5:
                preview += f" (+{len(field_names) - 5} more)"
            entity_lines.append(f"{ent['name']}: {preview}")
        schema_summary = "\n".join(f"  • {line}" for line in entity_lines)
        reply = (
            f"Here's what I found in the database for your question:\n{schema_summary}\n\n"
            "To generate SQL, configure Boyce's LLM credentials: "
            "set BOYCE_PROVIDER and BOYCE_MODEL, or run `boyce-init`."
        )
        return JSONResponse({"reply": reply, "tool_used": "ask_boyce", "data": data})

    # Mode A/B: SQL result
    entities = ", ".join(data.get("entities_resolved", []))
    reply = f"Here's the SQL:\n\n{data['sql']}\n\n-- Entities: {entities}"

    if "warning" in data:
        w = data["warning"]
        reply += f"\n\n⚠ {w['code']}: {w['message']}"

    if "compat_risks" in data:
        for risk in data["compat_risks"]:
            reply += f"\n[COMPAT] {risk}"

    return JSONResponse({"reply": reply, "tool_used": "ask_boyce", "data": data})


async def route_query(request: Request) -> JSONResponse:
    from .server import query_database  # noqa: PLC0415
    body = await _json_body(request)
    sql = body.get("sql", "")
    reason = body.get("reason", "HTTP API call")
    result = json.loads(await query_database(sql, reason))
    status = 400 if "error" in result else 200
    return JSONResponse(result, status_code=status)


async def route_profile(request: Request) -> JSONResponse:
    from .server import profile_data  # noqa: PLC0415
    body = await _json_body(request)
    table = body.get("table", "")
    column = body.get("column", "")
    result = json.loads(await profile_data(table, column))
    status = 400 if "error" in result else 200
    return JSONResponse(result, status_code=status)


async def route_ingest(request: Request) -> JSONResponse:
    from .server import ingest_source  # noqa: PLC0415
    body = await _json_body(request)
    source_path = body.get("source_path")
    snapshot_json = body.get("snapshot_json")
    snapshot_name = body.get("snapshot_name", "default")
    result = json.loads(await ingest_source(source_path, snapshot_json, snapshot_name))
    status = 400 if "error" in result else 200
    return JSONResponse(result, status_code=status)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def build_app(token: Optional[str] = None) -> Any:
    """
    Build and return the Starlette ASGI application.

    Args:
        token: Bearer token for auth. If None, resolved via _load_or_create_token().

    Returns:
        Starlette application instance.

    Raises:
        ImportError: If starlette is not installed.
    """
    if not _STARLETTE_AVAILABLE:
        raise ImportError(
            "starlette is required for HTTP API mode. "
            "It is installed automatically with the mcp dependency."
        )

    if token is None:
        token = _load_or_create_token()

    routes = [
        Route("/health",    health,          methods=["GET"]),
        Route("/schema",    route_schema,    methods=["POST"]),
        Route("/build-sql", route_build_sql, methods=["POST"]),
        Route("/ask",       route_ask,       methods=["POST"]),
        Route("/chat",      route_chat,      methods=["POST"]),
        Route("/query",     route_query,     methods=["POST"]),
        Route("/profile",   route_profile,   methods=["POST"]),
        Route("/ingest",    route_ingest,    methods=["POST"]),
    ]

    middleware = [
        Middleware(BearerAuthMiddleware, token=token),
    ]

    return Starlette(routes=routes, middleware=middleware)


# ---------------------------------------------------------------------------
# Module-level app for direct uvicorn use:
#   uvicorn boyce.http_api:app --port 8741
# ---------------------------------------------------------------------------

app = build_app()
