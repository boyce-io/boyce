"""
Mock data for testing DataShark components.

Contains sample metadata with valid_values for testing smart filter extraction.
"""

# Mock metadata with valid_values for testing smart filters
MOCK_METADATA_WITH_VALID_VALUES = {
    "entities": {
        "entity:users": {
            "entity_id": "entity:users",
            "entity_name": "users",
            "name": "users",
            "type": "table",
            "fields": [
                {
                    "field_id": "field:users:id",
                    "field_name": "id",
                    "column_name": "id",
                    "type": "integer"
                },
                {
                    "field_id": "field:users:name",
                    "field_name": "name",
                    "column_name": "name",
                    "type": "string"
                },
                {
                    "field_id": "field:users:region",
                    "field_name": "region",
                    "column_name": "region",
                    "type": "varchar",
                    "valid_values": ["ID", "NY", "CA", "WA", "TX", "FL"]
                },
                {
                    "field_id": "field:users:department",
                    "field_name": "department",
                    "column_name": "department",
                    "type": "varchar",
                    "valid_values": ["Engineering", "Sales", "HR", "Marketing", "Finance"]
                },
                {
                    "field_id": "field:users:salary_amount",
                    "field_name": "salary_amount",
                    "column_name": "salary_amount",
                    "type": "decimal"
                }
            ]
        },
        "entity:orders": {
            "entity_id": "entity:orders",
            "entity_name": "orders",
            "name": "orders",
            "type": "table",
            "fields": [
                {
                    "field_id": "field:orders:id",
                    "field_name": "id",
                    "column_name": "id",
                    "type": "integer"
                },
                {
                    "field_id": "field:orders:user_id",
                    "field_name": "user_id",
                    "column_name": "user_id",
                    "type": "integer"
                },
                {
                    "field_id": "field:orders:status",
                    "field_name": "status",
                    "column_name": "status",
                    "type": "varchar",
                    "valid_values": ["pending", "completed", "cancelled", "shipped"]
                },
                {
                    "field_id": "field:orders:amount",
                    "field_name": "amount",
                    "column_name": "amount",
                    "type": "decimal"
                }
            ]
        }
    },
    "relationships": [
        {
            "source_entity_id": "entity:users",
            "target_entity_id": "entity:orders",
            "join_condition": "users.id = orders.user_id",
            "confidence_score": 0.9
        }
    ]
}





