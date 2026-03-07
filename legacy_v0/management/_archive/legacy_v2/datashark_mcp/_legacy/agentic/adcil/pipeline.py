"""
ADCIL Pipeline

Orchestrates the full ADCIL inference pipeline:
1. Context listening (monitor changes)
2. Semantic induction (concept inference)
3. Join inference
4. Confidence scoring
5. Validation
6. Persistence
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from datashark_mcp.context.store import GraphStore
from datashark_mcp.agentic.adcil.context_listener import ContextListener
from datashark_mcp.agentic.adcil.semantic_inducer import SemanticInducer
from datashark_mcp.agentic.adcil.join_inference import JoinInference
from datashark_mcp.agentic.adcil.confidence_model import ConfidenceModel
from datashark_mcp.agentic.adcil.validator import ADCILValidator
from datashark_mcp.agentic.adcil.persistence import ADCILPersistence

logger = logging.getLogger(__name__)


class ADCILPipeline:
    """
    Main ADCIL pipeline orchestrator.
    
    Runs inference pipeline after extractor phase:
    - Semantic concept inference
    - Join relationship inference
    - Validation and confidence scoring
    - Persistence to manifests
    """
    
    def __init__(
        self,
        store: GraphStore,
        instance_path: Path,
        config: Dict[str, Any]
    ):
        """
        Initialize ADCIL pipeline.
        
        Args:
            store: GraphStore instance (already populated with extracted nodes/edges)
            instance_path: Path to instance directory
            config: ADCIL configuration from instance config.yaml
        """
        self.store = store
        self.instance_path = instance_path
        self.config = config.get("adcil", {})
        
        self.enabled = self.config.get("enabled", True)
        self.confidence_threshold = self.config.get("confidence_threshold", 0.8)
        
        # Initialize components
        self.listener = ContextListener(instance_path)
        self.confidence_model = ConfidenceModel(
            storage_path=instance_path / "cache" / "adcil_confidence.json"
        )
        self.validator = ADCILValidator(store)
        
        # Semantic inducer (load concept catalog and rules)
        concept_catalog = self._load_concept_catalog()
        rules = self._load_rules()
        
        self.semantic_inducer = SemanticInducer(
            store=store,
            concept_catalog=concept_catalog,
            rules=rules,
            confidence_threshold=self.confidence_threshold
        )
        
        self.join_inference = JoinInference(
            store=store,
            confidence_threshold=self.confidence_threshold
        )
        
        self.persistence = ADCILPersistence(
            store=store,
            output_dir=instance_path / "manifests"
        )
        
        logger.info(f"Initialized ADCILPipeline (enabled={self.enabled}, threshold={self.confidence_threshold})")
    
    def run(self) -> Dict[str, Any]:
        """
        Run the full ADCIL pipeline.
        
        Returns:
            Summary dict with metrics and timing
        """
        if not self.enabled:
            logger.info("ADCIL disabled, skipping")
            return {"enabled": False}
        
        start_time = time.time()
        
        try:
            # Step 1: Check for context changes (monitoring)
            logger.info("Step 1: Checking for context changes...")
            changes = self.listener.check_changes()
            
            # Step 2: Semantic concept inference
            logger.info("Step 2: Running semantic concept inference...")
            concept_inferences = self.semantic_inducer.infer_concepts()
            
            # Step 3: Validate concept inferences
            logger.info("Step 3: Validating concept inferences...")
            accepted_concepts, rejected_concepts = self.validator.validate_concept_inferences(concept_inferences)
            
            # Record confidence scores
            for inf in accepted_concepts:
                self.confidence_model.record_score(
                    inference_id=f"concept:{inf.node_id}:{inf.concept_name}",
                    inference_type="concept",
                    confidence=inf.confidence,
                    method=inf.method,
                    accepted=True
                )
            
            for inf in rejected_concepts:
                self.confidence_model.record_score(
                    inference_id=f"concept:{inf.node_id}:{inf.concept_name}",
                    inference_type="concept",
                    confidence=inf.confidence,
                    method=inf.method,
                    accepted=False
                )
            
            # Step 4: Generate concept nodes and edges
            logger.info("Step 4: Generating concept nodes and edges...")
            concept_nodes, concept_edges = self.semantic_inducer.generate_nodes_and_edges(accepted_concepts)
            
            # Add to store
            for node in concept_nodes:
                self.store.add_node(node)
            for edge in concept_edges:
                self.store.add_edge(edge)
            
            # Step 5: Join inference
            logger.info("Step 5: Running join inference...")
            join_inferences = self.join_inference.infer_joins()
            
            # Step 6: Validate join inferences
            logger.info("Step 6: Validating join inferences...")
            accepted_joins, rejected_joins = self.validator.validate_join_inferences(join_inferences)
            
            # Record confidence scores
            for inf in accepted_joins:
                self.confidence_model.record_score(
                    inference_id=f"join:{inf.source_table_id}:{inf.target_table_id}",
                    inference_type="join",
                    confidence=inf.confidence,
                    method=inf.method,
                    accepted=True
                )
            
            # Step 7: Generate join edges
            logger.info("Step 7: Generating join edges...")
            join_edges = self.join_inference.generate_edges(accepted_joins)
            
            # Add to store
            for edge in join_edges:
                self.store.add_edge(edge)
            
            # Step 8: Persist all inferences
            logger.info("Step 8: Persisting inferences...")
            persistence_summary = self.persistence.persist_inferences(
                concept_nodes, concept_edges, join_edges
            )
            
            elapsed = time.time() - start_time
            
            summary = {
                "enabled": True,
                "runtime_ms": int(elapsed * 1000),
                "changes_detected": len(changes),
                "concept_inferences": {
                    "total": len(concept_inferences),
                    "accepted": len(accepted_concepts),
                    "rejected": len(rejected_concepts)
                },
                "join_inferences": {
                    "total": len(join_inferences),
                    "accepted": len(accepted_joins),
                    "rejected": len(rejected_joins)
                },
                "persisted": persistence_summary
            }
            
            logger.info(f"ADCIL pipeline complete: {summary}")
            return summary
            
        except Exception as e:
            logger.error(f"ADCIL pipeline failed: {e}", exc_info=True)
            return {
                "enabled": True,
                "error": str(e),
                "runtime_ms": int((time.time() - start_time) * 1000)
            }
    
    def _load_concept_catalog(self) -> Dict[str, Dict[str, Any]]:
        """Load concept catalog from instance or defaults."""
        # Try instance-specific catalog
        catalog_path = self.instance_path / "concepts.json"
        if catalog_path.exists():
            import json
            with open(catalog_path, "r", encoding="utf-8") as f:
                return json.load(f)
        
        # Use default catalog
        return {
            "Revenue": {
                "description": "Revenue or sales amount",
                "aliases": ["sales", "income", "revenue_amount"]
            },
            "Customer": {
                "description": "Customer or client entity",
                "aliases": ["client", "user", "customer_id"]
            },
            "Date": {
                "description": "Date or timestamp",
                "aliases": ["timestamp", "created_at", "updated_at", "date"]
            },
            "Country": {
                "description": "Country or region",
                "aliases": ["region", "nation", "country_code"]
            },
            "Amount": {
                "description": "Monetary amount or value",
                "aliases": ["value", "price", "cost", "amount"]
            }
        }
    
    def _load_rules(self) -> List[Dict[str, Any]]:
        """Load enrichment rules from instance or defaults."""
        # Try instance-specific rules
        rules_path = self.instance_path / "enrichment_rules.yaml"
        if rules_path.exists():
            try:
                import yaml
                with open(rules_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f).get("rules", [])
            except Exception as e:
                logger.warning(f"Failed to load rules from {rules_path}: {e}")
        
        # Use default rules
        return [
            {"pattern": r"(?i)\brevenue\b|\bsales\b|\bincome\b", "concept": "Revenue", "weight": 1.0},
            {"pattern": r"(?i)\bcustomer\b|\bclient\b|\buser\b", "concept": "Customer", "weight": 1.0},
            {"pattern": r"(?i)\bdate\b|\btimestamp\b|\bcreated_at\b|\bupdated_at\b", "concept": "Date", "weight": 1.0},
            {"pattern": r"(?i)\bcountry\b|\bregion\b|\bnation\b", "concept": "Country", "weight": 1.0},
            {"pattern": r"(?i)\bamount\b|\bvalue\b|\bprice\b|\bcost\b", "concept": "Amount", "weight": 1.0}
        ]

