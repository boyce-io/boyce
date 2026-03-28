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

try:
    import networkx as nx
except ImportError:
    nx = None  # type: ignore[assignment]

from ..graph import SemanticGraph
from ..types import FieldType


def _score_field_match(query_field_name: str, candidate_field_name: str) -> int:
    """Score keyword overlap between a query field reference and a candidate field name.

    Splits on underscores and whitespace so "original_language" scores higher
    against "original_language_id" (overlap 2) than "language_id" (overlap 1).
    """
    query_words = set(w for w in re.split(r"[_\s]+", query_field_name.lower()) if w)
    candidate_words = set(w for w in re.split(r"[_\s]+", candidate_field_name.lower()) if w)
    return len(query_words & candidate_words)


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
            Dictionary matching the StructuredFilter v0.2 schema::

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
                    "order_by": [...],
                    "limit": int,
                    "expressions": [...],
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
  "metrics": [{"name": "alias_name", "field": "column_name", "aggregation_type": "COUNT"}],
  "dimensions": ["column1"],
  "filters": [
    {"field": "status", "operator": "=", "value": "complete", "entity": "orders"}
  ],
  "temporal": {
    "field": "created_at",
    "operator": "trailing_interval",
    "value": {"value": 12, "unit": "month"}
  },
  "order_by": [{"field": "column_or_metric_alias", "direction": "ASC|DESC"}],
  "limit": 5,
  "expressions": [{"name": "alias", "expression_type": "concatenation", "fields": ["col1", "col2"], "separator": " "}]
}

Rules:
- Only use table and column names that exist in the provided schema
- For metrics: name is the output alias, field is the actual column name to aggregate
- aggregation_type options: "COUNT", "COUNT_DISTINCT", "SUM", "AVG", "MIN", "MAX"
- For COUNT(*) with no specific column, omit the "field" key or set it to "*"
- For "Top N", "most", "least" queries, include order_by and limit
- For "combined", "full name", "concatenated" requests, use expressions with expression_type "concatenation"
- For filters, operator: "=", "!=", ">", ">=", "<", "<=", "IN", "NOT IN", "LIKE", "ILIKE", "IS NULL", "IS NOT NULL"
- For temporal filters, operator: "trailing_interval", "leading_interval", "between", "on_or_after", "on_or_before", "equals"
- Return ONLY valid JSON, no markdown, no explanation"""

        schema_text = "Available tables and columns:\n"
        for entity_info in entity_context:
            schema_text += f"\nTable: {entity_info['name']}\n"
            for field in entity_info["fields"]:
                schema_text += f"  - {field['name']} ({field['type']}, {field['data_type']})\n"

        # Planner context: inject semantic definitions/DDL (RAG, no SQL generation)
        if self.brain is not None and hasattr(self.brain, "retrieve_context"):
            context = self.brain.retrieve_context(query, n_results=5)
            if context:
                system_prompt += (
                    "\n\nAdditional Schema Context:\n"
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

        # --- Entity validation ---
        for entity_name in result.get("entities", []):
            entity_id = f"entity:{entity_name}"
            if entity_id in graph.graph:
                validated_entities.append({"entity_id": entity_id, "entity_name": entity_name})

        # BUG-C: Entity reachability — drop unreachable entities before join resolution.
        # Keeps the LLM's first entity as the FROM table; sorts the rest for determinism.
        if len(validated_entities) > 1 and nx is not None:
            undirected = graph.graph.to_undirected()
            first = validated_entities[0]
            rest = sorted(validated_entities[1:], key=lambda e: e["entity_id"])
            sorted_entities = [first] + rest
            reachable = [sorted_entities[0]]
            for ent in sorted_entities[1:]:
                target_id = ent["entity_id"]
                can_reach = any(
                    target_id in undirected
                    and r["entity_id"] in undirected
                    and nx.has_path(undirected, r["entity_id"], target_id)
                    for r in reachable
                )
                if can_reach:
                    reachable.append(ent)
            validated_entities = reachable

        # --- Field validation with keyword scoring (BUG-G) ---
        for field_name in result.get("fields", []):
            best_match: Optional[Dict[str, Any]] = None
            best_score = -1
            for ent in validated_entities:
                entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                if not entity:
                    continue
                for field_id in entity.fields:
                    if field_id not in graph.field_cache:
                        continue
                    candidate_name = graph.field_cache[field_id].name
                    if candidate_name == field_name:
                        best_match = {
                            "field_id": field_id,
                            "field_name": field_name,
                            "entity_id": ent["entity_id"],
                        }
                        best_score = 999
                        break
                    score = _score_field_match(field_name, candidate_name)
                    if score > best_score:
                        best_score = score
                        best_match = {
                            "field_id": field_id,
                            "field_name": field_name,
                            "entity_id": ent["entity_id"],
                        }
                if best_score == 999:
                    break
            if best_match and best_score > 0:
                validated_fields.append(best_match)

        # --- Metric validation — BUG-A rewrite ---
        # The metric's "name" is an OUTPUT ALIAS, not a field lookup key.
        # Resolution order:
        #   1. Explicit "field" key from LLM → match by name (with keyword scoring)
        #   2. metric_name matches a field name exactly
        #   3. MEASURE-typed field fallback
        #   4. COUNT(*) sentinel if aggregation_type is COUNT and nothing resolved
        _VALID_AGG_TYPES = {"COUNT", "COUNT_DISTINCT", "SUM", "AVG", "MIN", "MAX"}

        for metric in result.get("metrics", []):
            metric_name = metric.get("name", "")
            metric_field = metric.get("field", None)  # explicit column reference from LLM
            agg_type = metric.get("aggregation_type", "COUNT").upper()
            if agg_type not in _VALID_AGG_TYPES:
                agg_type = "COUNT"

            # Explicit COUNT(*): field key absent or set to "*"
            if metric_field == "*":
                validated_metrics.append({
                    "metric_name": metric_name,
                    "field_id": "",
                    "aggregation_type": agg_type,
                })
                continue

            resolved_field_id: Optional[str] = None

            # Priority 1: explicit "field" key → name + keyword scoring
            if metric_field:
                for ent in validated_entities:
                    entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                    if not entity:
                        continue
                    p1_best_score = -1
                    p1_best_fid: Optional[str] = None
                    for fid in entity.fields:
                        if fid not in graph.field_cache:
                            continue
                        cname = graph.field_cache[fid].name
                        if cname == metric_field:
                            resolved_field_id = fid
                            break
                        score = _score_field_match(metric_field, cname)
                        if score > p1_best_score:
                            p1_best_score = score
                            p1_best_fid = fid
                    if resolved_field_id:
                        break
                    if p1_best_score > 0 and p1_best_fid and not resolved_field_id:
                        resolved_field_id = p1_best_fid
                        break

            # Priority 2: metric_name exactly matches a field name
            if not resolved_field_id and metric_name:
                for ent in validated_entities:
                    entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                    if not entity:
                        continue
                    for fid in entity.fields:
                        if fid in graph.field_cache and graph.field_cache[fid].name == metric_name:
                            resolved_field_id = fid
                            break
                    if resolved_field_id:
                        break

            # Priority 3: MEASURE-typed field fallback
            if not resolved_field_id:
                for ent in validated_entities:
                    entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                    if not entity:
                        continue
                    for fid in entity.fields:
                        if fid in graph.field_cache and graph.field_cache[fid].field_type == FieldType.MEASURE:
                            resolved_field_id = fid
                            break
                    if resolved_field_id:
                        break

            # Priority 4: COUNT(*) sentinel — no field resolved, COUNT aggregation
            if not resolved_field_id and agg_type == "COUNT":
                validated_metrics.append({
                    "metric_name": metric_name,
                    "field_id": "",
                    "aggregation_type": agg_type,
                })
                continue

            if resolved_field_id:
                validated_metrics.append({
                    "metric_name": metric_name,
                    "field_id": resolved_field_id,
                    "aggregation_type": agg_type,
                })

        # --- Dimension validation with keyword scoring (BUG-G) ---
        for dim_name in result.get("dimensions", []):
            dim_best_match: Optional[Dict[str, Any]] = None
            dim_best_score = -1
            for ent in validated_entities:
                entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                if not entity:
                    continue
                for field_id in entity.fields:
                    if field_id not in graph.field_cache:
                        continue
                    candidate_name = graph.field_cache[field_id].name
                    if candidate_name == dim_name:
                        dim_best_match = {
                            "field_id": field_id,
                            "field_name": dim_name,
                            "entity_id": ent["entity_id"],
                        }
                        dim_best_score = 999
                        break
                    score = _score_field_match(dim_name, candidate_name)
                    if score > dim_best_score:
                        dim_best_score = score
                        dim_best_match = {
                            "field_id": field_id,
                            "field_name": dim_name,
                            "entity_id": ent["entity_id"],
                        }
                if dim_best_score == 999:
                    break
            if dim_best_match and dim_best_score > 0:
                validated_dimensions.append(dim_best_match)

        # --- Filter validation with keyword scoring (BUG-G) ---
        for filter_item in result.get("filters", []):
            field_name = filter_item.get("field", "")
            entity_name = filter_item.get("entity", "")
            entity_id = f"entity:{entity_name}" if entity_name else None

            # Prefer the specified entity, fall back to all validated entities
            search_entities = (
                [e for e in validated_entities if e["entity_id"] == entity_id]
                if entity_id and entity_id in graph.graph
                else []
            ) or validated_entities

            flt_best_match: Optional[Dict[str, Any]] = None
            flt_best_score = -1
            for ent in search_entities:
                entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                if not entity:
                    continue
                for fid in entity.fields:
                    if fid not in graph.field_cache:
                        continue
                    cname = graph.field_cache[fid].name
                    if cname == field_name:
                        flt_best_match = {"field_id": fid, "entity_id": ent["entity_id"]}
                        flt_best_score = 999
                        break
                    score = _score_field_match(field_name, cname)
                    if score > flt_best_score:
                        flt_best_score = score
                        flt_best_match = {"field_id": fid, "entity_id": ent["entity_id"]}
                if flt_best_score == 999:
                    break

            if flt_best_match and flt_best_score > 0:
                validated_filters.append({
                    "field_id": flt_best_match["field_id"],
                    "operator": filter_item.get("operator", "="),
                    "value": filter_item.get("value"),
                    "entity_id": flt_best_match["entity_id"],
                })

        # --- Temporal filter ---
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

        # --- Expression validation (BUG-F) ---
        validated_expressions: List[Dict[str, Any]] = []
        for expr in result.get("expressions", []):
            expr_fields = expr.get("fields", [])
            resolved_fields = []
            for fname in expr_fields:
                for ent in validated_entities:
                    entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                    if not entity:
                        continue
                    for fid in entity.fields:
                        if fid in graph.field_cache and graph.field_cache[fid].name == fname:
                            resolved_fields.append({"field_id": fid, "field_name": fname})
                            break
            if resolved_fields:
                validated_expressions.append({
                    "name": expr.get("name", "expression"),
                    "expression_type": expr.get("expression_type", "concatenation"),
                    "fields": resolved_fields,
                    "separator": expr.get("separator", ""),
                })

        # ------------------------------------------------------------------
        # Step 4: Assemble StructuredFilter v0.2
        # ------------------------------------------------------------------
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
                # BUG-D fix: emit field_ids (not bare names) so the builder
                # can produce table-qualified GROUP BY when names collide.
                "grouping_fields": [d["field_id"] for d in validated_dimensions],
            },
            "policy_context": {"resolved_predicates": []},
        }

        if temporal_filter:
            structured_filter["temporal_filters"] = [temporal_filter]

        # BUG-B: ORDER BY / LIMIT
        validated_order_by: List[Dict[str, Any]] = []
        for ob in result.get("order_by", []):
            ob_field = ob.get("field", "")
            direction = ob.get("direction", "ASC").upper()
            if direction not in ("ASC", "DESC"):
                direction = "ASC"

            resolved = False
            for ent in validated_entities:
                entity = graph.graph.nodes[ent["entity_id"]].get("entity")
                if not entity:
                    continue
                for fid in entity.fields:
                    if fid in graph.field_cache and graph.field_cache[fid].name == ob_field:
                        validated_order_by.append({"field_id": fid, "direction": direction})
                        resolved = True
                        break
                if resolved:
                    break
            if not resolved and ob_field:
                # Aggregate alias — pass through for builder to match against SELECT aliases
                validated_order_by.append({"metric_name": ob_field, "direction": direction})

        if validated_order_by:
            structured_filter["order_by"] = validated_order_by

        limit_from_llm = result.get("limit")
        if limit_from_llm is not None:
            try:
                structured_filter["limit"] = int(limit_from_llm)
            except (ValueError, TypeError):
                pass

        # BUG-F: Expressions
        if validated_expressions:
            structured_filter["expressions"] = validated_expressions

        return structured_filter
