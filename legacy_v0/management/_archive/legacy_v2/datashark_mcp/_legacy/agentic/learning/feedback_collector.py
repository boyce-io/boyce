"""
Feedback Collector

Aggregates telemetry and user corrections for learning.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class FeedbackCollector:
    """
    Collects feedback from:
    - UI telemetry (instance/logs/ui_events.jsonl)
    - Ingestion telemetry (instance/logs/ingest_run.jsonl)
    - User corrections (manual feedback)
    """
    
    def __init__(self, instance_path: Path):
        """
        Initialize feedback collector.
        
        Args:
            instance_path: Path to instance directory
        """
        self.instance_path = instance_path
        self.logs_dir = instance_path / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized FeedbackCollector for instance: {instance_path}")
    
    def collect_telemetry(self) -> List[Dict[str, Any]]:
        """
        Collect telemetry from all instance log files.
        
        Returns:
            List of telemetry events
        """
        events: List[Dict[str, Any]] = []
        
        # Collect UI events
        ui_events_file = self.logs_dir / "ui_events.jsonl"
        if ui_events_file.exists():
            events.extend(self._read_jsonl(ui_events_file))
        
        # Collect ingestion telemetry
        ingest_file = self.logs_dir / "ingest_run.jsonl"
        if ingest_file.exists():
            events.extend(self._read_jsonl(ingest_file))
        
        # Collect extraction telemetry
        extraction_file = self.logs_dir / "extraction_telemetry.jsonl"
        if extraction_file.exists():
            events.extend(self._read_jsonl(extraction_file))
        
        logger.info(f"Collected {len(events)} telemetry events")
        return events
    
    def collect_user_corrections(self) -> List[Dict[str, Any]]:
        """
        Collect user corrections (manual feedback).
        
        Returns:
            List of correction events
        """
        corrections_file = self.logs_dir / "corrections.jsonl"
        
        if corrections_file.exists():
            return self._read_jsonl(corrections_file)
        
        return []
    
    def record_correction(
        self,
        inference_id: str,
        inference_type: str,
        correction: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Record a user correction.
        
        Args:
            inference_id: ID of the inference being corrected
            inference_type: Type of inference (concept, join, etc.)
            correction: Correction description
            details: Additional correction details
        """
        corrections_file = self.logs_dir / "corrections.jsonl"
        
        correction_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "inference_id": inference_id,
            "inference_type": inference_type,
            "correction": correction,
            "details": details or {}
        }
        
        with open(corrections_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(correction_entry) + "\n")
        
        logger.info(f"Recorded correction for {inference_id}")
    
    def gather_feedback(self) -> List[Dict[str, Any]]:
        """
        Gather and normalize all feedback entries.
        
        Returns:
            List of normalized feedback entries with common schema
        """
        normalized: List[Dict[str, Any]] = []
        
        # Collect telemetry
        telemetry = self.collect_telemetry()
        for event in telemetry:
            normalized.append({
                "source": "telemetry",
                "context": event.get("source", "unknown"),
                "correction": None,
                "outcome": "observed",
                "timestamp": event.get("timestamp", datetime.utcnow().isoformat() + "Z"),
                "metadata": {
                    "event_type": event.get("event", "unknown"),
                    "extractor": event.get("extractor"),
                    "latency_ms": event.get("extraction_time_ms") or event.get("latency_ms")
                }
            })
        
        # Collect user corrections
        corrections = self.collect_user_corrections()
        for correction in corrections:
            normalized.append({
                "source": "user_correction",
                "context": correction.get("inference_type", "unknown"),
                "correction": correction.get("correction", ""),
                "outcome": "corrected",
                "timestamp": correction.get("timestamp", datetime.utcnow().isoformat() + "Z"),
                "metadata": {
                    "inference_id": correction.get("inference_id"),
                    "details": correction.get("details", {})
                }
            })
        
        # Collect error logs
        error_log = self.logs_dir / "errors.jsonl"
        if error_log.exists():
            errors = self._read_jsonl(error_log)
            for error in errors:
                normalized.append({
                    "source": "error_log",
                    "context": error.get("component", "unknown"),
                    "correction": error.get("error_message", ""),
                    "outcome": "error",
                    "timestamp": error.get("timestamp", datetime.utcnow().isoformat() + "Z"),
                    "metadata": {
                        "error_type": error.get("error_type", "unknown"),
                        "traceback": error.get("traceback", "")
                    }
                })
        
        # Sort by timestamp
        normalized.sort(key=lambda x: x["timestamp"])
        
        logger.info(f"Gathered {len(normalized)} feedback entries")
        return normalized
    
    def aggregate_feedback(self) -> Dict[str, Any]:
        """
        Aggregate all feedback sources.
        
        Returns:
            Summary dict with aggregated metrics
        """
        feedback = self.gather_feedback()
        telemetry = self.collect_telemetry()
        corrections = self.collect_user_corrections()
        
        from datashark_mcp.context.determinism import normalize_timestamp
        
        # Aggregate metrics
        # Normalize timestamp for deterministic output using content-based key
        content_key = f"{len(telemetry)}:{len(corrections)}:{len(feedback)}"
        normalized_ts = normalize_timestamp(datetime.utcnow().isoformat() + "Z", content=content_key)
        
        summary = {
            "timestamp": normalized_ts,
            "telemetry_events": len(telemetry),
            "corrections": len(corrections),
            "total_feedback_entries": len(feedback),
            "metrics": {
                "avg_extraction_time_ms": round(self._avg_metric(telemetry, "extraction_time_ms"), 2),
                "avg_build_time_ms": round(self._avg_metric(telemetry, "value", filter_key="metric", filter_value="build_instance"), 2),
                "total_ui_actions": len([e for e in telemetry if e.get("source") == "ui"]),
                "error_count": len([e for e in feedback if e["outcome"] == "error"]),
                "correction_count": len([e for e in feedback if e["outcome"] == "corrected"])
            }
        }
        
        logger.info(f"Aggregated feedback: {summary}")
        return summary
    
    def _read_jsonl(self, file_path: Path) -> List[Dict[str, Any]]:
        """Read JSONL file."""
        events = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
        return events
    
    def _avg_metric(self, events: List[Dict[str, Any]], metric_key: str, filter_key: Optional[str] = None, filter_value: Optional[str] = None) -> float:
        """Calculate average metric value."""
        values = []
        for event in events:
            if filter_key and filter_value:
                if event.get(filter_key) != filter_value:
                    continue
            value = event.get(metric_key)
            if value is not None:
                values.append(float(value))
        
        if values:
            return sum(values) / len(values)
        return 0.0

