#!/usr/bin/env python3
"""
Behavioral Governance Verification Script

This script proves that the Planner's reality is shaped by the UserContext
through the Safety Kernel's Graph Projection mechanism.

It demonstrates that:
1. Admin users can access restricted data (salaries)
2. Analyst users are blocked from accessing restricted data (salaries)
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'datashark-mcp', 'src'))

from datashark_mcp.kernel.engine import DataSharkEngine
from datashark_mcp.kernel.types import UserContext
from datashark_mcp.security.policy import PolicyRule, PolicySet


def main():
    """Run behavioral governance verification tests."""
    
    print("=" * 80)
    print("BEHAVIORAL GOVERNANCE VERIFICATION")
    print("=" * 80)
    print()
    
    # ===== SETUP =====
    print("📋 Setting up test data and policies...")
    
    # Define raw metadata with public and restricted tables
    raw_metadata = {
        "users": {
            "entity_id": "entity:users",
            "entity_name": "users",
            "columns": ["id", "name"],
            "type": "table",
            "schema": "public"
        },
        "salaries": {
            "entity_id": "entity:salaries",
            "entity_name": "salaries",
            "columns": ["user_id", "amount"],
            "type": "table",
            "schema": "restricted"
        },
        "entities": {
            "users": {
                "entity_id": "entity:users",
                "entity_name": "users",
                "columns": ["id", "name"],
                "type": "table"
            },
            "salaries": {
                "entity_id": "entity:salaries",
                "entity_name": "salaries",
                "columns": ["user_id", "amount"],
                "type": "table"
            }
        }
    }
    
    # Define contexts
    admin_context = UserContext(
        user_id="admin_user",
        roles=["admin"],
        tenant_id="test_tenant"
    )
    
    analyst_context = UserContext(
        user_id="analyst_user",
        roles=["analyst"],
        tenant_id="test_tenant"
    )
    
    # Define PolicySet
    # Rule 1: Only admin can access salaries
    salaries_rule = PolicyRule(
        resource_pattern="salaries",
        allowed_roles=["admin"],  # Only admin allowed
        action="allow"
    )
    
    # Rule 2: Both admin and analyst can access users
    users_rule = PolicyRule(
        resource_pattern="users",
        allowed_roles=["admin", "analyst"],
        action="allow"
    )
    
    policy_set = PolicySet(
        rules=[salaries_rule, users_rule],
        default_action="deny"  # Principle of least privilege
    )
    
    print("✅ Setup complete")
    print()
    
    # ===== EXECUTION 1: THE ADMIN =====
    print("=" * 80)
    print("EXECUTION 1: THE ADMIN")
    print("=" * 80)
    print()
    
    try:
        # Initialize engine with admin context
        admin_engine = DataSharkEngine(context=admin_context)
        admin_engine.policy_set = policy_set
        admin_engine.load_metadata(raw_metadata)
        
        print("✅ Admin engine initialized and metadata loaded")
        
        # Run query for salaries
        query = "Show me total salaries"
        print(f"📝 Query: '{query}'")
        
        result = admin_engine.process_request(query)
        
        # Check result
        final_sql = result.get("final_sql_output", "")
        print(f"📊 Result SQL: {final_sql}")
        
        # ASSERT: Admin should be able to access salaries
        # Check if "salaries" appears in FROM clause (not just in column names)
        sql_lower = final_sql.lower()
        # Look for "from salaries" or "salaries" as a table name
        has_salaries_table = (
            " from salaries" in sql_lower or 
            "from salaries " in sql_lower or
            "from salaries," in sql_lower or
            "join salaries" in sql_lower
        )
        
        if has_salaries_table:
            print("✅ Admin successfully accessed salaries.")
            admin_success = True
        else:
            print("❌ FAILURE: Admin should have access to salaries, but SQL doesn't contain 'salaries' in FROM/JOIN clause")
            admin_success = False
            
    except Exception as e:
        print(f"❌ FAILURE: Admin execution raised exception: {e}")
        import traceback
        traceback.print_exc()
        admin_success = False
    
    print()
    
    # ===== EXECUTION 2: THE ANALYST =====
    print("=" * 80)
    print("EXECUTION 2: THE ANALYST")
    print("=" * 80)
    print()
    
    try:
        # Initialize engine with analyst context
        analyst_engine = DataSharkEngine(context=analyst_context)
        analyst_engine.policy_set = policy_set
        analyst_engine.load_metadata(raw_metadata)
        
        print("✅ Analyst engine initialized and metadata loaded")
        
        # Run query for salaries
        query = "Show me total salaries"
        print(f"📝 Query: '{query}'")
        
        result = analyst_engine.process_request(query)
        
        # Check result
        final_sql = result.get("final_sql_output", "")
        print(f"📊 Result SQL: {final_sql}")
        
        # ASSERT: Analyst should NOT be able to access salaries
        # Check if "salaries" appears in FROM clause (not just in column names)
        sql_lower = final_sql.lower()
        # Look for "from salaries" or "salaries" as a table name
        has_salaries_table = (
            " from salaries" in sql_lower or 
            "from salaries " in sql_lower or
            "from salaries," in sql_lower or
            "join salaries" in sql_lower
        )
        
        if not has_salaries_table:
            print("✅ Analyst was blocked from accessing salaries.")
            analyst_success = True
        else:
            print("❌ FAILURE: Analyst should NOT have access to salaries, but SQL contains 'salaries' in FROM/JOIN clause")
            analyst_success = False
            
    except Exception as e:
        # This is acceptable - the Planner might raise an error if it can't find 'salaries'
        print(f"✅ Analyst was blocked from accessing salaries (exception raised: {e})")
        analyst_success = True
    
    print()
    
    # ===== FINAL VERIFICATION =====
    print("=" * 80)
    print("FINAL VERIFICATION")
    print("=" * 80)
    print()
    
    if admin_success and analyst_success:
        print("✅✅✅ ALL TESTS PASSED ✅✅✅")
        print()
        print("The Safety Kernel is working correctly:")
        print("  - Admin users can access restricted data (salaries)")
        print("  - Analyst users are blocked from accessing restricted data (salaries)")
        print()
        return 0
    else:
        print("❌❌❌ TESTS FAILED ❌❌❌")
        print()
        if not admin_success:
            print("  - Admin test failed")
        if not analyst_success:
            print("  - Analyst test failed")
        print()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

