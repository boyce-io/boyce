"""
Instance Hub

Manages multiple DataShark instances and enables federated queries.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
# Legacy imports - InstanceHub needs refactoring to use Safety Kernel
# For now, importing from legacy location to maintain functionality
from datashark_mcp._legacy.context.store.json_store import JSONStore
from datashark_mcp._legacy.context.api import ContextAPI
from datashark_mcp._legacy.context.store.memory_store import MemoryStore
from statistics import mean

logger = logging.getLogger(__name__)


class InstanceHub:
    """
    Manages multiple DataShark instances and enables federated queries.
    
    Features:
    - List and connect to multiple instances
    - Federated queries across instance manifests
    - Shared telemetry aggregation
    """
    
    def __init__(self):
        """Initialize InstanceHub."""
        self.instances: Dict[str, Dict[str, Any]] = {}
        self.stores: Dict[str, ContextAPI] = {}
        logger.info("Initialized InstanceHub")
    
    def register_instance(self, name: str, instance_path: Path) -> bool:
        """
        Register an instance with the hub.
        
        Args:
            name: Instance name
            instance_path: Path to instance directory
            
        Returns:
            True if successfully registered
        """
        try:
            if not instance_path.exists():
                logger.error(f"Instance path does not exist: {instance_path}")
                return False
            
            manifest_dir = instance_path / "manifests"
            if not manifest_dir.exists():
                logger.warning(f"Manifests directory not found: {manifest_dir}")
            
            # Load instance store
            store = JSONStore(manifest_dir) if manifest_dir.exists() else MemoryStore()
            api = ContextAPI(store)
            
            self.instances[name] = {
                "name": name,
                "path": str(instance_path),
                "manifest_dir": str(manifest_dir)
            }
            self.stores[name] = api
            
            logger.info(f"Registered instance: {name} at {instance_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register instance {name}: {e}")
            return False
    
    def list_instances(self) -> List[str]:
        """List all registered instance names."""
        return list(self.instances.keys())
    
    def get_instance_api(self, name: str) -> Optional[ContextAPI]:
        """Get ContextAPI for a specific instance."""
        return self.stores.get(name)
    
    def federated_query(
        self,
        query_type: str,
        filters: Optional[Dict[str, Any]] = None,
        instance_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Execute federated query across multiple instances.
        
        Args:
            query_type: Type of query (find_entities, search, etc.)
            filters: Query filters
            instance_names: Optional list of instance names (if None, queries all)
            
        Returns:
            Aggregated results from all instances
        """
        results = []
        instance_results = {}
        
        target_instances = instance_names if instance_names else self.list_instances()
        
        for instance_name in target_instances:
            api = self.stores.get(instance_name)
            if not api:
                logger.warning(f"Instance {instance_name} not available")
                continue
            
            try:
                if query_type == "find_entities":
                    instance_result = api.find_entities(filters or {})
                elif query_type == "search":
                    term = filters.get("term", "") if filters else ""
                    instance_result = api.search(term)
                else:
                    logger.warning(f"Unknown query type: {query_type}")
                    continue
                
                instance_results[instance_name] = instance_result
                if isinstance(instance_result, list):
                    results.extend(instance_result)
                elif isinstance(instance_result, dict) and "nodes" in instance_result:
                    results.extend(instance_result["nodes"])
                    
            except Exception as e:
                logger.error(f"Error querying instance {instance_name}: {e}")
                instance_results[instance_name] = {"error": str(e)}
        
        return {
            "results": results,
            "instance_results": instance_results,
            "total_count": len(results),
            "instances_queried": len(target_instances)
        }
    
    def aggregate_telemetry(
        self,
        instance_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Aggregate telemetry from multiple instances.
        
        Args:
            instance_names: Optional list of instance names (if None, aggregates all)
            
        Returns:
            Aggregated telemetry summary
        """
        from datetime import datetime, timezone
        import json
        
        target_instances = instance_names if instance_names else self.list_instances()
        
        aggregated = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instances": {},
            "total_queries": 0,
            "total_ingestion_runs": 0,
            "total_learning_runs": 0
        }
        
        for instance_name in target_instances:
            instance_info = self.instances.get(instance_name)
            if not instance_info:
                continue
            
            instance_path = Path(instance_info["path"])
            logs_dir = instance_path / "logs"
            
            if not logs_dir.exists():
                continue
            
            instance_telemetry = {
                "queries": 0,
                "ingestion_runs": 0,
                "learning_runs": 0
            }
            
            # Count queries from query_history.jsonl
            query_history_file = logs_dir / "query_history.jsonl"
            if query_history_file.exists():
                try:
                    with open(query_history_file, 'r') as f:
                        instance_telemetry["queries"] = sum(1 for line in f if line.strip())
                        aggregated["total_queries"] += instance_telemetry["queries"]
                except:
                    pass
            
            # Count ingestion runs
            ingest_log = logs_dir / "ingest_run.jsonl"
            if ingest_log.exists():
                try:
                    with open(ingest_log, 'r') as f:
                        instance_telemetry["ingestion_runs"] = sum(1 for line in f if line.strip())
                        aggregated["total_ingestion_runs"] += instance_telemetry["ingestion_runs"]
                except:
                    pass
            
            # Count learning runs
            learning_log = logs_dir / "learning_run.jsonl"
            if learning_log.exists():
                try:
                    with open(learning_log, 'r') as f:
                        instance_telemetry["learning_runs"] = sum(1 for line in f if line.strip())
                        aggregated["total_learning_runs"] += instance_telemetry["learning_runs"]
                except:
                    pass
            
            aggregated["instances"][instance_name] = instance_telemetry
        
        return aggregated


class FederatedIntelligenceManager:
    """Federated intelligence across multiple instances.

    Provides deterministic aggregation of telemetry/learning metrics,
    computes per-instance confidence weights, and propagates model updates.
    """

    def __init__(self, hub: InstanceHub, seed: int = 42):
        self.hub = hub
        self.seed = seed  # Reserved for future stochastic strategies

    def collect_federated_metrics(self, instance_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """Aggregate learning + telemetry across instances.

        Returns dict with per-instance accuracy/precision/recall/latency summaries
        and a global weighted view placeholder.
        """
        from pathlib import Path
        import json
        from datetime import datetime, timezone

        target_instances = instance_names if instance_names else self.hub.list_instances()
        per_instance: Dict[str, Dict[str, Any]] = {}

        for name in target_instances:
            info = self.hub.instances.get(name)
            if not info:
                continue
            logs = Path(info["path"]) / "logs"
            metrics_file = logs / "learning_metrics.jsonl"

            acc, prec, rec, lat = [], [], [], []
            if metrics_file.exists():
                try:
                    with open(metrics_file, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            m = json.loads(line)
                            metric = m.get("metric")
                            val = m.get("value")
                            if metric == "accuracy":
                                acc.append(val)
                            elif metric == "precision":
                                prec.append(val)
                            elif metric == "recall":
                                rec.append(val)
                            elif metric == "latency":
                                lat.append(val)
                except Exception as e:
                    logger.warning(f"Failed reading metrics for {name}: {e}")

            per_instance[name] = {
                "avg_accuracy": mean(acc) if acc else 0.0,
                "avg_precision": mean(prec) if prec else 0.0,
                "avg_recall": mean(rec) if rec else 0.0,
                "avg_latency_ms": mean(lat) if lat else 0.0,
                "samples": {
                    "accuracy": len(acc),
                    "precision": len(prec),
                    "recall": len(rec),
                    "latency": len(lat),
                },
            }

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instances": per_instance,
        }

    def compute_confidence_weights(self, metrics: Dict[str, Any]) -> Dict[str, float]:
        """Assign per-instance trust scores in [0,1].

        Deterministic formula (transparent):
          weight = 0.6*accuracy + 0.2*precision + 0.2*recall, then scaled by latency factor
          latency_factor = 1 / (1 + avg_latency_ms / 1000)
        Normalized so weights sum to 1 when any positive.
        """
        weights: Dict[str, float] = {}
        for name, m in metrics.get("instances", {}).items():
            acc = float(m.get("avg_accuracy", 0.0))
            prec = float(m.get("avg_precision", 0.0))
            rec = float(m.get("avg_recall", 0.0))
            lat = float(m.get("avg_latency_ms", 0.0))
            latency_factor = 1.0 / (1.0 + (lat / 1000.0))
            base = max(0.0, 0.6 * acc + 0.2 * prec + 0.2 * rec)
            weights[name] = base * latency_factor

        total = sum(weights.values())
        if total > 0:
            for k in list(weights.keys()):
                weights[k] = weights[k] / total
        else:
            # Equal weights when no signal
            n = len(weights) or 1
            for k in list(weights.keys()):
                weights[k] = 1.0 / n
        return weights

    def propagate_model_updates(
        self,
        updates: Dict[str, Any],
        instance_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Propagate model updates to instances using confidence weights.

        The method does not alter update contents; it records intended effect
        per-instance for auditability and returns a summary.
        """
        from pathlib import Path
        import json
        from datetime import datetime, timezone

        metrics = self.collect_federated_metrics(instance_names)
        weights = self.compute_confidence_weights(metrics)

        target_instances = instance_names if instance_names else self.hub.list_instances()
        results: Dict[str, Any] = {"instances": {}, "weights": weights}

        for name in target_instances:
            info = self.hub.instances.get(name)
            if not info:
                continue
            # Record propagation event
            logs = Path(info["path"]) / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            record = {
                "event": "federated_model_update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "weight": float(weights.get(name, 0.0)),
                "updates": updates,
            }
            try:
                with open(logs / "federated_learning.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
            except Exception as e:
                logger.warning(f"Failed to write federated record for {name}: {e}")

            results["instances"][name] = {
                "applied": True,
                "weight": float(weights.get(name, 0.0)),
            }

        return results

