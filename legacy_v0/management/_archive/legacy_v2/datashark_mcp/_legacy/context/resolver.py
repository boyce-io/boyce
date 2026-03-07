from __future__ import annotations

from typing import Dict, Any, Optional

def resolve_entity(ctx: Any, value: str) -> Optional[Dict[str, Any]]:
    """
    Heuristic resolver using ContextAPI.search and salience.
    Returns {id, type, confidence}
    """
    hits = ctx.search(value)
    if not hits:
        return None
    # score = salience + string containment bonus
    best = None
    best_score = -1.0
    for n in hits:
        sal = ctx.get_salience(n.id)
        name = (n.name or "").lower()
        bonus = 0.3 if value.lower() in name else 0.0
        score = sal + bonus
        if score > best_score:
            best = n
            best_score = score
    if not best:
        return None
    return {"id": best.id, "type": best.type.value, "confidence": round(min(1.0, max(0.0, best_score)), 3)}


