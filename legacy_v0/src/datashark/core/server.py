import sys
import json
import logging
import os
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add src to path for imports if running as script
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Safety Kernel: try extensions/mcp/src (this repo) then datashark-mcp/src (legacy)
_repo_root = src_path.parent
for kernel_src in [_repo_root / "extensions" / "mcp" / "src", _repo_root / "datashark-mcp" / "src"]:
    if kernel_src.exists() and str(kernel_src) not in sys.path:
        sys.path.insert(0, str(kernel_src))
        break

try:
    from safety_kernel.redshift_guardrails import (
        lint_redshift_compat,
        transform_sql_for_redshift_safety,
    )
except ImportError:
    lint_redshift_compat = None
    transform_sql_for_redshift_safety = None

from datashark.core.api import process_request
from datashark.core.graph import SemanticGraph
from datashark.core.parsers import parse_dbt_manifest, parse_dbt_project_source, parse_lookml_file
from datashark.core.types import SemanticSnapshot
from datashark.runtime.planner.planner import QueryPlanner # Keep this import for fallback
from datashark.ingestion.watcher import ProjectWatcher
from datashark.ingestion.sniper import ContextSniper

try:
    from datashark.agent_engine.capabilities.reasoning.brain import DataSharkBrain
except ImportError:
    DataSharkBrain = None

# Configure logging to stderr so it doesn't interfere with stdout JSON-RPC
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("datashark-server")

# Global Brain Instance
brain = None
if DataSharkBrain:
    try:
        brain = DataSharkBrain()
    except Exception as e:
        logger.warning(f"Failed to initialize DataSharkBrain: {e}")

class DataSharkServer:
    def __init__(self):
        self.graph = SemanticGraph()
        self.workspace_root: Optional[Path] = None
        self.context_files: List[str] = []
        self.config: Dict[str, Any] = {}
        
        # Initialize ingestion engine components
        self.sniper: Optional[ContextSniper] = None
        self.watcher: Optional[ProjectWatcher] = None
        
        # Initialize planner (lazy initialization in generate_sql if needed)
        self.planner: Optional[QueryPlanner] = None
        
        # Run bootstrap if brain is available
        self.bootstrap_knowledge()

    def bootstrap_knowledge(self):
        """Scan ddl/ folder and train the brain."""
        if not brain:
            return
            
        ddl_dir = Path(os.getcwd()) / "ddl"
        if not ddl_dir.exists():
            return
            
        count = 0
        for sql_file in ddl_dir.glob("*.sql"):
            try:
                content = sql_file.read_text()
                brain.train(content)
                count += 1
                logger.info(f"🧠 Loaded knowledge from {sql_file.name}")
            except Exception as e:
                logger.warning(f"Failed to load {sql_file.name}: {e}")
        
        if count > 0:
            logger.info(f"🧠 Brain bootstrapped with {count} DDL files.")

    def run(self):
        """Main JSON-RPC loop"""
        logger.info("DataShark Server starting...")
        
        try:
            for line in sys.stdin:
                if not line.strip():
                    continue
                    
                try:
                    request = json.loads(line)
                    response = self.handle_request(request)
                    print(json.dumps(response))
                    sys.stdout.flush()
                except json.JSONDecodeError:
                    self._send_error(None, -32700, "Parse error")
                except Exception as e:
                    logger.error(f"Unexpected error: {e}")
                    logger.error(traceback.format_exc())
                    self._send_error(None, -32603, f"Internal error: {str(e)}")
        finally:
            # Gracefully stop the watcher on shutdown
            if self.watcher is not None:
                try:
                    self.watcher.stop()
                    logger.info("File watcher stopped")
                except Exception as e:
                    logger.warning(f"Error stopping watcher: {e}")

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Route JSON-RPC request to method handler"""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if not method:
            return self._make_error(req_id, -32600, "Invalid Request")

        try:
            if method == "ping":
                result = "pong"
            elif method == "initialize":
                result = self.initialize(params)
            elif method == "ingest_context":
                result = self.ingest_context(params)
            elif method == "generate_sql":
                result = self.generate_sql(params)
            elif method == "verify_sql":
                result = self.verify_sql(params)
            else:
                return self._make_error(req_id, -32601, f"Method not found: {method}")
            
            return {
                "jsonrpc": "2.0",
                "result": result,
                "id": req_id
            }
        except Exception as e:
            logger.error(f"Error handling {method}: {e}")
            logger.error(traceback.format_exc())
            return self._make_error(req_id, -32603, str(e))

    def _make_error(self, req_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
        error = {"code": code, "message": message}
        if data:
            error["data"] = data
        return {
            "jsonrpc": "2.0",
            "error": error,
            "id": req_id
        }

    def _send_error(self, req_id: Any, code: int, message: str):
        response = self._make_error(req_id, code, message)
        print(json.dumps(response))
        sys.stdout.flush()

    # --- Methods ---

    def initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self.workspace_root = Path(params.get("workspace_root", os.getcwd()))
        self.context_files = params.get("context_files", [])
        client_info = params.get("client_info", {})
        
        logger.info(f"Initialized with root: {self.workspace_root}")
        logger.info(f"Client: {client_info.get('name')} {client_info.get('version')}")

        # Initialize ingestion engine components
        self.sniper = ContextSniper()
        
        # Perform initial project scan
        try:
            scanned_files = self.sniper.scan_project(self.workspace_root)
            sys.stderr.write(f"[System] Mapped {len(scanned_files)} files\n")
            sys.stderr.flush()
            logger.info(f"Initial project scan complete: {len(scanned_files)} files mapped")
        except Exception as e:
            logger.warning(f"Failed to scan project: {e}")
            # Continue without initial scan - can scan later
        
        # Start file watcher for real-time ingestion
        try:
            self.watcher = ProjectWatcher(
                root_path=self.workspace_root,
                on_change=self.on_file_change,
                debounce_seconds=0.5
            )
            self.watcher.start()
            logger.info(f"File watcher started for: {self.workspace_root}")
        except Exception as e:
            logger.warning(f"Failed to start file watcher: {e}")
            # Continue without watcher - server can still function

        # Load config if available (e.g. from env vars or .datashark/config.json)
        # For now, we rely on env vars for API keys as per typical server deployment
        
        return {
            "status": "ready",
            "kernel_version": "0.1.0",
            "capabilities": {
                "dbt": True,
                "lookml": True,
                "airflow": False
            }
        }

    def ingest_context(self, params: Dict[str, Any]) -> Dict[str, Any]:
        start_time = __import__("time").time()
        force = params.get("force", False)
        
        if not self.workspace_root:
             raise ValueError("Workspace root not initialized")

        # Basic ingestion logic reused from CLI (simplified)
        # In a real scenario, we would selectively ingest based on context_files
        # For MVP, we auto-scan the root if no specific files parsed, or just parse everything.
        
        sources = []
        
        # 1. dbt Manifest
        manifest_path = None
        for path in [
            self.workspace_root / "target" / "manifest.json",
            self.workspace_root / "dbt" / "target" / "manifest.json",
        ]:
            if path.exists():
                manifest_path = path
                break
        
        if manifest_path:
            try:
                snapshot = parse_dbt_manifest(manifest_path)
                self.graph.add_snapshot(snapshot)
                sources.append("dbt")
            except Exception as e:
                logger.warning(f"Failed to ingest dbt manifest: {e}")

        # 2. LookML
        lookml_files = list(self.workspace_root.glob("*.lkml"))
        if lookml_files:
            count = 0
            for lkml_file in lookml_files[:20]: # Limit for MVP speed
                try:
                    snapshot = parse_lookml_file(lkml_file)
                    self.graph.add_snapshot(snapshot)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to parse {lkml_file}: {e}")
            if count > 0:
                sources.append("lookml")

        # 3. dbt Project (fallback)
        if "dbt" not in sources and (self.workspace_root / "dbt_project.yml").exists():
             try:
                snapshot = parse_dbt_project_source(self.workspace_root)
                self.graph.add_snapshot(snapshot)
                sources.append("dbt_project")
             except Exception as e:
                 logger.warning(f"Failed to parse dbt project: {e}")

        duration = (__import__("time").time() - start_time) * 1000
        
        return {
            "graph_summary": {
                "nodes": len(self.graph.graph.nodes()),
                "edges": len(self.graph.graph.edges()),
                "sources": sources,
                "status": "healthy" if sources else "empty"
            },
            "duration_ms": int(duration)
        }

    def generate_sql(self, params: Dict[str, Any]) -> Dict[str, Any]:
        user_prompt = params.get("user_prompt")
        structured_hints = params.get("structured_filter", {})
        
        if not user_prompt:
            raise ValueError("user_prompt is required")

        # Safety Protocol: SQL comes ONLY from process_request -> SQLBuilder.
        # Brain is used as context via Planner (retrieve_context), not as a SQL compiler.
        if not self.graph.snapshots:
            raise ValueError("Graph is empty. Call ingest_context first.")

        if not self.planner:
            # Try to get credentials from env
            provider = os.environ.get("DATASHARK_PROVIDER", "openai")
            model = os.environ.get("DATASHARK_MODEL", "gpt-4")
            api_key = os.environ.get("LITELLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
            
            if not api_key:
                 # Try loading from config file as fallback
                 config_path = self.workspace_root / ".datashark" / "config.json"
                 if config_path.exists():
                     try:
                         with open(config_path) as f:
                             cfg = json.load(f)
                             api_key = cfg.get("api_key")
                             provider = cfg.get("provider", provider)
                             model = cfg.get("model", model)
                     except:
                         pass

            if not api_key:
                raise ValueError("API Key not found. Please set LITELLM_API_KEY environment variable.")

            self.planner = QueryPlanner(
                provider=provider, model=model, api_key=api_key, brain=brain
            )

        # 1. Plan (Brain context is injected inside plan_query when brain is set)
        structured_filter = self.planner.plan_query(user_prompt, self.graph)
        
        # 2. Merge hints (simple override for dialect/limit if Planner didn't set them or we want to force them)
        # The Kernel's process_request expects the planner output structure mostly.
        # But we can inject dialect into the request logic if needed. 
        # process_request extracts 'dialect' from structured_filter (the dict passed to it).
        if "dialect" in structured_hints:
            structured_filter["dialect"] = structured_hints["dialect"]
            
        # 3. Generate
        # We need a snapshot to pass to process_request. The Kernel currently takes A snapshot.
        # But the Graph might have multiple.
        # The Graph object aggregates them. process_request takes a Snapshot object.
        # We need to create a "Merged Snapshot" or pass the primary one.
        # For MVP, let's use the first available snapshot or a merged view if API supports it.
        # Looking at api.py: process_request(snapshot: SemanticSnapshot, ...)
        # We should probably pass the snapshot that contains the relevant entities?
        # Or maybe we need to update api.py to accept a Graph?
        # For now, let's pick the first one as done in cli.py, noting this is a limitation.
        snapshot = list(self.graph.snapshots.values())[0]

        sql = process_request(snapshot, structured_filter)

        # Redshift/Postgres: post-process with safety kernel when available
        dialect = structured_filter.get("dialect", "postgres")
        if dialect and dialect.lower() in ("postgres", "redshift") and transform_sql_for_redshift_safety:
            sql = transform_sql_for_redshift_safety(sql)

        # 4. Explain (Mock for now, or derive from path)
        explanation = "Generated SQL based on semantic graph path."

        return {
            "sql": sql,
            "explanation": explanation,
            "confidence_score": 1.0, # Placeholder
            "semantic_path": structured_filter.get("join_path", [])
        }

    def verify_sql(self, params: Dict[str, Any]) -> Dict[str, Any]:
        sql = params.get("sql", "")
        if not sql:
             raise ValueError("sql is required")

        risks = []
        is_valid = True
        
        # Use Redshift Guardrails if available
        if lint_redshift_compat:
            compat_errors = lint_redshift_compat(sql)
            if compat_errors:
                is_valid = False # Or just warning?
                for err in compat_errors:
                    risks.append({
                        "severity": "medium",
                        "type": "compatibility",
                        "message": err
                    })
        
        return {
            "is_valid": is_valid,
            "risks": risks
        }

    def on_file_change(self, file_path: Path) -> None:
        """
        Callback invoked when a monitored file changes.
        
        CRITICAL: All output goes to stderr, not stdout, to preserve JSON-RPC protocol.
        
        Args:
            file_path: Path to the file that changed.
        """
        try:
            # Write to stderr (not stdout) to preserve JSON-RPC protocol
            sys.stderr.write(f"[Event] Changed: {file_path}\n")
            sys.stderr.flush()
            
            # Log via logger (which also goes to stderr)
            logger.info(f"File change detected: {file_path}")
            
            # Parse file and extract dependencies
            if self.sniper is not None:
                try:
                    deps = self.sniper.parse_file(file_path)
                    if deps:
                        deps_str = ", ".join(f"'{d}'" for d in deps)
                        sys.stderr.write(f"[Analysis] Found Tables: [{deps_str}]\n")
                        sys.stderr.flush()
                        logger.info(f"Dependencies extracted: {deps}")
                    else:
                        # File might not be SQL or had no parseable tables
                        sys.stderr.write(f"[Analysis] No tables found in {file_path.name}\n")
                        sys.stderr.flush()
                except Exception as parse_error:
                    sys.stderr.write(f"[Analysis] Failed to parse {file_path}: {parse_error}\n")
                    sys.stderr.flush()
                    logger.warning(f"Parse error for {file_path}: {parse_error}")
            
        except Exception as e:
            # Even errors go to stderr
            sys.stderr.write(f"[Error] Failed to process file change for {file_path}: {e}\n")
            sys.stderr.flush()
            logger.error(f"Error in file change callback: {e}", exc_info=True)

if __name__ == "__main__":
    server = DataSharkServer()
    server.run()
