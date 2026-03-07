import subprocess
import json
import sys
import os
from pathlib import Path

def run_test():
    # Path to the CLI entrypoint
    root_dir = Path(__file__).parent.parent
    cli_path = root_dir / "src" / "datashark" / "cli.py"
    fixture_path = root_dir / "tests" / "fixtures" / "golden_repo"
    
    print(f"Starting DataShark Server from {cli_path}...")
    print(f"Using Fixture Root: {fixture_path}")
    
    # Start the server process
    process = subprocess.Popen(
        [sys.executable, str(cli_path), "--server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr, # Let stderr flow through to console for debugging
        text=True,
        cwd=str(root_dir), # Run from project root to ensure imports work
        env={**os.environ, "PYTHONPATH": str(root_dir / "src")}
    )

    try:
        # 1. Test Initialize
        print("\n--- Sending Initialize Request ---")
        init_req = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "workspace_root": str(fixture_path),
                "client_info": {"name": "test-script", "version": "0.1"}
            },
            "id": 1
        }
        process.stdin.write(json.dumps(init_req) + "\n")
        process.stdin.flush()
        
        response_line = process.stdout.readline()
        print(f"Received: {response_line.strip()}")
        response = json.loads(response_line)
        
        assert response["jsonrpc"] == "2.0"
        assert response["result"]["status"] == "ready"
        print("✅ Initialize Success")

        # 2. Test Ingest (Expecting Nodes!)
        print("\n--- Sending Ingest Request ---")
        ingest_req = {
            "jsonrpc": "2.0",
            "method": "ingest_context",
            "params": {"force": True},
            "id": 2
        }
        process.stdin.write(json.dumps(ingest_req) + "\n")
        process.stdin.flush()
        
        response_line = process.stdout.readline()
        print(f"Received: {response_line.strip()}")
        response = json.loads(response_line)
        
        result = response["result"]
        summary = result["graph_summary"]
        
        print(f"Graph Summary: {summary}")
        
        # Assertion: Must have ingested nodes from manifest.json or lkml
        assert summary["nodes"] > 0, "Graph is empty! Ingestion failed to find fixture files."
        assert "dbt" in summary["sources"] or "lookml" in summary["sources"], "Source types not detected."
        
        print("✅ Ingest Success (Nodes found)")

    finally:
        process.terminate()

if __name__ == "__main__":
    run_test()
