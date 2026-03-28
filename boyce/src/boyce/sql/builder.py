"""
Dialect-aware SQL Builder using Strategy Pattern.

This builder renders structured filters (TemporalFilter, FilterDef) into
dialect-specific SQL. It never interprets natural language; it only renders
structured objects resolved by the Planner.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from boyce.sql.dialects import (
    SQLDialect,
    PostgresDialect,
    DuckDBDialect,
    BigQueryDialect,
    RedshiftDialect,
)
from boyce.sql.join_resolver import JoinPathResolver
from boyce.types import (
    FilterDef,
    FilterOperator,
    SemanticSnapshot,
    TemporalFilter,
    TemporalOperator,
)


# Operator aliases — host LLMs use underscore variants; normalise to SQL spacing.
_OPERATOR_ALIASES: Dict[str, str] = {
    "NOT_IN": "NOT IN",
    "IS_NULL": "IS NULL",
    "IS_NOT_NULL": "IS NOT NULL",
    "ISNULL": "IS NULL",
    "ISNOTNULL": "IS NOT NULL",
    "NOT_EQUALS": "!=",
    "GREATER_THAN": ">",
    "GREATER_THAN_OR_EQUAL": ">=",
    "LESS_THAN": "<",
    "LESS_THAN_OR_EQUAL": "<=",
}


class SQLBuilder:
    """
    Dialect-aware SQL builder for rendering executable SQL from planner output.

    Contract:
        - Takes planner_output with structured filters (TemporalFilter, FilterDef)
        - Uses Strategy Pattern to render dialect-specific SQL
        - Never interprets natural language; only renders structured objects
        - Deterministic: same input → same SQL string
    """

    def __init__(self, dialect: Optional[SQLDialect] = None):
        """
        Initialize SQL builder with a dialect.

        Args:
            dialect: SQL dialect implementation (defaults to PostgresDialect)
        """
        self.dialect: SQLDialect = dialect or PostgresDialect()

    def set_dialect(self, dialect_name: str) -> None:
        """
        Set the SQL dialect by name.

        Args:
            dialect_name: One of "postgres", "duckdb", "bigquery", "redshift"
        """
        dialect_map = {
            "postgres": PostgresDialect(),
            "duckdb": DuckDBDialect(),
            "bigquery": BigQueryDialect(),
            "redshift": RedshiftDialect(),
        }
        if dialect_name.lower() not in dialect_map:
            raise ValueError(f"Unknown dialect: {dialect_name}. Supported: {list(dialect_map.keys())}")
        self.dialect = dialect_map[dialect_name.lower()]

    def _render_cast(self, expression: str, type_name: str) -> str:
        """
        Render a type cast via the dialect (e.g. safe numeric casts for Redshift).
        Use this for any SELECT/filter projection that requires a cast.
        """
        return self.dialect.render_cast(expression, type_name)

    # ------------------------------------------------------------------
    # Field reference resolution — single source of truth
    # ------------------------------------------------------------------

    def _resolve_field_ref(
        self,
        field_id: str,
        field_name: str,
        snapshot: SemanticSnapshot,
        entity_id: str = "",
    ) -> Tuple[str, str]:
        """Resolve a field reference to table-qualified SQL and its entity name.

        All SELECT, GROUP BY, and WHERE field references funnel through here.

        Resolution order:
          1. Explicit *entity_id* → snapshot.entities  (filters set this)
          2. *field_id* → snapshot.fields → entity     (dimensions / metrics)
          3. Fallback: bare quoted *field_name*, empty entity name

        Returns:
            (sql_ref, entity_name) — e.g. ('"customer"."email"', 'customer')
            or ('"email"', '') when resolution fails.
        """
        q = self.dialect.quote_identifier

        # Strategy 1: explicit entity_id (filters provide this)
        if entity_id:
            entity = snapshot.entities.get(entity_id)
            if entity:
                return f"{q(entity.name)}.{q(field_name)}", entity.name

        # Strategy 2: field registry lookup
        if field_id:
            field_def = snapshot.fields.get(field_id)
            if field_def:
                entity = snapshot.entities.get(field_def.entity_id)
                if entity:
                    return f"{q(entity.name)}.{q(field_def.name)}", entity.name

        # Fallback: bare column
        return q(field_name), ""

    @staticmethod
    def _resolve_grouping_field(
        field_ref: str, snapshot: SemanticSnapshot
    ) -> Tuple[str, str]:
        """Resolve a grouping_fields entry to (field_id, column_name).

        grouping_fields entries may be full field_ids ("field:Table:Col")
        or bare column names.
        """
        # Direct field_id match
        if field_ref in snapshot.fields:
            return field_ref, snapshot.fields[field_ref].name

        # "field:Table:Col" format — search by column name
        if ":" in field_ref:
            col_name = field_ref.split(":")[-1]
            for fid, fdef in snapshot.fields.items():
                if fdef.name == col_name:
                    return fid, fdef.name
            return "", col_name

        # Bare column name
        return "", field_ref

    # ------------------------------------------------------------------
    # Top-level SQL assembly
    # ------------------------------------------------------------------

    def build_final_sql(
        self,
        planner_output: Dict[str, Any],
        snapshot: SemanticSnapshot,
        input_query: Optional[str] = None
    ) -> str:
        """
        Build final executable SQL string from planner output and SemanticSnapshot.

        **Architectural Contract:** The SemanticSnapshot is the sole source of truth for
        JOIN definitions. The planner_output join_path is used only as a sequence hint
        to determine which entities to join, but all join structure (fields, types) comes
        from snapshot.joins.

        Args:
            planner_output: Dictionary with structured filters:
                - concept_map: entities, metrics, dimensions, filters (structured)
                - join_path: list of entity IDs (used as sequence hint, validated against snapshot)
                - grain_context: grain_id, grouping_fields, aggregation_required, date_trunc_field, date_trunc_unit
                - policy_context: resolved_predicates
            snapshot: SemanticSnapshot containing JoinDef objects (REQUIRED).
                     This is the sole source of truth for join structure.

        Returns:
            Complete, executable SQL statement

        Raises:
            ValueError: If snapshot is missing or join_path references invalid entities
        """
        if not snapshot:
            raise ValueError("SemanticSnapshot is required. The snapshot is the sole source of truth for JOIN definitions.")

        concept_map = planner_output.get("concept_map", {})
        grain_context = planner_output.get("grain_context", {})
        policy_context = planner_output.get("policy_context", {})

        # Build SELECT clause (with DATE_TRUNC support)
        select_clause = self._build_select_clause(concept_map, grain_context, snapshot)

        # Build FROM and JOIN clauses using JoinPathResolver
        # Use planner_output join_path only as entity sequence hint
        from_clause, join_clauses = self._build_joins_from_snapshot(
            snapshot, concept_map, planner_output.get("join_path", [])
        )

        # Build WHERE clause (structured filters + policy predicates + temporal filters)
        where_clause = self._build_where_clause(
            concept_map, policy_context, snapshot,
            temporal_filters=planner_output.get("temporal_filters", []),
        )

        # Build GROUP BY clause (with DATE_TRUNC support)
        group_by_clause = self._build_group_by_clause(grain_context, snapshot)

        # Build ORDER BY and LIMIT (BUG-B)
        order_by_clause = self._build_order_by_clause(planner_output, snapshot)
        limit = planner_output.get("limit")

        # Assemble final SQL
        sql_parts = [select_clause, from_clause]
        sql_parts.extend(join_clauses)
        if where_clause:
            sql_parts.append(where_clause)
        if group_by_clause:
            sql_parts.append(group_by_clause)
        if order_by_clause:
            sql_parts.append(order_by_clause)
        if limit is not None:
            sql_parts.append(f"LIMIT {int(limit)}")

        final_sql = " ".join(sql_parts)

        # Enforce dialect compatibility (e.g. LATERAL / JSONB for Redshift)
        errors = self.dialect.validate_compatibility(final_sql)
        if errors:
            raise ValueError(
                f"Dialect Incompatibility ({self.dialect.__class__.__name__}): {'; '.join(errors)}"
            )

        return final_sql

    # ------------------------------------------------------------------
    # FROM / JOIN clauses
    # ------------------------------------------------------------------

    def _build_joins_from_snapshot(
        self,
        snapshot: SemanticSnapshot,
        concept_map: Dict[str, Any],
        join_path_hint: List = None
    ) -> tuple:
        """
        Build FROM and JOIN clauses using JoinPathResolver from SemanticSnapshot.

        **Architectural Contract:** snapshot.joins is the sole source of truth for join
        structure. The join_path_hint (from planner_output) is used only as a sequence
        hint to determine which entities to join, but all join details come from snapshot.

        Args:
            snapshot: SemanticSnapshot containing JoinDef objects (sole source of truth)
            concept_map: Concept map with entity IDs
            join_path_hint: Optional list of entity IDs from planner (used as sequence hint only)

        Returns:
            Tuple of (from_clause, join_clauses)

        Raises:
            ValueError: If join_path_hint references entities not in snapshot
        """
        # Extract entity IDs from concept_map or join_path_hint
        if join_path_hint:
            # Validate that all entities in join_path_hint exist in snapshot
            for entity_id in join_path_hint:
                if entity_id not in snapshot.entities:
                    raise ValueError(
                        f"Join path hint references entity '{entity_id}' not found in snapshot. "
                        f"Available entities: {list(snapshot.entities.keys())}"
                    )
            entity_ids = join_path_hint
        else:
            # Extract from concept_map
            entities = concept_map.get("entities", [])
            if not entities:
                # Fallback: use first entity in snapshot
                if snapshot.entities:
                    first_entity_id = sorted(snapshot.entities.keys())[0]
                    entity_ids = [first_entity_id]
                else:
                    return ("FROM unknown_table", [])
            else:
                entity_ids = [e.get("entity_id", "") for e in entities if e.get("entity_id")]
                # Validate entities exist in snapshot
                for entity_id in entity_ids:
                    if entity_id not in snapshot.entities:
                        raise ValueError(
                            f"Concept map references entity '{entity_id}' not found in snapshot. "
                            f"Available entities: {list(snapshot.entities.keys())}"
                        )

        if not entity_ids:
            return ("FROM unknown_table", [])

        # Use JoinPathResolver to build joins (uses snapshot.joins as sole source of truth)
        resolver = JoinPathResolver(snapshot, self.dialect)

        if len(entity_ids) == 1:
            # Single entity: no joins
            entity = snapshot.entities.get(entity_ids[0])
            if entity:
                from_clause = f"FROM {self.dialect.quote_identifier(entity.name)}"
                return (from_clause, [])
            else:
                return ("FROM unknown_table", [])
        else:
            # Multiple entities: resolve join path using snapshot.joins
            return resolver.resolve_joins_from_entity_list(entity_ids)

    # ------------------------------------------------------------------
    # SELECT clause
    # ------------------------------------------------------------------

    def _build_select_clause(
        self,
        concept_map: Dict[str, Any],
        grain_context: Dict[str, Any],
        snapshot: SemanticSnapshot
    ) -> str:
        """Build SELECT clause from concept_map and grain_context with DATE_TRUNC support."""
        select_fields: List[str] = []
        aggregation_required = grain_context.get("aggregation_required", False)
        date_trunc_field = grain_context.get("date_trunc_field")
        date_trunc_unit = grain_context.get("date_trunc_unit")
        q = self.dialect.quote_identifier

        # --- Dimension fields ---
        dimensions = concept_map.get("dimensions", [])
        for dim in dimensions:
            field_id = dim.get("field_id", "")
            field_name = dim.get("field_name", "")
            if not field_name:
                continue

            if date_trunc_field and field_id == date_trunc_field and date_trunc_unit:
                ref, _ = self._resolve_field_ref(field_id, field_name, snapshot)
                expr = self.dialect.render_date_trunc(ref, date_trunc_unit)
                select_fields.append(f"{expr} AS {q(f'{field_name}_month')}")
            else:
                ref, entity_name = self._resolve_field_ref(field_id, field_name, snapshot)
                conflict = any(
                    d.get("field_name") == field_name and d.get("field_id") != field_id
                    for d in dimensions
                )
                if conflict and entity_name:
                    select_fields.append(f"{ref} AS {q(f'{entity_name}_{field_name}')}")
                else:
                    select_fields.append(ref)

        # --- Expression columns (BUG-F) ---
        for expr in concept_map.get("expressions", []):
            expr_type = expr.get("expression_type", "")
            alias = q(expr.get("name", "expression"))
            if expr_type == "concatenation":
                separator = expr.get("separator", "")
                parts = []
                for f in expr.get("fields", []):
                    fid = f.get("field_id", "")
                    fname = f.get("field_name", "")
                    ref, _ = self._resolve_field_ref(fid, fname, snapshot)
                    parts.append(ref)
                if parts:
                    if separator:
                        joined = f" || {self._escape_value(separator)} || ".join(parts)
                    else:
                        joined = " || ".join(parts)
                    select_fields.append(f"{joined} AS {alias}")

        # --- Metric fields ---
        for metric in concept_map.get("metrics", []):
            metric_name = metric.get("metric_name", "")
            field_id = metric.get("field_id", "")
            if not metric_name:
                continue

            # BUG-I: COUNT(*) sentinel — empty field_id means COUNT(*)
            if not field_id and aggregation_required:
                agg = metric.get("aggregation_type", "COUNT").upper()
                if agg == "COUNT":
                    select_fields.append(f"COUNT(*) AS {q(metric_name)}")
                    continue

            # Resolve column name: field_def.name → field_id tail → metric_name
            if field_id:
                field_def = snapshot.fields.get(field_id)
                fallback = field_def.name if field_def else (
                    field_id.split(":")[-1] if ":" in field_id else metric_name
                )
            else:
                fallback = metric_name

            col_ref, _ = self._resolve_field_ref(field_id, fallback, snapshot)
            alias = q(metric_name)

            if aggregation_required:
                agg = metric.get("aggregation_type", "SUM")
                if agg.upper() == "COUNT_DISTINCT":
                    select_fields.append(f"COUNT(DISTINCT {col_ref}) AS {alias}")
                else:
                    select_fields.append(f"{agg}({col_ref}) AS {alias}")
            else:
                select_fields.append(f"{col_ref} AS {alias}")

        # --- Fallback: concept_map.fields (raw SELECT without aggregation) ---
        if not select_fields:
            fields_list = concept_map.get("fields", [])
            for field in fields_list:
                fid = field.get("field_id", "")
                fname = field.get("field_name", "")
                if not fname:
                    continue
                ref, ename = self._resolve_field_ref(fid, fname, snapshot)
                conflict = any(
                    f.get("field_name") == fname and f.get("field_id") != fid
                    for f in fields_list
                )
                if conflict and ename:
                    select_fields.append(f"{ref} AS {q(f'{ename}_{fname}')}")
                else:
                    select_fields.append(ref)

        if not select_fields:
            select_fields.append("*")

        return f"SELECT {', '.join(select_fields)}"

    # ------------------------------------------------------------------
    # WHERE clause
    # ------------------------------------------------------------------

    def _build_where_clause(
        self,
        concept_map: Dict[str, Any],
        policy_context: Dict[str, Any],
        snapshot: Optional[SemanticSnapshot] = None,
        temporal_filters: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Build WHERE clause from structured filters, temporal filters, and policy predicates.

        Args:
            concept_map: Concept map with filters
            policy_context: Policy context with resolved predicates
            snapshot: Optional SemanticSnapshot for fully qualified field names
            temporal_filters: Top-level temporal_filters from StructuredFilter
        """
        where_predicates: List[str] = []

        # Process top-level temporal_filters (e.g. between/trailing_interval on date fields)
        for tf in (temporal_filters or []):
            if not isinstance(tf, dict):
                continue
            op = tf.get("operator")
            val = tf.get("value")
            if not op or val is None:
                continue
            temporal_filter = TemporalFilter(
                field_id=tf.get("field_id", ""),
                operator=TemporalOperator(op),
                value=val,
            )
            sql_expr = self.dialect.render_temporal_filter(temporal_filter)
            where_predicates.append(sql_expr)

        # Process structured filters from concept_map
        filters = concept_map.get("filters", [])
        for filter_item in filters:
            # Check if it's a TemporalFilter (structured)
            if isinstance(filter_item, dict) and "operator" in filter_item:
                operator = _OPERATOR_ALIASES.get(filter_item.get("operator", ""), filter_item.get("operator", ""))

                # Handle temporal filters
                if operator in ["trailing_interval", "leading_interval", "between", "on_or_after", "on_or_before", "equals"]:
                    val = filter_item.get("value")
                    if val is None:
                        continue
                    temporal_filter = TemporalFilter(
                        field_id=filter_item.get("field_id", ""),
                        operator=TemporalOperator(operator),
                        value=val,
                    )
                    sql_expr = self.dialect.render_temporal_filter(temporal_filter)
                    where_predicates.append(sql_expr)

                # Handle standard filters
                else:
                    filter_def = FilterDef(
                        field_id=filter_item.get("field_id", ""),
                        operator=FilterOperator(operator or "="),
                        value=filter_item.get("value"),
                        entity_id=filter_item.get("entity_id")
                    )
                    sql_expr = self._render_filter_def(filter_def, snapshot)
                    where_predicates.append(sql_expr)

        # Add policy predicates
        resolved_predicates = policy_context.get("resolved_predicates", [])
        where_predicates.extend(resolved_predicates)

        if not where_predicates:
            return ""

        return f"WHERE {' AND '.join(where_predicates)}"

    def _escape_value(self, value: Any) -> str:
        """
        Escape a value for safe SQL insertion.

        Args:
            value: Value to escape (string values will have single quotes escaped)

        Returns:
            Escaped string representation of the value
        """
        if isinstance(value, str):
            escaped = value.replace("'", "''")
            return f"'{escaped}'"
        else:
            return str(value)

    def _render_filter_def(self, filter_def: FilterDef, snapshot: Optional[SemanticSnapshot] = None) -> str:
        """Render a FilterDef into a SQL predicate with fully qualified field names."""
        field_name = filter_def.field_id.split(":")[-1] if ":" in filter_def.field_id else filter_def.field_id

        # Resolve field reference through the single helper
        if snapshot:
            field_ref, _ = self._resolve_field_ref(
                filter_def.field_id, field_name, snapshot,
                entity_id=filter_def.entity_id or "",
            )
        else:
            field_ref = self.dialect.quote_identifier(field_name)

        if filter_def.operator == FilterOperator.IS_NULL:
            return f"{field_ref} IS NULL"

        elif filter_def.operator == FilterOperator.IS_NOT_NULL:
            return f"{field_ref} IS NOT NULL"

        elif filter_def.operator == FilterOperator.IN:
            if isinstance(filter_def.value, list):
                values_str = ", ".join([self._escape_value(v) for v in filter_def.value])
                return f"{field_ref} IN ({values_str})"
            else:
                return f"{field_ref} = {self._escape_value(filter_def.value)}"

        elif filter_def.operator == FilterOperator.NOT_IN:
            if isinstance(filter_def.value, list):
                values_str = ", ".join([self._escape_value(v) for v in filter_def.value])
                return f"{field_ref} NOT IN ({values_str})"
            else:
                return f"{field_ref} != {self._escape_value(filter_def.value)}"

        elif filter_def.operator in [FilterOperator.EQUALS, FilterOperator.NOT_EQUALS,
                                      FilterOperator.GREATER_THAN, FilterOperator.GREATER_THAN_OR_EQUAL,
                                      FilterOperator.LESS_THAN, FilterOperator.LESS_THAN_OR_EQUAL]:
            value_str = self._escape_value(filter_def.value) if isinstance(filter_def.value, str) else str(filter_def.value)
            return f"{field_ref} {filter_def.operator.value} {value_str}"

        elif filter_def.operator in [FilterOperator.LIKE, FilterOperator.ILIKE]:
            return f"{field_ref} {filter_def.operator.value} {self._escape_value(filter_def.value)}"

        else:
            raise ValueError(f"Unsupported filter operator: {filter_def.operator}")

    # ------------------------------------------------------------------
    # GROUP BY clause
    # ------------------------------------------------------------------

    def _build_group_by_clause(
        self,
        grain_context: Dict[str, Any],
        snapshot: SemanticSnapshot
    ) -> str:
        """Build GROUP BY clause from grain_context with DATE_TRUNC support."""
        grouping_fields = grain_context.get("grouping_fields", [])
        if not grain_context.get("aggregation_required", False) or not grouping_fields:
            return ""

        date_trunc_field = grain_context.get("date_trunc_field")
        date_trunc_unit = grain_context.get("date_trunc_unit")
        quoted: List[str] = []

        for field_ref in grouping_fields:
            field_id, col_name = self._resolve_grouping_field(field_ref, snapshot)

            if date_trunc_field and date_trunc_unit and field_id == date_trunc_field:
                ref, _ = self._resolve_field_ref(field_id, col_name, snapshot)
                quoted.append(self.dialect.render_date_trunc(ref, date_trunc_unit))
            else:
                ref, _ = self._resolve_field_ref(field_id, col_name, snapshot)
                quoted.append(ref)

        return f"GROUP BY {', '.join(quoted)}" if quoted else ""

    # ------------------------------------------------------------------
    # ORDER BY clause (BUG-B)
    # ------------------------------------------------------------------

    def _build_order_by_clause(
        self,
        planner_output: Dict[str, Any],
        snapshot: SemanticSnapshot,
    ) -> str:
        """Build ORDER BY clause from planner_output order_by list.

        order_by entries may reference a field_id (raw column) or a metric_name
        (aggregate alias). The builder handles both.
        """
        order_by = planner_output.get("order_by", [])
        if not order_by:
            return ""

        q = self.dialect.quote_identifier
        clauses = []
        for ob in order_by:
            direction = ob.get("direction", "ASC")
            field_id = ob.get("field_id", "")
            metric_name = ob.get("metric_name", "")

            if field_id:
                field_def = snapshot.fields.get(field_id)
                if field_def:
                    entity = snapshot.entities.get(field_def.entity_id)
                    if entity:
                        ref = f"{q(entity.name)}.{q(field_def.name)}"
                        clauses.append(f"{ref} {direction}")
                        continue
            if metric_name:
                # Reference the aggregate alias from SELECT
                clauses.append(f"{q(metric_name)} {direction}")

        return f"ORDER BY {', '.join(clauses)}" if clauses else ""
