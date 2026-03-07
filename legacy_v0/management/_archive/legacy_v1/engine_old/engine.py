"""Safety Kernel Engine - Governance Enforcer.

This module provides the DataSharkEngine that enforces the Safety Kernel pattern
by coordinating the SnapshotFactory, GraphProjector, and AirGapAPI.
"""

import json
import logging
from typing import Any, Dict, Optional

from datashark.core.types import SemanticSnapshot
from datashark_mcp.kernel.exceptions import ContextValidationError, SnapshotIntegrityError, SnapshotNotFoundError
from datashark_mcp.kernel.snapshot_factory import SnapshotFactory
from datashark_mcp.kernel.snapshot_store import SnapshotStore
from datashark_mcp.kernel.types import SemanticGraph, SnapshotID, UserContext
from datashark_mcp.kernel.air_gap_api import AirGapAPI
from datashark_mcp.planner.planner import Planner
from datashark_mcp.security.graph_projector import GraphProjector
from datashark_mcp.security.policy import PolicySet
from datashark.core.audit import log_artifact

logger = logging.getLogger(__name__)


class DataSharkEngine:
    """Safety Kernel Engine - The Governance Enforcer.
    
    This engine enforces the Safety Kernel pattern by:
    1. Holding UserContext and PolicySet (trusted components)
    2. Using SnapshotFactory to ingest metadata (the only entry point)
    3. Using GraphProjector to create ProjectedGraph (air gap enforcement)
    4. Exposing AirGapAPI to untrusted components (the only interface they see)
    
    The engine ensures that untrusted components (like Planner) can only
    access the ProjectedGraph through the AirGapAPI, never the raw SemanticGraph.
    """
    
    def __init__(self, context: UserContext):
        """Initialize engine with user context.
        
        Args:
            context: UserContext containing user identity and roles
        """
        self.context = context
        self.policy_set: Optional[PolicySet] = None
        self._semantic_graph: Optional[SemanticGraph] = None
        self._snapshot_id: Optional[SnapshotID] = None
        self._semantic_snapshot: Optional[SemanticSnapshot] = None  # CAS-loaded snapshot
        self._snapshot_store: Optional[SnapshotStore] = None
        self._projected_graph = None
        self._api_client: Optional[AirGapAPI] = None
    
    def load_metadata(self, raw_metadata: Dict) -> None:
        """Load raw metadata through the SnapshotFactory (the only entry point).
        
        This method uses SnapshotFactory to create a SemanticGraph and SnapshotID
        from raw metadata. This enforces the integrity gate.
        
        Args:
            raw_metadata: Dictionary containing raw metadata to be ingested
        
        Raises:
            SnapshotIntegrityError: If metadata validation or snapshot creation fails
        """
        try:
            graph, snapshot_id = SnapshotFactory.create_snapshot(raw_metadata)
            self._semantic_graph = graph
            self._snapshot_id = snapshot_id
            # Note: SemanticSnapshot is not created here; this method works with SemanticGraph
            # For CAS integration, use load_snapshot_by_id() or ensure adapters save snapshots
        except Exception as e:
            raise SnapshotIntegrityError(
                f"Failed to load metadata: {str(e)}"
            ) from e
    
    def load_snapshot_by_id(self, snapshot_id: str) -> None:
        """Load SemanticSnapshot from CAS by snapshot_id.
        
        This method loads a persisted snapshot from content-addressable storage
        and makes it available for the planner/SQL builder. It also creates a
        SemanticGraph from the snapshot's raw_data for internal engine use.
        
        Args:
            snapshot_id: SHA-256 hash string (64 hex chars) identifying the snapshot
        
        Raises:
            SnapshotNotFoundError: If snapshot doesn't exist in CAS
            SnapshotIntegrityError: If snapshot fails to load or validate
        """
        if self._snapshot_store is None:
            self._snapshot_store = SnapshotStore()
        
        try:
            # Load snapshot from CAS
            snapshot = self._snapshot_store.load(snapshot_id)
            self._semantic_snapshot = snapshot
            
            # Create SemanticGraph from snapshot for internal engine use
            # Convert snapshot to raw_metadata format for SemanticGraph
            raw_metadata = {
                "entities": {eid: {
                    "id": e.id,
                    "name": e.name,
                    "schema": e.schema_name,
                    "fields": e.fields,
                    "grain": e.grain
                } for eid, e in snapshot.entities.items()},
                "fields": {fid: {
                    "id": f.id,
                    "entity_id": f.entity_id,
                    "name": f.name,
                    "field_type": f.field_type.value,
                    "data_type": f.data_type,
                    "nullable": f.nullable,
                    "primary_key": f.primary_key
                } for fid, f in snapshot.fields.items()},
                "joins": [{
                    "id": j.id,
                    "source_entity_id": j.source_entity_id,
                    "target_entity_id": j.target_entity_id,
                    "join_type": j.join_type.value,
                    "source_field_id": j.source_field_id,
                    "target_field_id": j.target_field_id
                } for j in snapshot.joins]
            }
            
            # Create SemanticGraph and SnapshotID for backwards compatibility
            graph, snapshot_id_obj = SnapshotFactory.create_snapshot(raw_metadata)
            self._semantic_graph = graph
            self._snapshot_id = snapshot_id_obj
            
            # Validate loaded snapshot_id matches requested one
            if snapshot.snapshot_id != snapshot_id:
                raise SnapshotIntegrityError(
                    f"Snapshot ID mismatch: requested {snapshot_id}, got {snapshot.snapshot_id}"
                )
            
            logger.info(f"Loaded snapshot {snapshot_id[:16]}... from CAS")
            
        except SnapshotNotFoundError:
            raise
        except Exception as e:
            if isinstance(e, (SnapshotNotFoundError, SnapshotIntegrityError)):
                raise
            raise SnapshotIntegrityError(
                f"Failed to load snapshot by ID: {str(e)}"
            ) from e
    
    def get_semantic_snapshot(self) -> Optional[SemanticSnapshot]:
        """Get the loaded SemanticSnapshot if available.
        
        Returns:
            SemanticSnapshot if loaded via load_snapshot_by_id(), None otherwise
        """
        return self._semantic_snapshot
    
    def get_api_client(self) -> AirGapAPI:
        """Get the AirGapAPI client for accessing the projected graph.
        
        This method creates a ProjectedGraph from the SemanticGraph using
        GraphProjector, then returns an AirGapAPI that operates on the
        projected graph. This is the ONLY interface untrusted components
        should use.
        
        Returns:
            AirGapAPI instance that provides read-only access to ProjectedGraph
        
        Raises:
            ContextValidationError: If policy_set is not configured
            SnapshotIntegrityError: If semantic graph is not loaded
        """
        if self.policy_set is None:
            raise ContextValidationError(
                "PolicySet must be configured before getting API client. "
                "Set engine.policy_set before calling get_api_client()."
            )
        
        if self._semantic_graph is None:
            raise SnapshotIntegrityError(
                "Semantic graph not loaded. Call load_metadata() first."
            )
        
        # Project the graph through the Air Gap
        self._projected_graph = GraphProjector.project_graph(
            self._semantic_graph,
            self.context,
            self.policy_set
        )
        
        # Create and return the AirGapAPI (the only interface untrusted components see)
        self._api_client = AirGapAPI(self._projected_graph)
        return self._api_client
    
    def process_request(self, intent: str) -> Dict[str, Any]:
        """Process a natural language query request through the Safety Kernel.
        
        This method orchestrates the complete flow:
        1. Validates that metadata is loaded (snapshot_id is set)
        2. Gets the AirGapAPI client (creates ProjectedGraph if needed)
        3. Instantiates the Planner with the AirGapAPI
        4. Executes the planning pipeline
        5. Returns the structured result
        
        Args:
            intent: Natural language query string
        
        Returns:
            Dictionary conforming to PLANNER_IO_CONTRACT.md Planner Output schema:
            - reasoning_steps (list[str])
            - concept_map (dict)
            - join_path (list[tuple])
            - grain_context (dict)
            - policy_context (dict)
            - sql_template (dict)
            - final_sql_output (str)
        
        Raises:
            SnapshotIntegrityError: If metadata is not loaded
            ContextValidationError: If policy_set is not configured
        """
        # Step 1: Ensure metadata is loaded (either via load_metadata or load_snapshot_by_id)
        # If we have snapshot_id but no graph, try loading from CAS
        if self._snapshot_id is None:
            raise SnapshotIntegrityError(
                "Metadata not loaded. Call load_metadata() or load_snapshot_by_id() before process_request()."
            )
        
        # If we have snapshot_id but no semantic_snapshot, try loading from CAS
        # This supports the case where only snapshot_id is known (e.g., from audit log)
        if self._semantic_snapshot is None and self._snapshot_id is not None:
            snapshot_id_str = self._snapshot_id.id
            try:
                self.load_snapshot_by_id(snapshot_id_str)
            except SnapshotNotFoundError:
                # If snapshot not in CAS, continue with in-memory graph (backwards compatibility)
                logger.warning(
                    f"Snapshot {snapshot_id_str[:16]}... not found in CAS, using in-memory graph"
                )
        
        # Step 2: Instantiate the client (creates ProjectedGraph if needed)
        api_client = self.get_api_client()
        
        # Step 3: Instantiate the planner with AirGapAPI
        planner = Planner(api_client)
        
        # Step 4: Execute planning pipeline
        # Convert UserContext to dict for planner
        user_context_dict = self.context.model_dump()
        
        # Get snapshot_id string
        snapshot_id_str = self._snapshot_id.id
        
        result = planner.plan_and_build_sql(
            query_input=intent,
            user_context=user_context_dict,
            active_snapshot_id=snapshot_id_str
        )
        
        # Step 5: Log artifact (fail-open: don't block on audit errors)
        try:
            generated_sql = result.get("final_sql_output", "")
            log_artifact(
                input_query=intent,
                snapshot_id=snapshot_id_str,
                generated_sql=generated_sql,
                metadata={"dialect": "postgres"}  # Default dialect
            )
        except Exception as e:
            # Fail-open: log error but don't raise
            logger.warning(f"Artifact logging failed: {e}")
        
        # Step 6: Return result
        return result

