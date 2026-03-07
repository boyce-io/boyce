"""
Query Planner - The SQL Writer

Bridges natural language queries to StructuredFilter format.
Uses LiteLLM to convert user queries into structured SQL components.

This is a clean-room reimplementation of the legacy planner.
All imports reference boyce.* only.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

try:
    import litellm
except ImportError:
    litellm = None  # type: ignore[assignment]

from ..graph import SemanticGraph
from ..types import FieldType


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
        brain: Optional[Any] = None,
    ) -> None:
        """
        Initialize the Query Planner.

        Args:
            provider: LLM provider (e.g. "openai", "anthropic").
            model: Model name (e.g. "gpt-4", "claude-3-opus").
            api_key: API key. Falls back to LITELLM_API_KEY / OPENAI_API_KEY /
                ANTHROPIC_API_KEY env vars.
            brain: Optional context object. If it exposes retrieve_context(query),
                the results are injected into the system prompt as additional schema
                context (RAG). SQL still comes only from SQLBuilder via
                process_request() — the brain never generates SQL.
        """
        self.provider = provider
        self.model = model
        self.api_key = (
            api_key
            or os.environ.get("LITELLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
        )
        self.brain = brain

    def plan_query(
        self,
        query: str,
        graph: SemanticGraph,
        definitions_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Plan a natural language query and return a StructuredFilter dict.

        Args:
            query: Natural language query string.
            graph: SemanticGraph containing entities and fields.
            definitions_context: Optional pre-formatted string of certified business
                definitions (from DefinitionStore.as_context_string). When provided,
                injected into the system prompt so the LLM applies them when
                interpreting the query.

        Returns:
            Dictionary matching the StructuredFilter schema::

                {
                    "concept_map": {
                        "entities":    [...],
                        "fields":      [...],
                        "metrics":     [...],
                        "dimensions":  [...],
                        "filters":     [...],
                    },
                    "join_path":     [...],
                    "grain_context": {...},
                    "policy_context": {...},
                    # optional:
                    "temporal_filters": [...],
                }

        Raises:
            ValueError: If LiteLLM is not installed, provider/model are not set,
                or the LLM response cannot be parsed.
        """
        if not litellm:
            raise ValueError(
                "LiteLLM is not installed. Run: pip install litellm"
            )

        if not self.provider or not self.model:
            raise ValueError(
                "LLM provider and model must be configured. "
                "Set BOYCE_PROVIDER and BOYCE_MODEL environment variables."
            )

        if not self.api_key:
            raise ValueError(
                "API key not found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, "
                "or LITELLM_API_KEY environment variable."
            )

        # ------------------------------------------------------------------
        # Step 1: Retrieval — build entity/field context from graph
        # ------------------------------------------------------------------
        all_entity_ids = graph.list_entities()
        entity_names = [eid.replace("entity:", "") for eid in all_entity_ids]

        # Score entities by keyword overlap with query (top-50 to save tokens)
        query_words = set(re.findall(r"\b\w+\b", query.lower()))
        entity_scores: List[tuple[int, str]] = []
        for entity_name in entity_names:
            score = sum(1 for w in query_words if w in entity_name.lower())
            if score > 0 or len(entity_names) <= 50:
                entity_scores.append((score, entity_name))
        entity_scores.sort(reverse=True, key=lambda x: x[0])
        top_entities = [name for _, name in entity_scores[:50]]

        entity_context: List[Dict[str, Any]] = []
        for entity_name in top_entities:
            entity_id = f"entity:{entity_name}"
            if entity_id not in graph.graph:
                continue
            node_data = graph.graph.nodes[entity_id]
            entity = node_data.get("entity")
            if not entity:
                continue
            fields = []
            for field_id in entity.fields:
                if field_id in graph.field_cache:
                    field = graph.field_cache[field_id]
                    fields.append({
                        "name": field.name,
                        "type": field.field_type.value,
                        "data_type": field.data_type,
                    })
            entity_context.append({"name": entity_name, "fields": fields[:20]})

        # ------------------------------------------------------------------
        # Step 2: Reasoning — call LiteLLM
        # ------------------------------------------------------------------
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
            for field in entity_info["fields"]:
                schema_text += f"  - {field['name']} ({field['type']}, {field['data_type']})\n"

        # Brain-as-context: inject semantic definitions/DDL (RAG, no SQL generation)
        if self.brain is not None and hasattr(self.brain, "retrieve_context"):
            context = self.brain.retrieve_context(query, n_results=5)
            if context:
                system_prompt += (
                    "\n\nAdditional Schema Context from Brain:\n"
                    f"{context}\n\nUse this to map the user's intent to the Semantic Graph."
                )

        # Certified business definitions — highest priority context
        if definitions_context:
            system_prompt += (
                f"\n\n{definitions_context}\n\n"
                "When the user's query references any of these terms, apply the certified "
                "definition exactly. Do not infer or approximate — use the SQL expression "
                "provided when one is given."
            )

        # Set API key env vars for LiteLLM
        os.environ["LITELLM_API_KEY"] = self.api_key
        if self.provider == "openai":
            os.environ["OPENAI_API_KEY"] = self.api_key
        elif self.provider == "anthropic":
            os.environ["ANTHROPIC_API_KEY"] = self.api_key

        response = litellm.completion(
            model=f"{self.provider}/{self.model}",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User query: {query}\n\n{schema_text}"},
            ],
            temperature=0.1,
        )

        response_text = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse LLM response as JSON: {e}\n"
                f"Response: {response_text[:500]}"
            )

        # ------------------------------------------------------------------
        # Step 3: Validation — ground every entity/field against the graph
        # ------------------------------------------------------------------
        validated_entities: List[Dict[str, Any]] = []
        validated_fields: List[Dict[str, Any]] = []
        validated_metrics: List[Dict[str, Any]] = []
        validated_dimensions: List[Dict[str, Any]] = []
        validated_filters: List[Dict[str, Any]] = []

        for entity_name in result.get("entities", []):
            entity_id = f"entity:{entity_name}"
            if entity_id in graph.graph:
                validated_entities.append({"entity_id": entity_id, "entity_name": entity_name})

        for field_name in result.get("fields", []):
            for ent in validated_entities:
                entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                if not entity:
                    continue
                for field_id in entity.fields:
                    if field_id in graph.field_cache and graph.field_cache[field_id].name == field_name:
                        validated_fields.append({
                            "field_id": field_id,
                            "field_name": field_name,
                            "entity_id": ent["entity_id"],
                        })
                        break

        for metric in result.get("metrics", []):
            metric_name = metric.get("name", "")
            for ent in validated_entities:
                entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                if not entity:
                    continue
                for field_id in entity.fields:
                    if field_id not in graph.field_cache:
                        continue
                    field = graph.field_cache[field_id]
                    if field.name == metric_name or (
                        field.field_type == FieldType.MEASURE
                        and metric_name in ("count", "sum", "avg")
                    ):
                        validated_metrics.append({
                            "metric_name": metric_name,
                            "field_id": field_id,
                            "aggregation_type": metric.get("aggregation_type", "COUNT").upper(),
                        })
                        break

        for dim_name in result.get("dimensions", []):
            for ent in validated_entities:
                entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                if not entity:
                    continue
                for field_id in entity.fields:
                    if field_id in graph.field_cache and graph.field_cache[field_id].name == dim_name:
                        validated_dimensions.append({
                            "field_id": field_id,
                            "field_name": dim_name,
                            "entity_id": ent["entity_id"],
                        })
                        break

        for filter_item in result.get("filters", []):
            field_name = filter_item.get("field", "")
            entity_name = filter_item.get("entity", "")
            entity_id = f"entity:{entity_name}" if entity_name else None
            if entity_id and entity_id in graph.graph:
                entity = graph.graph.nodes[entity_id].get("entity")
                if entity:
                    for field_id in entity.fields:
                        if field_id in graph.field_cache and graph.field_cache[field_id].name == field_name:
                            validated_filters.append({
                                "field_id": field_id,
                                "operator": filter_item.get("operator", "="),
                                "value": filter_item.get("value"),
                                "entity_id": entity_id,
                            })
                            break

        # ------------------------------------------------------------------
        # Step 4: Assemble StructuredFilter
        # ------------------------------------------------------------------
        temporal_filter = None
        temporal_from_llm = result.get("temporal")
        if temporal_from_llm:
            temporal_field_name = temporal_from_llm.get("field", "")
            for ent in validated_entities:
                entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                if not entity:
                    continue
                for field_id in entity.fields:
                    if field_id in graph.field_cache and graph.field_cache[field_id].name == temporal_field_name:
                        temporal_filter = {
                            "field_id": field_id,
                            "operator": temporal_from_llm.get("operator", "trailing_interval"),
                            "value": temporal_from_llm.get("value", {}),
                        }
                        break
                if temporal_filter:
                    break

        structured_filter: Dict[str, Any] = {
            "concept_map": {
                "entities":   validated_entities,
                "fields":     validated_fields,
                "metrics":    validated_metrics,
                "dimensions": validated_dimensions,
                "filters":    validated_filters,
            },
            "join_path": [e["entity_id"] for e in validated_entities],
            "grain_context": {
                "aggregation_required": len(validated_metrics) > 0,
                "grouping_fields": [d["field_name"] for d in validated_dimensions],
            },
            "policy_context": {"resolved_predicates": []},
        }

        if temporal_filter:
            structured_filter["temporal_filters"] = [temporal_filter]

        return structured_filter
