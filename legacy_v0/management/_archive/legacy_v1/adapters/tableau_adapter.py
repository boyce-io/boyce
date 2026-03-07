from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List


def load_from_json(path: str | Path) -> List[Dict[str, Any]]:
    """
    Parse a minimal Tableau datasource/extract JSON into artifacts.

    Expect structure:
      {
        "datasources": [{"name": "sales", "columns": ["id","amount"]}, ...],
        "extracts": [{"name": "sales_extract", "source": "sales"}],
      }
    """
    p = Path(path)
    obj = json.loads(p.read_text(encoding="utf-8"))
    artifacts: List[Dict[str, Any]] = []

    for ds in obj.get("datasources", []) or []:
        name = ds.get("name")
        if not name:
            continue
        artifacts.append({
            "system": "tableau",
            "type": "entity",
            "name": name,
            "attributes": {"columns": ds.get("columns", [])},
            "source_path": str(p),
        })

    for ex in obj.get("extracts", []) or []:
        src = ex.get("source")
        name = ex.get("name")
        if src and name:
            artifacts.append({
                "system": "tableau",
                "type": "relationship",
                "name": f"{name}->{src}",
                "attributes": {"left": name, "right": src},
                "source_path": str(p),
            })

    return artifacts


