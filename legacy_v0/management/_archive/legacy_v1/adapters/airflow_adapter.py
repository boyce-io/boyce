from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List


def load_from_dag_json(path: str | Path) -> List[Dict[str, Any]]:
    """
    Parse a minimal Airflow DAG JSON into artifacts.

    Expect structure:
      {
        "dag_id": "example",
        "tasks": [{"task_id": "t1", "downstream": ["t2"]}, {"task_id":"t2"}]
      }
    """
    p = Path(path)
    obj = json.loads(p.read_text(encoding="utf-8"))
    artifacts: List[Dict[str, Any]] = []

    dag_id = obj.get("dag_id") or p.stem
    artifacts.append({
        "system": "airflow",
        "type": "entity",
        "name": dag_id,
        "attributes": {"kind": "dag"},
        "source_path": str(p),
    })

    tasks = obj.get("tasks", []) or []
    for t in tasks:
        tid = t.get("task_id")
        if not tid:
            continue
        artifacts.append({
            "system": "airflow",
            "type": "entity",
            "name": f"{dag_id}.{tid}",
            "attributes": {"kind": "task"},
            "source_path": str(p),
        })
        for d in t.get("downstream", []) or []:
            artifacts.append({
                "system": "airflow",
                "type": "relationship",
                "name": f"{dag_id}.{tid}->{dag_id}.{d}",
                "attributes": {"left": f"{dag_id}.{tid}", "right": f"{dag_id}.{d}"},
                "source_path": str(p),
            })

    return artifacts


