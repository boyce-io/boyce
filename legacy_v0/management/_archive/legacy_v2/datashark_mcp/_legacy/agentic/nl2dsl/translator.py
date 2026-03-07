"""
Natural Language to DSL Translator

Translates natural language queries into DSL queries using pattern matching
and embedding similarity.
"""

from __future__ import annotations

import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datashark_mcp.context.enrichment.concept_catalog import ConceptCatalog
from datashark_mcp.context.embedding.embedder import SimpleHashEmbedder
from datashark_mcp.context.embedding.vector_index import VectorIndex


class NLTranslator:
    """Translates natural language to DSL queries."""
    
    def __init__(self, catalog: ConceptCatalog = None, templates_file: Optional[Path] = None):
        """
        Initialize NL translator.
        
        Args:
            catalog: ConceptCatalog instance (optional)
            templates_file: Path to templates.yaml (defaults to templates.yaml)
        """
        if catalog is None:
            catalog = ConceptCatalog()
        
        self.catalog = catalog
        self.embedder = SimpleHashEmbedder()
        self.index = VectorIndex(embedder=self.embedder)
        
        # Load templates
        if templates_file is None:
            templates_file = Path(__file__).parent / "templates.yaml"
        self.templates = self._load_templates(templates_file)
        
        # Build concept index
        concept_nodes = catalog.to_nodes()
        self.index.build_index(concept_nodes)
    
    def _load_templates(self, templates_file: Path) -> List[Dict]:
        """Load query templates."""
        if not templates_file.exists():
            return []
        
        try:
            with open(templates_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data.get("templates", [])
        except Exception:
            # Fallback if YAML parsing fails
            return []
    
    def translate(self, prompt: str) -> str:
        """
        Translate natural language prompt to DSL query.
        
        Args:
            prompt: Natural language query
            
        Returns:
            DSL query string
        """
        prompt_lower = prompt.lower().strip()
        
        # Pattern matching for common question forms
        # "Show", "Find", "List" → FIND
        if re.search(r'\b(show|find|list|get)\b', prompt_lower):
            return self._translate_find(prompt)
        
        # "Path between", "relationship", "connect" → PATH
        if re.search(r'\b(path|relationship|connect|link|join)\b', prompt_lower):
            return self._translate_path(prompt)
        
        # Default: SEARCH
        return self._translate_search(prompt)
    
    def _translate_find(self, prompt: str) -> str:
        """Translate FIND query."""
        prompt_lower = prompt.lower()
        
        # Extract system filter
        system_match = re.search(r'\b(database|dbt|bi[_\s]?tool|airflow|catalog)\b', prompt_lower)
        if system_match:
            system = system_match.group(1).replace(" ", "_")
            return f"FIND ENTITY WHERE system='{system}'"
        
        # Extract entity type
        entity_types = ["entity", "table", "metric", "dataset", "model"]
        for etype in entity_types:
            if etype in prompt_lower:
                return f"FIND {etype.upper()} WHERE system='database'"
        
        # Default FIND
        return "FIND ENTITY WHERE system='database'"
    
    def _translate_path(self, prompt: str) -> str:
        """Translate PATH query."""
        # Try to extract entity names
        # Look for patterns like "between X and Y" or "X to Y"
        between_match = re.search(r'between\s+([^\s]+)\s+and\s+([^\s]+)', prompt, re.IGNORECASE)
        if between_match:
            from_entity = between_match.group(1).strip()
            to_entity = between_match.group(2).strip()
            
            # Try to resolve via concept catalog
            from_concept = self._resolve_entity_name(from_entity)
            to_concept = self._resolve_entity_name(to_entity)
            
            return f"PATH FROM '{from_concept}' TO '{to_concept}'"
        
        # Try "X to Y" pattern
        to_match = re.search(r'([^\s]+)\s+to\s+([^\s]+)', prompt, re.IGNORECASE)
        if to_match:
            from_entity = to_match.group(1).strip()
            to_entity = to_match.group(2).strip()
            from_concept = self._resolve_entity_name(from_entity)
            to_concept = self._resolve_entity_name(to_entity)
            return f"PATH FROM '{from_concept}' TO '{to_concept}'"
        
        # Default path query (placeholder)
        return "PATH FROM 'unknown' TO 'unknown'"
    
    def _translate_search(self, prompt: str) -> str:
        """Translate SEARCH query."""
        # Extract search term (remove common question words)
        stop_words = ["show", "find", "list", "get", "what", "where", "how", "which"]
        words = prompt.split()
        search_terms = [w for w in words if w.lower() not in stop_words]
        
        if search_terms:
            term = " ".join(search_terms[:3])  # Take first 3 words
            return f"SEARCH '{term}'"
        
        return "SEARCH 'unknown'"
    
    def _resolve_entity_name(self, name: str) -> str:
        """
        Resolve entity name to concept or node ID.
        
        Args:
            name: Entity name
            
        Returns:
            Resolved name (concept name or original)
        """
        # Try concept catalog first
        concept = self.catalog.get_concept(name)
        if concept:
            return concept.name
        
        # Try search
        matches = self.catalog.search(name)
        if matches:
            return matches[0].name
        
        # Try embedding similarity
        similar = self.index.query_text(name, top_k=1)
        if similar:
            return similar[0][0].name
        
        # Return original (normalized)
        return name.lower().strip()


def translate_nl_to_dsl(prompt: str, catalog: ConceptCatalog = None) -> str:
    """
    Convenience function to translate NL to DSL.
    
    Args:
        prompt: Natural language query
        catalog: Optional ConceptCatalog
        
    Returns:
        DSL query string
    """
    translator = NLTranslator(catalog=catalog)
    return translator.translate(prompt)

