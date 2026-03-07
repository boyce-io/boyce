from __future__ import annotations

import re
from typing import Dict, Any, List, Tuple

from datashark_mcp.kernel.air_gap_api import AirGapAPI


TIME_RE_NUM = re.compile(r"past\s+(\d+)\s+(day|days|week|weeks|month|months|year|years)", re.IGNORECASE)
TIME_RE_WORD = re.compile(r"past\s+(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+(day|days|week|weeks|month|months|year|years)", re.IGNORECASE)
NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


def normalize_date_range(expression: str) -> Dict[str, str]:
    """
    Parse simple expressions like 'past 6 months' into ISO gte/lte placeholders.
    For testing, returns relative markers rather than computing actual dates.
    """
    m = TIME_RE_NUM.search(expression or "")
    qty = None
    unit = None
    if m:
        qty = int(m.group(1))
        unit = m.group(2).lower()
    else:
        m2 = TIME_RE_WORD.search(expression or "")
        if m2:
            qty = NUM_WORDS.get(m2.group(1).lower())
            unit = m2.group(2).lower()
    if not qty or not unit:
        return {"gte": "RELATIVE:UNKNOWN", "lte": "RELATIVE:NOW"}
    return {"gte": f"RELATIVE:-{qty} {unit}", "lte": "RELATIVE:NOW"}


def parse_question(text: str, ctx: AirGapAPI) -> Dict[str, Any]:
    """
    Extract a minimal plan from natural language.
    Heuristics:
      - metric tokens contain 'total' or 'count' → select ['total']
      - dimension tokens like 'daily' → group_by ['day']
      - filters from known entities via resolver/search
      - time range via 'past N months/weeks/etc.'
    """
    t = text.strip()
    plan: Dict[str, Any] = {"select": [], "from": [], "filters": [], "group_by": [], "order_by": [], "limit": 100}
    warnings: List[str] = []

    # Metric
    if re.search(r"\b(total|count|sum)\b", t, re.IGNORECASE):
        plan["select"].append("total")
    # Dimension granularity
    if re.search(r"\bdaily\b", t, re.IGNORECASE):
        plan["group_by"].append("day")

    # Resolve entities (simple noun tokens by capitalization or known words)
    candidates = re.findall(r"[A-Za-z][A-Za-z0-9_]+(?:\s+[A-Za-z][A-Za-z0-9_]+)*", t)
    resolved: List[Tuple[str, float]] = []
    for c in candidates:
        r = ctx.resolve_entity(c)
        if r and r.get("confidence", 0.0) > 0.3:
            if r.get("type") == "entity":
                plan["from"].append(r["id"])
            else:
                plan["filters"].append(f"{c}")
            resolved.append((c, r.get("confidence", 0.0)))

    # Time range
    tr = normalize_date_range(t)
    plan["filters"].append(f"_time BETWEEN {tr['gte']} AND {tr['lte']}")

    # Confidence (simple average of resolutions if any)
    conf = sum(x[1] for x in resolved) / len(resolved) if resolved else 0.5

    return {"plan": plan, "confidence": round(conf, 3), "warnings": warnings, "temporal_range": tr}


