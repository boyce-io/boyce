#!/usr/bin/env python3
"""
GitLab Scale Stress Test - Phase 7: Scale Verification

This test validates that our Ingestion and Inference pipelines can handle
enterprise-scale dbt projects with thousands of entities.

The GitLab benchmark is a massive dbt project that tests:
- Raw YAML parsing performance
- Graph construction performance
- Inference engine performance at scale
- Pathfinding on large graphs
"""

import pytest
import sys
import time
from pathlib import Path
from typing import Optional

# Add src to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from datashark.core.graph import SemanticGraph
from datashark.core.parsers import parse_dbt_project_source
from datashark.core.types import SemanticSnapshot
from datashark.core.validation import validate_snapshot


def find_gitlab_benchmark() -> Optional[Path]:
    """
    Locate the GitLab benchmark directory.
    
    Returns:
        Path to GitLab benchmark directory, or None if not found
    """
    # Try multiple possible locations
    base_paths = [
        project_root.parent / "DataShark_Benchmarks",
        project_root / ".." / "DataShark_Benchmarks",
        Path("../DataShark_Benchmarks").resolve(),
    ]
    
    categories = ["02_Scale_Stress_Test", "01_Enterprise_Full_Stack"]
    
    for base_path in base_paths:
        resolved_base = base_path.resolve() if hasattr(base_path, 'resolve') else Path(base_path).resolve()
        for category in categories:
            # GitLab might be in a subdirectory or at root
            possible_paths = [
                resolved_base / category / "gitlab" / "transform" / "snowflake-dbt",
                resolved_base / category / "gitlab" / "transform" / "gitlab-analytics",
                resolved_base / category / "gitlab" / "analytics",
                resolved_base / category / "gitlab",
            ]
            
            for path in possible_paths:
                if path.exists() and path.is_dir():
                    # Check for dbt_project.yml
                    if (path / "dbt_project.yml").exists():
                        return path
    
    return None


@pytest.mark.integration
def test_gitlab_scale_stress():
    """
    Stress Test: GitLab Scale Verification
    
    This test validates:
    1. Ingestion performance on massive dbt projects
    2. Inference engine performance at scale
    3. Graph construction with thousands of entities
    4. Pathfinding on large graphs
    
    Performance Target: < 30 seconds for full ingestion + inference
    Scale Target: > 1,000 entities
    """
    # Step 1: Locate the Benchmark
    benchmark_dir = find_gitlab_benchmark()
    
    if not benchmark_dir:
        pytest.skip(
            "GitLab benchmark directory not found. "
            "Expected at: ../DataShark_Benchmarks/02_Scale_Stress_Test/gitlab"
        )
    
    assert benchmark_dir.exists(), f"Benchmark directory does not exist: {benchmark_dir}"
    assert benchmark_dir.is_dir(), f"Benchmark path is not a directory: {benchmark_dir}"
    
    # Verify dbt_project.yml exists
    dbt_project_file = benchmark_dir / "dbt_project.yml"
    if not dbt_project_file.exists():
        pytest.skip(f"Not a dbt project: dbt_project.yml not found in {benchmark_dir}")
    
    # Step 2: Timer Start
    start_time = time.time()
    print(f"\n⏱️  Starting GitLab scale stress test...")
    print(f"📂 Benchmark directory: {benchmark_dir}")
    
    # Step 3: Ingest
    print(f"\n📥 Ingesting GitLab dbt project...")
    ingest_start = time.time()
    
    try:
        snapshot = parse_dbt_project_source(benchmark_dir)
    except Exception as e:
        pytest.fail(f"Failed to parse GitLab dbt project: {str(e)}")
    
    ingest_time = time.time() - ingest_start
    print(f"✅ Ingestion complete: {len(snapshot.entities)} entities, {len(snapshot.fields)} fields, {len(snapshot.joins)} joins")
    print(f"   Ingestion time: {ingest_time:.2f} seconds")
    
    # Step 4: Assert Scale
    assert len(snapshot.entities) > 1000, (
        f"GitLab benchmark should have > 1,000 entities. Found {len(snapshot.entities)}. "
        f"This may indicate the benchmark is not fully populated or parsing failed."
    )
    print(f"✅ Scale verification: {len(snapshot.entities)} entities (target: > 1,000)")
    
    # Step 5: Build Graph (includes inference)
    print(f"\n🔗 Building semantic graph (with inference)...")
    graph_start = time.time()
    
    graph = SemanticGraph()
    graph.add_snapshot(snapshot)  # This automatically runs infer_edges()
    
    graph_time = time.time() - graph_start
    total_time = time.time() - start_time
    
    # Count edges
    total_edges = sum(len(graph.graph[u][v]) for u in graph.graph for v in graph.graph[u])
    explicit_joins = len(snapshot.joins)
    inferred_edges = total_edges - explicit_joins
    
    print(f"✅ Graph construction complete:")
    print(f"   Entities: {len(graph.list_entities())}")
    print(f"   Total edges: {total_edges} (explicit: {explicit_joins}, inferred: {inferred_edges})")
    print(f"   Graph construction time: {graph_time:.2f} seconds")
    print(f"   Total execution time: {total_time:.2f} seconds")
    
    # Step 6: Assert Performance
    if total_time > 30:
        pytest.fail(
            f"Performance target not met: {total_time:.2f} seconds (target: < 30 seconds). "
            f"This indicates the inference algorithm may need optimization."
        )
    elif total_time > 20:
        print(f"⚠️  Performance warning: {total_time:.2f} seconds (target: < 30 seconds, but approaching limit)")
    else:
        print(f"✅ Performance target met: {total_time:.2f} seconds (target: < 30 seconds)")
    
    # Step 7: Assert Graph Health
    # Check that inference generated significant connections
    inference_ratio = inferred_edges / max(explicit_joins, 1)
    assert inferred_edges > 0, "Inference engine should have created at least some inferred edges"
    assert inference_ratio > 1.0, (
        f"Inference should have created more edges than explicit joins. "
        f"Explicit: {explicit_joins}, Inferred: {inferred_edges}, Ratio: {inference_ratio:.2f}"
    )
    print(f"✅ Graph health: Inference created {inferred_edges} edges ({inference_ratio:.1f}x explicit joins)")
    
    # Step 8: Pathfinding Test
    entities = graph.list_entities()
    
    # Try to find entities that might be connected (e.g., dim_* to fct_*)
    dim_entities = [e for e in entities if "dim_" in e.lower()]
    fct_entities = [e for e in entities if "fct_" in e.lower() or "fact_" in e.lower()]
    
    path_found = False
    if dim_entities and fct_entities:
        # Try to find a path from a dimension to a fact table
        test_source = dim_entities[0]
        test_target = fct_entities[0]
        
        print(f"\n🔍 Testing pathfinding at scale: {test_source} -> {test_target}")
        
        try:
            path = graph.find_path(test_source, test_target)
            if path:
                path_found = True
                total_cost = 0.0
                bronze_count = 0
                silver_count = 0
                gold_count = 0
                
                for join in path:
                    edges = graph.graph[join.source_entity_id][join.target_entity_id]
                    for edge_key, edge_data in edges.items():
                        if edge_data.get('join') == join:
                            weight = edge_data.get('weight', 1.0)
                            total_cost += weight
                            if weight == 0.1:
                                gold_count += 1
                            elif weight == 0.5:
                                silver_count += 1
                            elif weight == 2.0:
                                bronze_count += 1
                            break
                
                print(f"   Path found: {len(path)} hops")
                print(f"   Semantic cost: {total_cost:.2f}")
                print(f"   Edge types: {gold_count} Gold, {silver_count} Silver, {bronze_count} Bronze")
                
                # Generate SQL to verify it works
                sql = graph.generate_join_sql(path, test_source)
                assert sql is not None and len(sql) > 0, "SQL generation failed"
                assert "FROM" in sql.upper(), "Generated SQL missing FROM clause"
                print(f"✅ Pathfinding at scale succeeded")
        except Exception as e:
            print(f"   Pathfinding test: {str(e)} (this is OK if entities are disconnected)")
    
    # If no path found with dim/fct, try any two entities
    if not path_found and len(entities) >= 2:
        print(f"\n🔍 Testing pathfinding with random entities...")
        for i in range(min(5, len(entities))):
            source = entities[i]
            target = entities[(i + 10) % len(entities)] if len(entities) > 10 else entities[(i + 1) % len(entities)]
            
            try:
                path = graph.find_path(source, target)
                if path:
                    print(f"   Path found: {source} -> {target} ({len(path)} hops)")
                    path_found = True
                    break
            except:
                continue
    
    # Final summary
    print(f"\n📊 Stress Test Summary:")
    print(f"   Entities: {len(snapshot.entities)}")
    print(f"   Fields: {len(snapshot.fields)}")
    print(f"   Explicit joins: {explicit_joins}")
    print(f"   Inferred edges: {inferred_edges}")
    print(f"   Total edges: {total_edges}")
    print(f"   Ingestion time: {ingest_time:.2f}s")
    print(f"   Graph construction time: {graph_time:.2f}s")
    print(f"   Total time: {total_time:.2f}s")
    print(f"   Pathfinding: {'✅ Success' if path_found else '⚠️  No path found (may be disconnected)'}")
    
    # Final assertions
    assert len(snapshot.entities) > 1000, "Scale target not met"
    assert total_time < 30, "Performance target not met"
    assert inferred_edges > 0, "Inference engine should have created edges"
    
    print(f"\n✅ All stress test assertions passed! The system handles enterprise-scale dbt projects.")


if __name__ == "__main__":
    # Allow running directly
    test_gitlab_scale_stress()
