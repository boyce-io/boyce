"""
DataShark Service Entrypoint

Simple service wrapper around engine.process_request() for extension/MCP integration.
This is the golden path entrypoint that ensures audit logging.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

# Add src to path for imports
import sys
from pathlib import Path as PathType

# Find project root (datashark-mcp directory)
# service.py is at: datashark-mcp/src/datashark/core/service.py
# We need: datashark-mcp/src/ in path
service_file = PathType(__file__).resolve()
mcp_src = service_file.parent.parent.parent.parent / "src"  # Go up to datashark-mcp/src/
if str(mcp_src) not in sys.path:
    sys.path.insert(0, str(mcp_src))

from datashark.core.audit import get_audit_writer, log_artifact
from datashark.ingestion.looker.adapter import LookerAdapter
from datashark_mcp.kernel.engine import DataSharkEngine
from datashark_mcp.kernel.types import UserContext
from datashark_mcp.security.policy import PolicyRule, PolicySet

logger = logging.getLogger(__name__)


def generate_sql(
    prompt: str,
    profile: Optional[str] = None,
    dialect: Optional[str] = None,
    metadata_path: Optional[str] = None,
    audit_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate SQL from natural language prompt using the golden path.
    
    This is the canonical entrypoint that:
    1. Uses engine.process_request() (same as GoldenHarness)
    2. Ensures audit logging happens
    3. Returns structured response with SQL, snapshot_id, and audit artifact path
    
    Args:
        prompt: Natural language query string
        profile: Optional profile name (for future use - currently uses default)
        dialect: Optional SQL dialect (default: "postgres")
        metadata_path: Optional path to LookML JSON file (for MVP, uses default test data)
        audit_dir: Optional audit directory path (default: .datashark/audit/)
        
    Returns:
        Dictionary with:
        - sql: Generated SQL string
        - snapshot_id: SHA-256 snapshot identifier
        - audit_artifact_path: Path to audit JSONL file (or None if logging failed)
        - error: Optional error message if generation failed
        
    Raises:
        ValueError: If prompt is empty or metadata cannot be loaded
    """
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty")
    
    # Set audit directory
    if audit_dir:
        audit_dir_path = Path(audit_dir).resolve()
        audit_dir_path.mkdir(parents=True, exist_ok=True)
        os.environ["DATASHARK_AUDIT_DIR"] = str(audit_dir_path)
    else:
        # Default audit directory
        audit_dir_path = Path.cwd() / ".datashark" / "audit"
        audit_dir_path.mkdir(parents=True, exist_ok=True)
        os.environ["DATASHARK_AUDIT_DIR"] = str(audit_dir_path)
    
    # Reset global audit writer to pick up new directory
    import datashark.core.audit as audit_module
    audit_module._global_writer = None
    
    # For MVP: Use default test LookML (Q1 structure) as metadata source
    # In production, this would load from profile/metadata_path
    # Import from tools directory (not in src/)
    import sys
    tools_path = PathType(__file__).resolve().parent.parent.parent.parent / "tools"
    if str(tools_path) not in sys.path:
        sys.path.insert(0, str(tools_path))
    from golden_harness import create_lookml_for_q1
    lookml_data = create_lookml_for_q1()
    
    # Create snapshot from LookML
    adapter = LookerAdapter()
    snapshot = adapter.ingest(lookml_data)
    
    # Set up engine with user context
    context = UserContext(
        user_id="extension_user",
        roles=["admin"],
        tenant_id="default_tenant"
    )
    engine = DataSharkEngine(context=context)
    
    # Set up permissive policy for MVP
    policy_set = PolicySet(
        rules=[PolicyRule(resource_pattern=".*", allowed_roles=["admin"], action="allow")],
        default_action="deny"
    )
    engine.policy_set = policy_set
    
    # Load metadata into engine
    raw_metadata = {
        "source_system": snapshot.source_system,
        "source_version": snapshot.source_version or "1.0",
        "entities": {eid: {
            "id": e.id,
            "name": e.name,
            "schema": e.schema_name if hasattr(e, 'schema_name') else None,
            "fields": e.fields,
            "grain": e.grain if hasattr(e, 'grain') else None
        } for eid, e in snapshot.entities.items()},
        "fields": {fid: {
            "id": f.id,
            "entity_id": f.entity_id,
            "name": f.name,
            "field_type": f.field_type.value if hasattr(f.field_type, 'value') else str(f.field_type),
            "data_type": f.data_type,
            "nullable": f.nullable if hasattr(f, 'nullable') else None,
            "primary_key": f.primary_key if hasattr(f, 'primary_key') else None
        } for fid, f in snapshot.fields.items()},
        "joins": [{
            "id": j.id if hasattr(j, 'id') else None,
            "source_entity_id": j.source_entity_id,
            "target_entity_id": j.target_entity_id,
            "join_type": j.join_type.value if hasattr(j.join_type, 'value') else str(j.join_type),
            "source_field_id": j.source_field_id,
            "target_field_id": j.target_field_id
        } for j in snapshot.joins],
        "metadata": snapshot.metadata if hasattr(snapshot, 'metadata') else {}
    }
    engine.load_metadata(raw_metadata)
    
    # Get snapshot_id
    snapshot_id_str = engine._snapshot_id.id
    
    # Capture audit files BEFORE processing request
    pre_files = set(audit_dir_path.glob("*.jsonl"))
    
    # Process request (this triggers audit logging)
    try:
        result = engine.process_request(prompt)
        generated_sql = result.get("final_sql_output", "")
        
        # Find the audit file created by THIS run
        post_files = set(audit_dir_path.glob("*.jsonl"))
        new_files = sorted(post_files - pre_files, key=lambda p: p.stat().st_mtime, reverse=True)
        
        audit_artifact_path = None
        if new_files:
            audit_artifact_path = str(new_files[0])
        
        return {
            "sql": generated_sql,
            "snapshot_id": snapshot_id_str,
            "audit_artifact_path": audit_artifact_path,
            "error": None
        }
    except Exception as e:
        logger.error(f"SQL generation failed: {e}", exc_info=True)
        return {
            "sql": None,
            "snapshot_id": snapshot_id_str,
            "audit_artifact_path": None,
            "error": str(e)
        }

