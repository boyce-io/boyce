"""
Capability Test: Join Path Selection

Scenario: An analyst asks "show me order revenue by customer segment."
Two paths exist between orders and customers:

    Path A: orders → customers           (FK join, weight 1.0)
    Path B: orders → order_tags → customers  (inferred edges, weight 2.0 each = 4.0)

A junior analyst might not notice the path choice matters. A staff engineer knows:
the FK path is authoritative (defined in the schema), while the inferred path goes
through a tagging table that could fan out rows and inflate revenue.

The graph's Dijkstra pathfinding IS the staff engineer's join instinct — it always
picks the lowest-cost path, preferring explicit metadata over heuristic inference.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_PROTO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_PROTO_ROOT / "src"))

from boyce.types import (
    Entity,
    FieldDef,
    FieldType,
    JoinDef,
    JoinType,
    SemanticSnapshot,
)
from boyce.graph import SemanticGraph


def _build_multi_path_snapshot() -> SemanticSnapshot:
    """Build a snapshot with two paths between orders and customers.

    Direct path (FK, weight 1.0):
        orders.customer_id → customers.id

    Indirect path through order_tags (inferred, weight 2.0 each leg):
        orders.id → order_tags.order_id (inferred)
        order_tags.customer_id → customers.id (inferred)
    """
    return SemanticSnapshot(
        snapshot_id="test-join-path-001",
        source_system="test",
        source_version="1.0",
        entities={
            "entity:orders": Entity(
                id="entity:orders",
                name="orders",
                fields=[
                    "field:orders:id",
                    "field:orders:customer_id",
                    "field:orders:revenue",
                ],
                grain="id",
            ),
            "entity:customers": Entity(
                id="entity:customers",
                name="customers",
                fields=[
                    "field:customers:id",
                    "field:customers:segment",
                ],
                grain="id",
            ),
            "entity:order_tags": Entity(
                id="entity:order_tags",
                name="order_tags",
                fields=[
                    "field:order_tags:id",
                    "field:order_tags:order_id",
                    "field:order_tags:customer_id",
                    "field:order_tags:tag",
                ],
                grain="id",
            ),
        },
        fields={
            "field:orders:id": FieldDef(
                id="field:orders:id",
                entity_id="entity:orders",
                name="id",
                field_type=FieldType.ID,
                data_type="INTEGER",
                primary_key=True,
            ),
            "field:orders:customer_id": FieldDef(
                id="field:orders:customer_id",
                entity_id="entity:orders",
                name="customer_id",
                field_type=FieldType.FOREIGN_KEY,
                data_type="INTEGER",
            ),
            "field:orders:revenue": FieldDef(
                id="field:orders:revenue",
                entity_id="entity:orders",
                name="revenue",
                field_type=FieldType.MEASURE,
                data_type="DECIMAL",
            ),
            "field:customers:id": FieldDef(
                id="field:customers:id",
                entity_id="entity:customers",
                name="id",
                field_type=FieldType.ID,
                data_type="INTEGER",
                primary_key=True,
            ),
            "field:customers:segment": FieldDef(
                id="field:customers:segment",
                entity_id="entity:customers",
                name="segment",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR",
            ),
            "field:order_tags:id": FieldDef(
                id="field:order_tags:id",
                entity_id="entity:order_tags",
                name="id",
                field_type=FieldType.ID,
                data_type="INTEGER",
                primary_key=True,
            ),
            "field:order_tags:order_id": FieldDef(
                id="field:order_tags:order_id",
                entity_id="entity:order_tags",
                name="order_id",
                field_type=FieldType.FOREIGN_KEY,
                data_type="INTEGER",
            ),
            "field:order_tags:customer_id": FieldDef(
                id="field:order_tags:customer_id",
                entity_id="entity:order_tags",
                name="customer_id",
                field_type=FieldType.FOREIGN_KEY,
                data_type="INTEGER",
            ),
            "field:order_tags:tag": FieldDef(
                id="field:order_tags:tag",
                entity_id="entity:order_tags",
                name="tag",
                field_type=FieldType.DIMENSION,
                data_type="VARCHAR",
            ),
        },
        joins=[
            # Direct FK: orders → customers (weight 1.0)
            JoinDef(
                id="join:orders:customers",
                source_entity_id="entity:orders",
                target_entity_id="entity:customers",
                join_type=JoinType.LEFT,
                source_field_id="field:orders:customer_id",
                target_field_id="field:customers:id",
                description="FK: orders.customer_id -> customers.id",
            ),
            # Indirect via order_tags: orders → order_tags (FK, weight 1.0)
            JoinDef(
                id="join:order_tags:orders",
                source_entity_id="entity:order_tags",
                target_entity_id="entity:orders",
                join_type=JoinType.LEFT,
                source_field_id="field:order_tags:order_id",
                target_field_id="field:orders:id",
                description="FK: order_tags.order_id -> orders.id",
            ),
            # Indirect via order_tags: order_tags → customers (FK, weight 1.0)
            JoinDef(
                id="join:order_tags:customers",
                source_entity_id="entity:order_tags",
                target_entity_id="entity:customers",
                join_type=JoinType.LEFT,
                source_field_id="field:order_tags:customer_id",
                target_field_id="field:customers:id",
                description="FK: order_tags.customer_id -> customers.id",
            ),
        ],
    )


class TestJoinPathSelection(unittest.TestCase):
    """Does the system pick the right join path when multiple options exist?"""

    def test_prefers_direct_fk_over_indirect_path(self):
        """Direct FK (weight 1.0) must beat indirect via order_tags (weight 2.0+)."""
        graph = SemanticGraph()
        snapshot = _build_multi_path_snapshot()
        graph.add_snapshot(snapshot)

        path = graph.find_path("entity:orders", "entity:customers")

        # The direct path is a single hop
        self.assertEqual(len(path), 1, "Should take the direct 1-hop path, not the 2-hop indirect")
        self.assertEqual(path[0].source_entity_id, "entity:orders")
        self.assertEqual(path[0].target_entity_id, "entity:customers")

    def test_gold_standard_beats_fk(self):
        """Explicit dbt/LookML joins (0.1) must beat FK joins (1.0).

        This is the data-mesh scenario: the dbt model owner has declared
        the canonical join, and it should be preferred over a raw FK that
        might be an implementation detail.
        """
        snapshot = SemanticSnapshot(
            snapshot_id="test-gold-vs-fk",
            source_system="dbt",
            source_version="1.0",
            entities={
                "entity:orders": Entity(
                    id="entity:orders",
                    name="orders",
                    fields=["field:orders:id", "field:orders:customer_id"],
                    grain="id",
                ),
                "entity:customers": Entity(
                    id="entity:customers",
                    name="customers",
                    fields=["field:customers:id"],
                    grain="id",
                ),
            },
            fields={
                "field:orders:id": FieldDef(
                    id="field:orders:id",
                    entity_id="entity:orders",
                    name="id",
                    field_type=FieldType.ID,
                    data_type="INTEGER",
                    primary_key=True,
                ),
                "field:orders:customer_id": FieldDef(
                    id="field:orders:customer_id",
                    entity_id="entity:orders",
                    name="customer_id",
                    field_type=FieldType.FOREIGN_KEY,
                    data_type="INTEGER",
                ),
                "field:customers:id": FieldDef(
                    id="field:customers:id",
                    entity_id="entity:customers",
                    name="id",
                    field_type=FieldType.ID,
                    data_type="INTEGER",
                    primary_key=True,
                ),
            },
            joins=[
                # FK join (weight 1.0)
                JoinDef(
                    id="join:orders:customers:fk",
                    source_entity_id="entity:orders",
                    target_entity_id="entity:customers",
                    join_type=JoinType.LEFT,
                    source_field_id="field:orders:customer_id",
                    target_field_id="field:customers:id",
                    description="FK: orders.customer_id -> customers.id",
                ),
                # Gold standard dbt join (weight 0.1)
                JoinDef(
                    id="join:orders:customers:dbt",
                    source_entity_id="entity:orders",
                    target_entity_id="entity:customers",
                    join_type=JoinType.LEFT,
                    source_field_id="field:orders:customer_id",
                    target_field_id="field:customers:id",
                    description="dbt relationship: orders -> customers",
                ),
            ],
            metadata={"source_type": "manifest"},
        )

        graph = SemanticGraph()
        graph.add_snapshot(snapshot)

        path = graph.find_path("entity:orders", "entity:customers")

        self.assertEqual(len(path), 1)
        # The selected join should be the gold standard (dbt) one
        self.assertEqual(path[0].id, "join:orders:customers:dbt")

    def test_avoids_many_to_many(self):
        """M:M joins (weight 100.0) should be avoided when any alternative exists.

        Graph topology (directed):
            warehouses ──FK(1.0)──→ shipments ──FK(1.0)──→ stores
            warehouses ──M:M(100)──→ stores

        Dijkstra should pick the 2-hop FK path (total 2.0) over the direct M:M (100.0).
        """
        snapshot = SemanticSnapshot(
            snapshot_id="test-m2m-avoidance",
            source_system="test",
            source_version="1.0",
            entities={
                "entity:warehouses": Entity(
                    id="entity:warehouses",
                    name="warehouses",
                    fields=["field:warehouses:id", "field:warehouses:shipment_id"],
                    grain="id",
                ),
                "entity:shipments": Entity(
                    id="entity:shipments",
                    name="shipments",
                    fields=["field:shipments:id", "field:shipments:store_id"],
                    grain="id",
                ),
                "entity:stores": Entity(
                    id="entity:stores",
                    name="stores",
                    fields=["field:stores:id", "field:stores:name"],
                    grain="id",
                ),
            },
            fields={
                "field:warehouses:id": FieldDef(
                    id="field:warehouses:id",
                    entity_id="entity:warehouses",
                    name="id",
                    field_type=FieldType.ID,
                    data_type="INTEGER",
                    primary_key=True,
                ),
                "field:warehouses:shipment_id": FieldDef(
                    id="field:warehouses:shipment_id",
                    entity_id="entity:warehouses",
                    name="shipment_id",
                    field_type=FieldType.FOREIGN_KEY,
                    data_type="INTEGER",
                ),
                "field:shipments:id": FieldDef(
                    id="field:shipments:id",
                    entity_id="entity:shipments",
                    name="id",
                    field_type=FieldType.ID,
                    data_type="INTEGER",
                    primary_key=True,
                ),
                "field:shipments:store_id": FieldDef(
                    id="field:shipments:store_id",
                    entity_id="entity:shipments",
                    name="store_id",
                    field_type=FieldType.FOREIGN_KEY,
                    data_type="INTEGER",
                ),
                "field:stores:id": FieldDef(
                    id="field:stores:id",
                    entity_id="entity:stores",
                    name="id",
                    field_type=FieldType.ID,
                    data_type="INTEGER",
                    primary_key=True,
                ),
                "field:stores:name": FieldDef(
                    id="field:stores:name",
                    entity_id="entity:stores",
                    name="name",
                    field_type=FieldType.DIMENSION,
                    data_type="VARCHAR",
                ),
            },
            joins=[
                # Direct M:M: warehouses → stores (weight 100.0)
                JoinDef(
                    id="join:warehouses:stores:m2m",
                    source_entity_id="entity:warehouses",
                    target_entity_id="entity:stores",
                    join_type=JoinType.LEFT,
                    source_field_id="field:warehouses:id",
                    target_field_id="field:stores:id",
                    description="many_to_many: warehouses <-> stores",
                ),
                # Hop 1: warehouses → shipments (FK, weight 1.0)
                JoinDef(
                    id="join:warehouses:shipments",
                    source_entity_id="entity:warehouses",
                    target_entity_id="entity:shipments",
                    join_type=JoinType.LEFT,
                    source_field_id="field:warehouses:shipment_id",
                    target_field_id="field:shipments:id",
                    description="FK: warehouses.shipment_id -> shipments.id",
                ),
                # Hop 2: shipments → stores (FK, weight 1.0)
                JoinDef(
                    id="join:shipments:stores",
                    source_entity_id="entity:shipments",
                    target_entity_id="entity:stores",
                    join_type=JoinType.LEFT,
                    source_field_id="field:shipments:store_id",
                    target_field_id="field:stores:id",
                    description="FK: shipments.store_id -> stores.id",
                ),
            ],
        )

        graph = SemanticGraph()
        graph.add_snapshot(snapshot)

        path = graph.find_path("entity:warehouses", "entity:stores")

        # The 2-hop FK path (1.0 + 1.0 = 2.0) should beat the direct M:M (100.0)
        self.assertEqual(len(path), 2, "Should take the 2-hop FK path, not the direct M:M")
        # First hop: warehouses → shipments
        self.assertEqual(path[0].source_entity_id, "entity:warehouses")
        self.assertEqual(path[0].target_entity_id, "entity:shipments")
        # Second hop: shipments → stores
        self.assertEqual(path[1].source_entity_id, "entity:shipments")
        self.assertEqual(path[1].target_entity_id, "entity:stores")

    def test_no_path_returns_empty(self):
        """When no path exists, return empty — don't crash, don't hallucinate a join."""
        snapshot = SemanticSnapshot(
            snapshot_id="test-no-path",
            source_system="test",
            source_version="1.0",
            entities={
                "entity:orders": Entity(
                    id="entity:orders",
                    name="orders",
                    fields=["field:orders:id"],
                    grain="id",
                ),
                "entity:weather": Entity(
                    id="entity:weather",
                    name="weather",
                    fields=["field:weather:id"],
                    grain="id",
                ),
            },
            fields={
                "field:orders:id": FieldDef(
                    id="field:orders:id",
                    entity_id="entity:orders",
                    name="id",
                    field_type=FieldType.ID,
                    data_type="INTEGER",
                    primary_key=True,
                ),
                "field:weather:id": FieldDef(
                    id="field:weather:id",
                    entity_id="entity:weather",
                    name="id",
                    field_type=FieldType.ID,
                    data_type="INTEGER",
                    primary_key=True,
                ),
            },
            joins=[],
        )

        graph = SemanticGraph()
        graph.add_snapshot(snapshot)

        path = graph.find_path("entity:orders", "entity:weather")

        self.assertEqual(len(path), 0, "No path between unrelated entities — don't hallucinate")

    def test_generate_join_sql_correct_for_selected_path(self):
        """The SQL generated from the selected path must be syntactically correct."""
        graph = SemanticGraph()
        snapshot = _build_multi_path_snapshot()
        graph.add_snapshot(snapshot)

        path = graph.find_path("entity:orders", "entity:customers")
        sql = graph.generate_join_sql(path, "entity:orders")

        self.assertIn("FROM orders", sql)
        self.assertIn("LEFT JOIN customers", sql)
        self.assertIn("customer_id", sql)
        # Should NOT go through order_tags
        self.assertNotIn("order_tags", sql)

    def test_inferred_edges_weight_is_bronze(self):
        """Inferred edges (name-match heuristic) must get weight 2.0 — Bronze Standard."""
        snapshot = SemanticSnapshot(
            snapshot_id="test-infer-weight",
            source_system="test",
            source_version="1.0",
            entities={
                "entity:orders": Entity(
                    id="entity:orders",
                    name="orders",
                    fields=["field:orders:id", "field:orders:product_id"],
                    grain="id",
                ),
                "entity:products": Entity(
                    id="entity:products",
                    name="products",
                    fields=["field:products:id", "field:products:name"],
                    grain="id",
                ),
            },
            fields={
                "field:orders:id": FieldDef(
                    id="field:orders:id",
                    entity_id="entity:orders",
                    name="id",
                    field_type=FieldType.ID,
                    data_type="INTEGER",
                    primary_key=True,
                ),
                "field:orders:product_id": FieldDef(
                    id="field:orders:product_id",
                    entity_id="entity:orders",
                    name="product_id",
                    field_type=FieldType.DIMENSION,
                    data_type="INTEGER",
                ),
                "field:products:id": FieldDef(
                    id="field:products:id",
                    entity_id="entity:products",
                    name="id",
                    field_type=FieldType.ID,
                    data_type="INTEGER",
                    primary_key=True,
                ),
                "field:products:name": FieldDef(
                    id="field:products:name",
                    entity_id="entity:products",
                    name="name",
                    field_type=FieldType.DIMENSION,
                    data_type="VARCHAR",
                ),
            },
            joins=[],  # No explicit joins — force inference
        )

        graph = SemanticGraph()
        graph.add_snapshot(snapshot)

        # Check that inferred edge exists and has weight 2.0
        path = graph.find_path("entity:orders", "entity:products")
        self.assertEqual(len(path), 1, "Inferred edge should connect orders → products")

        # Verify the weight
        for _, _, data in graph.graph.edges(data=True):
            join = data.get("join")
            if join and join.id.startswith("inferred:"):
                self.assertEqual(data["weight"], 2.0, "Inferred edges must be Bronze Standard (2.0)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
