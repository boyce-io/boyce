import json
import tempfile
from pathlib import Path

from datashark_mcp.context.graph_builder import GraphBuilder
from core.adapters.dbt_adapter import load_from_manifest as load_dbt
from core.adapters.tableau_adapter import load_from_json as load_tableau
from core.adapters.airflow_adapter import load_from_dag_json as load_airflow


def _write(p: Path, obj):
    p.write_text(json.dumps(obj), encoding="utf-8")


def test_cross_connectors_parse_and_build_counts_and_determinism():
    gb = GraphBuilder()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # dbt manifest
        manifest = {
            "nodes": {
                "model.proj.orders": {
                    "resource_type": "model", "name": "orders", "database": "db", "schema": "public", "path": "models/orders.sql",
                    "depends_on": {"nodes": ["model.proj.customers"]},
                },
                "model.proj.customers": {
                    "resource_type": "model", "name": "customers", "database": "db", "schema": "public", "path": "models/customers.sql",
                    "depends_on": {"nodes": []},
                },
            },
            "exposures": {
                "exposure.proj.dashboard": {"name": "dashboard", "type": "dashboard", "path": "exposures/dashboard.yml"}
            }
        }
        mf = tmp / "manifest.json"
        _write(mf, manifest)

        # tableau json
        tableau_obj = {"datasources": [{"name": "sales", "columns": ["id", "amount"]}], "extracts": [{"name": "sales_extract", "source": "sales"}]}
        tf = tmp / "tableau.json"
        _write(tf, tableau_obj)

        # airflow dag json
        dag_obj = {"dag_id": "example", "tasks": [{"task_id": "t1", "downstream": ["t2"]}, {"task_id": "t2"}]}
        af = tmp / "dag.json"
        _write(af, dag_obj)

        artifacts = []
        artifacts += load_dbt(mf)
        artifacts += load_tableau(tf)
        artifacts += load_airflow(af)

        nodes, edges = gb.build(artifacts)

        # Counts > 0
        assert len(nodes) > 0
        assert len(edges) > 0

        # Determinism: rebuild should yield same ids/hashes
        nodes2, edges2 = gb.build(artifacts)
        ids1 = sorted([n.id for n in nodes])
        ids2 = sorted([n.id for n in nodes2])
        assert ids1 == ids2
        hashes1 = sorted([n.hash for n in nodes])
        hashes2 = sorted([n.hash for n in nodes2])
        assert hashes1 == hashes2

        # Provenance tags include systems
        systems = set([n.provenance.system for n in nodes] + [e.provenance.system for e in edges])
        assert {"dbt", "tableau", "airflow"}.issubset(systems)


