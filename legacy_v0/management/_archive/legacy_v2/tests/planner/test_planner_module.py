"""
Placeholder tests for the planner module interfaces.

These tests verify that the Planner and related contracts are importable.
"""

from datashark_mcp.planner import Planner, PlannerIntent, PlannerPlan


def test_planner_interfaces_exist() -> None:
    """Planner, PlannerIntent, and PlannerPlan should be importable stubs."""
    intent = PlannerIntent(text="test")
    plan = PlannerPlan(intent=intent, concept_map={}, join_plan={}, sql_template="", sql="")
    planner = Planner()
    assert intent.text == "test"
    assert plan.intent is intent
    assert planner is not None


