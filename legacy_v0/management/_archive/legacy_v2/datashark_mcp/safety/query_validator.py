"""
Query Safety Validator

SQL parser-based query validation.
More robust than regex blacklist - catches injection attacks.
"""

import logging
from typing import List, Tuple
import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Keyword, DML

logger = logging.getLogger(__name__)


class QueryValidator:
    """
    SQL parser-based query validation.
    
    More robust than regex blacklist.
    
    Blocks:
    - DELETE, DROP, TRUNCATE, ALTER, CREATE, INSERT, UPDATE
    - Multiple statements (SQL injection)
    - Non-SELECT queries
    
    Allows:
    - SELECT, EXPLAIN, SHOW, DESCRIBE, WITH
    """
    
    ALLOWED_TYPES = {'SELECT', 'EXPLAIN', 'SHOW', 'DESCRIBE', 'WITH'}
    DANGEROUS_KEYWORDS = {
        'DELETE', 'DROP', 'TRUNCATE', 'ALTER',
        'CREATE', 'INSERT', 'UPDATE', 'GRANT', 'REVOKE'
    }
    
    def __init__(self):
        """Initialize query validator"""
        logger.info("QueryValidator initialized")
    
    def validate(self, sql: str, allow_batch: bool = False) -> Tuple[bool, str]:
        """
        Validate query is safe to execute.
        
        Args:
            sql: SQL query to validate
            allow_batch: If True, allows multiple statements
        
        Returns:
            (is_safe: bool, message: str)
        
        Examples:
            >>> validator.validate("SELECT * FROM users")
            (True, "OK")
            
            >>> validator.validate("DELETE FROM users")
            (False, "Query type 'DELETE' not allowed...")
            
            >>> validator.validate("SELECT * FROM x; DROP TABLE y")
            (False, "Multiple statements detected...")
        """
        try:
            # Parse SQL
            statements = sqlparse.parse(sql)
            
            if not statements:
                return False, "Empty query"
            
            if len(statements) > 1 and not allow_batch:
                return False, "Multiple statements not allowed. Use execute_batch for multi-statement scripts."
            
            # Validate each statement
            for stmt in statements:
                # Check statement type
                stmt_type = self._get_statement_type(stmt)
                
                if stmt_type not in self.ALLOWED_TYPES:
                    return False, f"Query type '{stmt_type}' not allowed. Only SELECT queries permitted."
                
                # Check for dangerous keywords in any part of query
                if self._contains_dangerous_keywords(stmt):
                    return False, "Query contains dangerous keywords (DELETE, DROP, etc.)"
            
            logger.debug(f"Query validated: {len(statements)} statement(s)")
            return True, "OK"
            
        except Exception as e:
            logger.error(f"SQL parsing error: {e}")
            return False, f"SQL parsing error: {str(e)}"
    
    def split_statements(self, sql: str) -> List[str]:
        """
        Split a multi-statement SQL script into individual statements.
        
        Args:
            sql: SQL script with potentially multiple statements
        
        Returns:
            List of individual SQL statements
        """
        statements = sqlparse.parse(sql)
        return [str(stmt).strip() for stmt in statements if str(stmt).strip()]
    
    def _get_statement_type(self, stmt: Statement) -> str:
        """
        Extract statement type (SELECT, DELETE, etc.)
        
        Args:
            stmt: Parsed SQL statement
        
        Returns:
            Statement type string
        """
        for token in stmt.tokens:
            if token.ttype is Keyword.DML:
                return token.value.upper()
            if token.ttype is Keyword and token.value.upper() in self.ALLOWED_TYPES:
                return token.value.upper()
        return 'UNKNOWN'
    
    def _contains_dangerous_keywords(self, stmt: Statement) -> bool:
        """
        Check if statement contains any dangerous keywords.
        
        Args:
            stmt: Parsed SQL statement
        
        Returns:
            True if dangerous keywords found
        """
        sql_upper = str(stmt).upper()
        return any(keyword in sql_upper for keyword in self.DANGEROUS_KEYWORDS)

