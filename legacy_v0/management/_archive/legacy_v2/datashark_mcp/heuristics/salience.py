from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Tuple


@dataclass(frozen=True)
class SalienceRecord:
    id: str
    score: float
    evidence: Dict[str, Any]
    last_updated_utc: str


def _normalize(value: float, min_v: float, max_v: float) -> float:
    if max_v <= min_v:
        return 0.0
    x = (value - min_v) / (max_v - min_v)
    return max(0.0, min(1.0, x))


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_salience(
    usage: Dict[str, Dict[str, float]],
    weights: Dict[str, float] | None = None,
) -> Dict[str, SalienceRecord]:
    """
    Compute normalized salience in [0,1] per id.

    usage[id] = { 'query_frequency': x, 'dashboard_refs': y, 'lineage_count': z }
    weights defaults: {'query_frequency': 0.5, 'dashboard_refs': 0.3, 'lineage_count': 0.2}
    """
    weights = weights or {"query_frequency": 0.5, "dashboard_refs": 0.3, "lineage_count": 0.2}
    # Gather mins/maxes per feature
    feats = ("query_frequency", "dashboard_refs", "lineage_count")
    mins = {k: float("inf") for k in feats}
    maxs = {k: float("-inf") for k in feats}
    for rec in usage.values():
        for k in feats:
            v = float(rec.get(k, 0.0))
            mins[k] = min(mins[k], v)
            maxs[k] = max(maxs[k], v)
    # Compute scores
    now = _timestamp()
    out: Dict[str, SalienceRecord] = {}
    for _id, rec in usage.items():
        nf = _normalize(float(rec.get("query_frequency", 0.0)), mins["query_frequency"], maxs["query_frequency"]) if usage else 0.0
        nd = _normalize(float(rec.get("dashboard_refs", 0.0)), mins["dashboard_refs"], maxs["dashboard_refs"]) if usage else 0.0
        nl = _normalize(float(rec.get("lineage_count", 0.0)), mins["lineage_count"], maxs["lineage_count"]) if usage else 0.0
        score = (
            weights.get("query_frequency", 0.0) * nf +
            weights.get("dashboard_refs", 0.0) * nd +
            weights.get("lineage_count", 0.0) * nl
        )
        out[_id] = SalienceRecord(
            id=_id,
            score=round(score, 8),
            evidence={"nf": nf, "nd": nd, "nl": nl, "raw": rec},
            last_updated_utc=now,
        )
    return out


def save_salience(records: Dict[str, SalienceRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [r.__dict__ for r in records.values()]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_salience(path: Path) -> Dict[str, SalienceRecord]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        arr = json.load(f)
    out: Dict[str, SalienceRecord] = {}
    for o in arr:
        out[o["id"]] = SalienceRecord(
            id=o["id"],
            score=float(o["score"]),
            evidence=o.get("evidence", {}),
            last_updated_utc=o.get("last_updated_utc", ""),
        )
    return out


def get_salience(records: Dict[str, SalienceRecord], _id: str) -> float:
    rec = records.get(_id)
    return rec.score if rec else 0.0


def list_high_value_entities(records: Dict[str, SalienceRecord], top_n: int = 10) -> List[Tuple[str, float]]:
    ranked = sorted(((rid, r.score) for rid, r in records.items()), key=lambda x: (-x[1], x[0]))
    return ranked[: max(0, top_n)]

if __name__ == "__main__":
    import argparse, sys, json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Recompute salience scores for entities.")
    parser.add_argument("--recompute", action="store_true")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        in_path = Path(args.input)
        # Expect nodes/edges next to manifest or a summary json with node_count/edge_count
        nodes_path = in_path.parent / "nodes.json"
        edges_path = in_path.parent / "edges.json"
        usage: Dict[str, Dict[str, float]] = {}
        if nodes_path.exists() and edges_path.exists():
            nodes = json.loads(nodes_path.read_text(encoding="utf-8"))
            edges = json.loads(edges_path.read_text(encoding="utf-8"))
            degree: Dict[str, int] = {}
            for e in edges:
                degree[e["src"]] = degree.get(e["src"], 0) + 1
                degree[e["dst"]] = degree.get(e["dst"], 0) + 1
            for n in nodes:
                d = float(degree.get(n["id"], 0))
                usage[n["id"]] = {"query_frequency": 0.0, "dashboard_refs": 0.0, "lineage_count": d}
        else:
            # Fallback: empty usage
            usage = {}

        if args.recompute:
            recs = compute_salience(usage)
            out_path = Path(args.output)
            save_salience(recs, out_path)
            print(f"✅ Salience recomputed: {args.output}")
            print(f"Entries: {len(recs)}")
        else:
            loaded = load_salience(Path(args.output))
            print(f"Loaded salience entries: {len(loaded)}")
    except Exception as e:
        print(f"❌ Salience recompute failed: {e}")
        sys.exit(1)


