"""
Production-Grade Context Sniper for DataShark Ingestion Engine

Recursively scans project directories to identify and catalog relevant files
(dbt, LookML, SQL) for dependency graph construction.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import sqlglot
    from sqlglot import exp
except ImportError:
    sqlglot = None
    exp = None
    logging.warning("sqlglot not available. SQL dependency extraction will be disabled.")

logger = logging.getLogger(__name__)


class ContextSniper:
    """
    Scans project directories to identify relevant files for ingestion.

    Production-grade implementation with proper error handling and type safety.
    """

    # File extensions to scan
    TARGET_EXTENSIONS = {
        ".sql": "sql",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
        ".lkml": "lookml",
        ".lookml": "lookml",
    }

    # Specific filenames of interest
    TARGET_FILENAMES = {
        "dbt_project.yml": "dbt_project",
        "dbt_project.yaml": "dbt_project",
        "manifest.json": "dbt_manifest",
        "catalog.json": "dbt_catalog",
        "schema.yml": "dbt_schema",
        "schema.yaml": "dbt_schema",
        "sources.yml": "dbt_sources",
        "sources.yaml": "dbt_sources",
        "models.yml": "dbt_models",
        "models.yaml": "dbt_models",
    }

    # Directories to ignore during scanning
    IGNORED_DIRS = {
        ".git",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "target",  # dbt build artifacts (except manifest.json)
        ".pytest_cache",
        ".mypy_cache",
        "coverage",
        ".tox",
    }

    def __init__(self):
        """Initialize the context sniper."""
        self.scanned_files: List[Dict[str, Any]] = []

    def scan_project(self, root_path: Path) -> List[Dict[str, Any]]:
        """
        Recursively scan a project directory for relevant files.

        Args:
            root_path: Root directory to scan.

        Returns:
            List of dictionaries containing file metadata:
            {
                "path": str,           # Absolute path to file
                "name": str,            # Filename
                "type": str,            # Detected file type (e.g., "dbt_model", "lookml_view")
                "size": int,            # File size in bytes
                "modified": float,      # Modification timestamp
            }
        """
        root = Path(root_path).resolve()
        if not root.exists():
            logger.error(f"Root path does not exist: {root}")
            return []

        if not root.is_dir():
            logger.error(f"Root path is not a directory: {root}")
            return []

        logger.info(f"Scanning project: {root}")
        self.scanned_files = []

        try:
            self._scan_directory(root)
        except PermissionError as e:
            logger.error(f"Permission denied while scanning {root}: {e}")
            # Return partial results if available
        except Exception as e:
            logger.error(f"Error scanning project: {e}", exc_info=True)
            raise

        logger.info(f"Scan complete. Found {len(self.scanned_files)} relevant files.")
        return self.scanned_files

    def _scan_directory(self, directory: Path) -> None:
        """
        Recursively scan a directory.

        Args:
            directory: Directory to scan.
        """
        try:
            # Get directory contents
            entries = list(directory.iterdir())
        except PermissionError:
            logger.warning(f"Permission denied accessing directory: {directory}")
            return
        except Exception as e:
            logger.warning(f"Error reading directory {directory}: {e}")
            return

        for entry in entries:
            try:
                # Skip ignored directories
                if entry.is_dir():
                    if entry.name in self.IGNORED_DIRS:
                        # Special case: allow scanning target/ for manifest.json
                        if entry.name == "target":
                            # Scan target but only for manifest.json
                            self._scan_directory_selective(entry, {"manifest.json"})
                        continue
                    # Recurse into non-ignored directories
                    self._scan_directory(entry)
                elif entry.is_file():
                    self._process_file(entry)
            except PermissionError:
                logger.warning(f"Permission denied accessing {entry}")
                continue
            except Exception as e:
                logger.warning(f"Error processing {entry}: {e}")
                continue

    def _scan_directory_selective(
        self, directory: Path, allowed_filenames: set[str]
    ) -> None:
        """
        Scan a directory but only process specific filenames.

        Used for scanning target/ directories where we only want manifest.json.

        Args:
            directory: Directory to scan.
            allowed_filenames: Set of filenames to process.
        """
        try:
            entries = list(directory.iterdir())
        except PermissionError:
            return
        except Exception as e:
            logger.warning(f"Error reading directory {directory}: {e}")
            return

        for entry in entries:
            try:
                if entry.is_file() and entry.name in allowed_filenames:
                    self._process_file(entry)
            except PermissionError:
                continue
            except Exception as e:
                logger.warning(f"Error processing {entry}: {e}")
                continue

    def _process_file(self, file_path: Path) -> None:
        """
        Process a single file and add it to the scanned files list if relevant.

        Args:
            file_path: Path to the file to process.
        """
        try:
            # Check for target filenames first (highest priority)
            if file_path.name in self.TARGET_FILENAMES:
                file_type = self.TARGET_FILENAMES[file_path.name]
                self._add_file(file_path, file_type)
                return

            # Check file extension
            ext = file_path.suffix.lower()
            if ext not in self.TARGET_EXTENSIONS:
                return

            # Determine file type based on extension and context
            base_type = self.TARGET_EXTENSIONS[ext]
            file_type = self._refine_file_type(file_path, base_type)

            if file_type:
                self._add_file(file_path, file_type)

        except Exception as e:
            logger.warning(f"Error processing file {file_path}: {e}")

    def _refine_file_type(self, file_path: Path, base_type: str) -> Optional[str]:
        """
        Refine file type based on path context and naming conventions.

        Args:
            file_path: Path to the file.
            base_type: Base type from extension.

        Returns:
            Refined file type, or None if file should be ignored.
        """
        path_parts = file_path.parts
        filename = file_path.name.lower()

        # SQL files
        if base_type == "sql":
            # Check if in dbt models directory
            if "models" in path_parts:
                return "dbt_model"
            elif "macros" in path_parts:
                return "dbt_macro"
            elif "tests" in path_parts:
                return "dbt_test"
            elif "target" in path_parts:
                # Skip compiled SQL in target/ (noise)
                return None
            else:
                return "raw_sql"

        # YAML files
        elif base_type in ("yaml", "yml"):
            if "models" in path_parts or filename.startswith("schema"):
                return "dbt_schema"
            elif "sources" in path_parts or filename.startswith("sources"):
                return "dbt_sources"
            elif "macros" in path_parts:
                return "dbt_macro"
            else:
                return "dbt_yaml"  # Generic dbt YAML

        # LookML files
        elif base_type == "lookml":
            if ".view" in filename or filename.endswith(".view.lkml"):
                return "lookml_view"
            elif ".model" in filename or filename.endswith(".model.lkml"):
                return "lookml_model"
            elif ".explore" in filename or filename.endswith(".explore.lkml"):
                return "lookml_explore"
            else:
                return "lookml_file"

        # JSON files
        elif base_type == "json":
            # Only specific JSON files are interesting
            if filename in ("manifest.json", "catalog.json"):
                return "dbt_manifest" if filename == "manifest.json" else "dbt_catalog"
            else:
                # Skip other JSON files (usually noise)
                return None

        return base_type

    def parse_file(self, file_path: Path) -> List[str]:
        """
        Parse a SQL file and extract table dependencies using sqlglot.

        Public method for real-time file analysis.

        Args:
            file_path: Path to the SQL file to parse.

        Returns:
            List of unique table names referenced in the SQL file.
            Returns empty list if parsing fails or file is not SQL.
        """
        if not sqlglot or not exp:
            return []

        # Only process SQL files
        if file_path.suffix.lower() != ".sql":
            return []

        try:
            # Read file content
            sql_content = file_path.read_text(encoding="utf-8", errors="ignore")

            # Parse SQL into AST
            # Use parse() to handle multiple statements, then iterate
            # Note: parse() returns a list that may contain None values for unparseable statements
            parsed_statements = sqlglot.parse(sql_content, error_level=sqlglot.errors.ErrorLevel.IGNORE)

            if not parsed_statements:
                return []

            # Collect all table references
            table_names: Set[str] = set()

            # Filter out None values and iterate through valid statements only
            for statement in parsed_statements:
                # Skip None values (e.g., from pure comments, Jinja templates, or parse errors)
                if statement is None:
                    continue

                try:
                    # Find all Table expressions in the AST
                    for table_node in statement.find_all(exp.Table):
                        # Extract table name
                        table_name = table_node.name
                        if table_name:
                            # Optionally include schema/database prefix
                            # Format: "schema.table" or just "table"
                            if table_node.db:
                                full_name = f"{table_node.db}.{table_name}"
                            else:
                                full_name = table_name

                            table_names.add(full_name)
                except AttributeError as e:
                    # Handle cases where statement doesn't have find_all (shouldn't happen, but be safe)
                    logger.debug(f"Statement in {file_path} doesn't support find_all: {e}")
                    continue
                except Exception as e:
                    # Catch any other errors during table extraction from this statement
                    logger.debug(f"Error extracting tables from statement in {file_path}: {e}")
                    continue

            return sorted(list(table_names))

        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return []

    def _add_file(self, file_path: Path, file_type: str) -> None:
        """
        Add a file to the scanned files list.

        Args:
            file_path: Path to the file.
            file_type: Detected type of the file.
        """
        try:
            stat = file_path.stat()
            file_info = {
                "path": str(file_path),
                "name": file_path.name,
                "type": file_type,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }

            # Extract dependencies for SQL files
            if file_type in ("dbt_model", "dbt_macro", "dbt_test", "raw_sql"):
                dependencies = self.parse_file(file_path)
                file_info["dependencies"] = dependencies

            self.scanned_files.append(file_info)
        except PermissionError:
            logger.warning(f"Permission denied accessing {file_path}")
        except Exception as e:
            logger.error(f"Error adding file {file_path}: {e}")

    def build_map(self) -> Dict[str, Any]:
        """
        Build a dependency map from scanned files.

        Now includes SQL dependency extraction using sqlglot for SQL files.

        Returns:
            Dictionary containing the dependency map structure:
            {
                "files": List[Dict],  # File metadata with dependencies
                "summary": Dict,       # Count by file type
                "total_files": int,    # Total files scanned
                "dependency_graph": Dict,  # Table -> [files that reference it]
            }
        """
        if not self.scanned_files:
            logger.warning("No files scanned. Call scan_project() first.")
            return {
                "files": [],
                "summary": {},
                "total_files": 0,
                "dependency_graph": {},
            }

        # Group files by type
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for file_info in self.scanned_files:
            file_type = file_info["type"]
            if file_type not in by_type:
                by_type[file_type] = []
            by_type[file_type].append(file_info)

        # Build summary
        summary = {
            file_type: len(files) for file_type, files in by_type.items()
        }

        # Build reverse dependency graph: table -> [files that reference it]
        dependency_graph: Dict[str, List[str]] = {}
        for file_info in self.scanned_files:
            dependencies = file_info.get("dependencies", [])
            file_path = file_info["path"]
            for table_name in dependencies:
                if table_name not in dependency_graph:
                    dependency_graph[table_name] = []
                dependency_graph[table_name].append(file_path)

        return {
            "files": self.scanned_files,
            "summary": summary,
            "total_files": len(self.scanned_files),
            "dependency_graph": dependency_graph,
        }
