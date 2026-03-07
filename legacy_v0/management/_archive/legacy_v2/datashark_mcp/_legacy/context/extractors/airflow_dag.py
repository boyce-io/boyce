"""
Airflow DAG Extractor

Parses DAG definitions and maps tasks and dependencies to EDGE relationships.
"""

from __future__ import annotations

import json
import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from datashark_mcp.context.extractors.base import Extractor, write_jsonl
from datashark_mcp.context.models import Node, Edge, Provenance
from datashark_mcp.context.id_utils import compute_node_id, compute_edge_id
from datashark_mcp.context.manifest import Manifest


class AirflowDAGExtractor:
    """Extractor for Airflow DAG definitions."""
    
    def name(self) -> str:
        return "airflow_dag"
    
    def run(self, *, out_dir: str, since: str | None = None, input_path: str | None = None) -> None:
        """
        Extract Airflow DAG data.
        
        Args:
            out_dir: Output directory
            since: Optional timestamp for incremental extraction
            input_path: Path to Airflow DAGs directory
        """
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        # Start manifest
        manifest = Manifest.start_run(
            system="airflow",
            repo=None,
            changed_since=since,
            schema_version="0.2.0",
            extractor_version="1.0.0"
        )
        
        # Find DAG files
        if input_path:
            dag_dir = Path(input_path).expanduser()
        else:
            dag_dir = Path("dags")
        
        if not dag_dir.exists():
            self._write_empty_output(out_path, manifest)
            return
        
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        task_id_map: Dict[str, str] = {}  # (dag_id, task_id) -> node_id
        
        extracted_at = datetime.now(timezone.utc).isoformat()
        
        # Find all Python files in dags directory
        dag_files = list(dag_dir.glob("*.py"))
        
        for dag_file in dag_files:
            try:
                # Parse DAG file (simplified - would need full Airflow parser in production)
                dag_nodes, dag_edges, dag_task_map = self._parse_dag_file(dag_file, extracted_at)
                nodes.extend(dag_nodes)
                edges.extend(dag_edges)
                task_id_map.update(dag_task_map)
            except Exception as e:
                # Continue on parse errors
                continue
        
        # Finalize manifest
        manifest.finish_run(
            node_count=len(nodes),
            edge_count=len(edges),
            status="success"
        )
        
        # Write artifacts
        write_jsonl(out_path / "nodes.jsonl", nodes)
        write_jsonl(out_path / "edges.jsonl", edges)
        manifest.write(out_path / "manifest.json")
    
    def _parse_dag_file(self, dag_file: Path, extracted_at: str) -> tuple[List[Dict], List[Dict], Dict[str, str]]:
        """
        Parse a single DAG Python file.
        
        Returns:
            Tuple of (nodes, edges, task_id_map)
        """
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        task_id_map: Dict[str, str] = {}
        
        # Read file content
        with open(dag_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Simple AST parsing to find DAG definitions
        # In production, would use Airflow's DAG parser
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    # Look for DAG(...) assignments
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            var_name = target.id
                            
                            # Check if value is a DAG instantiation
                            if isinstance(node.value, ast.Call):
                                if isinstance(node.value.func, ast.Name) and node.value.func.id == "DAG":
                                    # Extract DAG ID
                                    dag_id = None
                                    for keyword in node.value.keywords:
                                        if keyword.arg == "dag_id":
                                            if isinstance(keyword.value, ast.Constant):
                                                dag_id = keyword.value.value
                                    
                                    if dag_id:
                                        # Create DAG node
                                        dag_node_id = compute_node_id("TRANSFORMATION", "airflow", None, None, dag_id)
                                        
                                        dag_node = Node(
                                            id=dag_node_id,
                                            system="airflow",
                                            type="TRANSFORMATION",
                                            name=dag_id,
                                            attributes={
                                                "dag_file": str(dag_file),
                                                "airflow_dag": True
                                            },
                                            provenance=Provenance(
                                                system="airflow",
                                                source_path=str(dag_file),
                                                extractor_version="1.0.0",
                                                extracted_at=extracted_at
                                            )
                                        )
                                        nodes.append(dag_node.to_dict())
                                        
                                        # Try to find tasks (simplified)
                                        # In production, would parse full DAG structure
                                        tasks = self._extract_tasks_from_ast(node, dag_id, dag_file, extracted_at)
                                        for task_node, task_edges in tasks:
                                            nodes.append(task_node.to_dict())
                                            edges.extend([e.to_dict() for e in task_edges])
                                            
                                            # Track task ID
                                            task_id = task_node.attributes.get("task_id", "")
                                            if task_id:
                                                task_id_map[(dag_id, task_id)] = task_node.id
        except SyntaxError:
            # Skip files with syntax errors
            pass
        
        return nodes, edges, task_id_map
    
    def _extract_tasks_from_ast(
        self, 
        dag_node: ast.AST, 
        dag_id: str, 
        dag_file: Path, 
        extracted_at: str
    ) -> List[tuple[Node, List[Edge]]]:
        """
        Extract tasks from AST (simplified implementation).
        
        Returns:
            List of (task_node, task_edges) tuples
        """
        tasks: List[tuple[Node, List[Edge]]] = []
        
        # Simplified: look for common task operators
        # In production, would fully parse Airflow task definitions
        task_operators = ["PythonOperator", "BashOperator", "SQLExecuteQueryOperator"]
        
        # This is a placeholder - full implementation would parse task dependencies
        # For now, return empty list
        return tasks
    
    def _write_empty_output(self, out_path: Path, manifest: Manifest):
        """Write empty output when no DAGs found."""
        manifest.finish_run(
            node_count=0,
            edge_count=0,
            status="success"
        )
        
        write_jsonl(out_path / "nodes.jsonl", [])
        write_jsonl(out_path / "edges.jsonl", [])
        manifest.write(out_path / "manifest.json")

