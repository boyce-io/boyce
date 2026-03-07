"""
Staleness Tracking System - DataGrip-Style Metadata Management
Tracks when schemas were last extracted and detects database changes.

Enables:
- Fast startup (check if refresh needed)
- Incremental updates (only changed tables)
- Automatic background refresh
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import pandas as pd

from core.connection_manager import RedshiftConnectionManager


class StalenessTracker:
    """
    Tracks metadata extraction history and detects database changes.
    Commercial tool behavior - knows what changed, when.
    """
    
    def __init__(
        self, 
        connection_manager: RedshiftConnectionManager,
        history_file: str = "data/extraction_history.json"
    ):
        self.conn_manager = connection_manager
        self.history_file = Path(history_file)
        self.history = self._load_history()
    
    def _load_history(self) -> Dict:
        """Load extraction history from file."""
        if not self.history_file.exists():
            return {
                "database": "your-database",
                "schemas": {},
                "last_full_extraction": None,
            }
        
        with open(self.history_file, 'r') as f:
            return json.load(f)
    
    def _save_history(self):
        """Save extraction history to file."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2)
    
    def record_extraction(
        self, 
        schema: str, 
        tables: List[str],
        extraction_time: Optional[datetime] = None
    ):
        """
        Record that a schema was extracted.
        
        Args:
            schema: Schema name
            tables: List of table names extracted
            extraction_time: When extraction occurred (defaults to now)
        """
        if extraction_time is None:
            extraction_time = datetime.now()
        
        timestamp = extraction_time.isoformat()
        
        self.history["schemas"][schema] = {
            "last_extracted": timestamp,
            "table_count": len(tables),
            "tables": tables,
        }
        
        self._save_history()
    
    def record_full_extraction(self, schemas: List[str]):
        """Record that a full database extraction completed."""
        self.history["last_full_extraction"] = datetime.now().isoformat()
        self._save_history()
    
    def get_last_extraction_time(self, schema: str) -> Optional[datetime]:
        """Get when schema was last extracted."""
        schema_info = self.history["schemas"].get(schema)
        if not schema_info:
            return None
        
        return datetime.fromisoformat(schema_info["last_extracted"])
    
    def is_schema_stale(
        self, 
        schema: str, 
        max_age_days: int = 7
    ) -> bool:
        """
        Check if schema needs refresh based on age.
        
        Args:
            schema: Schema name
            max_age_days: Maximum age before considered stale
        
        Returns:
            True if schema needs refresh
        """
        last_extracted = self.get_last_extraction_time(schema)
        
        if not last_extracted:
            return True  # Never extracted
        
        age = datetime.now() - last_extracted
        return age > timedelta(days=max_age_days)
    
    def get_changed_tables(
        self, 
        schema: str,
        since: Optional[datetime] = None
    ) -> List[str]:
        """
        Detect which tables changed since last extraction.
        Uses Redshift's svv_table_info for change tracking.
        
        Args:
            schema: Schema name
            since: Check changes since this time (defaults to last extraction)
        
        Returns:
            List of changed table names
        """
        if since is None:
            since = self.get_last_extraction_time(schema)
        
        if not since:
            # Never extracted, return all tables
            return self._get_all_tables(schema)
        
        # Query Redshift for changed tables
        query = """
        SELECT "table" as table_name, last_altered
        FROM svv_table_info
        WHERE schema = %s
        AND last_altered > %s
        ORDER BY table_name;
        """
        
        try:
            with self.conn_manager.get_connection() as conn:
                df = pd.read_sql(query, conn, params=(schema, since))
            
            return df['table_name'].tolist()
        except:
            # If query fails, assume all tables need refresh
            return self._get_all_tables(schema)
    
    def _get_all_tables(self, schema: str) -> List[str]:
        """Get all tables in a schema."""
        query = """
        SELECT c.relname as table_name
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s
        AND c.relkind = 'r'
        ORDER BY c.relname;
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(schema,))
        
        return df['table_name'].tolist()
    
    def get_stale_schemas(
        self, 
        schemas: List[str], 
        max_age_days: int = 7
    ) -> List[str]:
        """
        Get list of schemas that need refresh.
        
        Args:
            schemas: List of schema names to check
            max_age_days: Maximum age before considered stale
        
        Returns:
            List of schema names that need refresh
        """
        stale = []
        for schema in schemas:
            if self.is_schema_stale(schema, max_age_days):
                stale.append(schema)
        
        return stale
    
    def get_database_last_modified(self) -> Optional[datetime]:
        """
        Get the most recent modification time across entire database.
        Used for quick staleness check.
        """
        query = """
        SELECT MAX(last_altered) as last_modified
        FROM svv_table_info;
        """
        
        try:
            with self.conn_manager.get_connection() as conn:
                df = pd.read_sql(query, conn)
            
            if not df.empty and df.iloc[0]['last_modified']:
                return pd.to_datetime(df.iloc[0]['last_modified'])
        except:
            pass
        
        return None
    
    def needs_refresh(self, max_age_days: int = 7) -> Tuple[bool, List[str]]:
        """
        Check if database needs refresh.
        DataGrip-style: quick check on startup.
        
        Args:
            max_age_days: Maximum age before refresh needed
        
        Returns:
            (needs_refresh: bool, stale_schemas: List[str])
        """
        all_schemas = self._get_all_schemas()
        stale_schemas = self.get_stale_schemas(all_schemas, max_age_days)
        
        return len(stale_schemas) > 0, stale_schemas
    
    def _get_all_schemas(self) -> List[str]:
        """Get all non-system schemas."""
        query = """
        SELECT nspname as schema_name
        FROM pg_namespace
        WHERE nspname NOT LIKE 'pg_%'
        AND nspname != 'information_schema'
        ORDER BY nspname;
        """
        
        with self.conn_manager.get_connection() as conn:
            df = pd.read_sql(query, conn)
        
        return df['schema_name'].tolist()
    
    def get_extraction_summary(self) -> Dict:
        """Get summary of current extraction state."""
        total_schemas = len(self.history["schemas"])
        total_tables = sum(s["table_count"] for s in self.history["schemas"].values())
        
        oldest_extraction = None
        if self.history["schemas"]:
            oldest = min(
                datetime.fromisoformat(s["last_extracted"]) 
                for s in self.history["schemas"].values()
            )
            oldest_extraction = oldest.isoformat()
        
        return {
            "total_schemas_extracted": total_schemas,
            "total_tables_extracted": total_tables,
            "last_full_extraction": self.history.get("last_full_extraction"),
            "oldest_schema_extraction": oldest_extraction,
        }

