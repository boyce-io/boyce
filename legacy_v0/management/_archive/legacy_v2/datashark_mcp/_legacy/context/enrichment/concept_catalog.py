"""
Concept Catalog

Stores BUSINESS_CONCEPT nodes and provides search capabilities.
Persists to docs/concepts.json with deterministic ordering.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional
from datashark_mcp.context.models import Node, Provenance
from datashark_mcp.context.id_utils import compute_node_id
from datetime import datetime, timezone


@dataclass
class Concept:
    """Business concept definition."""
    name: str
    description: str
    aliases: List[str]
    domain: str = "general"
    
    def to_node(self) -> Node:
        """Convert to BUSINESS_CONCEPT node."""
        node_id = compute_node_id("BUSINESS_CONCEPT", "semantic", "_", "_", self.name)
        
        return Node(
            id=node_id,
            system="semantic",
            type="BUSINESS_CONCEPT",
            name=self.name,
            attributes={
                "domain": self.domain,
                "definition": self.description,
                "aliases": self.aliases
            },
            provenance=Provenance(
                system="semantic",
                source_path="concepts.json",
                extractor_version="1.0.0",
                extracted_at=datetime.now(timezone.utc).isoformat()
            )
        )


class ConceptCatalog:
    """Catalog of business concepts with persistence."""
    
    def __init__(self, concepts_file: Optional[Path] = None):
        """
        Initialize concept catalog.
        
        Args:
            concepts_file: Path to concepts.json (defaults to docs/concepts.json)
        """
        if concepts_file is None:
            project_root = Path(__file__).resolve().parents[5]
            concepts_file = project_root / "docs" / "concepts.json"
        
        self.concepts_file = concepts_file
        self._concepts: Dict[str, Concept] = {}
        self._load()
    
    def _load(self) -> None:
        """Load concepts from file."""
        if self.concepts_file.exists():
            with open(self.concepts_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for concept_data in data.get("concepts", []):
                    concept = Concept(**concept_data)
                    self._concepts[concept.name] = concept
        else:
            # Initialize with empty catalog
            self._concepts = {}
    
    def _save(self) -> None:
        """Save concepts to file (deterministic, sorted by name)."""
        self.concepts_file.parent.mkdir(parents=True, exist_ok=True)
        
        concepts_list = [
            {
                "name": c.name,
                "description": c.description,
                "aliases": c.aliases,
                "domain": c.domain
            }
            for c in sorted(self._concepts.values(), key=lambda x: x.name)
        ]
        
        data = {
            "concepts": concepts_list,
            "version": "0.1.0",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        with open(self.concepts_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
    
    def add_concept(self, name: str, description: str, aliases: List[str] = None, domain: str = "general") -> Concept:
        """
        Add or update a concept.
        
        Args:
            name: Concept name
            description: Concept description
            aliases: List of aliases
            domain: Business domain (default: "general")
            
        Returns:
            Concept object
        """
        if aliases is None:
            aliases = []
        
        concept = Concept(
            name=name,
            description=description,
            aliases=aliases,
            domain=domain
        )
        
        self._concepts[name] = concept
        self._save()
        
        return concept
    
    def get_concept(self, name: str) -> Optional[Concept]:
        """
        Get concept by name.
        
        Args:
            name: Concept name
            
        Returns:
            Concept if found, None otherwise
        """
        return self._concepts.get(name)
    
    def search(self, term: str) -> List[Concept]:
        """
        Search concepts by name, description, or aliases.
        
        Args:
            term: Search term (case-insensitive)
            
        Returns:
            List of matching concepts
        """
        term_lower = term.lower()
        results = []
        
        for concept in self._concepts.values():
            # Check name
            if term_lower in concept.name.lower():
                results.append(concept)
                continue
            
            # Check aliases
            if any(term_lower in alias.lower() for alias in concept.aliases):
                results.append(concept)
                continue
            
            # Check description
            if term_lower in concept.description.lower():
                results.append(concept)
                continue
        
        return results
    
    def get_all_concepts(self) -> List[Concept]:
        """Get all concepts (sorted by name)."""
        return sorted(self._concepts.values(), key=lambda x: x.name)
    
    def to_nodes(self) -> List[Node]:
        """Convert all concepts to BUSINESS_CONCEPT nodes."""
        return [concept.to_node() for concept in self.get_all_concepts()]

