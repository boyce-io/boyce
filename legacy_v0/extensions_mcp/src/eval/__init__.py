"""
Evaluation utilities for deterministic SQL correctness.

This package currently exposes:
- Result-set comparison harness for Golden vs Agent SQL.
"""

from .result_harness import compare_query_results

__all__ = ["compare_query_results"]


