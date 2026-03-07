"""
SQL Dialect implementations using Strategy Pattern.

Each dialect implements dialect-specific SQL rendering for:
- Temporal intervals (INTERVAL syntax)
- Identifier quoting
- Function names
- Data types
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from boyce.types import TemporalFilter, TemporalOperator, TemporalUnit


class SQLDialect(ABC):
    """Abstract base class for SQL dialect implementations."""

    @abstractmethod
    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier (table/column name) for this dialect."""
        pass

    @abstractmethod
    def render_temporal_filter(self, filter_obj: TemporalFilter) -> str:
        """Render a temporal filter into dialect-specific SQL."""
        pass

    @abstractmethod
    def render_interval(self, value: int, unit: TemporalUnit) -> str:
        """Render an interval expression (e.g., INTERVAL '12 months')."""
        pass

    def render_cast(self, expression: str, type_name: str) -> str:
        """
        Render a type cast. Dialects may override to inject safe casting (e.g., NULLIF for numerics).
        Default: CAST(expression AS type_name).
        """
        return f"CAST({expression} AS {type_name})"

    def validate_compatibility(self, sql: str) -> List[str]:
        """
        Return a list of compatibility errors for this dialect. Empty list means valid.
        Dialects may override to reject SQL that is syntactically valid but unsupported
        (e.g., LATERAL joins, JSONB).
        """
        return []


class PostgresDialect(SQLDialect):
    """PostgreSQL dialect implementation."""

    def quote_identifier(self, identifier: str) -> str:
        """Postgres uses double quotes for identifiers."""
        return f'"{identifier}"'

    def render_interval(self, value: int, unit: TemporalUnit) -> str:
        """Postgres: INTERVAL '12 months'"""
        unit_str = unit.value
        if unit == TemporalUnit.MONTH:
            unit_str = "month" if value == 1 else "months"
        elif unit == TemporalUnit.YEAR:
            unit_str = "year" if value == 1 else "years"
        elif unit == TemporalUnit.DAY:
            unit_str = "day" if value == 1 else "days"
        elif unit == TemporalUnit.HOUR:
            unit_str = "hour" if value == 1 else "hours"
        elif unit == TemporalUnit.MINUTE:
            unit_str = "minute" if value == 1 else "minutes"
        elif unit == TemporalUnit.SECOND:
            unit_str = "second" if value == 1 else "seconds"
        elif unit == TemporalUnit.WEEK:
            unit_str = "week" if value == 1 else "weeks"
        elif unit == TemporalUnit.QUARTER:
            unit_str = "quarter" if value == 1 else "quarters"

        return f"INTERVAL '{value} {unit_str}'"

    def render_temporal_filter(self, filter_obj: TemporalFilter) -> str:
        """Render temporal filter for Postgres."""
        field_ref = self.quote_identifier(filter_obj.field_id.split(":")[-1])

        if filter_obj.operator == TemporalOperator.TRAILING_INTERVAL:
            # "last 12 months" -> field >= CURRENT_DATE - INTERVAL '12 months'
            if isinstance(filter_obj.value, dict):
                value = filter_obj.value.get("value", 12)
                unit = TemporalUnit(filter_obj.value.get("unit", "month"))
                interval = self.render_interval(value, unit)
                return f"{field_ref} >= CURRENT_DATE - {interval}"
            else:
                # Fallback
                return f"{field_ref} >= CURRENT_DATE - INTERVAL '12 months'"

        elif filter_obj.operator == TemporalOperator.LEADING_INTERVAL:
            # "next 12 months" -> field <= CURRENT_DATE + INTERVAL '12 months'
            if isinstance(filter_obj.value, dict):
                value = filter_obj.value.get("value", 12)
                unit = TemporalUnit(filter_obj.value.get("unit", "month"))
                interval = self.render_interval(value, unit)
                return f"{field_ref} <= CURRENT_DATE + {interval}"
            else:
                return f"{field_ref} <= CURRENT_DATE + INTERVAL '12 months'"

        elif filter_obj.operator == TemporalOperator.BETWEEN:
            # "between date1 and date2"
            if isinstance(filter_obj.value, dict):
                start = filter_obj.value.get("start", "")
                end = filter_obj.value.get("end", "")
                return f"{field_ref} BETWEEN '{start}' AND '{end}'"
            else:
                return f"{field_ref} BETWEEN '{filter_obj.value}' AND '{filter_obj.value}'"

        elif filter_obj.operator == TemporalOperator.ON_OR_AFTER:
            return f"{field_ref} >= '{filter_obj.value}'"

        elif filter_obj.operator == TemporalOperator.ON_OR_BEFORE:
            return f"{field_ref} <= '{filter_obj.value}'"

        elif filter_obj.operator == TemporalOperator.EQUALS:
            return f"{field_ref} = '{filter_obj.value}'"

        else:
            raise ValueError(f"Unsupported temporal operator: {filter_obj.operator}")

    def render_date_trunc(self, field: str, unit: str) -> str:
        """Postgres: DATE_TRUNC('month', field)"""
        return f"DATE_TRUNC('{unit}', {field})"


class DuckDBDialect(SQLDialect):
    """DuckDB dialect implementation."""

    def quote_identifier(self, identifier: str) -> str:
        """DuckDB uses double quotes for identifiers."""
        return f'"{identifier}"'

    def render_interval(self, value: int, unit: TemporalUnit) -> str:
        """DuckDB: INTERVAL 1 YEAR or INTERVAL '12 months'"""
        if unit == TemporalUnit.MONTH:
            return f"INTERVAL '{value} months'"
        elif unit == TemporalUnit.YEAR:
            return f"INTERVAL {value} YEAR" if value == 1 else f"INTERVAL {value} YEARS"
        else:
            return f"INTERVAL '{value} {unit.value}s'"

    def render_temporal_filter(self, filter_obj: TemporalFilter) -> str:
        """Render temporal filter for DuckDB."""
        field_ref = self.quote_identifier(filter_obj.field_id.split(":")[-1])

        if filter_obj.operator == TemporalOperator.TRAILING_INTERVAL:
            if isinstance(filter_obj.value, dict):
                value = filter_obj.value.get("value", 12)
                unit = TemporalUnit(filter_obj.value.get("unit", "month"))
                interval = self.render_interval(value, unit)
                return f"{field_ref} >= CURRENT_DATE - {interval}"
            else:
                return f"{field_ref} >= CURRENT_DATE - INTERVAL '12 months'"

        elif filter_obj.operator == TemporalOperator.LEADING_INTERVAL:
            if isinstance(filter_obj.value, dict):
                value = filter_obj.value.get("value", 12)
                unit = TemporalUnit(filter_obj.value.get("unit", "month"))
                interval = self.render_interval(value, unit)
                return f"{field_ref} <= CURRENT_DATE + {interval}"
            else:
                return f"{field_ref} <= CURRENT_DATE + INTERVAL '12 months'"

        elif filter_obj.operator == TemporalOperator.BETWEEN:
            if isinstance(filter_obj.value, dict):
                start = filter_obj.value.get("start", "")
                end = filter_obj.value.get("end", "")
                return f"{field_ref} BETWEEN '{start}' AND '{end}'"
            else:
                return f"{field_ref} BETWEEN '{filter_obj.value}' AND '{filter_obj.value}'"

        elif filter_obj.operator == TemporalOperator.ON_OR_AFTER:
            return f"{field_ref} >= '{filter_obj.value}'"

        elif filter_obj.operator == TemporalOperator.ON_OR_BEFORE:
            return f"{field_ref} <= '{filter_obj.value}'"

        elif filter_obj.operator == TemporalOperator.EQUALS:
            return f"{field_ref} = '{filter_obj.value}'"

        else:
            raise ValueError(f"Unsupported temporal operator: {filter_obj.operator}")

    def render_date_trunc(self, field: str, unit: str) -> str:
        """DuckDB: DATE_TRUNC('month', field)"""
        return f"DATE_TRUNC('{unit}', {field})"


class BigQueryDialect(SQLDialect):
    """BigQuery dialect implementation."""

    def quote_identifier(self, identifier: str) -> str:
        """BigQuery uses backticks for identifiers."""
        return f"`{identifier}`"

    def render_interval(self, value: int, unit: TemporalUnit) -> str:
        """BigQuery: INTERVAL 12 MONTH"""
        unit_str = unit.value.upper()
        return f"INTERVAL {value} {unit_str}"

    def render_temporal_filter(self, filter_obj: TemporalFilter) -> str:
        """Render temporal filter for BigQuery."""
        field_ref = self.quote_identifier(filter_obj.field_id.split(":")[-1])

        if filter_obj.operator == TemporalOperator.TRAILING_INTERVAL:
            if isinstance(filter_obj.value, dict):
                value = filter_obj.value.get("value", 12)
                unit = TemporalUnit(filter_obj.value.get("unit", "month"))
                interval = self.render_interval(value, unit)
                return f"{field_ref} >= DATE_SUB(CURRENT_DATE(), {interval})"
            else:
                return f"{field_ref} >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)"

        elif filter_obj.operator == TemporalOperator.LEADING_INTERVAL:
            if isinstance(filter_obj.value, dict):
                value = filter_obj.value.get("value", 12)
                unit = TemporalUnit(filter_obj.value.get("unit", "month"))
                interval = self.render_interval(value, unit)
                return f"{field_ref} <= DATE_ADD(CURRENT_DATE(), {interval})"
            else:
                return f"{field_ref} <= DATE_ADD(CURRENT_DATE(), INTERVAL 12 MONTH)"

        elif filter_obj.operator == TemporalOperator.BETWEEN:
            if isinstance(filter_obj.value, dict):
                start = filter_obj.value.get("start", "")
                end = filter_obj.value.get("end", "")
                return f"{field_ref} BETWEEN '{start}' AND '{end}'"
            else:
                return f"{field_ref} BETWEEN '{filter_obj.value}' AND '{filter_obj.value}'"

        elif filter_obj.operator == TemporalOperator.ON_OR_AFTER:
            return f"{field_ref} >= '{filter_obj.value}'"

        elif filter_obj.operator == TemporalOperator.ON_OR_BEFORE:
            return f"{field_ref} <= '{filter_obj.value}'"

        elif filter_obj.operator == TemporalOperator.EQUALS:
            return f"{field_ref} = '{filter_obj.value}'"

        else:
            raise ValueError(f"Unsupported temporal operator: {filter_obj.operator}")

    def render_date_trunc(self, field: str, unit: str) -> str:
        """BigQuery: DATE_TRUNC(date_expression, date_part)"""
        date_part_map = {
            "DAY": "DATE",
            "WEEK": "WEEK",
            "MONTH": "MONTH",
            "QUARTER": "QUARTER",
            "YEAR": "YEAR",
        }
        date_part = date_part_map.get(unit.upper(), unit.upper())
        return f"DATE_TRUNC({field}, {date_part})"


# -----------------------------------------------------------------------------
# Redshift (Postgres 8.0.2–compatible, with constraints)
# -----------------------------------------------------------------------------

_NUMERIC_TYPE_NAMES = frozenset({
    "INT", "INTEGER", "DECIMAL", "NUMERIC", "FLOAT", "DOUBLE PRECISION",
})


class RedshiftDialect(PostgresDialect):
    """
    Redshift 1.0 dialect (Postgres 8.0.2–compatible).
    Enforces safe numeric casts (NULLIF empty string) and rejects unsupported features.
    """

    def render_cast(self, expression: str, type_name: str) -> str:
        """
        For numeric types, wrap in NULLIF(expression, '') to avoid invalid cast from ''.
        Otherwise delegate to default CAST.
        """
        normalized = type_name.upper().strip()
        if normalized in _NUMERIC_TYPE_NAMES:
            return f"CAST(NULLIF({expression}, '') AS {type_name})"
        return f"CAST({expression} AS {type_name})"

    def validate_compatibility(self, sql: str) -> List[str]:
        """
        Reject SQL that uses features not supported in Redshift 1.0
        (e.g., LATERAL joins, JSONB).
        """
        errors: List[str] = []
        upper = sql.upper()
        if " LATERAL " in upper:
            errors.append("Redshift 1.0 does not support LATERAL joins.")
        if "JSONB" in upper:
            errors.append("Redshift 1.0 does not support JSONB.")
        return errors
