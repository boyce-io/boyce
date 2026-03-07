from __future__ import annotations

from typing import Dict, Any, List, Tuple, Set

from datashark_mcp.kernel.air_gap_api import AirGapAPI
from datashark_mcp.reasoning.join_planner import plan_joins


SQL_KEYWORDS = {
    "select", "from", "where", "group", "by", "order", "limit", "join",
    "left", "inner", "on", "as", "asc", "desc"
}


def _quote_ident(ident: str) -> str:
    if ident is None:
        return ident
    s = ident.replace('"', '""')
    return f'"{s}"'


def _canon_sql(sql: str) -> str:
    tokens = sql.replace("\n", " ").split()
    out: List[str] = []
    for t in tokens:
        low = t.lower()
        if low in SQL_KEYWORDS:
            out.append(low.upper())
        else:
            out.append(t)
    return " ".join(out)


def _resolve_tables(plan: Dict[str, Any], ctx: AirGapAPI) -> List[str]:
    tables: List[str] = []
    for src in plan.get("from", []) or []:
        ent = ctx.find_entity(src) or None
        if ent:
            # AirGapAPI returns dict, extract entity_id or entity_name
            entity_id = ent.get("entity_id") or ent.get("entity_name") or ent.get("name")
            if entity_id:
                tables.append(entity_id)
            else:
                tables.append(src)
        else:
            # Fallback: assume input is already a node id/name
            tables.append(src)
    return tables


def _render_join_clause(j: Dict[str, Any], alias_map: Dict[str, str]) -> Tuple[str, List[str]]:
    left = alias_map.get(j["left"], j["left"]) 
    right = alias_map.get(j["right"], j["right"]) 
    keys = j.get("keys") or []
    warnings: List[str] = []
    if keys:
        conds = []
        for k in keys:
            l = k.get("left") or k.get("from")
            r = k.get("right") or k.get("to")
            if l and r:
                conds.append(f"{left}.{_quote_ident(l)} = {right}.{_quote_ident(r)}")
        on = " AND ".join(conds) if conds else "1=1"
    else:
        on = "1=1"
        warnings.append(f"Join {left}->{right} has no key metadata; using ON 1=1 placeholder")
    clause = f"LEFT JOIN {right} ON {on}"
    return clause, warnings


def build_sql(plan: Dict[str, Any], ctx: AirGapAPI) -> Dict[str, Any]:
    """
    Build canonical SQL and join plan from a simple plan dict and AirGapAPI.
    Returns: { sql, tables, joins, warnings }
    """
    warnings: List[str] = []
    # Resolve tables
    table_nodes = _resolve_tables(plan, ctx)
    joins = plan_joins(table_nodes, ctx)

    # Aliases in stable order
    alias_map: Dict[str, str] = {}
    tables_rendered: List[str] = []
    for idx, t in enumerate(table_nodes):
        alias = f"t{idx+1}"
        alias_map[t] = alias
        tables_rendered.append({"id": t, "alias": alias})

    # SELECT
    select_parts: List[str] = []
    for expr in plan.get("select", []) or []:
        # naive: if contains '.', assume already qualified; otherwise prefix first table alias
        if "." in expr:
            select_parts.append(expr)
        else:
            select_parts.append(f"{tables_rendered[0]['alias']}.{_quote_ident(expr)}")
    select_sql = ", ".join(select_parts) if select_parts else "*"

    # FROM and JOINs
    from_sql = f"{_quote_ident(plan.get('from', [tables_rendered[0]['id']])[0])} AS {tables_rendered[0]['alias']}"
    join_sql_parts: List[str] = []
    enriched_joins: List[Dict[str, Any]] = []
    for j in joins:
        clause, j_w = _render_join_clause(j, alias_map)
        join_sql_parts.append(clause)
        warnings.extend(j_w)
        enriched_joins.append({
            **j,
            "path_depth": j.get("path_depth", 1),
            "sources_involved": j.get("sources_involved", []),
        })

    # WHERE
    filters = plan.get("filters", []) or []
    where_sql = " AND ".join(filters) if filters else ""

    # GROUP BY / ORDER BY / LIMIT
    group_by = plan.get("group_by", []) or []
    order_by = plan.get("order_by", []) or []
    limit = plan.get("limit")

    sql_parts: List[str] = [
        f"SELECT {select_sql}",
        f"FROM {from_sql}",
    ]
    sql_parts.extend(join_sql_parts)
    if where_sql:
        sql_parts.append(f"WHERE {where_sql}")
    if group_by:
        sql_parts.append("GROUP BY " + ", ".join(group_by))
    if order_by:
        sql_parts.append("ORDER BY " + ", ".join(order_by))
    if isinstance(limit, int):
        sql_parts.append(f"LIMIT {limit}")

    sql = _canon_sql(" \n".join(sql_parts))

    # Validate plan (basic): ensure we had at least one table and all selections non-empty
    ok = bool(tables_rendered)
    if not ok:
        warnings.append("Empty FROM set; no tables resolved")
    # Surface AirGapAPI plan validation result (placeholder)
    _ = ctx.validate_query_plan({"tables": table_nodes, "select": plan.get("select", [])})

    return {
        "sql": sql,
        "tables": tables_rendered,
        "joins": enriched_joins,
        "warnings": warnings,
    }


