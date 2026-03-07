from pathlib import Path
import tempfile
from datashark_mcp.heuristics.salience import compute_salience, save_salience, load_salience, get_salience, list_high_value_entities
from datashark_mcp.context.store.memory_store import MemoryStore


def test_deterministic_scoring_for_identical_input():
    usage = {
        "A": {"query_frequency": 100, "dashboard_refs": 10, "lineage_count": 5},
        "B": {"query_frequency": 50, "dashboard_refs": 5, "lineage_count": 1},
    }
    s1 = compute_salience(usage)
    s2 = compute_salience(usage)
    assert s1["A"].score == s2["A"].score
    assert s1["B"].score == s2["B"].score


def test_correct_ranking_order():
    usage = {
        "X": {"query_frequency": 10, "dashboard_refs": 1, "lineage_count": 1},
        "Y": {"query_frequency": 100, "dashboard_refs": 10, "lineage_count": 5},
        "Z": {"query_frequency": 50, "dashboard_refs": 5, "lineage_count": 2},
    }
    recs = compute_salience(usage)
    ranked = list_high_value_entities(recs, top_n=2)
    assert ranked[0][0] == "Y"
    assert len(ranked) == 2


def test_file_load_save_integrity():
    usage = {"A": {"query_frequency": 1, "dashboard_refs": 0, "lineage_count": 0}}
    recs = compute_salience(usage)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "salience.json"
        save_salience(recs, p)
        loaded = load_salience(p)
        assert loaded["A"].score == recs["A"].score


def test_api_exposure_via_memory_store():
    usage = {
        "A": {"query_frequency": 10, "dashboard_refs": 1, "lineage_count": 0},
        "B": {"query_frequency": 5, "dashboard_refs": 2, "lineage_count": 1},
    }
    recs = compute_salience(usage)
    ms = MemoryStore()
    ms.set_salience({k: v.score for k, v in recs.items()})
    top = ms.top_salience(1)
    assert top[0][0] in ("A", "B")

