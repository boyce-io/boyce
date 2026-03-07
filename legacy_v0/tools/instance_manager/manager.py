"""
Instance Manager

Manages DataShark instance lifecycle: create, build, upgrade, destroy.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from .registry import InstanceRegistry

logger = logging.getLogger(__name__)


class InstanceManager:
    """Manages DataShark instances."""
    
    FRAMEWORK_VERSION = "0.2.0"
    
    def __init__(self, base_path: Optional[Path] = None):
        """
        Initialize instance manager.
        
        Args:
            base_path: Base directory for instances (default: ~/DataShark_Instances)
        """
        if base_path is None:
            home = Path.home()
            base_path = home / "DataShark_Instances"
        
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.registry = InstanceRegistry()
    
    def create_instance(self, name: str, config: Optional[Dict[str, Any]] = None) -> Path:
        """
        Create a new instance.
        
        Args:
            name: Instance name
            config: Optional initial configuration
        
        Returns:
            Instance directory path
        """
        instance_path = self.base_path / name
        
        if instance_path.exists():
            raise ValueError(f"Instance '{name}' already exists at {instance_path}")
        
        # Create directory structure
        instance_path.mkdir(parents=True, exist_ok=True)
        (instance_path / "manifests").mkdir(exist_ok=True)
        (instance_path / "cache").mkdir(exist_ok=True)
        (instance_path / "logs").mkdir(exist_ok=True)
        
        # Write version file
        version_file = instance_path / ".datashark_version"
        version_file.write_text(self.FRAMEWORK_VERSION + "\n")
        
        # Write config.yaml from template
        config_file = instance_path / "config.yaml"
        if config is None:
            config = self._get_default_config()
        
        try:
            import yaml
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        except ImportError:
            # Fallback to JSON if yaml not available
            import json
            with open(config_file.with_suffix('.json'), 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        
        # Write credentials template
        creds_file = instance_path / "credentials.env"
        creds_template = self._get_credentials_template()
        creds_file.write_text(creds_template)
        
        # Add to registry
        self.registry.add_instance(name, instance_path, self.FRAMEWORK_VERSION)
        
        logger.info(f"Created instance '{name}' at {instance_path}")
        return instance_path
    
    def list_instances(self) -> Dict[str, Dict[str, Any]]:
        """
        List all instances.
        
        Returns:
            Dict of instance name -> instance info
        """
        return self.registry.list_instances()
    
    def switch_instance(self, name: str) -> None:
        """
        Switch active instance.
        
        Args:
            name: Instance name
        """
        self.registry.set_active_instance(name)
        logger.info(f"Switched to instance '{name}'")
    
    def build_instance(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Build instance (run ingestion + enrichment pipeline).
        
        Args:
            name: Instance name (default: active instance)
        
        Returns:
            Build result summary
        """
        if name is None:
            active = self.registry.get_active_instance()
            if not active:
                raise ValueError("No active instance and no instance name provided")
            instance_path = Path(active["path"])
        else:
            instance_info = self.registry.get_instance(name)
            if not instance_info:
                raise ValueError(f"Instance '{name}' not found")
            instance_path = Path(instance_info["path"])
        
        # Load config
        config_file = instance_path / "config.yaml"
        config_json = instance_path / "config.json"
        
        if config_file.exists():
            try:
                import yaml
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
            except ImportError:
                raise ValueError("YAML library required for config.yaml")
        elif config_json.exists():
            import json
            with open(config_json, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            raise ValueError(f"Config file not found: {config_file} or {config_json}")
        
        # Run ingestion pipeline
        manifests_dir = instance_path / "manifests"
        logs_dir = instance_path / "logs"
        
        logger.info(f"Building instance at {instance_path}")
        
        # Import and run ingestion
        import sys
        import subprocess
        from pathlib import Path as P
        
        # Get repository configurations from config
        repositories = config.get("repositories", [])
        extractors_to_run = []
        input_paths = []
        
        # Collect extractors and input paths from repositories
        for repo in repositories:
            if isinstance(repo, dict):
                extractor = repo.get("extractor", "bi_tool")
                repo_path = repo.get("path", "")
                if repo_path:
                    # Expand ~ in paths
                    repo_path = str(P(repo_path).expanduser())
                    if extractor not in extractors_to_run:
                        extractors_to_run.append(extractor)
                    if repo_path and repo_path not in input_paths:
                        input_paths.append(repo_path)
            elif isinstance(repo, str):
                # Legacy format: just a path
                repo_path = str(P(repo).expanduser())
                if repo_path not in input_paths:
                    input_paths.append(repo_path)
                    if "bi_tool" not in extractors_to_run:
                        extractors_to_run.append("bi_tool")
        
        # Default to database_catalog if no repositories configured
        if not extractors_to_run:
            extractors_to_run = ["database_catalog"]
        
        # Build ingest command
        project_root = P(__file__).parent.parent.parent
        ingest_script = project_root / "datashark-mcp" / "tools" / "ingest.py"
        
        if not ingest_script.exists():
            logger.warning(f"Ingest script not found at {ingest_script}, using placeholder")
            result = {
                "instance": name or "active",
                "path": str(instance_path),
                "manifests_generated": 0,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "status": "placeholder"
            }
            return result
        
        # Run ingestion via subprocess
        cmd = [
            sys.executable,
            str(ingest_script),
            "--instance", name or config.get("instance_name", "active"),
            "--out", str(manifests_dir)
        ]
        
        # Add extractors
        for ext in extractors_to_run:
            cmd.extend(["--extractor", ext])
        
        # Add input path if available
        if input_paths:
            cmd.extend(["--input", input_paths[0]])  # Use first input path
        
        try:
            result_proc = subprocess.run(
                cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result_proc.returncode != 0:
                logger.error(f"Ingestion failed: {result_proc.stderr}")
                raise RuntimeError(f"Ingestion failed: {result_proc.stderr}")
            
            # Count generated manifests
            manifest_count = 0
            if manifests_dir.exists():
                manifest_count = len(list(manifests_dir.glob("*.jsonl"))) + len(list(manifests_dir.glob("*.json")))
            
            result = {
                "instance": name or "active",
                "path": str(instance_path),
                "manifests_generated": manifest_count,
                "extractors": extractors_to_run,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "status": "success"
            }
            
            logger.info(f"Instance build complete: {manifest_count} manifests generated")
            return result
            
        except subprocess.TimeoutExpired:
            logger.error("Ingestion timed out after 5 minutes")
            raise RuntimeError("Ingestion timed out")
        except Exception as e:
            logger.error(f"Failed to run ingestion: {e}")
            raise
    
    def upgrade_instance(self, name: Optional[str] = None, target_version: Optional[str] = None) -> Dict[str, Any]:
        """
        Upgrade instance to target version.
        
        Args:
            name: Instance name (default: active instance)
            target_version: Target version (default: current framework version)
        
        Returns:
            Upgrade result summary
        """
        if name is None:
            active = self.registry.get_active_instance()
            if not active:
                raise ValueError("No active instance and no instance name provided")
            instance_path = Path(active["path"])
            current_version = active["version"]
        else:
            instance_info = self.registry.get_instance(name)
            if not instance_info:
                raise ValueError(f"Instance '{name}' not found")
            instance_path = Path(instance_info["path"])
            current_version = instance_info["version"]
        
        if target_version is None:
            # Get framework version from package metadata
            try:
                import importlib.metadata
                target_version = importlib.metadata.version("datashark-mcp")
            except (ImportError, importlib.metadata.PackageNotFoundError):
                # Fallback to FRAMEWORK_VERSION constant
                target_version = self.FRAMEWORK_VERSION
        
        # Read current version
        version_file = instance_path / ".datashark_version"
        if version_file.exists():
            current_version = version_file.read_text().strip()
        
        if current_version == target_version:
            logger.info(f"Instance '{name or 'active'}' already at version {target_version}")
            # Log "already at latest" to migrations.jsonl
            from .migrate import MigrationManager
            migrator = MigrationManager()
            migrator._log_migration(instance_path, current_version, target_version, "no_op", "ok", 
                                   ["Instance already at latest version"])
            return {
                "instance": name or "active",
                "current_version": current_version,
                "target_version": target_version,
                "upgraded": False,
                "message": "already at latest"
            }
        
        # Run migration
        from .migrate import MigrationManager
        migrator = MigrationManager()
        migration_result = migrator.migrate(instance_path, current_version, target_version)
        
        # Update version file
        version_file.write_text(target_version + "\n")
        
        # Update registry
        self.registry.add_instance(name or "active", instance_path, target_version)
        
        return {
            "instance": name or "active",
            "current_version": current_version,
            "target_version": target_version,
            "upgraded": True,
            "migration_log": migration_result
        }
    
    def destroy_instance(self, name: str) -> None:
        """
        Destroy instance (delete directory and remove from registry).
        
        Args:
            name: Instance name
        """
        instance_info = self.registry.get_instance(name)
        if not instance_info:
            raise ValueError(f"Instance '{name}' not found")
        
        instance_path = Path(instance_info["path"])
        
        # Remove from registry first
        self.registry.remove_instance(name)
        
        # Delete directory
        if instance_path.exists():
            shutil.rmtree(instance_path)
            logger.info(f"Destroyed instance '{name}' at {instance_path}")
        else:
            logger.warning(f"Instance directory not found: {instance_path}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default instance configuration."""
        return {
            "repositories": [],
            "database": {
                "type": "redshift",
                "host": "",
                "user": "",
                "password": "",
                "database": ""
            },
            "settings": {
                "manifest_dir": "manifests/",
                "cache_dir": "cache/",
                "log_dir": "logs/"
            }
        }
    
    def _get_credentials_template(self) -> str:
        """Get credentials template."""
        return """# DataShark Instance Credentials
# Copy this file and fill in your credentials
# DO NOT commit this file to version control

REDSHIFT_HOST=
REDSHIFT_USER=
REDSHIFT_PASSWORD=
REDSHIFT_DB=

# Add other system credentials as needed
"""

