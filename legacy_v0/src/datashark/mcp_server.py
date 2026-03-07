#!/usr/bin/env python3
"""
DataShark MCP Server Entrypoint — DEPRECATED (Hand-Rolled Loop)

.. deprecated::
   Use datashark.mcp_app (FastMCP / official MCP SDK) instead. This module
   is kept only for compatibility during migration.

This was the legacy MCP server with a custom JSON-RPC/stdio loop.
The canonical MCP entrypoint is now: python -m datashark.mcp_app

KILL LIST (do not delete until Cursor/config and any bundles point at mcp_app):
  - handle_mcp_request() (lines ~507–622)
  - main() (lines ~632–682)
  - if __name__ == "__main__": asyncio.run(main()) (lines ~685–686)
  - The entire hand-rolled stdio loop (for line in sys.stdin ...)

Helper functions used by mcp_app or tests may be retained or moved:
  - save_snapshot_to_local_context, load_snapshot_from_local_context
  - mock_agent_ingestion, mock_chat_interface
  - handle_tool_call (logic ported to mcp_app; can be removed when loop is removed)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add src to path for imports
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from datashark.core.api import process_request
from datashark.core.graph import SemanticGraph
from datashark.core.parsers import detect_source_type, parse_dbt_manifest, parse_lookml_file
from datashark.core.types import SemanticSnapshot
from datashark.core.validation import validate_snapshot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Local context directory for snapshots
# mcp_server.py is at: src/datashark/mcp_server.py
# So we need to go up 3 levels to reach repo root
LOCAL_CONTEXT_DIR = Path(__file__).parent.parent.parent / "_local_context"

# Global semantic graph (maintains state across tool calls)
_global_graph = SemanticGraph()


def save_snapshot_to_local_context(snapshot: SemanticSnapshot, snapshot_name: str) -> Path:
    """
    Save a snapshot to _local_context/ directory.
    
    Args:
        snapshot: SemanticSnapshot to save
        snapshot_name: Name for the snapshot file (without extension)
        
    Returns:
        Path to saved snapshot file
    """
    LOCAL_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    
    snapshot_file = LOCAL_CONTEXT_DIR / f"{snapshot_name}.json"
    
    # Serialize snapshot to JSON
    snapshot_dict = snapshot.model_dump(mode='json')
    
    with open(snapshot_file, "w") as f:
        json.dump(snapshot_dict, f, indent=2)
    
    logger.info(f"Saved snapshot to {snapshot_file}")
    return snapshot_file


def load_snapshot_from_local_context(snapshot_name: str) -> SemanticSnapshot:
    """
    Load a snapshot from _local_context/ directory.
    
    Args:
        snapshot_name: Name of the snapshot file (without extension)
        
    Returns:
        SemanticSnapshot instance
        
    Raises:
        FileNotFoundError: If snapshot file doesn't exist
        ValueError: If snapshot is invalid
    """
    snapshot_file = LOCAL_CONTEXT_DIR / f"{snapshot_name}.json"
    
    if not snapshot_file.exists():
        raise FileNotFoundError(f"Snapshot '{snapshot_name}' not found in _local_context/")
    
    with open(snapshot_file, "r") as f:
        snapshot_data = json.load(f)
    
    # Validate snapshot
    validation_errors = validate_snapshot(snapshot_data)
    if validation_errors:
        raise ValueError(f"Invalid snapshot: {validation_errors}")
    
    snapshot = SemanticSnapshot(**snapshot_data)
    return snapshot


def mock_agent_ingestion(source_text: str, source_type: str) -> Dict[str, Any]:
    """
    Mock agentic ingestion - simulates Agent converting raw text to SemanticSnapshot.
    
    In Phase 1, this is a placeholder. The actual Agent (Cursor) would:
    1. Read the source_text (DDL/LookML)
    2. Use concepts/INGESTION.md as guidance
    3. Generate a SemanticSnapshot JSON
    
    For now, this validates that the input can conceptually be parsed
    and returns a minimal valid snapshot structure.
    
    Args:
        source_text: Raw DDL/LookML text
        source_type: Type of source ("ddl", "lookml", "dbt")
        
    Returns:
        Dictionary representation of a SemanticSnapshot (to be validated)
        
    Note: This is a MOCK. Real implementation would use Agent reasoning.
    """
    # For Phase 1, this is a placeholder that returns a minimal valid structure
    # The actual Agent would use concepts/INGESTION.md to generate the snapshot
    
    # Compute a deterministic snapshot_id from source text
    source_hash = hashlib.sha256(source_text.encode('utf-8')).hexdigest()[:16]
    
    # Return minimal valid snapshot structure (Agent would generate this)
    # This is just a placeholder - real Agent would parse source_text
    return {
        "snapshot_id": source_hash,  # Will be recomputed by validation
        "source_system": source_type,
        "source_version": "1.0",
        "schema_version": "v0.1",
        "entities": {},
        "fields": {},
        "joins": [],
        "metadata": {
            "source_text_length": len(source_text),
            "source_type": source_type
        }
    }


def mock_chat_interface(natural_language_query: str) -> Dict[str, Any]:
    """
    Mock chat interface - simulates Chat converting natural language to StructuredFilter.
    
    In Phase 1, this is a placeholder. The actual Chat Interface (Agent) would:
    1. Read the natural_language_query
    2. Use concepts/QUERYING.md as guidance (when created)
    3. Generate a StructuredFilter
    
    For now, this returns a minimal structured filter.
    
    Args:
        natural_language_query: Natural language query string
        
    Returns:
        Structured filter dictionary
        
    Note: This is a MOCK. Real implementation would use Agent reasoning.
    """
    # For Phase 1, this is a placeholder
    # The actual Chat Interface would use Agent reasoning to convert
    # natural language to structured filters
    
    return {
        "concept_map": {
            "entities": [],
            "metrics": [],
            "dimensions": []
        },
        "filters": [],
        "temporal_filters": [],
        "join_path": [],
        "grain_context": {
            "aggregation_required": False
        },
        "policy_context": {
            "resolved_predicates": []
        },
        "dialect": "postgres"
    }


async def handle_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle MCP tool call.
    
    Args:
        tool_name: Name of the tool
        arguments: Tool arguments
        
    Returns:
        Tool result dictionary
    """
    if tool_name == "ingest_source":
        # Tool 1: Ingest source file or text (DDL/LookML/dbt) into SemanticSnapshot
        source_text = arguments.get("source_text", "")
        source_path = arguments.get("source_path", None)
        source_type = arguments.get("source_type", None)
        snapshot_name = arguments.get("snapshot_name", "default")
        
        # Determine source type and parse
        snapshot = None
        
        if source_path:
            # File-based ingestion (preferred)
            file_path = Path(source_path)
            if not file_path.exists():
                return {
                    "error": {
                        "code": -32602,
                        "message": f"Source file not found: {source_path}"
                    }
                }
            
            # Auto-detect source type from file path
            detected_type = detect_source_type(file_path=file_path)
            
            if detected_type == "dbt":
                try:
                    snapshot = parse_dbt_manifest(file_path)
                except Exception as e:
                    return {
                        "error": {
                            "code": -32603,
                            "message": f"Failed to parse dbt manifest: {str(e)}"
                        }
                    }
            elif detected_type == "lookml":
                try:
                    snapshot = parse_lookml_file(file_path)
                except Exception as e:
                    return {
                        "error": {
                            "code": -32603,
                            "message": f"Failed to parse LookML file: {str(e)}"
                        }
                    }
            else:
                # Fallback to text-based ingestion
                if not source_text:
                    source_text = file_path.read_text()
                detected_type = detect_source_type(source_text=source_text)
                source_type = source_type or detected_type
        
        if snapshot is None:
            # Text-based ingestion (fallback or explicit)
            if not source_text:
                return {
                    "error": {
                        "code": -32602,
                        "message": "Either source_path or source_text is required"
                    }
                }
            
            # Auto-detect source type if not provided
            if not source_type:
                source_type = detect_source_type(source_text=source_text)
            
            # For now, use mock for text-based (DDL parsing not yet implemented)
            if source_type == "unknown":
                source_type = "ddl"  # Default fallback
            
            snapshot_data = mock_agent_ingestion(source_text, source_type)
        
            # Compute snapshot_id before creating snapshot (validation requires correct ID)
            snapshot_data.pop("snapshot_id", None)  # Remove placeholder ID
            snapshot_json = json.dumps(snapshot_data, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            snapshot_id = hashlib.sha256(snapshot_json.encode('utf-8')).hexdigest()
            snapshot_data["snapshot_id"] = snapshot_id
            
            # Validate the snapshot
            validation_errors = validate_snapshot(snapshot_data)
            if validation_errors:
                return {
                    "error": {
                        "code": -32602,
                        "message": "Snapshot failed validation",
                        "data": validation_errors
                    }
                }
            
            # Create snapshot with correct ID
            snapshot = SemanticSnapshot(**snapshot_data)
        
        # Validate the parsed snapshot
        snapshot_dict = snapshot.model_dump(mode='json')
        validation_errors = validate_snapshot(snapshot_dict)
        if validation_errors:
            return {
                "error": {
                    "code": -32602,
                    "message": "Parsed snapshot failed validation",
                    "data": validation_errors
                }
            }
        
        # Save to _local_context/
        snapshot_path = save_snapshot_to_local_context(snapshot, snapshot_name)
        
        # Add snapshot to global graph
        _global_graph.add_snapshot(snapshot)
        
        return {
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_name": snapshot_name,
            "snapshot_path": str(snapshot_path),
            "message": "Snapshot ingested and saved to _local_context/",
            "entities_count": len(snapshot.entities),
            "fields_count": len(snapshot.fields),
            "joins_count": len(snapshot.joins)
        }
    
    elif tool_name == "solve_path":
        # Tool 2: Find optimal path between two entities using semantic graph
        source_entity = arguments.get("source", "")
        target_entity = arguments.get("target", "")
        snapshot_name = arguments.get("snapshot_name", None)
        
        if not source_entity or not target_entity:
            return {
                "error": {
                    "code": -32602,
                    "message": "Both 'source' and 'target' entity IDs are required"
                }
            }
        
        # Normalize entity IDs (accept with or without 'entity:' prefix)
        if not source_entity.startswith("entity:"):
            source_entity = f"entity:{source_entity}"
        if not target_entity.startswith("entity:"):
            target_entity = f"entity:{target_entity}"
        
        # If snapshot_name provided, load it and ensure it's in the graph
        if snapshot_name:
            try:
                snapshot = load_snapshot_from_local_context(snapshot_name)
                # Add to graph if not already present
                if snapshot.snapshot_id not in _global_graph.snapshots:
                    _global_graph.add_snapshot(snapshot)
            except FileNotFoundError:
                return {
                    "error": {
                        "code": -32602,
                        "message": f"Snapshot '{snapshot_name}' not found in _local_context/"
                    }
                }
            except ValueError as e:
                return {
                    "error": {
                        "code": -32602,
                        "message": f"Invalid snapshot: {str(e)}"
                    }
                }
        
        # Find path using graph
        try:
            path = _global_graph.find_path(source_entity, target_entity)
        except ValueError as e:
            return {
                "error": {
                    "code": -32602,
                    "message": str(e)
                }
            }
        except Exception as e:
            # Handle networkx.NoPath exception
            import networkx as nx
            if isinstance(e, nx.NetworkXNoPath):
                return {
                    "error": {
                        "code": -32603,
                        "message": f"No path found between {source_entity} and {target_entity}"
                    }
                }
            raise
        
        # Empty path is valid (same entity)
        if not path and source_entity == target_entity:
            # Generate SQL for single entity
            try:
                join_sql = _global_graph.generate_join_sql([], source_entity)
            except Exception as e:
                return {
                    "error": {
                        "code": -32603,
                        "message": f"Failed to generate SQL: {str(e)}"
                    }
                }
            
            return {
                "source_entity": source_entity,
                "target_entity": target_entity,
                "path_length": 0,
                "semantic_cost": 0.0,
                "joins": [],
                "sql": join_sql
            }
        
        if not path:
            return {
                "error": {
                    "code": -32603,
                    "message": f"No path found between {source_entity} and {target_entity}"
                }
            }
        
        # Generate SQL
        try:
            join_sql = _global_graph.generate_join_sql(path, source_entity)
        except Exception as e:
            return {
                "error": {
                    "code": -32603,
                    "message": f"Failed to generate SQL: {str(e)}"
                }
            }
        
        # Calculate total semantic cost
        total_cost = sum(
            _global_graph.graph[path[i].source_entity_id][path[i].target_entity_id][path[i].id].get('weight', 1.0)
            for i in range(len(path))
        )
        
        return {
            "source_entity": source_entity,
            "target_entity": target_entity,
            "path_length": len(path),
            "semantic_cost": total_cost,
            "joins": [
                {
                    "id": join.id,
                    "source": join.source_entity_id,
                    "target": join.target_entity_id,
                    "type": join.join_type.value,
                    "weight": _global_graph.graph[join.source_entity_id][join.target_entity_id][join.id].get('weight', 1.0)
                }
                for join in path
            ],
            "sql": join_sql
        }
    
    elif tool_name == "ask_datashark":
        # Tool 2: Generate SQL from natural language query
        natural_language_query = arguments.get("natural_language_query", "")
        snapshot_name = arguments.get("snapshot_name", "default")
        
        if not natural_language_query:
            return {
                "error": {
                    "code": -32602,
                    "message": "natural_language_query is required"
                }
            }
        
        # Load snapshot from _local_context/
        try:
            snapshot = load_snapshot_from_local_context(snapshot_name)
        except FileNotFoundError as e:
            return {
                "error": {
                    "code": -32602,
                    "message": str(e)
                }
            }
        except ValueError as e:
            return {
                "error": {
                    "code": -32602,
                    "message": f"Invalid snapshot: {str(e)}"
                }
            }
        
        # Mock Chat Interface: Convert natural language to StructuredFilter
        structured_filter = mock_chat_interface(natural_language_query)
        
        # Kernel Step: Call api.process_request()
        try:
            sql = process_request(snapshot, structured_filter)
            return {
                "sql": sql,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_name": snapshot_name
            }
        except ValueError as e:
            return {
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
    
    else:
        return {
            "error": {
                "code": -32601,
                "message": f"Unknown tool: {tool_name}"
            }
        }


# ----- KILL LIST: hand-rolled MCP dispatch (replaced by mcp_app + FastMCP) -----
async def handle_mcp_request(request: dict) -> dict:
    """
    [DEPRECATED] Handle an MCP request. Use datashark.mcp_app instead.
    
    Args:
        request: MCP request dictionary
        
    Returns:
        MCP response dictionary
    """
    method = request.get("method")
    params = request.get("params", {})
    
    if method == "initialize":
        # Return server capabilities
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": True
                }
            },
            "serverInfo": {
                "name": "datashark",
                "version": "0.1.0"
            }
        }
    
    elif method == "tools/list":
        # List available tools
        return {
            "tools": [
                {
                    "name": "ingest_source",
                    "description": "Ingest source text (DDL/LookML) into a SemanticSnapshot and save to _local_context/",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "source_path": {
                                "type": "string",
                                "description": "Path to source file (manifest.json, .lkml, or .sql). Preferred over source_text."
                            },
                            "source_text": {
                                "type": "string",
                                "description": "Raw DDL, LookML, or dbt text (used if source_path not provided)"
                            },
                            "source_type": {
                                "type": "string",
                                "description": "Type of source: 'ddl', 'lookml', or 'dbt'. Auto-detected if not provided.",
                                "default": "auto"
                            },
                            "snapshot_name": {
                                "type": "string",
                                "description": "Name for the snapshot file (without extension)",
                                "default": "default"
                            }
                        },
                        "required": []  # Either source_path or source_text is required, but not both
                    }
                },
                {
                    "name": "solve_path",
                    "description": "Find optimal semantic path between two entities using weighted graph traversal",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                                "description": "Source entity ID (e.g., 'entity:orders' or 'orders')"
                            },
                            "target": {
                                "type": "string",
                                "description": "Target entity ID (e.g., 'entity:users' or 'users')"
                            },
                            "snapshot_name": {
                                "type": "string",
                                "description": "Optional: Name of snapshot to load if not already in graph"
                            }
                        },
                        "required": ["source", "target"]
                    }
                },
                {
                    "name": "ask_datashark",
                    "description": "Generate SQL from a natural language query using a saved snapshot",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "natural_language_query": {
                                "type": "string",
                                "description": "Natural language query (e.g., 'Show me total revenue by month')"
                            },
                            "snapshot_name": {
                                "type": "string",
                                "description": "Name of the snapshot to use (from _local_context/)",
                                "default": "default"
                            }
                        },
                        "required": ["natural_language_query"]
                    }
                }
            ]
        }
    
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        result = await handle_tool_call(tool_name, arguments)
        # MCP protocol expects content array for tool results
        if "error" in result:
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
        else:
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
    
    else:
        return {
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }


# ----- KILL LIST: custom stdio loop (replaced by mcp.run(transport="stdio")) -----
async def main():
    """
    [DEPRECATED] Main MCP server loop. Use mcp_app.main() / mcp.run(transport="stdio") instead.
    Reads JSON-RPC requests from stdin and writes responses to stdout.
    """
    logger.info("DataShark MCP Server starting...")
    
    # Main request loop
    for line in sys.stdin:
        if not line.strip():
            continue
        
        try:
            request = json.loads(line)
            request_id = request.get("id")
            
            # Handle request
            response_data = await handle_mcp_request(request)
            
            # Build response
            if "error" in response_data:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": response_data["error"]
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": response_data
                }
            
            print(json.dumps(response))
            sys.stdout.flush()
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error"
                }
            }
            print(json.dumps(error_response))
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if 'request' in locals() else None,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
            print(json.dumps(error_response))
            sys.stdout.flush()


# ----- KILL LIST: legacy entrypoint; point Cursor/config at datashark.mcp_app -----
if __name__ == "__main__":
    import warnings
    warnings.warn(
        "mcp_server.py is deprecated. Use: python -m datashark.mcp_app",
        DeprecationWarning,
        stacklevel=1,
    )
    asyncio.run(main())
