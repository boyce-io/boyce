"""
Migration Manager

Handles instance schema and manifest migrations between framework versions.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Callable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class MigrationManager:
    """Manages instance migrations."""
    
    # Registered migrations: (from_version, to_version, migration_name, migration_func)
    MIGRATIONS: List[tuple[str, str, str, Callable]] = []
    
    def __init__(self):
        """Initialize migration manager."""
        self.migration_log: List[Dict[str, Any]] = []
        self._register_migrations()
    
    def _register_migrations(self):
        """Register all available migrations."""
        # Example migrations - add more as needed
        self.MIGRATIONS = [
            ("0.2.0", "0.3.0", "schema_v2_to_v3", self._migration_v2_to_v3),
            ("0.3.0", "0.3.1", "manifest_enrichment", self._migration_v3_to_v31),
            ("0.3.1", "0.3.2-dev", "dev_migration", self._migration_v31_to_v32dev),
        ]
    
    def _migration_v2_to_v3(self, instance_path: Path) -> List[str]:
        """Migrate from 0.2.0 to 0.3.0."""
        actions = []
        # Clean up old Looker-specific manifests if any
        manifests_dir = instance_path / "manifests"
        if manifests_dir.exists():
            for manifest_file in manifests_dir.glob("*.json"):
                try:
                    with open(manifest_file, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                        if manifest.get("system") == "looker":
                            manifest_file.unlink()
                            actions.append(f"Removed Looker manifest: {manifest_file.name}")
                except Exception as e:
                    logger.warning(f"Error processing manifest {manifest_file}: {e}")
        return actions
    
    def _migration_v3_to_v31(self, instance_path: Path) -> List[str]:
        """Migrate from 0.3.0 to 0.3.1."""
        actions = []
        # No-op migration - schema compatible
        actions.append("Schema compatible, no changes needed")
        return actions
    
    def _migration_v31_to_v32dev(self, instance_path: Path) -> List[str]:
        """Migrate from 0.3.1 to 0.3.2-dev."""
        actions = []
        # Ensure logs directory exists
        logs_dir = instance_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        actions.append("Ensured logs directory structure")
        return actions
    
    def _normalize_version(self, version: str) -> tuple:
        """Normalize version string for comparison (handles dev versions)."""
        # Remove -dev, -alpha, -dev0, etc. for comparison
        # Handle both 0.3.2-dev and 0.3.2.dev0 formats
        base_version = version.split('-')[0].split('.dev')[0].split('+')[0]
        parts = base_version.split('.')
        # Pad to 3 parts (major.minor.patch)
        while len(parts) < 3:
            parts.append('0')
        try:
            return tuple(int(x) for x in parts)
        except ValueError:
            # If version can't be parsed, treat as (0, 0, 0)
            logger.warning(f"Could not parse version: {version}")
            return (0, 0, 0)
    
    def _compare_versions(self, v1: str, v2: str) -> int:
        """Compare two version strings. Returns -1 if v1 < v2, 0 if equal, 1 if v1 > v2."""
        v1_norm = self._normalize_version(v1)
        v2_norm = self._normalize_version(v2)
        if v1_norm < v2_norm:
            return -1
        elif v1_norm > v2_norm:
            return 1
        else:
            return 0
    
    def migrate(self, instance_path: Path, from_version: str, to_version: str) -> Dict[str, Any]:
        """
        Migrate instance from one version to another.
        
        Args:
            instance_path: Instance directory path
            from_version: Source version
            to_version: Target version
        
        Returns:
            Migration result summary
        """
        logger.info(f"Migrating instance from {from_version} to {to_version}")
        
        # Version comparison
        comparison = self._compare_versions(from_version, to_version)
        
        if comparison == 0:
            # Already at target version
            self._log_migration(instance_path, from_version, to_version, "no_op", "ok", [])
            return {
                "from_version": from_version,
                "to_version": to_version,
                "migrations_applied": [],
                "success": True
            }
        elif comparison > 0:
            # Downgrade - warn and require --force
            raise ValueError(
                f"Instance version ({from_version}) is newer than target ({to_version}). "
                "Downgrades are not supported. Use --force to override."
            )
        
        # Find and execute all migrations in the upgrade path
        migrations_applied = []
        current_version = from_version
        
        # Find chain of migrations from current_version to to_version
        # Build migration chain by finding sequential migrations
        migration_chain = []
        search_version = from_version
        
        while self._compare_versions(search_version, to_version) < 0:
            # Find next migration that starts from search_version
            next_migration = None
            for from_v, to_v, name, func in self.MIGRATIONS:
                if self._compare_versions(from_v, search_version) == 0:
                    next_migration = (from_v, to_v, name, func)
                    break
            
            if next_migration is None:
                # No migration found - check if we can skip to target
                if self._compare_versions(search_version, to_version) < 0:
                    # Try to find any migration that brings us closer
                    candidates = [
                        (f, t, name, func) for f, t, name, func in self.MIGRATIONS
                        if self._compare_versions(f, search_version) >= 0 and 
                           self._compare_versions(t, to_version) <= 0
                    ]
                    if candidates:
                        # Sort by how close they get us to target
                        candidates.sort(key=lambda x: (
                            self._normalize_version(x[1]),
                            self._normalize_version(x[0])
                        ))
                        next_migration = candidates[0]
                    else:
                        # No applicable migration - skip to target
                        logger.warning(f"No migration found from {search_version} to {to_version}, skipping")
                        break
            
            if next_migration:
                migration_chain.append(next_migration)
                search_version = next_migration[1]
            else:
                break
        
        # Execute migrations in order
        for from_v, to_v, migration_name, migration_func in migration_chain:
            logger.info(f"Applying migration: {migration_name} ({from_v} -> {to_v})")
            try:
                actions = migration_func(instance_path)
                status = "ok"
                self._log_migration(instance_path, from_v, to_v, migration_name, status, actions)
                migrations_applied.append({
                    "from": from_v,
                    "to": to_v,
                    "migration": migration_name,
                    "status": status,
                    "actions": actions
                })
                current_version = to_v
            except Exception as e:
                status = "error"
                error_msg = str(e)
                logger.error(f"Migration {migration_name} failed: {e}")
                self._log_migration(instance_path, from_v, to_v, migration_name, status, [error_msg])
                migrations_applied.append({
                    "from": from_v,
                    "to": to_v,
                    "migration": migration_name,
                    "status": status,
                    "error": error_msg
                })
                raise RuntimeError(f"Migration {migration_name} failed: {e}")
        
        return {
            "from_version": from_version,
            "to_version": to_version,
            "migrations_applied": migrations_applied,
            "success": True
        }
    
    def _log_migration(self, instance_path: Path, from_version: str, to_version: str,
                       migration_name: str, status: str, actions: List[str]) -> None:
        """Log migration to instance/logs/migrations.jsonl."""
        logs_dir = instance_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        log_entry = {
            "from": from_version,
            "to": to_version,
            "migration": migration_name,
            "status": status,
            "ts": datetime.now(timezone.utc).isoformat(),
            "actions": actions
        }
        
        migration_log_file = logs_dir / "migrations.jsonl"
        with open(migration_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + "\n")

