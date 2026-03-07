"""
Boyce — Ingestion Parsers

Parsers for extracting SemanticSnapshot structures from:
- dbt manifest.json (Gold Standard)
- dbt raw YAML source files (Silver Standard)
- LookML .lkml files
- SQLite database files
- Raw SQL DDL files
- CSV / Parquet tabular files
- Django models.py files
- SQLAlchemy models.py files
- Prisma schema files

Plugin interface for community-extensible parsers:
    from boyce.parsers import SnapshotParser, ParserRegistry

Usage:
    from boyce.parsers import parse_dbt_manifest, detect_source_type
"""

from .base import SnapshotParser, build_snapshot
from .registry import ParserRegistry, get_default_registry, reset_default_registry
from .dbt import parse_dbt_manifest, parse_dbt_project_source, DbtManifestParser, DbtProjectParser
from .lookml import parse_lookml_file, LookMLParser
from .sqlite import parse_sqlite_file, SQLiteParser
from .ddl import parse_ddl_file, DDLParser
from .tabular import parse_csv_file, CSVParser, parse_parquet_file, ParquetParser
from .django import parse_django_models, DjangoParser
from .sqlalchemy_models import parse_sqlalchemy_models, SQLAlchemyParser
from .prisma import parse_prisma_schema, PrismaParser
from .detect import detect_source_type, parse_from_path

__all__ = [
    # Protocol + shared
    "SnapshotParser",
    "build_snapshot",
    "ParserRegistry",
    "get_default_registry",
    "reset_default_registry",
    # Parser classes
    "DbtManifestParser",
    "DbtProjectParser",
    "LookMLParser",
    "SQLiteParser",
    "DDLParser",
    "CSVParser",
    "ParquetParser",
    "DjangoParser",
    "SQLAlchemyParser",
    "PrismaParser",
    # Function API
    "parse_dbt_manifest",
    "parse_dbt_project_source",
    "parse_lookml_file",
    "parse_sqlite_file",
    "parse_ddl_file",
    "parse_csv_file",
    "parse_parquet_file",
    "parse_django_models",
    "parse_sqlalchemy_models",
    "parse_prisma_schema",
    "detect_source_type",
    "parse_from_path",
]
