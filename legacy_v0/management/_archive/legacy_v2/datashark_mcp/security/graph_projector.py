"""Graph Projector - Physical Removal Logic.

This module implements the Air-Gap security mechanism by physically removing
nodes/edges from the semantic graph based on policy rules and user context.

The GraphProjector creates a ProjectedGraph that contains only the resources
the user is permitted to access, ensuring untrusted components never see
restricted data.
"""

import copy
import re
from typing import Dict, Any

from datashark_mcp.kernel.exceptions import GovernanceViolationError
from datashark_mcp.kernel.types import ProjectedGraph, SemanticGraph, UserContext
from datashark_mcp.security.policy import PolicyRule, PolicySet


class GraphProjector:
    """The Graph Projector - Enforces policy by physically removing nodes/edges.
    
    This class implements the Air-Gap security pattern by creating a filtered
    view of the semantic graph. Resources that the user is not permitted to
    access are physically removed from the projected view.
    
    The projector:
    1. Evaluates each resource against policy rules
    2. Checks user context roles against allowed roles
    3. Creates a deep copy of permitted resources only
    4. Returns an immutable ProjectedGraph
    
    Invariant: The returned ProjectedGraph must NOT share references with
    the original SemanticGraph data (deep copy enforced).
    """
    
    @staticmethod
    def project_graph(
        graph: SemanticGraph,
        context: UserContext,
        policy: PolicySet
    ) -> ProjectedGraph:
        """Project a semantic graph based on user context and policy rules.
        
        This method creates a filtered view of the semantic graph by:
        1. Accessing the graph's internal _raw_data
        2. Evaluating each resource against policy rules
        3. Checking if user roles match allowed roles
        4. Creating a deep copy of permitted resources
        5. Returning an immutable ProjectedGraph
        
        Args:
            graph: The complete SemanticGraph to be filtered
            context: UserContext containing user identity and roles
            policy: PolicySet containing rules and default action
        
        Returns:
            ProjectedGraph: Immutable filtered view containing only permitted resources
        
        Raises:
            GovernanceViolationError: If projection fails due to invalid data structure
        
        Example:
            >>> graph = SemanticGraph(_raw_data={"entities": {...}, "relationships": {...}})
            >>> context = UserContext(user_id="user1", roles=["analyst"], tenant_id="acme")
            >>> policy = PolicySet(rules=[...], default_action="deny")
            >>> projected = GraphProjector.project_graph(graph, context, policy)
        """
        try:
            # Step 1: Access graph.raw_data (or _raw_data for backward compatibility)
            raw_data = getattr(graph, 'raw_data', None) or getattr(graph, '_raw_data', {})
            
            # Step 2: Create a new dictionary for filtered_data
            # This will be a deep copy to ensure no shared references
            filtered_data: Dict[str, Any] = {}
            
            # Step 3: Iterate through keys/items in _raw_data
            # We'll process the graph structure based on common semantic graph patterns
            # Structural keys (like "entities", "relationships") are allowed to pass through
            # and only their contents are filtered
            STRUCTURAL_KEYS = {"entities", "relationships", "nodes", "edges", "metadata"}
            
            for key, value in raw_data.items():
                # Structural keys are always allowed - they're containers, not resources
                is_structural = key in STRUCTURAL_KEYS
                
                if isinstance(value, dict):
                    if is_structural:
                        # Structural key - filter contents but allow the key itself
                        filtered_value = GraphProjector._filter_dict_resource(
                            value, context, policy
                        )
                        # Include structural key even if empty (for consistency)
                        filtered_data[key] = filtered_value
                    else:
                        # Regular resource key - check if allowed
                        if GraphProjector._is_resource_allowed(key, context, policy):
                            filtered_value = GraphProjector._filter_dict_resource(
                                value, context, policy
                            )
                            if filtered_value:
                                filtered_data[key] = filtered_value
                elif isinstance(value, list):
                    if is_structural:
                        # Structural key - filter contents but allow the key itself
                        filtered_value = GraphProjector._filter_list_resource(
                            value, context, policy
                        )
                        filtered_data[key] = filtered_value
                    else:
                        # Regular resource key - check if allowed
                        if GraphProjector._is_resource_allowed(key, context, policy):
                            filtered_value = GraphProjector._filter_list_resource(
                                value, context, policy
                            )
                            if filtered_value:
                                filtered_data[key] = filtered_value
                else:
                    # Primitive value - check if key is allowed (unless structural)
                    if is_structural or GraphProjector._is_resource_allowed(key, context, policy):
                        filtered_data[key] = copy.deepcopy(value)
            
            # Step 5: Return ProjectedGraph initialized with filtered_data
            # Use model_construct to bypass validation and directly set the field
            # This is necessary because raw_data has exclude=True which affects __init__
            return ProjectedGraph.model_construct(raw_data=filtered_data)
            
        except Exception as e:
            raise GovernanceViolationError(
                f"Graph projection failed: {str(e)}. "
                f"Type: {type(e).__name__}"
            ) from e
    
    @staticmethod
    def _is_resource_allowed(
        resource_path: str,
        context: UserContext,
        policy: PolicySet
    ) -> bool:
        """Check if a resource is allowed based on policy and user context.
        
        Args:
            resource_path: String identifier/path for the resource
            context: UserContext with user roles
            policy: PolicySet containing rules
        
        Returns:
            bool: True if resource is allowed, False if denied
        """
        # Check each rule in order (first match wins)
        for rule in policy.rules:
            if GraphProjector._matches_pattern(resource_path, rule.resource_pattern):
                # Rule matches - check if user has allowed role
                if any(role in rule.allowed_roles for role in context.roles):
                    # User has allowed role - apply rule action
                    return rule.action == "allow"
                # User doesn't have allowed role - deny
                return False
        
        # No rule matched - apply default action
        return policy.default_action == "allow"
    
    @staticmethod
    def _matches_pattern(resource_path: str, pattern: str) -> bool:
        """Check if resource_path matches the pattern.
        
        Supports both exact match and regex patterns.
        
        Args:
            resource_path: Resource identifier to match
            pattern: Pattern string (exact or regex)
        
        Returns:
            bool: True if pattern matches
        """
        # Try exact match first
        if resource_path == pattern:
            return True
        
        # Try regex match (if pattern contains regex special chars)
        try:
            if re.search(r'[.*+?^${}|()\[\]\\]', pattern):
                # Pattern contains regex special characters - treat as regex
                return bool(re.match(pattern, resource_path))
        except re.error:
            # Invalid regex - fall back to exact match
            pass
        
        # Fall back to exact match
        return resource_path == pattern
    
    @staticmethod
    def _filter_dict_resource(
        resource_dict: Dict[str, Any],
        context: UserContext,
        policy: PolicySet
    ) -> Dict[str, Any]:
        """Filter a dictionary resource recursively.
        
        Args:
            resource_dict: Dictionary to filter
            context: UserContext with roles
            policy: PolicySet with rules
        
        Returns:
            Dict: Deep copy of filtered dictionary
        """
        filtered = {}
        for key, value in resource_dict.items():
            # Use the key as the resource identifier for policy checking
            resource_path = key
            
            # Check if this key is allowed by policy
            if not GraphProjector._is_resource_allowed(resource_path, context, policy):
                # Key is not allowed - skip it entirely
                continue
            
            # Key is allowed - include its value (deep copy, no recursive filtering)
            # If a resource is allowed, we include its entire value structure
            # without further filtering (the resource itself is the unit of access control)
            filtered[key] = copy.deepcopy(value)
        
        return filtered
    
    @staticmethod
    def _filter_list_resource(
        resource_list: list,
        context: UserContext,
        policy: PolicySet
    ) -> list:
        """Filter a list resource.
        
        Args:
            resource_list: List to filter
            context: UserContext with roles
            policy: PolicySet with rules
        
        Returns:
            list: Deep copy of filtered list
        """
        filtered = []
        for item in resource_list:
            # For list items, we need to extract a resource identifier
            # Common patterns: dict with 'id' or 'name' field, or string items
            if isinstance(item, dict):
                # Try to extract resource identifier
                resource_id = item.get('id') or item.get('name') or item.get('resource', '')
                if GraphProjector._is_resource_allowed(str(resource_id), context, policy):
                    filtered.append(copy.deepcopy(item))
            elif isinstance(item, str):
                # String item - use as resource identifier
                if GraphProjector._is_resource_allowed(item, context, policy):
                    filtered.append(copy.deepcopy(item))
            else:
                # Other types - include if we can't determine resource
                # (conservative: include if uncertain)
                filtered.append(copy.deepcopy(item))
        
        return filtered

