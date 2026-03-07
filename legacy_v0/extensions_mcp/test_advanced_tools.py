#!/usr/bin/env python3
"""
Test Advanced Tools (Day 11-12)
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from datashark.core.server import DataSharkMCPServer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_advanced_tools():
    """Test all advanced tools"""
    logger.info("Testing Advanced Tools (Day 11-12)")
    
    # Initialize server
    server = DataSharkMCPServer()
    await server.initialize()
    
    try:
        # Test 1: Schema Statistics (all schemas)
        logger.info("\n=== Test: get_schema_statistics (all) ===")
        result = await server.call_tool('get_schema_statistics', {})
        logger.info(f"Total schemas: {result.get('total_schemas')}")
        logger.info(f"Total tables: {result.get('total_tables')}")
        logger.info(f"Total size: {result.get('total_size_mb')} MB")
        logger.info(f"Top 5 schemas: {result['schemas'][:5]}")
        
        # Test 2: Schema Statistics (single schema)
        logger.info("\n=== Test: get_schema_statistics (scratch) ===")
        result = await server.call_tool('get_schema_statistics', {'schema': 'scratch'})
        logger.info(f"Scratch schema: {result.get('table_count')} tables")
        logger.info(f"Total size: {result.get('total_size_mb')} MB")
        logger.info(f"Avg columns: {result.get('avg_columns_per_table')}")
        
        # Test 3: Large Tables
        logger.info("\n=== Test: get_large_tables ===")
        result = await server.call_tool('get_large_tables', {'limit': 10})
        logger.info(f"Analyzed {result.get('total_tables_analyzed')} tables")
        logger.info(f"Top 10 largest:")
        for i, table in enumerate(result['tables'][:10], 1):
            logger.info(f"  {i}. {table['schema']}.{table['table']}: {table['size_mb']} MB")
        
        # Test 4: Table Sample
        logger.info("\n=== Test: get_table_sample ===")
        # Get first table from scratch schema
        schemas_result = await server.call_tool('list_schemas', {})
        scratch_tables = await server.call_tool('search_tables', {'schema': 'scratch', 'pattern': '*'})
        
        if scratch_tables.get('count', 0) > 0:
            first_table = scratch_tables['tables'][0]['name']
            result = await server.call_tool('get_table_sample', {
                'schema': 'scratch',
                'table': first_table,
                'limit': 3
            })
            logger.info(f"Sample from scratch.{first_table}:")
            logger.info(f"  Columns: {result.get('columns', [])}")
            logger.info(f"  Rows returned: {result.get('row_count')}")
        else:
            logger.info("No tables in scratch schema to sample")
        
        # Test 5: Query Performance Analysis
        logger.info("\n=== Test: analyze_query_performance ===")
        result = await server.call_tool('analyze_query_performance', {})
        logger.info(f"Total queries: {result.get('total_queries')}")
        logger.info(f"Error rate: {result.get('error_rate')}%")
        logger.info(f"Avg duration: {result.get('avg_duration_ms')} ms")
        
        # Test 6: Search Table by Content
        logger.info("\n=== Test: search_table_by_content ===")
        result = await server.call_tool('search_table_by_content', {'search_term': 'user'})
        logger.info(f"Found {result.get('match_count')} tables matching 'user'")
        if result.get('match_count', 0) > 0:
            logger.info(f"Sample matches: {result['matches'][:3]}")
        
        logger.info("\n✅ All advanced tools tests passed!")
        
    finally:
        server.cleanup()


if __name__ == "__main__":
    asyncio.run(test_advanced_tools())


