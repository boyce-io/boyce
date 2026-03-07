"""
Enrichment Rules

Lightweight rule system for mapping entities to business concepts.
Rules are loaded from docs/enrichment_rules.yaml with deterministic ordering.

Note: Requires PyYAML (pip install pyyaml)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    import yaml
except ImportError:
    yaml = None
    # Fallback: parse YAML manually if PyYAML not available
    pass


@dataclass
class EnrichmentRule:
    """A rule for mapping entities to concepts."""
    pattern: str  # Regex pattern
    concept: str  # Concept name
    confidence: float = 0.7  # Confidence score (0.0-1.0)
    source: str = "pattern"  # Rule source identifier
    
    def matches(self, text: str) -> bool:
        """Check if rule matches text."""
        try:
            return bool(re.search(self.pattern, text, re.IGNORECASE))
        except re.error:
            return False


class EnrichmentRules:
    """Collection of enrichment rules."""
    
    def __init__(self, rules_file: Optional[Path] = None):
        """
        Initialize enrichment rules.
        
        Args:
            rules_file: Path to enrichment_rules.yaml (defaults to docs/enrichment_rules.yaml)
        """
        if rules_file is None:
            project_root = Path(__file__).resolve().parents[5]
            rules_file = project_root / "docs" / "enrichment_rules.yaml"
        
        self.rules_file = rules_file
        self._rules: List[EnrichmentRule] = []
        self._load()
    
    def _load(self) -> None:
        """Load rules from YAML file."""
        if not self.rules_file.exists():
            # Create default rules file
            self._create_default_rules()
            return
        
        if yaml is None:
            # Fallback: simple YAML parsing
            self._load_simple_yaml()
            return
        
        with open(self.rules_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            
            rules_list = data.get("rules", [])
            # Sort by pattern for deterministic ordering
            rules_list = sorted(rules_list, key=lambda x: x.get("pattern", ""))
            
            for rule_data in rules_list:
                rule = EnrichmentRule(
                    pattern=rule_data["pattern"],
                    concept=rule_data["concept"],
                    confidence=rule_data.get("confidence", 0.7),
                    source=rule_data.get("source", "pattern")
                )
                self._rules.append(rule)
    
    def _load_simple_yaml(self) -> None:
        """Simple YAML parser fallback (basic, handles our format)."""
        with open(self.rules_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Simple parsing for our specific format
        import re as re_mod
        pattern = r'concept:\s*(\w+)\s+confidence:\s*([\d.]+)\s+pattern:\s*([^\n]+)\s+source:\s*(\w+)'
        matches = re_mod.findall(pattern, content)
        
        for match in matches:
            concept, conf_str, pattern_str, source = match
            confidence = float(conf_str)
            rule = EnrichmentRule(
                pattern=pattern_str.strip(),
                concept=concept,
                confidence=confidence,
                source=source
            )
            self._rules.append(rule)
        
        # Sort by pattern
        self._rules.sort(key=lambda x: x.pattern)
    
    def _create_default_rules(self) -> None:
        """Create default rules file."""
        self.rules_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write as simple YAML (no PyYAML dependency)
        default_rules_content = """rules:
  - concept: Revenue
    confidence: 0.8
    pattern: (?i)\\brevenue\\b|\\bsales\\b|\\bincome\\b
    source: pattern
  - concept: Product
    confidence: 0.8
    pattern: (?i)\\bproduct\\b|\\bitem\\b|\\bsku\\b
    source: pattern
  - concept: Audience
    confidence: 0.7
    pattern: (?i)\\baudience\\b|\\bviewer\\b|\\buser\\b
    source: pattern
  - concept: Date
    confidence: 0.9
    pattern: (?i)\\bdate\\b|\\bdatetime\\b|\\bcreated_at\\b|\\bupdated_at\\b
    source: pattern
  - concept: Country
    confidence: 0.7
    pattern: (?i)\\bcountry\\b|\\bregion\\b|\\blocation\\b
    source: pattern
"""
        
        with open(self.rules_file, "w", encoding="utf-8") as f:
            f.write(default_rules_content)
        
        # Reload
        self._load()
    
    def find_matches(self, text: str) -> List[EnrichmentRule]:
        """
        Find all rules that match text.
        
        Args:
            text: Text to match against
            
        Returns:
            List of matching rules (sorted by confidence descending)
        """
        matches = [rule for rule in self._rules if rule.matches(text)]
        # Sort by confidence descending for deterministic ordering
        return sorted(matches, key=lambda x: (-x.confidence, x.concept))
    
    def get_all_rules(self) -> List[EnrichmentRule]:
        """Get all rules (sorted by pattern)."""
        return sorted(self._rules, key=lambda x: x.pattern)
