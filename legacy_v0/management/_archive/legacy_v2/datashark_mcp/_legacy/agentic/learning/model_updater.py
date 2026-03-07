"""
Model Updater

API for retraining DSL templates and join heuristics based on feedback.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Any, Optional
from datashark_mcp.agentic.learning.feedback_collector import FeedbackCollector
from datashark_mcp.agentic.learning.model_storage import ModelStorage
from datashark_mcp.orchestration.instance_hub import InstanceHub, FederatedIntelligenceManager

logger = logging.getLogger(__name__)


class ModelUpdater:
    """
    Updates models based on feedback:
    - DSL templates (nl2dsl/templates.yaml)
    - Join heuristics (join_inference patterns)
    - Concept catalog (concept mappings)
    """
    
    def __init__(self, instance_path: Path, seed: int = 42):
        """
        Initialize model updater.
        
        Args:
            instance_path: Path to instance directory
            seed: Random seed for deterministic updates
        """
        self.instance_path = instance_path
        self.feedback_collector = FeedbackCollector(instance_path)
        self.model_storage = ModelStorage(instance_path)
        self.seed = seed
        random.seed(seed)
        
        logger.info(f"Initialized ModelUpdater for instance: {instance_path} (seed={seed})")
    
    def update_dsl_templates(self, feedback: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update DSL templates based on feedback.
        
        Args:
            feedback: Aggregated feedback data
            
        Returns:
            Update summary
        """
        # Load current templates
        current_templates = self.model_storage.load_model("dsl_templates")
        
        if not current_templates:
            # Initialize default templates
            current_templates = {
                "version": "1.0.0",
                "templates": {
                    "find_entity": {
                        "pattern": "FIND ENTITY WHERE {conditions}",
                        "weight": 1.0,
                        "success_count": 0,
                        "failure_count": 0
                    },
                    "path_query": {
                        "pattern": "PATH FROM {source} TO {target}",
                        "weight": 1.0,
                        "success_count": 0,
                        "failure_count": 0
                    }
                }
            }
        
        # Analyze feedback to adjust weights
        feedback_entries = self.feedback_collector.gather_feedback()
        corrections = [f for f in feedback_entries if f["outcome"] == "corrected"]
        
        templates_data = current_templates.get("data", current_templates).get("templates", {})
        
        # Update template weights based on corrections
        for correction in corrections:
            context = correction.get("context", "")
            metadata = correction.get("metadata", {})
            
            # Adjust weights based on correction context
            if "dsl" in context.lower() or "template" in context.lower():
                # Find matching template and adjust
                for template_name, template_data in templates_data.items():
                    if template_data.get("pattern", "").lower() in correction.get("correction", "").lower():
                        # Decrease weight on failure
                        template_data["failure_count"] = template_data.get("failure_count", 0) + 1
                        template_data["weight"] = max(0.1, template_data["weight"] - 0.05)
        
        # Update version (handle version strings like "1.0.0" or "1.0")
        version_str = current_templates.get("version", "1.0")
        # Extract major.minor from version string (e.g., "1.0.0" -> "1.0", "1.0" -> "1.0")
        try:
            if '.' in version_str:
                parts = version_str.split('.')
                if len(parts) >= 2:
                    major_minor = float(f"{parts[0]}.{parts[1]}")
                else:
                    major_minor = float(version_str)
            else:
                major_minor = float(version_str)
            current_templates["version"] = f"{major_minor + 0.1:.1f}"
        except (ValueError, IndexError):
            # Fallback: use default version
            current_templates["version"] = "1.1"
        
        # Save updated model
        model_hash = self.model_storage.save_model("dsl_templates", current_templates, self.seed)
        
        logger.info(f"Updated DSL templates (hash: {model_hash})")
        
        return {
            "templates_updated": len(templates_data),
            "method": "weight_adjustment",
            "model_hash": model_hash
        }
    
    def update_join_heuristics(self, feedback: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update join inference heuristics based on feedback.
        
        Args:
            feedback: Aggregated feedback data
            
        Returns:
            Update summary
        """
        # Load current heuristics
        current_heuristics = self.model_storage.load_model("join_heuristics")
        
        if not current_heuristics:
            # Initialize default heuristics
            current_heuristics = {
                "version": "1.0.0",
                "confidence_multipliers": {
                    "exact_name_match": 1.0,
                    "fk_naming_convention": 1.0,
                    "id_pattern_match": 1.0,
                    "type_match": 1.0
                },
                "pattern_counts": {
                    "exact_name_match": {"success": 0, "failure": 0},
                    "fk_naming_convention": {"success": 0, "failure": 0},
                    "id_pattern_match": {"success": 0, "failure": 0},
                    "type_match": {"success": 0, "failure": 0}
                }
            }
        
        # Analyze feedback
        feedback_entries = self.feedback_collector.gather_feedback()
        corrections = [f for f in feedback_entries if f["outcome"] == "corrected"]
        
        heuristics_data = current_heuristics.get("data", current_heuristics)
        multipliers = heuristics_data.get("confidence_multipliers", {})
        pattern_counts = heuristics_data.get("pattern_counts", {})
        
        # Update multipliers based on corrections
        for correction in corrections:
            context = correction.get("context", "")
            metadata = correction.get("metadata", {})
            
            if "join" in context.lower():
                # Adjust multipliers based on correction
                method = metadata.get("details", {}).get("method", "")
                if method in multipliers:
                    # Decrease multiplier on failure
                    pattern_counts[method]["failure"] = pattern_counts[method].get("failure", 0) + 1
                    multipliers[method] = max(0.5, multipliers[method] - 0.1)
        
        # Update version
        heuristics_data["version"] = str(float(heuristics_data.get("version", "1.0")) + 0.1)
        
        # Save updated model
        model_hash = self.model_storage.save_model("join_heuristics", heuristics_data, self.seed)
        
        logger.info(f"Updated join heuristics (hash: {model_hash})")
        
        return {
            "patterns_updated": len(multipliers),
            "method": "confidence_adjustment",
            "model_hash": model_hash
        }
    
    def update_concept_catalog(self, feedback: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update concept catalog based on feedback.
        
        Args:
            feedback: Aggregated feedback data
            
        Returns:
            Update summary
        """
        # Placeholder: Would add new concepts or update aliases
        # For now, return summary
        
        logger.info("Concept catalog update (placeholder)")
        
        return {
            "concepts_added": 0,
            "aliases_updated": 0,
            "method": "placeholder"
        }
    
    def retrain_models(self, federated: bool = False, hub: Optional[InstanceHub] = None) -> Dict[str, Any]:
        """
        Retrain all models based on collected feedback.
        
        Returns:
            Summary of all updates
        """
        feedback = self.feedback_collector.aggregate_feedback()
        
        dsl_update = self.update_dsl_templates(feedback)
        join_update = self.update_join_heuristics(feedback)
        concept_update = self.update_concept_catalog(feedback)
        
        # Use normalized timestamp from feedback (already normalized)
        summary = {
            "timestamp": feedback["timestamp"],  # Already normalized by feedback_collector
            "dsl_templates": dsl_update,
            "join_heuristics": join_update,
            "concept_catalog": concept_update,
            "seed": self.seed
        }
        
        # Optionally propagate via InstanceHub
        if federated and hub is not None:
            try:
                fim = FederatedIntelligenceManager(hub)
                # Telemetry start
                self._log_federated_event("federated_learning_start", summary)
                prop = fim.propagate_model_updates(summary)
                summary["federated_propagation"] = prop
                # Telemetry complete
                self._log_federated_event("federated_learning_complete", prop)
            except Exception as e:
                logger.warning(f"Federated propagation failed: {e}")

        logger.info(f"Model retraining complete: {summary}")
        return summary
    
    def retrain_all(self) -> Dict[str, Any]:
        """Alias for retrain_models for backward compatibility."""
        return self.retrain_models()

    # Internal: write federated telemetry to instance logs
    def _log_federated_event(self, event: str, payload: Dict[str, Any]) -> None:
        from datetime import datetime, timezone
        import json
        logs = self.instance_path / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        record = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        try:
            with open(logs / "federated_learning.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass

