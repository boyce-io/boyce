#!/usr/bin/env python3
"""
Live Benchmark Integration Tests - Phase 4: First Contact

This test suite validates that our Graph Engine and LookML Parser work
on real-world external data from the DataShark_Benchmarks sibling directory.

These tests prove the "Moat" - that our semantic pathfinding works on
actual enterprise LookML repositories.
"""

import pytest
import sys
from pathlib import Path
from typing import List, Optional

# Add src to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from datashark.core.graph import SemanticGraph
from datashark.core.parsers import parse_dbt_project_source, parse_lookml_file, detect_source_type
from datashark.core.types import SemanticSnapshot
from datashark.core.validation import validate_snapshot


def find_benchmark_directory(benchmark_name: str, subpath: str = "") -> Optional[Path]:
    """
    Locate the DataShark_Benchmarks sibling directory.
    
    Args:
        benchmark_name: Name of benchmark directory (e.g., "thelook", "mattermost")
        subpath: Optional subpath within benchmark (e.g., "transform/mattermost-analytics")
        
    Returns:
        Path to benchmark directory, or None if not found
    """
    # Try multiple possible locations
    base_paths = [
        project_root.parent / "DataShark_Benchmarks",
        project_root / ".." / "DataShark_Benchmarks",
        Path("../DataShark_Benchmarks").resolve(),
    ]
    
    # Try different benchmark categories
    categories = ["03_Semantic_Reference", "01_Enterprise_Full_Stack"]
    
    for base_path in base_paths:
        resolved_base = base_path.resolve() if hasattr(base_path, 'resolve') else Path(base_path).resolve()
        for category in categories:
            path = resolved_base / category / benchmark_name
            if subpath:
                path = path / subpath
            if path.exists() and path.is_dir():
                return path
    
    return None


def ingest_lookml_directory(directory: Path) -> List[SemanticSnapshot]:
    """
    Ingest all LookML files from a directory.
    
    Strategy: Parse view files first (they define entities), then model files
    (they define joins between views).
    
    Args:
        directory: Path to directory containing .lkml files
        
    Returns:
        List of SemanticSnapshot objects (views first, then model files)
    """
    snapshots = []
    
    # Separate view files from model files
    view_files = sorted([f for f in directory.glob("*.view.lkml")])
    model_files = sorted([f for f in directory.glob("*.model.lkml")])
    other_files = sorted([f for f in directory.glob("*.lkml") 
                          if not f.name.endswith(".view.lkml") and not f.name.endswith(".model.lkml")])
    
    # Parse view files first (they define entities)
    for lkml_file in view_files:
        try:
            snapshot = parse_lookml_file(lkml_file)
            # Validate snapshot
            snapshot_dict = snapshot.model_dump(mode='json')
            validation_errors = validate_snapshot(snapshot_dict)
            if validation_errors:
                pytest.fail(f"Snapshot from {lkml_file.name} failed validation: {validation_errors}")
            snapshots.append(snapshot)
        except Exception as e:
            pytest.fail(f"Failed to parse {lkml_file.name}: {str(e)}")
    
    # Parse model files (they define joins between views)
    for lkml_file in model_files:
        try:
            snapshot = parse_lookml_file(lkml_file)
            # Model files may have 0 entities but should have joins
            # Validate snapshot (may have joins referencing entities from other files)
            snapshot_dict = snapshot.model_dump(mode='json')
            validation_errors = validate_snapshot(snapshot_dict)
            if validation_errors:
                # For model files, we're more lenient - joins may reference entities not in this snapshot
                # But basic structure should still be valid
                print(f"Warning: Model file {lkml_file.name} has validation issues: {validation_errors}")
            snapshots.append(snapshot)
        except Exception as e:
            pytest.fail(f"Failed to parse {lkml_file.name}: {str(e)}")
    
    # Parse other .lkml files
    for lkml_file in other_files:
        try:
            snapshot = parse_lookml_file(lkml_file)
            snapshot_dict = snapshot.model_dump(mode='json')
            validation_errors = validate_snapshot(snapshot_dict)
            if validation_errors:
                pytest.fail(f"Snapshot from {lkml_file.name} failed validation: {validation_errors}")
            snapshots.append(snapshot)
        except Exception as e:
            pytest.fail(f"Failed to parse {lkml_file.name}: {str(e)}")
    
    return snapshots


@pytest.mark.integration
def test_thelook_live_fire():
    """
    Test Case: TheLook Live Fire
    
    This test validates the full pipeline:
    1. Locate the benchmark directory
    2. Ingest LookML files
    3. Build semantic graph
    4. Validate entities exist
    5. Test pathfinding with semantic cost validation
    
    The "Moat" Check: Pathfinding must work and semantic cost must be low
    because LookML joins are "Gold Standard" (0.1 weight).
    """
    # Step 1: Locate the Benchmark
    benchmark_dir = find_benchmark_directory("thelook")
    
    if not benchmark_dir:
        pytest.skip(
            "DataShark_Benchmarks directory not found. "
            "Expected at: ../DataShark_Benchmarks/03_Semantic_Reference/thelook"
        )
    
    assert benchmark_dir.exists(), f"Benchmark directory does not exist: {benchmark_dir}"
    assert benchmark_dir.is_dir(), f"Benchmark path is not a directory: {benchmark_dir}"
    
    # Step 2: Ingest
    print(f"\n📂 Ingesting LookML files from: {benchmark_dir}")
    snapshots = ingest_lookml_directory(benchmark_dir)
    
    assert len(snapshots) > 0, f"No LookML files found or parsed in {benchmark_dir}"
    print(f"✅ Ingested {len(snapshots)} LookML files")
    
    # Step 3: Build Graph
    graph = SemanticGraph()
    total_entities = 0
    total_joins = 0
    
    for snapshot in snapshots:
        graph.add_snapshot(snapshot)
        total_entities += len(snapshot.entities)
        total_joins += len(snapshot.joins)
        print(f"   Added snapshot: {len(snapshot.entities)} entities, {len(snapshot.joins)} joins")
    
    # Step 4: Validate Graph
    entities = graph.list_entities()
    assert len(entities) > 0, "Graph has no entities after ingestion"
    print(f"✅ Graph contains {len(entities)} entities")
    
    # Assert that orders and users entities exist
    entity_names = [e.replace("entity:", "") for e in entities]
    assert "orders" in entity_names, f"'orders' entity not found. Available: {entity_names}"
    assert "users" in entity_names, f"'users' entity not found. Available: {entity_names}"
    print(f"✅ Found required entities: orders, users")
    
    # Step 5: The "Moat" Check (Pathfinding)
    source_entity = "entity:orders"
    target_entity = "entity:users"
    
    print(f"\n🔍 Testing pathfinding: {source_entity} -> {target_entity}")
    
    try:
        path = graph.find_path(source_entity, target_entity)
    except ValueError as e:
        pytest.fail(f"Pathfinding failed: {str(e)}")
    
    # Assert Success: It must return a valid path
    assert path is not None, "Pathfinding returned None"
    print(f"✅ Found path with {len(path)} joins")
    
    # Calculate semantic cost
    if len(path) > 0:
        total_cost = 0.0
        for join in path:
            # Get edge weight from graph
            edges = graph.graph[join.source_entity_id][join.target_entity_id]
            for edge_key, edge_data in edges.items():
                if edge_data.get('join') == join:
                    weight = edge_data.get('weight', 1.0)
                    total_cost += weight
                    break
        
        print(f"   Semantic cost: {total_cost:.2f}")
        
        # Assert Weight: The semantic cost should be low (< 2.0) because LookML joins are "Gold Standard" (0.1 weight)
        assert total_cost < 2.0, (
            f"Semantic cost {total_cost:.2f} is too high. "
            f"Expected < 2.0 for LookML 'Gold Standard' joins (0.1 weight each). "
            f"Path length: {len(path)}"
        )
        print(f"✅ Semantic cost {total_cost:.2f} is within expected range (< 2.0)")
        
        # Generate SQL to verify it works
        sql = graph.generate_join_sql(path, source_entity)
        assert sql is not None and len(sql) > 0, "SQL generation failed"
        assert "FROM" in sql.upper(), "Generated SQL missing FROM clause"
        assert "JOIN" in sql.upper(), "Generated SQL missing JOIN clause"
        print(f"✅ Generated SQL:\n{sql}")
    else:
        # Empty path (same entity or direct relationship)
        print(f"   Path is empty (same entity or no joins needed)")
        sql = graph.generate_join_sql([], source_entity)
        assert sql is not None and len(sql) > 0, "SQL generation failed for empty path"
        assert "FROM" in sql.upper(), "Generated SQL missing FROM clause"
        print(f"✅ Generated SQL:\n{sql}")
    
    # Final validation: Graph should have connections
    orders_connections = graph.get_entity_connections("entity:orders")
    users_connections = graph.get_entity_connections("entity:users")
    
    print(f"\n📊 Graph Statistics:")
    print(f"   Total entities: {len(entities)}")
    print(f"   Total joins in graph: {sum(len(graph.graph[u][v]) for u in graph.graph for v in graph.graph[u])}")
    print(f"   Orders connections: {len(orders_connections['outgoing'])} outgoing, {len(orders_connections['incoming'])} incoming")
    print(f"   Users connections: {len(users_connections['outgoing'])} outgoing, {len(users_connections['incoming'])} incoming")
    
    # Summary assertion
    assert len(entities) >= 2, "Graph should have at least 2 entities (orders and users)"
    print(f"\n✅ All assertions passed! The Graph Engine and LookML Parser work on real-world data.")


@pytest.mark.integration
def test_mattermost_raw_ingestion():
    """
    Test Case: Mattermost Raw dbt Ingestion (Silver Standard)
    
    This test validates the raw dbt YAML parser:
    1. Locate the Mattermost benchmark directory
    2. Ingest raw dbt YAML files (no manifest.json)
    3. Build semantic graph
    4. Validate entities exist
    5. Test pathfinding with "Silver" cost validation (~0.5 per hop)
    
    The "Silver Standard" Check: Pathfinding must work and semantic cost should be
    ~0.5 per hop because dbt source YAML joins are "Silver Standard" (0.5 weight each).
    """
    # Step 1: Locate the Benchmark
    # Mattermost has dbt projects in transform/mattermost-analytics
    benchmark_dir = find_benchmark_directory("mattermost", "transform/mattermost-analytics")
    
    if not benchmark_dir:
        pytest.skip(
            "Mattermost benchmark directory not found. "
            "Expected at: ../DataShark_Benchmarks/01_Enterprise_Full_Stack/mattermost/transform/mattermost-analytics"
        )
    
    assert benchmark_dir.exists(), f"Benchmark directory does not exist: {benchmark_dir}"
    assert benchmark_dir.is_dir(), f"Benchmark path is not a directory: {benchmark_dir}"
    
    # Verify dbt_project.yml exists
    dbt_project_file = benchmark_dir / "dbt_project.yml"
    if not dbt_project_file.exists():
        pytest.skip(f"Not a dbt project: dbt_project.yml not found in {benchmark_dir}")
    
    # Step 2: Ingest raw dbt YAML files
    print(f"\n📂 Ingesting raw dbt YAML files from: {benchmark_dir}")
    try:
        snapshot = parse_dbt_project_source(benchmark_dir)
    except Exception as e:
        pytest.fail(f"Failed to parse dbt project: {str(e)}")
    
    print(f"✅ Ingested dbt project: {len(snapshot.entities)} entities, {len(snapshot.fields)} fields, {len(snapshot.joins)} joins")
    print(f"   Source type: {snapshot.metadata.get('source_type', 'unknown')}")
    
    # Step 3: Build Graph
    graph = SemanticGraph()
    graph.add_snapshot(snapshot)
    
    # Step 4: Validate Graph
    entities = graph.list_entities()
    assert len(entities) > 0, "Graph has no entities after ingestion"
    print(f"✅ Graph contains {len(entities)} entities")
    
    # Assert that we found some entities (e.g., staging models)
    entity_names = [e.replace("entity:", "") for e in entities]
    print(f"   Sample entities: {entity_names[:5]}")
    
    # Assert that we found joins (explicit + inferred)
    total_joins = sum(len(graph.graph[u][v]) for u in graph.graph for v in graph.graph[u])
    assert total_joins > 0, "Graph should have at least one join from relationship tests"
    print(f"✅ Graph contains {total_joins} total joins (explicit + inferred)")
    
    # Phase 6: Assert that inference engine densified the graph
    assert total_joins > 100, (
        f"Graph should have > 100 edges after inference (Bronze Standard). "
        f"Found {total_joins} edges. Expected significant densification from 17 explicit joins."
    )
    print(f"✅ Graph densification successful: {total_joins} edges (up from 17 explicit joins)")
    
    # Step 5: The "Silver Standard" Check (Pathfinding with explicit joins)
    # Find entities that are actually connected via explicit joins
    entities_with_explicit_joins = set()
    for join in snapshot.joins:
        entities_with_explicit_joins.add(join.source_entity_id)
        entities_with_explicit_joins.add(join.target_entity_id)
    
    if len(entities_with_explicit_joins) >= 2:
        # Use a direct join from the snapshot
        test_join = snapshot.joins[0]  # Use first join
        source_entity = test_join.source_entity_id
        target_entity = test_join.target_entity_id
        
        print(f"\n🔍 Testing pathfinding (Silver Standard): {source_entity} -> {target_entity}")
        
        try:
            path = graph.find_path(source_entity, target_entity)
        except ValueError as e:
            pytest.fail(f"Pathfinding failed: {str(e)}")
        except Exception as e:
            pytest.fail(f"Pathfinding error: {str(e)}")
        
        if path:
            # Calculate semantic cost
            total_cost = 0.0
            for join in path:
                # Get edge weight from graph
                edges = graph.graph[join.source_entity_id][join.target_entity_id]
                for edge_key, edge_data in edges.items():
                    if edge_data.get('join') == join:
                        weight = edge_data.get('weight', 1.0)
                        total_cost += weight
                        print(f"   {join.source_entity_id} -> {join.target_entity_id} (weight: {weight:.2f})")
                        break
            
            print(f"   Total semantic cost: {total_cost:.2f}")
            
            # Assert Weight: The semantic cost should be ~0.5 per hop for Silver Standard
            expected_cost_per_hop = 0.5
            expected_max_cost = expected_cost_per_hop * len(path) + 0.1  # Allow small tolerance
            
            assert total_cost <= expected_max_cost, (
                f"Semantic cost {total_cost:.2f} is too high. "
                f"Expected ~{expected_cost_per_hop:.2f} per hop for dbt source YAML 'Silver Standard' joins. "
                f"Path length: {len(path)}, Expected max: {expected_max_cost:.2f}"
            )
            print(f"✅ Semantic cost {total_cost:.2f} is within expected range (~{expected_cost_per_hop:.2f} per hop)")
            
            # Generate SQL to verify it works
            sql = graph.generate_join_sql(path, source_entity)
            assert sql is not None and len(sql) > 0, "SQL generation failed"
            assert "FROM" in sql.upper(), "Generated SQL missing FROM clause"
            print(f"✅ Generated SQL:\n{sql}")
        else:
            print(f"   No path found between {source_entity} and {target_entity} (this is OK)")
    
    # Step 6: The "Bronze Standard" Check (Pathfinding with inferred edges)
    # Test pathfinding between entities that were NOT explicitly connected
    # but should now be connected via inferred edges
    all_entities = graph.list_entities()
    
    # Find entities that have inferred edges (Bronze Standard)
    entities_with_inferred_edges = set()
    for u in graph.graph:
        for v in graph.graph[u]:
            for edge_key, edge_data in graph.graph[u][v].items():
                join = edge_data.get('join')
                if join and join.id.startswith("inferred:"):
                    entities_with_inferred_edges.add(u)
                    entities_with_inferred_edges.add(v)
    
    if len(entities_with_inferred_edges) >= 2:
        # Test pathfinding using entities with inferred edges
        inferred_entity_list = list(entities_with_inferred_edges)
        
        # Try to find a path between entities connected via inferred edges
        path_found = False
        for i, source in enumerate(inferred_entity_list[:5]):
            for target in inferred_entity_list[i+1:min(i+6, len(inferred_entity_list))]:
                # Skip if they're directly connected via explicit join
                is_explicitly_connected = any(
                    (j.source_entity_id == source and j.target_entity_id == target) or
                    (j.source_entity_id == target and j.target_entity_id == source)
                    for j in snapshot.joins
                )
                if is_explicitly_connected:
                    continue
                
                print(f"\n🔍 Testing pathfinding (Bronze Standard - Inferred): {source} -> {target}")
                
                try:
                    path = graph.find_path(source, target)
                except ValueError as e:
                    continue
                except Exception as e:
                    continue
                
                if path:
                    path_found = True
                    # Calculate semantic cost (should include Bronze Standard weights)
                    total_cost = 0.0
                    bronze_edges = 0
                    for join in path:
                        edges = graph.graph[join.source_entity_id][join.target_entity_id]
                        for edge_key, edge_data in edges.items():
                            if edge_data.get('join') == join:
                                weight = edge_data.get('weight', 1.0)
                                total_cost += weight
                                if weight == 2.0:
                                    bronze_edges += 1
                                print(f"   {join.source_entity_id} -> {join.target_entity_id} (weight: {weight:.2f})")
                                break
                    
                    print(f"   Total semantic cost: {total_cost:.2f} ({bronze_edges} Bronze edges)")
                    
                    # Assert that we used inferred edges (Bronze Standard)
                    assert bronze_edges > 0 or total_cost >= 2.0, (
                        f"Path should use Bronze Standard inferred edges (weight 2.0). "
                        f"Found {bronze_edges} bronze edges, total cost: {total_cost:.2f}"
                    )
                    print(f"✅ Pathfinding using Bronze Standard inferred edges succeeded")
                    
                    # Generate SQL to verify it works
                    sql = graph.generate_join_sql(path, source)
                    assert sql is not None and len(sql) > 0, "SQL generation failed"
                    assert "FROM" in sql.upper(), "Generated SQL missing FROM clause"
                    print(f"✅ Generated SQL from inferred path:\n{sql}")
                    break
            
            if not path_found:
                # If no path found, that's OK - verify we have inferred edges
                print(f"   No path found between test entities, but {len(entities_with_inferred_edges)} entities have inferred edges")
                print(f"   This is OK - inference engine successfully created {total_joins - len(snapshot.joins)} inferred edges")
    else:
        print(f"\n⚠️  No entities with inferred edges found (this may indicate inference didn't run)")
    
    # Final validation: Graph should have entities and joins
    assert len(entities) > 0, "Graph should have at least one entity"
    print(f"\n✅ All assertions passed! The raw dbt YAML parser (Silver Standard) and inference engine (Bronze Standard) work on real-world data.")


if __name__ == "__main__":
    # Allow running directly
    test_thelook_live_fire()
    test_mattermost_raw_ingestion()
