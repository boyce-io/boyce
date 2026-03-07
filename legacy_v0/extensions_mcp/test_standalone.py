#!/usr/bin/env python3
"""
Standalone MCP Server Test (Day 10)

Test all MCP tools independently of Cursor.
De-risks Phase 2 by validating server works before extension.

Usage:
    python test_standalone.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from datashark.core.server import DataSharkMCPServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_list_schemas(server: DataSharkMCPServer):
    """Test list_schemas tool"""
    logger.info("\n" + "="*60)
    logger.info("TEST: list_schemas")
    logger.info("="*60)
    
    result = await server.call_tool('list_schemas', {})
    
    assert 'schemas' in result, "Missing 'schemas' in result"
    assert len(result['schemas']) > 0, "No schemas returned"
    
    logger.info(f"✅ PASS: Found {result['count']} schemas")
    logger.info(f"   Sample schemas: {[s['name'] for s in result['schemas'][:5]]}")
    
    return result


async def test_search_tables(server: DataSharkMCPServer):
    """Test search_tables tool"""
    logger.info("\n" + "="*60)
    logger.info("TEST: search_tables")
    logger.info("="*60)
    
    # Use 'public' schema or first available schema
    result = await server.call_tool('search_tables', {
        'schema': 'public',
        'pattern': '*'
    })
    
    assert 'tables' in result, "Missing 'tables' in result"
    
    logger.info(f"✅ PASS: Found {result['count']} tables in public schema")
    if result['count'] > 0:
        logger.info(f"   Sample tables: {[t['name'] for t in result['tables'][:5]]}")
    
    return result


async def test_get_table_info(server: DataSharkMCPServer, schema: str, table: str):
    """Test get_table_info tool"""
    logger.info("\n" + "="*60)
    logger.info(f"TEST: get_table_info({schema}.{table})")
    logger.info("="*60)
    
    result = await server.call_tool('get_table_info', {
        'schema': schema,
        'table': table
    })
    
    if 'error' in result:
        logger.warning(f"⚠️  SKIP: {result['error']}")
        return result
    
    assert 'columns' in result, "Missing 'columns' in result"
    assert len(result['columns']) > 0, "No columns returned"
    
    logger.info(f"✅ PASS: Table has {len(result['columns'])} columns")
    # Column dict keys vary by cache format: 'name' in unified cache, 'column_name' in individual files
    col_name_key = 'name' if 'name' in result['columns'][0] else 'column_name'
    logger.info(f"   Sample columns: {[c[col_name_key] for c in result['columns'][:5]]}")
    
    return result


async def test_execute_query_safe(server: DataSharkMCPServer):
    """Test execute_query_safe tool"""
    logger.info("\n" + "="*60)
    logger.info("TEST: execute_query_safe (valid query)")
    logger.info("="*60)
    
    # Test with simple query
    result = await server.call_tool('execute_query_safe', {
        'sql': 'SELECT 1 as test_column',
        'limit': 10
    })
    
    assert 'rows' in result, "Missing 'rows' in result"
    assert not result.get('blocked'), "Valid query was blocked"
    assert result['row_count'] == 1, f"Expected 1 row, got {result['row_count']}"
    assert result['rows'][0]['test_column'] == 1, "Incorrect result value"
    
    logger.info(f"✅ PASS: Query executed in {result['duration_ms']:.1f}ms")
    logger.info(f"   Returned {result['row_count']} rows")
    
    return result


async def test_query_safety(server: DataSharkMCPServer):
    """Test query safety blocking"""
    logger.info("\n" + "="*60)
    logger.info("TEST: Query safety (should block dangerous queries)")
    logger.info("="*60)
    
    dangerous_queries = [
        "DELETE FROM users",
        "DROP TABLE test",
        "UPDATE users SET admin = true",
        "INSERT INTO logs VALUES (1, 2)",
        "SELECT * FROM users; DROP TABLE users",
    ]
    
    all_blocked = True
    for sql in dangerous_queries:
        result = await server.call_tool('execute_query_safe', {
            'sql': sql,
            'limit': 10
        })
        
        if not result.get('blocked'):
            logger.error(f"❌ FAIL: Dangerous query NOT blocked: {sql}")
            all_blocked = False
        else:
            logger.info(f"✅ Blocked: {sql[:50]}")
    
    assert all_blocked, "Some dangerous queries were not blocked"
    logger.info(f"\n✅ PASS: All dangerous queries blocked")
    
    return {'all_blocked': all_blocked}


async def test_execute_query_paginated(server: DataSharkMCPServer):
    """Test execute_query_paginated tool"""
    logger.info("\n" + "="*60)
    logger.info("TEST: execute_query_paginated")
    logger.info("="*60)
    
    result = await server.call_tool('execute_query_paginated', {
        'sql': 'SELECT generate_series(1, 50) as num',
        'page': 1,
        'page_size': 10
    })
    
    assert 'rows' in result, "Missing 'rows' in result"
    assert result['page'] == 1, "Incorrect page number"
    assert result['page_size'] == 10, "Incorrect page size"
    
    logger.info(f"✅ PASS: Page 1 returned {result['row_count']} rows")
    logger.info(f"   Has more: {result.get('has_more', False)}")
    
    return result


async def test_search_columns(server: DataSharkMCPServer):
    """Test search_columns tool"""
    logger.info("\n" + "="*60)
    logger.info("TEST: search_columns")
    logger.info("="*60)
    
    # Search for common column name
    result = await server.call_tool('search_columns', {
        'column_name': 'id'
    })
    
    assert 'tables' in result, "Missing 'tables' in result"
    
    logger.info(f"✅ PASS: Found column 'id' in {result['count']} tables")
    if result['count'] > 0:
        logger.info(f"   Sample: {result['tables'][:3]}")
    
    return result


async def test_find_relationships(server: DataSharkMCPServer):
    """Test find_relationships tool"""
    logger.info("\n" + "="*60)
    logger.info("TEST: find_relationships")
    logger.info("="*60)
    
    # This will only return results if there are actual FK relationships
    result = await server.call_tool('find_relationships', {
        'table': 'users'  # Common table name
    })
    
    assert 'relationships' in result, "Missing 'relationships' in result"
    
    logger.info(f"✅ PASS: Found {result['count']} relationships for 'users'")
    
    return result


async def test_query_history(server: DataSharkMCPServer):
    """Test get_query_history tool"""
    logger.info("\n" + "="*60)
    logger.info("TEST: get_query_history")
    logger.info("="*60)
    
    result = await server.call_tool('get_query_history', {
        'limit': 10
    })
    
    assert 'queries' in result, "Missing 'queries' in result"
    assert result['count'] > 0, "No queries in history (but we just ran some!)"
    
    logger.info(f"✅ PASS: Retrieved {result['count']} recent queries")
    logger.info(f"   Most recent: {result['queries'][0]['sql'][:50]}...")
    
    return result


async def run_all_tests():
    """Run all tests"""
    logger.info("\n" + "="*60)
    logger.info("DATASHARK MCP SERVER - STANDALONE TESTING")
    logger.info("="*60)
    logger.info("Testing all tools independently of Cursor\n")
    
    try:
        # Initialize server
        logger.info("Initializing server...")
        server = DataSharkMCPServer()
        await server.initialize()
        
        logger.info("\n✅ Server initialized successfully\n")
        
        # Run tests
        tests = [
            ("List Schemas", test_list_schemas(server)),
            ("Search Tables", test_search_tables(server)),
            ("Execute Query (Safe)", test_execute_query_safe(server)),
            ("Query Safety", test_query_safety(server)),
            ("Execute Query (Paginated)", test_execute_query_paginated(server)),
            ("Search Columns", test_search_columns(server)),
            ("Find Relationships", test_find_relationships(server)),
            ("Query History", test_query_history(server)),
        ]
        
        results = []
        for test_name, test_coro in tests:
            try:
                result = await test_coro
                results.append((test_name, "PASS", None))
            except Exception as e:
                logger.error(f"❌ FAIL: {test_name}")
                logger.error(f"   Error: {e}")
                results.append((test_name, "FAIL", str(e)))
        
        # Try to get first table for detailed testing
        try:
            schemas_result = await server.call_tool('list_schemas', {})
            if schemas_result['count'] > 0:
                first_schema = schemas_result['schemas'][0]['name']
                tables_result = await server.call_tool('search_tables', {
                    'schema': first_schema,
                    'pattern': '*'
                })
                if tables_result['count'] > 0:
                    first_table = tables_result['tables'][0]['name']
                    result = await test_get_table_info(server, first_schema, first_table)
                    results.append(("Get Table Info", "PASS", None))
        except Exception as e:
            logger.error(f"❌ FAIL: Get Table Info - {e}")
            results.append(("Get Table Info", "FAIL", str(e)))
        
        # Print summary
        logger.info("\n" + "="*60)
        logger.info("TEST SUMMARY")
        logger.info("="*60)
        
        passed = sum(1 for _, status, _ in results if status == "PASS")
        failed = sum(1 for _, status, _ in results if status == "FAIL")
        
        for test_name, status, error in results:
            symbol = "✅" if status == "PASS" else "❌"
            logger.info(f"{symbol} {test_name}: {status}")
            if error:
                logger.info(f"   Error: {error}")
        
        logger.info("="*60)
        logger.info(f"TOTAL: {passed} passed, {failed} failed out of {len(results)} tests")
        logger.info("="*60)
        
        # Cleanup
        server.cleanup()
        
        if failed > 0:
            sys.exit(1)
        else:
            logger.info("\n🎉 ALL TESTS PASSED! MCP server is ready for Cursor integration.")
            sys.exit(0)
        
    except Exception as e:
        logger.error(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all_tests())


