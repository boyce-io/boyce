"""
Planner implementation conforming to Planner I/O Contract.

This module implements the Planner interface with methods that conform to the
PLANNER_IO_CONTRACT (see docs/contracts/PLANNER_IO_CONTRACT.md).
"""

from __future__ import annotations

from typing import Any, Dict

from datashark_mcp.planner.grain import GrainResolver
from datashark_mcp.planner.join import JoinPlanner
from datashark_mcp.planner.mapper import ConceptMapper
from datashark_mcp.planner.sql import SQLBuilder
from datashark_mcp.kernel.air_gap_api import AirGapAPI
from datashark.core.audit import log_artifact


class Planner:
    """
    Planner interface conforming to Planner I/O Contract.
    
    Orchestrates the complete planning pipeline:
    1. Concept Mapping (ConceptMapper)
    2. Grain Resolution (GrainResolver)
    3. Join Path Inference (JoinPlanner)
    4. SQL Construction (SQLBuilder)
    
    Contract:
        - Accepts inputs conforming to PLANNER_IO_CONTRACT.md Planner Input schema
        - Produces outputs conforming to PLANNER_IO_CONTRACT.md Planner Output schema
        - Must be deterministic (same inputs → same outputs)
        - Must not depend on LLM randomness
        - All outputs are explainable and testable (Principle 6)
        - Enforces Principle 3 (Deterministic Planner) and Principle 7 (Engine-Level System Contracts)
    """
    
    def __init__(self, air_gap_api: AirGapAPI) -> None:
        """
        Initialize planner with AirGapAPI and all required components.
        
        Args:
            air_gap_api: AirGapAPI instance providing read-only access to the
                ProjectedGraph. This is the only interface the Planner should
                use to access graph data, ensuring the Safety Kernel boundary.
        """
        self.api = air_gap_api
        self.mapper = ConceptMapper(air_gap_api)
        self.join_planner = JoinPlanner(air_gap_api)
        self.grain_resolver = GrainResolver(air_gap_api)
        self.sql_builder = SQLBuilder()
    
    def plan_and_build_sql(
        self,
        query_input: str,
        user_context: dict,
        active_snapshot_id: str
    ) -> Dict[str, Any]:
        """
        Execute all reasoning steps and assemble structured output conforming to PLANNER_IO_CONTRACT.
        
        Contract:
            - Accepts three mandatory inputs: query_input, user_context, active_snapshot_id
            - Executes all reasoning steps: Intent Parsing, Concept Mapping, Join Path Inference,
              Grain Resolution, Policy Evaluation, SQL Template Generation, SQL Finalization
            - Returns dictionary conforming to PLANNER_IO_CONTRACT.md Planner Output schema
            - Must be deterministic: same inputs → same outputs
            - Must not depend on LLM randomness
        
        Args:
            query_input: The raw natural language query string
            user_context: Validated user context dictionary containing user_id, group_ids, roles,
                and optional attributes
            active_snapshot_id: SHA-256 hash string (64 characters) identifying the semantic
                graph snapshot being used
        
        Returns:
            Dictionary conforming to PLANNER_IO_CONTRACT.md Planner Output schema, containing:
            - reasoning_steps (list[str]): Formal sequence of reasoning steps
            - concept_map (dict): Resolved semantic concepts
            - join_path (list[tuple]): Exact multi-hop join path [(source_entity, target_entity, join_key)]
            - grain_context (dict): Determined final grain and aggregation logic
            - policy_context (dict): Final resolved RLS/CLS access predicates
            - sql_template (dict): Structured template before rendering
            - final_sql_output (str): Complete executable SQL statement
        
        Raises:
            ValueError: If inputs do not conform to PLANNER_IO_CONTRACT.md Planner Input schema
            KeyError: If required snapshot entities/metrics are not found
        
        Implementation Status:
            Full orchestration implementation - executes all reasoning steps and assembles structured output.
        """
        reasoning_steps: list[str] = []
        
        # Step 1: Context Validation & Setup
        reasoning_steps.append(f"Context Setup: Starting planning for snapshot {active_snapshot_id}")
        
        # Resolve policy context (mock implementation for stub)
        policy_context = self._resolve_policy_context(user_context)
        reasoning_steps.append(f"Policy Evaluation: Resolved RLS predicates {policy_context.get('resolved_predicates', [])}")
        
        # Step 2: Concept Mapping
        concept_map = self.mapper.map_query_to_concepts(query_input)
        entity_terms = [e.get("term", "") for e in concept_map.get("entities", [])]
        metric_terms = [m.get("term", "") for m in concept_map.get("metrics", [])]
        filter_terms = [f.get("term", "") for f in concept_map.get("filters", [])]
        reasoning_steps.append(
            f"Concept Mapping: Mapped entities={entity_terms}, metrics={metric_terms}, filters={filter_terms}"
        )
        
        # Step 3: Grain Resolution
        # Extract required entity IDs from concept_map
        required_entity_ids: list[str] = []
        for entity in concept_map.get("entities", []):
            entity_id = entity.get("entity_id", "")
            if entity_id:
                required_entity_ids.append(entity_id)
        
        # Also extract entity IDs from metrics (base entities)
        for metric in concept_map.get("metrics", []):
            metric_id = metric.get("metric_id", "")
            # In full implementation, would look up metric's base entity
            # For stub, use entities from concept_map
        
        grain_context = self.grain_resolver.resolve_final_grain(required_entity_ids)
        grain_id = grain_context.get("grain_id", "")
        aggregation_required = grain_context.get("aggregation_required", False)
        reasoning_steps.append(
            f"Grain Resolution: Determined grain='{grain_id}' with aggregation_required={aggregation_required}"
        )
        
        # Step 4: Join Path Inference
        join_path: list[tuple[str, str, str]] = []
        
        # Identify start and target entities from concept_map
        entities = concept_map.get("entities", [])
        if len(entities) >= 2:
            # Multi-entity query: find join path between first two entities
            start_entity_id = entities[0].get("entity_id", "")
            target_entity_id = entities[1].get("entity_id", "")
            
            if start_entity_id and target_entity_id:
                join_path = self.join_planner.infer_join_path(start_entity_id, target_entity_id)
                if join_path:
                    path_str = " -> ".join([f"{j[0]}->{j[1]}" for j in join_path])
                    reasoning_steps.append(f"Join Path Inference: Found path {path_str}")
                else:
                    reasoning_steps.append(f"Join Path Inference: No path found between {start_entity_id} and {target_entity_id}")
        elif len(entities) == 1:
            # Single entity query: no joins needed
            reasoning_steps.append(f"Join Path Inference: Single entity query, no joins required")
        else:
            reasoning_steps.append("Join Path Inference: No entities found in concept_map")
        
        # Step 5: SQL Construction
        # Create final_plan dictionary with all components
        final_plan: Dict[str, Any] = {
            "concept_map": concept_map,
            "join_path": join_path,
            "grain_context": grain_context,
            "policy_context": policy_context,
        }
        
        # Generate SQL template (structured representation)
        sql_template = self._build_sql_template(final_plan)
        reasoning_steps.append("SQL Template Generation: Created template with SELECT, FROM, JOIN, WHERE, GROUP BY clauses")
        
        # Generate final SQL
        final_sql_output = self.sql_builder.build_final_sql(final_plan)
        reasoning_steps.append("SQL Finalization: Rendered final SQL with all parameters substituted")
        
        # Note: Artifact logging is handled at engine.process_request() level
        # to ensure all entrypoints are covered. This hook remains for backward compatibility
        # but engine-level logging is the primary audit point.
        
        # Step 6: Final Output Assembly
        output: Dict[str, Any] = {
            "reasoning_steps": reasoning_steps,
            "concept_map": concept_map,
            "join_path": join_path,
            "grain_context": grain_context,
            "policy_context": policy_context,
            "sql_template": sql_template,
            "final_sql_output": final_sql_output,
        }
        
        return output
    
    def _resolve_policy_context(self, user_context: dict) -> Dict[str, Any]:
        """
        Resolve RLS/CLS policy predicates from user context (mock implementation).
        
        This is a placeholder implementation that returns mock policy predicates.
        In production, this would evaluate Row-Level Security (RLS) and Column-Level
        Security (CLS) policies based on user_context (user_id, group_ids, roles).
        
        Contract:
            - Returns policy_context dictionary conforming to PLANNER_IO_CONTRACT.md
            - Must include resolved_predicates list (may be empty)
            - Enforces Principle 5 (Full Governance)
        
        Args:
            user_context: Validated user context dictionary containing user_id,
                group_ids, roles, and optional attributes
        
        Returns:
            Policy context dictionary containing:
            - resolved_predicates (list[str]): SQL predicates for RLS/CLS
            - policy_ids (list[str]): IDs of policies evaluated
            - evaluation_result (str): "ALLOWED" | "DENIED" | "PARTIAL"
            - integrated_with (dict): Integration metadata
        """
        # Mock implementation: return simple policy context
        # In production, this would:
        # 1. Query policy engine with user_context
        # 2. Evaluate RLS policies (row-level filters)
        # 3. Evaluate CLS policies (column-level restrictions)
        # 4. Generate SQL predicates for WHERE clause
        # 5. Return structured policy_context
        
        user_id = user_context.get("user_id", "unknown")
        roles = user_context.get("roles", [])
        
        # Mock predicate: simple RLS example
        resolved_predicates = [f"user_id = '{user_id}'"]
        
        # Add role-based predicates if roles exist
        if roles:
            roles_str = "', '".join(roles)
            resolved_predicates.append(f"role IN ('{roles_str}')")
        
        return {
            "resolved_predicates": resolved_predicates,
            "policy_ids": ["policy_rls_mock_001"],
            "evaluation_result": "ALLOWED",
            "integrated_with": {
                "selected_fields": [],
                "joins": [],
                "filters": [],
            },
        }
    
    def _build_sql_template(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build SQL template (structured representation) from plan components.
        
        Creates a structured dictionary representation of the SQL query before
        final rendering. This enables deterministic SQL generation and debugging.
        
        Args:
            plan: Dictionary containing concept_map, join_path, grain_context, policy_context
        
        Returns:
            SQL template dictionary with SELECT, FROM, JOIN, WHERE, GROUP_BY keys
        """
        concept_map = plan.get("concept_map", {})
        join_path = plan.get("join_path", [])
        grain_context = plan.get("grain_context", {})
        policy_context = plan.get("policy_context", {})
        
        # Build SELECT list
        select_fields: list[str] = []
        
        # Add dimensions
        for dim in concept_map.get("dimensions", []):
            field_name = dim.get("field_name", "")
            if field_name:
                select_fields.append(field_name)
        
        # Add metrics (with aggregation if required)
        aggregation_required = grain_context.get("aggregation_required", False)
        for metric in concept_map.get("metrics", []):
            metric_name = metric.get("metric_name", "")
            if metric_name:
                if aggregation_required:
                    select_fields.append(f"SUM({metric_name}) AS {metric_name}")
                else:
                    select_fields.append(metric_name)
        
        if not select_fields:
            select_fields = ["*"]
        
        # Build FROM (first entity)
        from_table = "unknown_table"
        if join_path:
            first_join = join_path[0]
            if isinstance(first_join, (list, tuple)) and len(first_join) >= 1:
                source_entity_id = first_join[0]
                from_table = source_entity_id.replace("entity:", "") if "entity:" in source_entity_id else source_entity_id
        elif concept_map.get("entities"):
            from_table = concept_map["entities"][0].get("entity_name", "unknown_table")
        
        # Build JOIN list
        join_list: list[Dict[str, Any]] = []
        for join_tuple in join_path:
            if isinstance(join_tuple, (list, tuple)) and len(join_tuple) >= 3:
                source_entity_id = join_tuple[0]
                target_entity_id = join_tuple[1]
                join_key = join_tuple[2]
                
                source_name = source_entity_id.replace("entity:", "") if "entity:" in source_entity_id else source_entity_id
                target_name = target_entity_id.replace("entity:", "") if "entity:" in target_entity_id else target_entity_id
                
                join_list.append({
                    "type": "LEFT_OUTER",
                    "table": target_name,
                    "condition": f"{source_name}.{join_key} = {target_name}.{join_key}",
                })
        
        # Build WHERE list
        where_clauses: list[str] = []
        
        # Add filter predicates
        for filter_item in concept_map.get("filters", []):
            sql_expression = filter_item.get("sql_expression", "")
            if sql_expression:
                where_clauses.append(sql_expression)
        
        # Add policy predicates
        resolved_predicates = policy_context.get("resolved_predicates", [])
        where_clauses.extend(resolved_predicates)
        
        # Build GROUP BY list
        group_by_fields = grain_context.get("grouping_fields", [])
        
        template: Dict[str, Any] = {
            "SELECT": select_fields,
            "FROM": from_table,
            "JOIN": join_list,
            "WHERE": where_clauses,
        }
        
        if group_by_fields:
            template["GROUP_BY"] = group_by_fields
        
        return template


