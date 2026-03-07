#!/usr/bin/env python3
"""
Determinism and Consistency Audit Script

Runs full pipeline reproducibility tests across:
1. Ingestion determinism
2. ADCIL determinism  
3. Learning reproducibility
4. Query reproducibility
"""
import subprocess
import sys
import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
INSTANCE_NAME = "audit_temp"
RESULTS_DIR = Path("/tmp/determinism_audit")
RESULTS_DIR.mkdir(exist_ok=True)

def run_cmd(cmd, cwd=None, capture_output=True):
    """Run a command and return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd or PROJECT_ROOT,
            capture_output=capture_output,
            text=True,
            check=False
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def sha256_file(filepath):
    """Compute SHA256 hash of a file."""
    if not Path(filepath).exists():
        return None
    with open(filepath, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def test_ingestion_determinism():
    """Test 1: Ingestion determinism - run twice, compare hashes."""
    print("\n" + "="*80)
    print("TEST 1: Ingestion Determinism")
    print("="*80)
    
    instance_path = Path.home() / "DataShark_Instances" / INSTANCE_NAME
    manifests_dir = instance_path / "manifests"
    
    # Run ingestion twice
    print("\nRunning first ingestion...")
    code1, out1, err1 = run_cmd(
        f"python3 -m tools.instance_manager.cli build --name {INSTANCE_NAME}",
        capture_output=True
    )
    
    if code1 != 0:
        print(f"ERROR: First ingestion failed:\n{err1}")
        return False, "First ingestion failed"
    
    # Find nodes.jsonl
    nodes_files = list(manifests_dir.glob("**/nodes.jsonl"))
    if not nodes_files:
        print("WARNING: No nodes.jsonl found after first ingestion")
        return False, "No nodes.jsonl generated"
    
    nodes_file = nodes_files[0]
    hash1 = sha256_file(nodes_file)
    print(f"First run hash: {hash1}")
    print(f"Nodes file: {nodes_file}")
    
    # Clean and run again
    print("\nCleaning manifests...")
    if manifests_dir.exists():
        shutil.rmtree(manifests_dir)
        manifests_dir.mkdir(parents=True, exist_ok=True)
    
    print("Running second ingestion...")
    code2, out2, err2 = run_cmd(
        f"python3 -m tools.instance_manager.cli build --name {INSTANCE_NAME}",
        capture_output=True
    )
    
    if code2 != 0:
        print(f"ERROR: Second ingestion failed:\n{err2}")
        return False, "Second ingestion failed"
    
    nodes_files2 = list(manifests_dir.glob("**/nodes.jsonl"))
    if not nodes_files2:
        print("WARNING: No nodes.jsonl found after second ingestion")
        return False, "No nodes.jsonl generated on second run"
    
    nodes_file2 = nodes_files2[0]
    hash2 = sha256_file(nodes_file2)
    print(f"Second run hash: {hash2}")
    
    # Compare
    if hash1 == hash2:
        print("\n✅ PASS: Ingestion determinism verified - identical hashes")
        return True, f"Identical hashes: {hash1}"
    else:
        print(f"\n❌ FAIL: Hashes differ:\n  Run 1: {hash1}\n  Run 2: {hash2}")
        return False, f"Hashes differ: {hash1} vs {hash2}"

def test_adcil_determinism():
    """Test 2: ADCIL determinism - check telemetry logs."""
    print("\n" + "="*80)
    print("TEST 2: ADCIL Determinism")
    print("="*80)
    
    instance_path = Path.home() / "DataShark_Instances" / INSTANCE_NAME
    logs_dir = instance_path / "logs"
    telemetry_file = logs_dir / "telemetry.jsonl"
    
    if not telemetry_file.exists():
        print("WARNING: No telemetry.jsonl found")
        return False, "No telemetry file"
    
    # Read ADCIL entries
    adcil_entries = []
    with open(telemetry_file, 'r') as f:
        for line in f:
            if line.strip() and "ADCIL" in line:
                try:
                    entry = json.loads(line)
                    adcil_entries.append(entry)
                except:
                    pass
    
    if len(adcil_entries) < 2:
        print("WARNING: Insufficient ADCIL entries for comparison")
        return False, "Insufficient ADCIL entries"
    
    # Extract concept/join counts from last 10 entries
    recent_entries = adcil_entries[-10:]
    counts = []
    for entry in recent_entries:
        if isinstance(entry, dict):
            counts.append({
                "concepts": entry.get("concept_count", 0),
                "joins": entry.get("join_count", 0),
                "timestamp": entry.get("timestamp", "")
            })
    
    print(f"\nFound {len(counts)} recent ADCIL entries")
    if counts:
        print(f"Sample counts: {counts[0]}")
    
    # Check for consistency
    if len(set(c["concepts"] for c in counts)) == 1 and len(set(c["joins"] for c in counts)) == 1:
        print("\n✅ PASS: ADCIL determinism - consistent concept/join counts")
        return True, f"Consistent counts: {counts[0]}"
    else:
        print(f"\n⚠️  WARNING: ADCIL counts vary across entries")
        return False, f"Varying counts: {counts}"

def test_learning_reproducibility():
    """Test 3: Learning reproducibility - run twice, compare outputs."""
    print("\n" + "="*80)
    print("TEST 3: Learning Reproducibility")
    print("="*80)
    
    # Run learn twice
    print("\nRunning first learn...")
    code1, out1, err1 = run_cmd(
        f"python3 -m tools.instance_manager.cli learn --instance {INSTANCE_NAME}",
        capture_output=True
    )
    
    if code1 != 0:
        print(f"ERROR: First learn failed:\n{err1}")
        return False, "First learn failed"
    
    # Save output
    output1_file = RESULTS_DIR / "learn_output1.txt"
    with open(output1_file, 'w') as f:
        f.write(out1)
    
    print("Running second learn...")
    code2, out2, err2 = run_cmd(
        f"python3 -m tools.instance_manager.cli learn --instance {INSTANCE_NAME}",
        capture_output=True
    )
    
    if code2 != 0:
        print(f"ERROR: Second learn failed:\n{err2}")
        return False, "Second learn failed"
    
    # Save output
    output2_file = RESULTS_DIR / "learn_output2.txt"
    with open(output2_file, 'w') as f:
        f.write(out2)
    
    # Compare
    if out1 == out2:
        print("\n✅ PASS: Learning reproducibility - identical outputs")
        return True, "Identical outputs"
    else:
        # Extract metrics for comparison
        metrics1 = extract_metrics(out1)
        metrics2 = extract_metrics(out2)
        
        if metrics1 == metrics2:
            print("\n✅ PASS: Learning reproducibility - identical metrics")
            return True, f"Identical metrics: {metrics1}"
        else:
            print(f"\n❌ FAIL: Metrics differ:\n  Run 1: {metrics1}\n  Run 2: {metrics2}")
            return False, f"Metrics differ: {metrics1} vs {metrics2}"

def extract_metrics(output):
    """Extract metrics from learn output."""
    metrics = {}
    for line in output.split('\n'):
        if 'accuracy' in line.lower() or 'precision' in line.lower() or 'recall' in line.lower():
            # Try to extract numbers
            parts = line.split()
            for i, part in enumerate(parts):
                if part.lower() in ['accuracy', 'precision', 'recall'] and i + 1 < len(parts):
                    try:
                        metrics[part.lower()] = float(parts[i+1])
                    except:
                        pass
    return metrics

def test_query_reproducibility():
    """Test 4: Query reproducibility - run same query twice."""
    print("\n" + "="*80)
    print("TEST 4: Query Reproducibility")
    print("="*80)
    
    # Use Python to call run_query via MCP server components
    query_script = RESULTS_DIR / "test_query.py"
    query_script.write_text("""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "datashark-mcp" / "src"))
sys.path.insert(0, str(project_root / "tools"))

from datashark_mcp.agentic.runtime.executor import Executor
from datashark_mcp.agentic.runtime.planner import Planner
from datashark_mcp.agentic.runtime.context_bridge import ContextBridge
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.context.store.json_store import JSONStore
from datashark_mcp.context.enrichment.concept_catalog import ConceptCatalog
from instance_manager.registry import InstanceRegistry

instance_name = sys.argv[1]
query = sys.argv[2]

# Load instance
registry = InstanceRegistry()
instance_info = registry.get_instance(instance_name)
if not instance_info:
    print(f"ERROR: Instance '{instance_name}' not found")
    sys.exit(1)

instance_path = Path(instance_info["path"])
manifests_dir = instance_path / "manifests"

# Find latest manifest
manifest_dirs = sorted(manifests_dir.glob("*/"), reverse=True)
if not manifest_dirs:
    print("ERROR: No manifests found")
    sys.exit(1)

# Load graph
json_store = JSONStore(manifest_dirs[0])
nodes_data, edges_data, _ = json_store.load()

from datashark_mcp.context.store import GraphStore
from datashark_mcp.context.models import Node, Edge

store = GraphStore()
for node_data in nodes_data:
    node = Node.from_dict(node_data)
    store.add_node(node)
for edge_data in edges_data:
    edge = Edge.from_dict(edge_data)
    store.add_edge(edge)

# Initialize executor
api = ContextAPI(store)
catalog = ConceptCatalog()
bridge = ContextBridge(api, catalog=catalog)
planner = Planner(bridge, seed=42)
executor = Executor(planner)

# Execute query
result = executor.execute(query)
import json
print(json.dumps({
    "trace_id": result.get("trace_id", ""),
    "success": result.get("success", False),
    "count": len(result.get("results", []))
}))
""")
    
    # Run query twice
    print("\nRunning first query...")
    code1, out1, err1 = run_cmd(
        f"python3 {query_script} {INSTANCE_NAME} 'SELECT 1'",
        capture_output=True
    )
    
    if code1 != 0:
        print(f"ERROR: First query failed:\n{err1}")
        return False, "First query failed"
    
    print("Running second query...")
    code2, out2, err2 = run_cmd(
        f"python3 {query_script} {INSTANCE_NAME} 'SELECT 1'",
        capture_output=True
    )
    
    if code2 != 0:
        print(f"ERROR: Second query failed:\n{err2}")
        return False, "Second query failed"
    
    # Parse results
    try:
        result1 = json.loads(out1.strip())
        result2 = json.loads(out2.strip())
        
        trace_id1 = result1.get("trace_id", "")
        trace_id2 = result2.get("trace_id", "")
        
        if trace_id1 and trace_id2:
            # Check if trace IDs follow same pattern (should be deterministic)
            if trace_id1 == trace_id2:
                print("\n✅ PASS: Query reproducibility - identical trace IDs")
                return True, f"Identical trace IDs: {trace_id1}"
            else:
                # Check if they're from same sequence
                print(f"\n⚠️  WARNING: Trace IDs differ: {trace_id1} vs {trace_id2}")
                return False, f"Trace IDs differ: {trace_id1} vs {trace_id2}"
        else:
            print("\n⚠️  WARNING: No trace IDs in results")
            return False, "No trace IDs"
    except Exception as e:
        print(f"\nERROR: Failed to parse results: {e}")
        return False, f"Parse error: {e}"

def main():
    """Run all determinism tests."""
    print("="*80)
    print("DataShark Determinism and Consistency Audit")
    print("="*80)
    print(f"Instance: {INSTANCE_NAME}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    results = {}
    
    # Test 1: Ingestion
    try:
        passed, msg = test_ingestion_determinism()
        results["ingestion"] = {"passed": passed, "message": msg}
    except Exception as e:
        results["ingestion"] = {"passed": False, "message": f"Exception: {e}"}
    
    # Test 2: ADCIL
    try:
        passed, msg = test_adcil_determinism()
        results["adcil"] = {"passed": passed, "message": msg}
    except Exception as e:
        results["adcil"] = {"passed": False, "message": f"Exception: {e}"}
    
    # Test 3: Learning
    try:
        passed, msg = test_learning_reproducibility()
        results["learning"] = {"passed": passed, "message": msg}
    except Exception as e:
        results["learning"] = {"passed": False, "message": f"Exception: {e}"}
    
    # Test 4: Query
    try:
        passed, msg = test_query_reproducibility()
        results["query"] = {"passed": passed, "message": msg}
    except Exception as e:
        results["query"] = {"passed": False, "message": f"Exception: {e}"}
    
    # Generate summary
    print("\n" + "="*80)
    print("AUDIT SUMMARY")
    print("="*80)
    
    summary_file = RESULTS_DIR / "audit_summary.txt"
    with open(summary_file, 'w') as f:
        f.write("DataShark Determinism and Consistency Audit\n")
        f.write("="*80 + "\n")
        f.write(f"Instance: {INSTANCE_NAME}\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n\n")
        
        for test_name, result in results.items():
            status = "✅ PASS" if result["passed"] else "❌ FAIL"
            f.write(f"{test_name.upper()}: {status}\n")
            f.write(f"  {result['message']}\n\n")
        
        # Overall
        all_passed = all(r["passed"] for r in results.values())
        overall = "✅ ALL TESTS PASSED" if all_passed else "❌ SOME TESTS FAILED"
        f.write(f"\nOVERALL: {overall}\n")
    
    # Print summary
    for test_name, result in results.items():
        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"{test_name.upper()}: {status}")
        print(f"  {result['message']}")
    
    all_passed = all(r["passed"] for r in results.values())
    overall = "✅ ALL TESTS PASSED" if all_passed else "❌ SOME TESTS FAILED"
    print(f"\nOVERALL: {overall}")
    print(f"\nSummary saved to: {summary_file}")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())

