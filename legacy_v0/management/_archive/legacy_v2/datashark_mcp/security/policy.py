"""Policy Rules Engine.

This module defines the policy rule system for access control, including
PolicyRule (individual rules) and PolicySet (collections of rules with defaults).
"""

from typing import List

from pydantic import BaseModel


class PolicyRule(BaseModel):
    """Immutable policy rule defining access control for a resource.
    
    A PolicyRule specifies:
    - Which resource pattern it applies to (e.g., "schema.table" or regex)
    - Which roles are allowed to access it
    - What action to take (allow or deny)
    
    Attributes:
        resource_pattern: String pattern matching resources (exact match or regex)
        allowed_roles: List of role identifiers that are permitted access
        action: Action to take ("allow" or "deny")
    """
    
    model_config = {"frozen": True}
    
    resource_pattern: str
    allowed_roles: List[str]
    action: str  # "allow" or "deny"


class PolicySet(BaseModel):
    """Immutable collection of policy rules with default action.
    
    A PolicySet contains multiple PolicyRules and a default action that
    applies when no rule matches a resource. The default follows the
    principle of least privilege (default="deny").
    
    Attributes:
        rules: List of PolicyRule instances to evaluate
        default_action: Default action when no rule matches ("allow" or "deny")
    """
    
    model_config = {"frozen": True}
    
    rules: List[PolicyRule]
    default_action: str = "deny"  # Principle of least privilege

