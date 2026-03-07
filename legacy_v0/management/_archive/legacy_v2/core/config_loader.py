"""
Configuration loader for DataShark.
Loads settings from config.json with sensible defaults.
"""

import json
from pathlib import Path
from typing import Dict, Any, List


class Config:
    """Configuration management for DataShark."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            return self._default_config()
        
        with open(self.config_path, 'r') as f:
            config = json.load(f)
        
        # Merge with defaults
        defaults = self._default_config()
        return self._merge_dicts(defaults, config)
    
    def _default_config(self) -> Dict[str, Any]:
        """Default configuration values."""
        return {
            'active_schemas': ['scratch'],
            'refresh': {
                'check_on_launch': True,
                'auto_refresh_threshold_days': 7,
                'include_row_counts': False,
            },
            'extraction': {
                'max_schemas': 200,
                'exclude_patterns': ['pg_temp*', 'pg_toast*'],
                'categories': {
                    'staging': '*_staging',
                    'history': '*_history',
                    'scratch': '*scratch*',
                },
            },
            'ui': {
                'show_all_schemas': True,
                'default_limit': 100,
            },
        }
    
    def _merge_dicts(self, default: dict, override: dict) -> dict:
        """Recursively merge two dictionaries."""
        result = default.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dicts(result[key], value)
            else:
                result[key] = value
        return result
    
    @property
    def active_schemas(self) -> List[str]:
        """Get list of active schemas for AI context."""
        return self._config.get('active_schemas', [])
    
    @property
    def check_on_launch(self) -> bool:
        """Whether to check for staleness on launch."""
        return self._config.get('refresh', {}).get('check_on_launch', True)
    
    @property
    def auto_refresh_threshold_days(self) -> int:
        """Days before data is considered stale."""
        return self._config.get('refresh', {}).get('auto_refresh_threshold_days', 7)
    
    @property
    def include_row_counts(self) -> bool:
        """Whether to include row counts in extraction."""
        return self._config.get('refresh', {}).get('include_row_counts', False)
    
    @property
    def exclude_patterns(self) -> List[str]:
        """Schema patterns to exclude from extraction."""
        return self._config.get('extraction', {}).get('exclude_patterns', [])
    
    @property
    def categories(self) -> Dict[str, str]:
        """Schema categorization patterns."""
        return self._config.get('extraction', {}).get('categories', {})
    
    @property
    def show_all_schemas(self) -> bool:
        """Show all schemas in UI browser."""
        return self._config.get('ui', {}).get('show_all_schemas', True)
    
    @property
    def default_limit(self) -> int:
        """Default LIMIT for queries."""
        return self._config.get('ui', {}).get('default_limit', 100)


# Global config instance
_config = None

def get_config() -> Config:
    """Get or create global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config

