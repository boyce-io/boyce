"""
Query Planner - The SQL Writer

This module bridges Natural Language queries to StructuredFilter format.
It uses LiteLLM to convert user queries into structured SQL components.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

try:
    import litellm
except ImportError:
    litellm = None

from datashark.core.graph import SemanticGraph
from datashark.core.types import FieldType, SemanticSnapshot

if TYPE_CHECKING:
    from datashark.agent_engine.capabilities.reasoning.brain import DataSharkBrain


class QueryPlanner:
    """
    Planner that converts natural language queries into structured filters.
    
    Uses LiteLLM to reason about the query and extract:
    - Entities (tables)
    - Fields (columns)
    - Filters (WHERE clauses)
    - Temporal filters (time-based filters)
    """
    
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        brain: Optional["DataSharkBrain"] = None,
    ):
        """
        Initialize the Query Planner.

        Args:
            provider: LLM provider (e.g., "openai", "anthropic")
            model: Model name (e.g., "gpt-4", "claude-3-opus")
            api_key: API key for the LLM provider
            brain: Optional DataSharkBrain. If present, retrieve_context(query) is
                   injected into the prompt as "Additional Schema Context" (RAG).
                   SQL still comes only from SQLBuilder via process_request().
        """
        self.provider = provider
        self.model = model
        self.api_key = api_key or os.environ.get("LITELLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        self.brain = brain
    
    def plan_query(self, query: str, graph: SemanticGraph) -> Dict[str, Any]:
        """
        Plan a natural language query and return structured filter.
        
        Args:
            query: Natural language query string
            graph: SemanticGraph containing entities and fields
            
        Returns:
            Dictionary matching StructuredFilter schema:
            {
                "concept_map": {
                    "entities": [...],
                    "fields": [...],
                    "metrics": [...],
                    "dimensions": [...],
                    "filters": [...]
                },
                "join_path": [...],
                "grain_context": {...},
                "policy_context": {...}
            }
            
        Raises:
            ValueError: If LLM is not configured or response is invalid
        """
        if not litellm:
            raise ValueError("LiteLLM is not installed. Please install it: pip install litellm")
        
        if not self.provider or not self.model:
            raise ValueError("LLM provider and model must be configured. Use datashark config to set them.")
        
        if not self.api_key:
            raise ValueError("API key not found. Set it via datashark config or environment variable.")
        
        # Step 1: Retrieval - Get context from graph
        all_entity_ids = graph.list_entities()
        entity_names = [eid.replace("entity:", "") for eid in all_entity_ids]
        
        # Filter to top 50 entities by query keyword matching (save tokens)
        query_words = set(re.findall(r'\b\w+\b', query.lower()))
        entity_scores = []
        for entity_name in entity_names:
            entity_lower = entity_name.lower()
            score = sum(1 for word in query_words if word in entity_lower)
            if score > 0 or len(entity_names) <= 50:
                entity_scores.append((score, entity_name))
        
        entity_scores.sort(reverse=True, key=lambda x: x[0])
        top_entities = [name for _, name in entity_scores[:50]]
        
        # Build entity context with fields
        entity_context = []
        for entity_name in top_entities:
            entity_id = f"entity:{entity_name}"
            if entity_id not in graph.graph:
                continue
            
            # Get entity from graph
            node_data = graph.graph.nodes[entity_id]
            entity = node_data.get('entity')
            if not entity:
                continue
            
            # Get fields for this entity
            fields = []
            for field_id in entity.fields:
                if field_id in graph.field_cache:
                    field = graph.field_cache[field_id]
                    fields.append({
                        "name": field.name,
                        "type": field.field_type.value,
                        "data_type": field.data_type
                    })
            
            entity_context.append({
                "name": entity_name,
                "fields": fields[:20]  # Limit fields per entity to save tokens
            })
        
        # Step 2: Reasoning - Send to LLM
        system_prompt = """You are a Data Engineer. Given a user query and a database schema, return a JSON object with the following structure:

{
  "entities": ["table1", "table2"],
  "fields": ["column1", "column2"],
  "metrics": [{"name": "count", "aggregation_type": "COUNT"}],
  "dimensions": ["column1"],
  "filters": [
    {"field": "status", "operator": "=", "value": "complete", "entity": "orders"}
  ],
  "temporal": {
    "field": "created_at",
    "operator": "trailing_interval",
    "value": {"value": 12, "unit": "month"}
  }
}

Rules:
- Only use table and column names that exist in the provided schema
- For metrics, use aggregation_type: "COUNT", "SUM", "AVG", "MIN", "MAX"
- For filters, operator can be: "=", "!=", ">", ">=", "<", "<=", "IN", "NOT IN", "LIKE", "ILIKE"
- For temporal filters, operator can be: "trailing_interval", "leading_interval", "between", "on_or_after", "on_or_before", "equals"
- Return ONLY valid JSON, no markdown, no explanation"""
        
        schema_text = "Available tables and columns:\n"
        for entity_info in entity_context:
            schema_text += f"\nTable: {entity_info['name']}\n"
            for field in entity_info['fields']:
                schema_text += f"  - {field['name']} ({field['type']}, {field['data_type']})\n"

        # Brain-as-Context: inject semantic definitions/DDL into system prompt (no SQL generation)
        if self.brain is not None and hasattr(self.brain, "retrieve_context"):
            context = self.brain.retrieve_context(query, n_results=5)
            if context:
                system_prompt += (
                    "\n\nYou have access to the following semantic definitions/DDL from the Brain:\n"
                    f"{context}\n\nUse this to map the user's intent to the Semantic Graph."
                )

        user_message = f"User query: {query}\n\n{schema_text}"
        
        # Set API key
        if self.api_key:
            os.environ["LITELLM_API_KEY"] = self.api_key
            if self.provider == "openai":
                os.environ["OPENAI_API_KEY"] = self.api_key
            elif self.provider == "anthropic":
                os.environ["ANTHROPIC_API_KEY"] = self.api_key
        
        # Call LiteLLM
        response = litellm.completion(
            model=f"{self.provider}/{self.model}",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,  # Low temperature for deterministic extraction
        )
        
        # Extract JSON from response
        response_text = response.choices[0].message.content.strip()
        
        # Try to extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        
        # Parse JSON
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}\nResponse: {response_text[:500]}")
        
        # Step 3: Validation - Ensure entities/fields exist in graph
        validated_entities = []
        validated_fields = []
        validated_metrics = []
        validated_dimensions = []
        validated_filters = []
        
        # Validate entities
        entities_from_llm = result.get("entities", [])
        for entity_name in entities_from_llm:
            entity_id = f"entity:{entity_name}"
            if entity_id in graph.graph:
                validated_entities.append({
                    "entity_id": entity_id,
                    "entity_name": entity_name
                })
        
        # Validate fields and build field references
        fields_from_llm = result.get("fields", [])
        for field_name in fields_from_llm:
            # Try to find field in graph
            found = False
            for entity_id in validated_entities:
                entity = graph.graph.nodes[entity_id["entity_id"]].get('entity')
                if entity:
                    for field_id in entity.fields:
                        if field_id in graph.field_cache:
                            field = graph.field_cache[field_id]
                            if field.name == field_name:
                                validated_fields.append({
                                    "field_id": field_id,
                                    "field_name": field_name,
                                    "entity_id": entity_id["entity_id"]
                                })
                                found = True
                                break
                if found:
                    break
        
        # Validate metrics
        metrics_from_llm = result.get("metrics", [])
        for metric in metrics_from_llm:
            metric_name = metric.get("name", "")
            # Try to find metric field in graph
            for entity_id in validated_entities:
                entity = graph.graph.nodes[entity_id["entity_id"]].get('entity')
                if entity:
                    for field_id in entity.fields:
                        if field_id in graph.field_cache:
                            field = graph.field_cache[field_id]
                            if field.name == metric_name or (field.field_type == FieldType.MEASURE and metric_name in ["count", "sum", "avg"]):
                                validated_metrics.append({
                                    "metric_name": metric_name,
                                    "field_id": field_id,
                                    "aggregation_type": metric.get("aggregation_type", "COUNT").upper()
                                })
                                break
        
        # Validate dimensions
        dimensions_from_llm = result.get("dimensions", [])
        for dim_name in dimensions_from_llm:
            # Try to find dimension field in graph
            for entity_id in validated_entities:
                entity = graph.graph.nodes[entity_id["entity_id"]].get('entity')
                if entity:
                    for field_id in entity.fields:
                        if field_id in graph.field_cache:
                            field = graph.field_cache[field_id]
                            if field.name == dim_name:
                                validated_dimensions.append({
                                    "field_id": field_id,
                                    "field_name": dim_name,
                                    "entity_id": entity_id["entity_id"]
                                })
                                break
        
        # Validate filters
        filters_from_llm = result.get("filters", [])
        for filter_item in filters_from_llm:
            field_name = filter_item.get("field", "")
            entity_name = filter_item.get("entity", "")
            
            # Find field in graph
            entity_id = f"entity:{entity_name}" if entity_name else None
            if entity_id and entity_id in graph.graph:
                entity = graph.graph.nodes[entity_id].get('entity')
                if entity:
                    for field_id in entity.fields:
                        if field_id in graph.field_cache:
                            field = graph.field_cache[field_id]
                            if field.name == field_name:
                                validated_filters.append({
                                    "field_id": field_id,
                                    "operator": filter_item.get("operator", "="),
                                    "value": filter_item.get("value"),
                                    "entity_id": entity_id
                                })
                                break
        
        # Build join_path from validated entities
        join_path = [e["entity_id"] for e in validated_entities]
        
        # Build temporal filter if present
        temporal_filter = None
        temporal_from_llm = result.get("temporal")
        if temporal_from_llm:
            temporal_field_name = temporal_from_llm.get("field", "")
            # Try to find temporal field
            for entity_id in validated_entities:
                entity = graph.graph.nodes[entity_id["entity_id"]].get('entity')
                if entity:
                    for field_id in entity.fields:
                        if field_id in graph.field_cache:
                            field = graph.field_cache[field_id]
                            if field.name == temporal_field_name:
                                temporal_filter = {
                                    "field_id": field_id,
                                    "operator": temporal_from_llm.get("operator", "trailing_interval"),
                                    "value": temporal_from_llm.get("value", {})
                                }
                                break
                if temporal_filter:
                    break
        
        # Step 4: Return structured filter
        structured_filter = {
            "concept_map": {
                "entities": validated_entities,
                "fields": validated_fields,
                "metrics": validated_metrics,
                "dimensions": validated_dimensions,
                "filters": validated_filters
            },
            "join_path": join_path,
            "grain_context": {
                "aggregation_required": len(validated_metrics) > 0,
                "grouping_fields": [d["field_name"] for d in validated_dimensions]
            },
            "policy_context": {
                "resolved_predicates": []
            }
        }
        
        # Add temporal filter if present
        if temporal_filter:
            structured_filter["temporal_filters"] = [temporal_filter]
        
        return structured_filter
