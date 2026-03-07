"""
Performance Benchmark Harness

Measures p50/p95 latency for key operations and enforces performance budgets.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timezone
from typing import List, Dict, Any
from datashark_mcp.context.store import GraphStore
from datashark_mcp.context.fixtures.synthetic_graph import generate_synthetic_graph


class BenchmarkResult:
    """Result of a single benchmark operation."""
    
    def __init__(self, op: str, latencies_ms: List[float], node_count: int, edge_count: int):
        self.op = op
        self.latencies_ms = latencies_ms
        self.node_count = node_count
        self.edge_count = edge_count
        self.p50_ms = statistics.median(latencies_ms)
        self.p95_ms = statistics.quantiles(latencies_ms, n=20)[18] if len(latencies_ms) > 1 else latencies_ms[0]
        self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_json(self) -> Dict[str, Any]:
        """Convert to JSON for logging."""
        return {
            "op": self.op,
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "timestamp": self.timestamp
        }
    
    def check_budget(self, budget_p95_ms: float) -> bool:
        """Check if p95 meets budget."""
        return self.p95_ms <= budget_p95_ms


def benchmark_get_node(store: GraphStore, node_ids: List[str], iterations: int = 1000) -> BenchmarkResult:
    """Benchmark ID lookup."""
    latencies = []
    
    for _ in range(iterations):
        node_id = node_ids[len(latencies) % len(node_ids)]
        start = time.time()
        store.get_node(node_id)
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    
    return BenchmarkResult("get_node", latencies, store.get_node_count(), store.get_edge_count())


def benchmark_search(store: GraphStore, iterations: int = 100) -> BenchmarkResult:
    """Benchmark filtered search."""
    latencies = []
    search_terms = ["entity_000", "entity_001", "entity_002", "entity_003", "entity_004"]
    
    for _ in range(iterations):
        term = search_terms[len(latencies) % len(search_terms)]
        filters = {"system": ["database", "dbt"]} if len(latencies) % 2 == 0 else None
        start = time.time()
        store.search(term, filters)
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    
    return BenchmarkResult("search", latencies, store.get_node_count(), store.get_edge_count())


def benchmark_bfs(store: GraphStore, node_ids: List[str], iterations: int = 50) -> BenchmarkResult:
    """Benchmark single-source BFS."""
    latencies = []
    
    for i in range(iterations):
        node_id = node_ids[i % len(node_ids)]
        start = time.time()
        store.find_join_paths_from(node_id, max_depth=4)
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    
    return BenchmarkResult("bfs_single_source", latencies, store.get_node_count(), store.get_edge_count())


def benchmark_cross_system_bfs(store: GraphStore, node_ids: List[str], iterations: int = 50) -> BenchmarkResult:
    """Benchmark cross-system BFS."""
    latencies = []
    
    for i in range(iterations):
        node_id = node_ids[i % len(node_ids)]
        start = time.time()
        store.find_join_paths_from(node_id, max_depth=4)
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    
    return BenchmarkResult("bfs_cross_system", latencies, store.get_node_count(), store.get_edge_count())


def benchmark_semantic_enrichment(store: GraphStore, iterations: int = 1) -> BenchmarkResult:
    """Benchmark semantic enrichment pass."""
    from datashark_mcp.context.enrichment.concept_catalog import ConceptCatalog
    from datashark_mcp.context.enrichment.semantic_enricher import SemanticEnricher
    
    latencies = []
    
    for _ in range(iterations):
        import tempfile
        from pathlib import Path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_file = Path(tmpdir) / "concepts.json"
            catalog = ConceptCatalog(concepts_file=catalog_file)
            catalog.add_concept("Revenue", "Total income")
            
            enricher = SemanticEnricher(store, catalog)
            
            start = time.time()
            enricher.enrich()
            duration_ms = (time.time() - start) * 1000
            latencies.append(duration_ms)
    
    return BenchmarkResult("semantic_enrichment", latencies, store.get_node_count(), store.get_edge_count())


def benchmark_dsl_query(store: GraphStore, iterations: int = 100) -> BenchmarkResult:
    """Benchmark DSL query execution."""
    from datashark_mcp.context.api import ContextAPI
    from datashark_mcp.context.query.dsl_parser import DSLParser
    from datashark_mcp.context.query.executor import QueryExecutor
    
    api = ContextAPI(store)
    parser = DSLParser()
    executor = QueryExecutor(api)
    
    latencies = []
    queries = [
        "FIND ENTITY WHERE system='database'",
        "SEARCH 'revenue'",
        "FIND ENTITY WHERE system IN ['database', 'dbt']"
    ]
    
    for i in range(iterations):
        query = queries[i % len(queries)]
        ast = parser.parse(query)
        
        start = time.time()
        executor.execute(ast)
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    
    return BenchmarkResult("dsl_query", latencies, store.get_node_count(), store.get_edge_count())


def benchmark_nl_translation(store: GraphStore, iterations: int = 100) -> BenchmarkResult:
    """Benchmark NL to DSL translation."""
    from datashark_mcp.agentic.nl2dsl.translator import NLTranslator
    
    translator = NLTranslator()
    queries = [
        "Show database entities",
        "Find revenue tables",
        "Path between Product and Revenue",
        "Search for orders"
    ]
    
    latencies = []
    for i in range(iterations):
        query = queries[i % len(queries)]
        start = time.time()
        translator.translate(query)
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    
    return BenchmarkResult("nl_translation", latencies, store.get_node_count(), store.get_edge_count())


def benchmark_reasoning_execution(store: GraphStore, iterations: int = 50) -> BenchmarkResult:
    """Benchmark reasoning execution (plan + execute)."""
    from datashark_mcp.context.api import ContextAPI
    from datashark_mcp.context.enrichment.concept_catalog import ConceptCatalog
    from datashark_mcp.agentic.runtime.context_bridge import ContextBridge
    from datashark_mcp.agentic.runtime.planner import Planner
    from datashark_mcp.agentic.runtime.executor import Executor
    
    api = ContextAPI(store)
    catalog = ConceptCatalog()
    bridge = ContextBridge(api, catalog=catalog)
    planner = Planner(bridge, seed=42)
    executor = Executor(planner)
    
    queries = [
        "Show database entities",
        "Find entities in database",
        "Search for revenue"
    ]
    
    latencies = []
    for i in range(iterations):
        query = queries[i % len(queries)]
        start = time.time()
        executor.execute(query)
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    
    return BenchmarkResult("reasoning_execution", latencies, store.get_node_count(), store.get_edge_count())


def benchmark_explanation_rendering(store: GraphStore, iterations: int = 100) -> BenchmarkResult:
    """Benchmark explanation rendering."""
    from datashark_mcp.agentic.explain.tracer import Tracer
    from datashark_mcp.agentic.explain.formatter import ExplanationFormatter
    
    latencies = []
    for _ in range(iterations):
        tracer = Tracer()
        tracer.start()
        tracer.add_step(1, "find_entities", duration_ms=10.0)
        tracer.add_step(2, "find_join_path", duration_ms=20.0)
        
        start = time.time()
        ExplanationFormatter.to_markdown(tracer)
        ExplanationFormatter.to_json(tracer)
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    
    return BenchmarkResult("explanation_rendering", latencies, store.get_node_count(), store.get_edge_count())


def benchmark_learning_loop(instance_path: str, iterations: int = 10) -> BenchmarkResult:
    """Benchmark learning loop (feedback + retraining + evaluation)."""
    from pathlib import Path
    from datashark_mcp.agentic.learning.feedback_collector import FeedbackCollector
    from datashark_mcp.agentic.learning.model_updater import ModelUpdater
    from datashark_mcp.agentic.learning.evaluation_tracker import EvaluationTracker
    
    latencies = []
    instance_path_obj = Path(instance_path)
    
    for _ in range(iterations):
        start = time.time()
        
        # Collect feedback
        collector = FeedbackCollector(instance_path_obj)
        feedback = collector.aggregate_feedback()
        
        # Retrain models
        updater = ModelUpdater(instance_path_obj, seed=42)
        model_updates = updater.retrain_models()
        
        # Evaluate
        tracker = EvaluationTracker(instance_path_obj)
        metrics = tracker.get_metrics_summary()
        
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    
    return BenchmarkResult("learning_loop", latencies, 0, 0)


def benchmark_query_execution(store: GraphStore, iterations: int = 50) -> BenchmarkResult:
    """Benchmark query execution (NL → Result)."""
    from datashark_mcp.context.api import ContextAPI
    from datashark_mcp.context.enrichment.concept_catalog import ConceptCatalog
    from datashark_mcp.agentic.runtime.context_bridge import ContextBridge
    from datashark_mcp.agentic.runtime.planner import Planner
    from datashark_mcp.agentic.runtime.executor import Executor
    
    api = ContextAPI(store)
    catalog = ConceptCatalog()
    bridge = ContextBridge(api, catalog=catalog)
    planner = Planner(bridge, seed=42)
    executor = Executor(planner)
    
    queries = [
        "Show database entities",
        "Find revenue tables",
        "Search for orders"
    ]
    
    latencies = []
    for i in range(iterations):
        query = queries[i % len(queries)]
        start = time.time()
        result = executor.execute(query)
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    
    return BenchmarkResult("query_execution", latencies, store.get_node_count(), store.get_edge_count())


def benchmark_end_to_end(store: GraphStore, iterations: int = 30) -> BenchmarkResult:
    """Benchmark end-to-end NL → Result pipeline."""
    from datashark_mcp.context.api import ContextAPI
    from datashark_mcp.context.enrichment.concept_catalog import ConceptCatalog
    from datashark_mcp.agentic.runtime.context_bridge import ContextBridge
    from datashark_mcp.agentic.runtime.planner import Planner
    from datashark_mcp.agentic.runtime.executor import Executor
    from datashark_mcp.agentic.explain.tracer import Tracer
    
    api = ContextAPI(store)
    catalog = ConceptCatalog()
    bridge = ContextBridge(api, catalog=catalog)
    planner = Planner(bridge, seed=42)
    executor = Executor(planner)
    
    queries = [
        "Show database entities",
        "Find revenue tables",
        "Search for orders"
    ]
    
    latencies = []
    for i in range(iterations):
        query = queries[i % len(queries)]
        
        # Full pipeline: NL → DSL → Plan → Execute → Trace
        start = time.time()
        
        tracer = Tracer()
        tracer.start()
        
        result = executor.execute(query)
        
        # Get trace
        trace = tracer.get_trace()
        
        duration_ms = (time.time() - start) * 1000
        latencies.append(duration_ms)
    
    return BenchmarkResult("end_to_end", latencies, store.get_node_count(), store.get_edge_count())


def run_benchmarks(
    num_nodes: int = 50000,
    num_edges: int = 100000,
    seed: int = 42
) -> List[BenchmarkResult]:
    """
    Run all benchmarks on synthetic graph.
    
    Args:
        num_nodes: Number of nodes to generate
        num_edges: Number of edges to generate
        seed: Random seed for deterministic generation
        
    Returns:
        List of BenchmarkResult objects
    """
    print(f"Generating synthetic graph: {num_nodes} nodes, {num_edges} edges...", file=sys.stderr)
    nodes, edges = generate_synthetic_graph(num_nodes, num_edges, seed)
    
    print(f"Loading graph into store...", file=sys.stderr)
    store = GraphStore()
    node_ids = []
    for node in nodes:
        store.add_node(node)
        node_ids.append(node.id)
    for edge in edges:
        store.add_edge(edge)
    
    print(f"Graph loaded: {store.get_node_count()} nodes, {store.get_edge_count()} edges", file=sys.stderr)
    
    results = []
    
    print("Benchmarking get_node...", file=sys.stderr)
    results.append(benchmark_get_node(store, node_ids))
    
    print("Benchmarking search...", file=sys.stderr)
    results.append(benchmark_search(store))
    
    print("Benchmarking BFS (single-source)...", file=sys.stderr)
    results.append(benchmark_bfs(store, node_ids))
    
    print("Benchmarking BFS (cross-system)...", file=sys.stderr)
    results.append(benchmark_cross_system_bfs(store, node_ids))
    
    print("Benchmarking semantic enrichment...", file=sys.stderr)
    results.append(benchmark_semantic_enrichment(store))
    
    print("Benchmarking DSL query...", file=sys.stderr)
    results.append(benchmark_dsl_query(store))
    
    print("Benchmarking NL translation...", file=sys.stderr)
    results.append(benchmark_nl_translation(store))
    
    print("Benchmarking reasoning execution...", file=sys.stderr)
    results.append(benchmark_reasoning_execution(store))
    
    print("Benchmarking explanation rendering...", file=sys.stderr)
    results.append(benchmark_explanation_rendering(store))
    
    print("Benchmarking query execution (NL → Result)...", file=sys.stderr)
    results.append(benchmark_query_execution(store))
    
    print("Benchmarking end-to-end (NL → Result)...", file=sys.stderr)
    results.append(benchmark_end_to_end(store))
    
    return results


def main():
    """Run benchmarks and output JSON lines."""
    import argparse
    
    parser = argparse.ArgumentParser(description="DataShark Performance Benchmarks")
    parser.add_argument("--phase", type=str, choices=["all", "end_to_end", "query_execution", "learning_loop"],
                        default="all", help="Benchmark phase to run")
    parser.add_argument("--runs", type=int, default=30, help="Number of iterations to run")
    parser.add_argument("--instance", type=str, help="Instance path for loading graph (optional)")
    
    args = parser.parse_args()
    
    # Load graph from instance if provided
    store = None
    if args.instance:
        from pathlib import Path
        import sys
        project_root = Path(__file__).resolve().parents[5]
        sys.path.insert(0, str(project_root / "tools"))
        from instance_manager.registry import InstanceRegistry
        from datashark_mcp.context.store import GraphStore
        from datashark_mcp.context.store.json_store import JSONStore
        from datashark_mcp.context.models import Node, Edge
        
        registry = InstanceRegistry()
        instance_info = registry.get_instance(args.instance)
        if not instance_info:
            print(f"ERROR: Instance '{args.instance}' not found", file=sys.stderr)
            sys.exit(1)
        
        instance_path = Path(instance_info["path"])
        manifests_dir = instance_path / "manifests"
        
        # Check if manifests are directly in manifests_dir or in subdirectories
        manifest_files = list(manifests_dir.glob("manifest.json"))
        if not manifest_files:
            # Try subdirectories
            manifest_dirs = sorted([d for d in manifests_dir.glob("*/") if d.is_dir()], reverse=True)
            if manifest_dirs:
                json_store = JSONStore(manifest_dirs[0])
            else:
                print(f"ERROR: No manifests found in {manifests_dir}", file=sys.stderr)
                sys.exit(1)
        else:
            # Manifests are directly in manifests_dir
            json_store = JSONStore(manifests_dir)
        nodes_data, edges_data, _ = json_store.load()
        
        store = GraphStore()
        for node_data in nodes_data:
            node = Node.from_dict(node_data)
            store.add_node(node)
        for edge_data in edges_data:
            edge = Edge.from_dict(edge_data)
            store.add_edge(edge)
        
        print(f"Loaded graph from instance: {store.get_node_count()} nodes, {store.get_edge_count()} edges", file=sys.stderr)
    else:
        # Generate synthetic graph for benchmarks
        store = None  # Will be created below
    
    # Run specific phase if requested
    if args.phase == "end_to_end":
        if store is None:
            # Generate synthetic graph
            nodes, edges = generate_synthetic_graph(50000, 100000, 42)
            from datashark_mcp.context.store import GraphStore
            store = GraphStore()
            for node in nodes:
                store.add_node(node)
            for edge in edges:
                store.add_edge(edge)
        results = [benchmark_end_to_end(store, iterations=args.runs)]
    elif args.phase == "query_execution":
        if store is None:
            nodes, edges = generate_synthetic_graph(50000, 100000, 42)
            from datashark_mcp.context.store import GraphStore
            store = GraphStore()
            for node in nodes:
                store.add_node(node)
            for edge in edges:
                store.add_edge(edge)
        results = [benchmark_query_execution(store, iterations=args.runs)]
    elif args.phase == "learning_loop":
        if not args.instance:
            print("ERROR: --instance required for learning_loop benchmark", file=sys.stderr)
            sys.exit(1)
        # instance_info already loaded above
        if not instance_info:
            print(f"ERROR: Instance '{args.instance}' not found", file=sys.stderr)
            sys.exit(1)
        instance_path = Path(instance_info["path"])
        results = [benchmark_learning_loop(str(instance_path), iterations=args.runs)]
    else:
        # Run all benchmarks
        if store is None:
            results = run_benchmarks(num_nodes=50000, num_edges=100000, seed=42)
        else:
            # Run benchmarks on loaded store
            node_ids = [node.id for node in store.nodes()]
            results = []
            results.append(benchmark_get_node(store, node_ids))
            results.append(benchmark_search(store))
            results.append(benchmark_bfs(store, node_ids))
            results.append(benchmark_cross_system_bfs(store, node_ids))
            results.append(benchmark_semantic_enrichment(store))
            results.append(benchmark_dsl_query(store))
            results.append(benchmark_nl_translation(store))
            results.append(benchmark_reasoning_execution(store))
            results.append(benchmark_explanation_rendering(store))
            results.append(benchmark_query_execution(store))
            results.append(benchmark_end_to_end(store))
    
    budgets = {
        "get_node": 1.0,
        "search": 10.0,
        "bfs_single_source": 100.0,
        "bfs_cross_system": 100.0,
        "semantic_enrichment": 500.0,  # ≤500ms for 10k nodes
        "dsl_query": 30.0,  # ≤30ms for filtered queries
        "nl_translation": 50.0,  # ≤50ms p95
        "reasoning_execution": 200.0,  # ≤200ms p95
        "explanation_rendering": 100.0,  # ≤100ms p95
        "learning_loop": 500.0,  # ≤500ms p95
        "query_execution": 300.0,  # ≤300ms p95
        "end_to_end": 500.0,  # ≤500ms p95 (NL → Result)
    }
    
    failed = False
    
    for result in results:
        # Output JSON line
        print(json.dumps(result.to_json()))
        
        # Check budget
        budget = budgets.get(result.op)
        if budget:
            if not result.check_budget(budget):
                print(
                    f"ERROR: {result.op} p95 {result.p95_ms:.3f}ms exceeds budget {budget}ms",
                    file=sys.stderr
                )
                failed = True
    
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

