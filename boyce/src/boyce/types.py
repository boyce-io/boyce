"""
Core type definitions for the Boyce protocol.

These types define the source-agnostic canonical representation of database
metadata that can be populated from any ingestion adapter (Looker, Tableau, dbt, etc.).

This file IS the protocol contract — the canonical Boyce type definitions.
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Semantic entity type classification (tables, views, BI/dbt objects)."""

    TABLE = "table"
    VIEW = "view"
    LOOKML_VIEW = "lookml_view"
    LOOKML_EXPLORE = "lookml_explore"
    AIRFLOW_DAG = "airflow_dag"
    METRIC = "metric"
    DBT_MODEL = "dbt_model"


class FieldType(str, Enum):
    """Semantic field type classification."""

    DIMENSION = "DIMENSION"
    MEASURE = "MEASURE"
    TIMESTAMP = "TIMESTAMP"
    ID = "ID"
    FOREIGN_KEY = "FOREIGN_KEY"


class JoinType(str, Enum):
    """SQL join type."""

    INNER = "INNER"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    FULL = "FULL"


class Entity(BaseModel):
    """
    Source-agnostic representation of a database table or semantic entity.

    Attributes:
        id: Unique identifier for this entity (e.g., "entity:orders")
        name: Human-readable name (e.g., "orders", "products")
        schema: Database schema name (optional)
        description: Optional description of the entity
        fields: List of fields (columns/measures) belonging to this entity
        grain: Optional grain specification (e.g., "ORDER", "DAILY", "CUSTOMER")

    Profiling fields (populated by profiler.py, excluded from snapshot_id hash):
        object_type: Storage type — "table", "view", "materialized_view", "external_table"
        row_count: Total row count as of last profile run
        view_sql: Raw view definition SQL (requires SQL parser — deferred)
        view_lineage: Source entity IDs this view reads from (deferred)
    """

    model_config = {"frozen": True, "populate_by_name": True}

    id: str
    name: str
    schema_name: Optional[str] = Field(default=None, alias="schema")
    description: Optional[str] = None
    fields: List[str] = Field(default_factory=list)  # List of field IDs
    grain: Optional[str] = None
    # Profiling fields — excluded from snapshot_id hash
    object_type: Optional[str] = None
    row_count: Optional[int] = None
    view_sql: Optional[str] = None
    view_lineage: Optional[List[str]] = None

    def to_vector_store_record(self) -> Dict[str, Any]:
        """JSON-safe dict for vector stores / agents. Uses Pydantic model_dump(mode='json')."""
        return self.model_dump(mode="json")


class FieldDef(BaseModel):
    """
    Source-agnostic representation of a database column or semantic field.

    Attributes:
        id: Unique identifier (e.g., "field:orders:order_id")
        entity_id: ID of the parent entity
        name: Column/field name
        field_type: Semantic classification (DIMENSION, MEASURE, etc.)
        data_type: SQL data type (e.g., "INTEGER", "VARCHAR(255)", "DECIMAL(10,2)")
        nullable: Whether the field can be NULL
        primary_key: Whether this is a primary key
        description: Optional description
        valid_values: Optional list of valid enum values (for filters)

    Profiling fields (populated by profiler.py, excluded from snapshot_id hash):
        null_rate: Fraction of rows where this column is NULL (0.0–1.0)
        distinct_count: Number of distinct non-NULL values
        sample_values: Distinct values when distinct_count <= 25 (enum detection)
        business_description: Human-readable column meaning from parser or host LLM
        business_rules: Assertions from dbt tests or similar (e.g. "not_null", "unique")
    """

    model_config = {"frozen": True}

    id: str
    entity_id: str
    name: str
    field_type: FieldType
    data_type: str
    nullable: bool = False
    primary_key: bool = False
    description: Optional[str] = None
    valid_values: Optional[List[str]] = None
    # Profiling fields — excluded from snapshot_id hash
    null_rate: Optional[float] = None
    distinct_count: Optional[int] = None
    sample_values: Optional[List[str]] = None
    business_description: Optional[str] = None
    business_rules: Optional[List[str]] = None


class JoinDef(BaseModel):
    """
    Source-agnostic representation of a join relationship between entities.

    Attributes:
        id: Unique identifier (e.g., "join:orders:products")
        source_entity_id: ID of the source entity
        target_entity_id: ID of the target entity
        join_type: Type of join (INNER, LEFT, etc.)
        source_field_id: ID of the source field used in the join
        target_field_id: ID of the target field used in the join
        description: Optional description of the relationship

    Profiling fields (populated by profiler.py, excluded from snapshot_id hash):
        join_confidence: FK match rate (0.0–1.0) — fraction of FK values with a parent match
        orphan_rate: Fraction of FK values with no parent match (1.0 - join_confidence)
    """

    model_config = {"frozen": True}

    id: str
    source_entity_id: str
    target_entity_id: str
    join_type: JoinType
    source_field_id: str
    target_field_id: str
    description: Optional[str] = None
    # Profiling fields — excluded from snapshot_id hash
    join_confidence: Optional[float] = None
    orphan_rate: Optional[float] = None


class SemanticSnapshot(BaseModel):
    """
    Source-agnostic canonical representation of database metadata.

    This is the deterministic, immutable snapshot that can be populated from
    any ingestion adapter (Looker, Tableau, dbt, etc.) and used by the Planner
    and SQLBuilder without knowledge of the source origin.

    Attributes:
        snapshot_id: Deterministic SHA-256 hash identifier
        source_system: Origin system (e.g., "looker", "tableau", "dbt")
        source_version: Version of the source system or extractor
        entities: Dictionary mapping entity_id -> Entity
        fields: Dictionary mapping field_id -> FieldDef
        joins: List of join relationships
        metadata: Optional additional metadata (source-specific, but opaque to engine)
    """

    model_config = {"frozen": True}

    snapshot_id: str  # SHA-256 hash
    source_system: str
    source_version: Optional[str] = None
    schema_version: str = Field(default="v0.1")  # Schema version for evolution/versioning
    entities: Dict[str, Entity] = Field(default_factory=dict)
    fields: Dict[str, FieldDef] = Field(default_factory=dict)
    joins: List[JoinDef] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # Profiling timestamp — excluded from snapshot_id hash
    profiled_at: Optional[str] = None  # ISO 8601 timestamp of last profile run

    def get_entity_fields(self, entity_id: str) -> List[FieldDef]:
        """Get all fields for a given entity."""
        entity = self.entities.get(entity_id)
        if not entity:
            return []
        return [self.fields[field_id] for field_id in entity.fields if field_id in self.fields]

    def get_entity_joins(self, entity_id: str) -> List[JoinDef]:
        """Get all joins where the given entity is the source."""
        return [j for j in self.joins if j.source_entity_id == entity_id]

    def to_vector_store_record(self) -> Dict[str, Any]:
        """JSON-safe dict for vector stores / agents. Uses Pydantic model_dump(mode='json')."""
        return self.model_dump(mode="json")

    def find_join_path(self, source_entity_id: str, target_entity_id: str) -> List[JoinDef]:
        """
        Find a join path between two entities (BFS, bidirectional FK traversal).

        Joins can be traversed in either direction — forward (FK source → target)
        or reverse (FK target → source). Reverse traversal is needed for junction
        tables (M:N) where the FK points INTO the junction from the surrounding
        entities (e.g. film → film_category requires reversing the FK
        film_category.film_id → film.film_id).

        Reversed JoinDef objects have source/target and field IDs swapped so the
        SQL renderer produces correct ON clauses regardless of direction.

        Returns empty list if no path exists.
        """
        if source_entity_id == target_entity_id:
            return []

        # Build adjacency list with both forward and reverse edges.
        adj: Dict[str, List[JoinDef]] = {}
        for join in self.joins:
            # Forward edge
            adj.setdefault(join.source_entity_id, []).append(join)
            # Reverse edge — swapped source/target and field IDs so SQL renderer
            # produces correct ON clauses when traversing in reverse.
            reverse = JoinDef(
                id=f"{join.id}:reverse",
                source_entity_id=join.target_entity_id,
                target_entity_id=join.source_entity_id,
                join_type=join.join_type,
                source_field_id=join.target_field_id,
                target_field_id=join.source_field_id,
                description=f"reverse: {join.description}" if join.description else None,
            )
            adj.setdefault(join.target_entity_id, []).append(reverse)

        # BFS to find path
        queue = deque([(source_entity_id, [])])
        visited = {source_entity_id}

        while queue:
            current, path = queue.popleft()

            if current == target_entity_id:
                return path

            for join in adj.get(current, []):
                next_entity = join.target_entity_id
                if next_entity not in visited:
                    visited.add(next_entity)
                    queue.append((next_entity, path + [join]))

        return []  # No path found


# ---------------------------------------------------------------------------
# Structured Filter Models (Temporal & Logical)
# ---------------------------------------------------------------------------


class TemporalUnit(str, Enum):
    """Time unit for temporal intervals."""

    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class TemporalOperator(str, Enum):
    """Temporal filter operators."""

    TRAILING_INTERVAL = "trailing_interval"  # "last 12 months"
    LEADING_INTERVAL = "leading_interval"    # "next 12 months"
    BETWEEN = "between"                       # "between date1 and date2"
    ON_OR_AFTER = "on_or_after"              # ">= date"
    ON_OR_BEFORE = "on_or_before"            # "<= date"
    EQUALS = "equals"                         # "= date"


class TemporalFilter(BaseModel):
    """
    Structured temporal filter resolved by the Planner.

    The Planner must resolve natural language temporal expressions (e.g., "last 12 months")
    into this structured format. The SQLBuilder then renders this into dialect-specific SQL.

    Attributes:
        field_id: ID of the timestamp field to filter on
        operator: Temporal operator (trailing_interval, between, etc.)
        value: For trailing/leading_interval: {value: 12, unit: "month"}
                For between: {start: "2023-01-01", end: "2023-12-31"}
                For on_or_after/on_or_before/equals: ISO date string
    """

    model_config = {"frozen": True}

    field_id: str
    operator: TemporalOperator
    value: Union[Dict[str, Any], str]  # Structured dict or ISO date string


class FilterOperator(str, Enum):
    """Standard SQL filter operators."""

    EQUALS = "="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    IN = "IN"
    NOT_IN = "NOT IN"
    LIKE = "LIKE"
    ILIKE = "ILIKE"  # Case-insensitive LIKE (Postgres)
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"


class FilterDef(BaseModel):
    """
    Structured filter definition resolved by the Planner.

    All filters must be structured objects, never raw SQL strings.
    The SQLBuilder renders these into dialect-specific SQL.

    Attributes:
        field_id: ID of the field to filter on
        operator: Filter operator
        value: Filter value (scalar, list for IN, or None for IS NULL)
        entity_id: Optional entity ID for table qualification
    """

    model_config = {"frozen": True}

    field_id: str
    operator: FilterOperator
    value: Union[str, int, float, List[Union[str, int, float]], None]
    entity_id: Optional[str] = None
