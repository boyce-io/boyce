"""
Synthetic Graph Fixture Generator

Deterministically generates nodes/edges with evenly distributed attributes,
a few hot hubs, and realistic fanouts for benchmarking.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import List
from datashark_mcp.context.models import Node, Edge, Provenance
from datashark_mcp.context.id_utils import compute_node_id, compute_edge_id


def generate_synthetic_graph(
    num_nodes: int = 50000,
    num_edges: int = 100000,
    seed: int = 42
) -> tuple[List[Node], List[Edge]]:
    """
    Generate synthetic graph deterministically.
    
    Args:
        num_nodes: Target number of nodes
        num_edges: Target number of edges
        seed: Random seed for deterministic generation
        
    Returns:
        Tuple of (nodes, edges)
    """
    random.seed(seed)
    
    systems = ["database", "dbt", "bi_tool", "airflow", "catalog"]
    repos = ["repo1", "repo2", "repo3", "repo4", "repo5"]
    schemas = ["public", "analytics", "staging", "raw", "warehouse"]
    
    nodes: List[Node] = []
    node_ids: List[str] = []
    
    # Generate nodes with even distribution
    for i in range(num_nodes):
        system = systems[i % len(systems)]
        repo = repos[i % len(repos)] if system != "database" else None
        schema = schemas[i % len(schemas)] if system == "database" else schemas[i % len(schemas)]
        name = f"entity_{i:06d}"
        
        # Compute deterministic ID
        node_id = compute_node_id("ENTITY", system, repo, schema, name)
        node_ids.append(node_id)
        
        # Create hot hubs (nodes with many connections)
        is_hub = (i % 100 == 0)  # Every 100th node is a hub
        
        node = Node(
            id=node_id,
            system=system,
            type="ENTITY",
            name=name,
            attributes={
                "schema": schema,
                "table": name,
                "is_hub": is_hub,
                "index": i
            },
            provenance=Provenance(
                system=system,
                source_path=f"{system}://{name}",
                extractor_version="1.0.0",
                extracted_at=datetime.now(timezone.utc).isoformat()
            ),
            repo=repo,
            schema=schema
        )
        nodes.append(node)
    
    # Generate edges with realistic fanouts
    edges: List[Edge] = []
    edge_types = ["JOINS_TO", "DERIVES_FROM", "DEPENDS_ON"]
    
    # Create some hot hubs (nodes with many outgoing edges)
    hub_indices = [i for i in range(len(node_ids)) if i % 100 == 0]
    
    for i in range(num_edges):
        # Prefer hubs for src (fanout pattern)
        if random.random() < 0.3 and hub_indices:
            src_idx = random.choice(hub_indices)
        else:
            src_idx = random.randint(0, len(node_ids) - 1)
        
        # Dst is random but not same as src
        dst_idx = random.randint(0, len(node_ids) - 1)
        while dst_idx == src_idx:
            dst_idx = random.randint(0, len(node_ids) - 1)
        
        src_id = node_ids[src_idx]
        dst_id = node_ids[dst_idx]
        
        edge_type = random.choice(edge_types)
        
        # Create join signature for some edges
        join_signature = None
        if edge_type == "JOINS_TO" and random.random() < 0.5:
            join_signature = {
                "join_condition": f"{nodes[src_idx].name}.id = {nodes[dst_idx].name}.id",
                "join_type": random.choice(["inner", "left", "right"])
            }
        
        edge_id = compute_edge_id(edge_type, src_id, dst_id, join_signature)
        
        edge = Edge(
            id=edge_id,
            src=src_id,
            dst=dst_id,
            type=edge_type,
            attributes=join_signature or {},
            provenance=Provenance(
                system=nodes[src_idx].system,
                source_path=f"{nodes[src_idx].system}://{nodes[src_idx].name}",
                extractor_version="1.0.0",
                extracted_at=datetime.now(timezone.utc).isoformat()
            )
        )
        edges.append(edge)
    
    return nodes, edges

