from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List


def load_from_manifest(manifest_path: str | Path) -> List[Dict[str, Any]]:
    """
    Parse dbt manifest.json minimally into generic artifacts for GraphBuilder.

    - Models -> type=entity, name=model_name
    - Exposures -> type=context_tag, name=exposure_name
    - Dependencies (child -> parent) -> type=relationship with attributes {left, right}
    """
    p = Path(manifest_path)
    obj = json.loads(p.read_text(encoding="utf-8"))
    artifacts: List[Dict[str, Any]] = []

    # Models/entities
    for key, node in (obj.get("nodes") or {}).items():
        if node.get("resource_type") == "model":
            name = node.get("name") or key
            artifacts.append({
                "system": "dbt",
                "type": "entity",
                "name": name,
                "source_path": node.get("path"),
                "source_commit": None,
                "attributes": {"database": node.get("database"), "schema": node.get("schema")},
            })
            # lineage relationships
            for dep in node.get("depends_on", {}).get("nodes", []):
                dep_name = dep.split(".")[-1]
                artifacts.append({
                    "system": "dbt",
                    "type": "relationship",
                    "name": f"{dep_name}->{name}",
                    "attributes": {"left": dep_name, "right": name},
                    "source_path": node.get("path"),
                })

    # Exposures as tags
    for key, exp in (obj.get("exposures") or {}).items():
        name = exp.get("name") or key
        artifacts.append({
            "system": "dbt",
            "type": "context_tag",
            "name": name,
            "attributes": {"type": exp.get("type")},
            "source_path": exp.get("path"),
        })

    return artifacts


