"""
Dialect-aware SQL Builder using Strategy Pattern.

This builder renders structured filters (TemporalFilter, FilterDef) into
dialect-specific SQL. It never interprets natural language; it only renders
structured objects resolved by the Planner.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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

        # Assemble final SQL
        sql_parts = [select_clause, from_clause]
        sql_parts.extend(join_clauses)
        if where_clause:
            sql_parts.append(where_clause)
        if group_by_clause:
            sql_parts.append(group_by_clause)

        final_sql = " ".join(sql_parts)

        # Enforce dialect compatibility (e.g. LATERAL / JSONB for Redshift)
        errors = self.dialect.validate_compatibility(final_sql)
        if errors:
            raise ValueError(
                f"Dialect Incompatibility ({self.dialect.__class__.__name__}): {'; '.join(errors)}"
            )

        return final_sql

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

    def _build_select_clause(
        self,
        concept_map: Dict[str, Any],
        grain_context: Dict[str, Any],
        snapshot: SemanticSnapshot
    ) -> str:
        """Build SELECT clause from concept_map and grain_context with DATE_TRUNC support."""
        select_fields: List[str] = []
        aggregation_required = grain_context.get("aggregation_required", False)

        # Check if DATE_TRUNC is required for temporal grouping
        date_trunc_field = grain_context.get("date_trunc_field")
        date_trunc_unit = grain_context.get("date_trunc_unit")

        # Add dimension fields (with DATE_TRUNC if specified)
        dimensions = concept_map.get("dimensions", [])
        for dim in dimensions:
            field_id = dim.get("field_id", "")
            field_name = dim.get("field_name", "")

            if not field_name:
                continue

            # Check if this field needs DATE_TRUNC
            if date_trunc_field and field_id == date_trunc_field and date_trunc_unit:
                # Get field from snapshot to get entity name for table qualification
                field_def = snapshot.fields.get(field_id)
                if field_def:
                    entity = snapshot.entities.get(field_def.entity_id)
                    if entity:
                        table_quoted = self.dialect.quote_identifier(entity.name)
                        field_quoted = self.dialect.quote_identifier(field_name)
                        date_trunc_expr = self.dialect.render_date_trunc(
                            f"{table_quoted}.{field_quoted}",
                            date_trunc_unit
                        )
                        select_fields.append(f"{date_trunc_expr} AS {self.dialect.quote_identifier(f'{field_name}_month')}")
                    else:
                        date_trunc_expr = self.dialect.render_date_trunc(
                            self.dialect.quote_identifier(field_name),
                            date_trunc_unit
                        )
                        select_fields.append(f"{date_trunc_expr} AS {self.dialect.quote_identifier(f'{field_name}_month')}")
                else:
                    date_trunc_expr = self.dialect.render_date_trunc(
                        self.dialect.quote_identifier(field_name),
                        date_trunc_unit
                    )
                    select_fields.append(f"{date_trunc_expr} AS {self.dialect.quote_identifier(f'{field_name}_month')}")
            else:
                # Regular dimension field
                quoted = self.dialect.quote_identifier(field_name)
                select_fields.append(quoted)

        # Add metrics (with aggregation if required)
        metrics = concept_map.get("metrics", [])
        for metric in metrics:
            metric_name = metric.get("metric_name", "")
            field_id = metric.get("field_id", "")
            if metric_name:
                # Resolve field_id → actual column name for the aggregation expression
                col_name = None
                if field_id:
                    field_def = snapshot.fields.get(field_id)
                    if field_def:
                        col_name = field_def.name
                    else:
                        # field_id format is "field:Table:ColumnName" — extract last segment
                        col_name = field_id.split(":")[-1] if ":" in field_id else field_id
                if not col_name:
                    col_name = metric_name
                col_quoted = self.dialect.quote_identifier(col_name)
                alias_quoted = self.dialect.quote_identifier(metric_name)
                if aggregation_required:
                    agg_func = metric.get("aggregation_type", "SUM")
                    select_fields.append(f"{agg_func}({col_quoted}) AS {alias_quoted}")
                else:
                    select_fields.append(f"{col_quoted} AS {alias_quoted}")

        if not select_fields:
            select_fields.append("*")

        return f"SELECT {', '.join(select_fields)}"

    def _build_from_clause(
        self,
        join_path: List[tuple],
        concept_map: Dict[str, Any]
    ) -> str:
        """Build FROM clause from join_path."""
        if join_path:
            first_join = join_path[0]
            if isinstance(first_join, (list, tuple)) and len(first_join) >= 1:
                source_entity_id = first_join[0]
                entity_name = source_entity_id.replace("entity:", "") if "entity:" in source_entity_id else source_entity_id
                quoted = self.dialect.quote_identifier(entity_name)
                return f"FROM {quoted}"

        entities = concept_map.get("entities", [])
        if entities:
            entity_name = entities[0].get("entity_name", "")
            if entity_name:
                quoted = self.dialect.quote_identifier(entity_name)
                return f"FROM {quoted}"

        return "FROM unknown_table"

    def _build_join_clauses(self, join_path: List) -> List[str]:
        """Build JOIN clauses from join_path."""
        join_clauses: List[str] = []

        for join_item in join_path:
            # Handle dict format (preferred)
            if isinstance(join_item, dict):
                source_entity_id = join_item.get("source_entity_id", "")
                target_entity_id = join_item.get("target_entity_id", "")
                source_field_id = join_item.get("source_field_id", "")
                target_field_id = join_item.get("target_field_id", "")

                source_name = source_entity_id.replace("entity:", "") if "entity:" in source_entity_id else source_entity_id
                target_name = target_entity_id.replace("entity:", "") if "entity:" in target_entity_id else target_entity_id

                source_field_name = source_field_id.split(":")[-1] if ":" in source_field_id else source_field_id
                target_field_name = target_field_id.split(":")[-1] if ":" in target_field_id else target_field_id

                source_quoted = self.dialect.quote_identifier(source_name)
                target_quoted = self.dialect.quote_identifier(target_name)
                source_field_quoted = self.dialect.quote_identifier(source_field_name)
                target_field_quoted = self.dialect.quote_identifier(target_field_name)

                join_condition = f"{source_quoted}.{source_field_quoted} = {target_quoted}.{target_field_quoted}"
                join_clause = f"LEFT OUTER JOIN {target_quoted} ON {join_condition}"
                join_clauses.append(join_clause)

            # Handle tuple format (legacy)
            elif isinstance(join_item, (list, tuple)) and len(join_item) >= 3:
                source_entity_id = join_item[0]
                target_entity_id = join_item[1]
                join_key = join_item[2]

                source_name = source_entity_id.replace("entity:", "") if "entity:" in source_entity_id else source_entity_id
                target_name = target_entity_id.replace("entity:", "") if "entity:" in target_entity_id else target_entity_id

                source_quoted = self.dialect.quote_identifier(source_name)
                target_quoted = self.dialect.quote_identifier(target_name)
                key_quoted = self.dialect.quote_identifier(join_key)

                join_condition = f"{source_quoted}.{key_quoted} = {target_quoted}.{key_quoted}"
                join_clause = f"LEFT OUTER JOIN {target_quoted} ON {join_condition}"
                join_clauses.append(join_clause)

        return join_clauses

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
                operator = filter_item.get("operator", "")

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
                        operator=FilterOperator(filter_item.get("operator", "=")),
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
        """
        Render a FilterDef into SQL predicate with fully qualified field names.

        Args:
            filter_def: FilterDef to render
            snapshot: Optional SemanticSnapshot to resolve entity names for fully qualified references

        Returns:
            SQL predicate string with fully qualified field names
        """
        field_name = filter_def.field_id.split(":")[-1]

        # Get fully qualified field reference (entity.field)
        if snapshot and filter_def.entity_id:
            entity = snapshot.entities.get(filter_def.entity_id)
            if entity:
                entity_quoted = self.dialect.quote_identifier(entity.name)
                field_quoted = self.dialect.quote_identifier(field_name)
                field_ref = f"{entity_quoted}.{field_quoted}"
            else:
                field_ref = self.dialect.quote_identifier(field_name)
        elif snapshot:
            field_def = snapshot.fields.get(filter_def.field_id)
            if field_def:
                entity = snapshot.entities.get(field_def.entity_id)
                if entity:
                    entity_quoted = self.dialect.quote_identifier(entity.name)
                    field_quoted = self.dialect.quote_identifier(field_name)
                    field_ref = f"{entity_quoted}.{field_quoted}"
                else:
                    field_ref = self.dialect.quote_identifier(field_name)
            else:
                field_ref = self.dialect.quote_identifier(field_name)
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

    def _build_group_by_clause(
        self,
        grain_context: Dict[str, Any],
        snapshot: SemanticSnapshot
    ) -> str:
        """Build GROUP BY clause from grain_context with DATE_TRUNC support."""
        grouping_fields = grain_context.get("grouping_fields", [])
        aggregation_required = grain_context.get("aggregation_required", False)
        date_trunc_field = grain_context.get("date_trunc_field")
        date_trunc_unit = grain_context.get("date_trunc_unit")

        if aggregation_required and grouping_fields:
            quoted_fields: List[str] = []

            for field_ref in grouping_fields:
                # grouping_fields may contain field_ids ("field:Table:Col") or plain names.
                # Resolve to the actual column name via snapshot.
                field_id = None
                col_name = field_ref
                if field_ref in snapshot.fields:
                    field_id = field_ref
                    col_name = snapshot.fields[field_ref].name
                elif ":" in field_ref:
                    # "field:Table:ColumnName" — extract last segment as fallback
                    col_name = field_ref.split(":")[-1]
                    # Also try to find the actual field_id for DATE_TRUNC lookup
                    for fid, fdef in snapshot.fields.items():
                        if fid == field_ref or fdef.name == col_name:
                            field_id = fid
                            col_name = fdef.name
                            break

                # Check if this field needs DATE_TRUNC in GROUP BY
                if date_trunc_field and date_trunc_unit and field_id == date_trunc_field:
                    field_def = snapshot.fields.get(field_id)
                    if field_def:
                        entity = snapshot.entities.get(field_def.entity_id)
                        if entity:
                            table_quoted = self.dialect.quote_identifier(entity.name)
                            field_quoted = self.dialect.quote_identifier(col_name)
                            date_trunc_expr = self.dialect.render_date_trunc(
                                f"{table_quoted}.{field_quoted}",
                                date_trunc_unit
                            )
                            quoted_fields.append(date_trunc_expr)
                        else:
                            date_trunc_expr = self.dialect.render_date_trunc(
                                self.dialect.quote_identifier(col_name),
                                date_trunc_unit
                            )
                            quoted_fields.append(date_trunc_expr)
                    else:
                        quoted_fields.append(self.dialect.quote_identifier(col_name))
                else:
                    quoted_fields.append(self.dialect.quote_identifier(col_name))

            if quoted_fields:
                return f"GROUP BY {', '.join(quoted_fields)}"

        return ""
