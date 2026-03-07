#!/usr/bin/env python3
"""
DataShark Command Line Interface

Interactive REPL for driving the DataShark Engine with Safety Kernel.
"""

import cmd
import json
import sys
from typing import Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from datashark_mcp.kernel.engine import DataSharkEngine
from datashark_mcp.kernel.types import UserContext
from datashark_mcp.security.policy import PolicyRule, PolicySet


class DataSharkShell(cmd.Cmd):
    """Interactive shell for DataShark Engine."""
    
    intro = "Welcome to DataShark (Safety Kernel Active). Type ? for help."
    prompt = "(shark) "
    
    def __init__(self):
        """Initialize the shell with default context and engine."""
        super().__init__()
        
        # Initialize console (rich if available, else None)
        self.console = Console() if RICH_AVAILABLE else None
        
        # Default context (admin role)
        self.context = UserContext(
            user_id="cli_user",
            roles=["admin"],
            tenant_id="default_tenant"
        )
        
        # Initialize engine
        self.engine: Optional[DataSharkEngine] = None
        
        # Default policy set (allow all for admin)
        self._setup_default_policy()
        
        # Load default dummy snapshot
        self._load_default_snapshot()
    
    def _setup_default_policy(self):
        """Set up default policy set that allows admin to access everything."""
        # Default policy: admin can access everything
        allow_all_rule = PolicyRule(
            resource_pattern=".*",  # Match all resources
            allowed_roles=["admin"],
            action="allow"
        )
        
        self.policy_set = PolicySet(
            rules=[allow_all_rule],
            default_action="deny"
        )
    
    def _load_default_snapshot(self):
        """Load a default dummy snapshot for demonstration."""
        default_metadata = {
            "users": {
                "entity_id": "entity:users",
                "entity_name": "users",
                "columns": ["id", "name", "email"],
                "type": "table",
                "schema": "public"
            },
            "orders": {
                "entity_id": "entity:orders",
                "entity_name": "orders",
                "columns": ["id", "user_id", "amount", "created_at"],
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
                    "columns": ["id", "name", "email"],
                    "type": "table"
                },
                "orders": {
                    "entity_id": "entity:orders",
                    "entity_name": "orders",
                    "columns": ["id", "user_id", "amount", "created_at"],
                    "type": "table"
                },
                "salaries": {
                    "entity_id": "entity:salaries",
                    "entity_name": "salaries",
                    "columns": ["user_id", "amount"],
                    "type": "table"
                }
            },
            "relationships": [
                {
                    "source_entity_id": "users",
                    "target_entity_id": "orders",
                    "join_condition": "users.id = orders.user_id",
                    "confidence_score": 0.9
                },
                {
                    "source_entity_id": "users",
                    "target_entity_id": "salaries",
                    "join_condition": "users.id = salaries.user_id",
                    "confidence_score": 0.95
                }
            ]
        }
        
        try:
            self.engine = DataSharkEngine(context=self.context)
            self.engine.policy_set = self.policy_set
            self.engine.load_metadata(default_metadata)
            self._print("✅ Default snapshot loaded (users, orders, salaries)")
        except Exception as e:
            self._print(f"❌ Failed to load default snapshot: {e}")
            self.engine = None
    
    def _print(self, message: str, style: Optional[str] = None):
        """Print message using rich if available, else standard print."""
        if self.console:
            if style:
                self.console.print(message, style=style)
            else:
                self.console.print(message)
        else:
            print(message)
    
    def do_query(self, arg: str):
        """Execute a natural language query.
        
        Usage: query <natural language question>
        Example: query Show me total sales by user
        """
        if not arg or not arg.strip():
            self._print("❌ Please provide a query. Usage: query <your question>")
            return
        
        if self.engine is None:
            self._print("❌ Engine not initialized. Please load a snapshot first.")
            return
        
        try:
            # Process the request
            result = self.engine.process_request(arg.strip())
            
            # Extract key information
            final_sql = result.get("final_sql_output", "")
            reasoning_steps = result.get("reasoning_steps", [])
            concept_map = result.get("concept_map", {})
            
            # Print results
            self._print("\n" + "=" * 80)
            self._print("QUERY RESULT", style="bold")
            self._print("=" * 80)
            
            # Print SQL
            if final_sql:
                if self.console:
                    sql_syntax = Syntax(final_sql, "sql", theme="monokai", line_numbers=False)
                    self.console.print(Panel(sql_syntax, title="Generated SQL", border_style="green"))
                else:
                    self._print(f"\n📊 Generated SQL:\n{final_sql}")
            
            # Print reasoning steps
            if reasoning_steps:
                self._print("\n📝 Reasoning Steps:")
                for i, step in enumerate(reasoning_steps, 1):
                    self._print(f"  {i}. {step}")
            
            # Print concept map summary
            if concept_map:
                entities = concept_map.get("entities", [])
                metrics = concept_map.get("metrics", [])
                if entities or metrics:
                    self._print("\n🔍 Concept Mapping:")
                    if entities:
                        entity_names = [e.get("entity_name", e.get("term", "")) for e in entities]
                        self._print(f"  Entities: {', '.join(entity_names)}")
                    if metrics:
                        metric_names = [m.get("metric_name", m.get("term", "")) for m in metrics]
                        self._print(f"  Metrics: {', '.join(metric_names)}")
            
            self._print("=" * 80 + "\n")
            
        except Exception as e:
            self._print(f"❌ Error processing query: {e}", style="red")
            if self.console:
                import traceback
                self.console.print_exception()
            else:
                import traceback
                traceback.print_exc()
    
    def do_login(self, arg: str):
        """Switch user context (change role).
        
        Usage: login <role>
        Example: login admin
        Example: login analyst
        
        This will re-initialize the engine with the new context, shifting
        the reality (ProjectedGraph) based on the new role's permissions.
        """
        if not arg or not arg.strip():
            self._print("❌ Please provide a role. Usage: login <role>")
            self._print("   Available roles: admin, analyst")
            return
        
        role = arg.strip().lower()
        
        # Validate role
        valid_roles = ["admin", "analyst"]
        if role not in valid_roles:
            self._print(f"❌ Invalid role: {role}. Available roles: {', '.join(valid_roles)}")
            return
        
        # Update context
        self.context = UserContext(
            user_id=f"cli_user_{role}",
            roles=[role],
            tenant_id="default_tenant"
        )
        
        # Update policy set based on role
        if role == "admin":
            # Admin can access everything
            allow_all_rule = PolicyRule(
                resource_pattern=".*",
                allowed_roles=["admin"],
                action="allow"
            )
            self.policy_set = PolicySet(
                rules=[allow_all_rule],
                default_action="deny"
            )
        elif role == "analyst":
            # Analyst can access users and orders, but NOT salaries
            users_rule = PolicyRule(
                resource_pattern="users",
                allowed_roles=["analyst", "admin"],
                action="allow"
            )
            orders_rule = PolicyRule(
                resource_pattern="orders",
                allowed_roles=["analyst", "admin"],
                action="allow"
            )
            # Explicitly deny salaries for analyst
            salaries_rule = PolicyRule(
                resource_pattern="salaries",
                allowed_roles=["admin"],  # Only admin
                action="allow"
            )
            self.policy_set = PolicySet(
                rules=[users_rule, orders_rule, salaries_rule],
                default_action="deny"
            )
        
        # Re-initialize engine with new context
        if self.engine is None:
            self._load_default_snapshot()
        else:
            # Re-create engine with new context
            old_metadata = self.engine._semantic_graph.raw_data if self.engine._semantic_graph else {}
            self.engine = DataSharkEngine(context=self.context)
            self.engine.policy_set = self.policy_set
            if old_metadata:
                self.engine.load_metadata(old_metadata)
        
        self._print(f"✅ Logged in as {role}. Reality shifted.", style="bold green")
        self._print(f"   Your projected graph now reflects {role} permissions.")
    
    def do_load(self, arg: str):
        """Load metadata from a JSON file.
        
        Usage: load <path_to_json_file>
        Example: load data/snapshot.json
        """
        if not arg or not arg.strip():
            self._print("❌ Please provide a file path. Usage: load <path_to_json_file>")
            return
        
        file_path = arg.strip()
        
        try:
            with open(file_path, 'r') as f:
                metadata = json.load(f)
            
            # Re-initialize engine
            self.engine = DataSharkEngine(context=self.context)
            self.engine.policy_set = self.policy_set
            self.engine.load_metadata(metadata)
            
            self._print(f"✅ Loaded metadata from {file_path}")
            
        except FileNotFoundError:
            self._print(f"❌ File not found: {file_path}")
        except json.JSONDecodeError as e:
            self._print(f"❌ Invalid JSON: {e}")
        except Exception as e:
            self._print(f"❌ Error loading metadata: {e}")
    
    def do_status(self, arg: str):
        """Show current status (user, role, snapshot).
        
        Usage: status
        """
        if self.engine is None:
            self._print("❌ Engine not initialized.")
            return
        
        self._print("\n" + "=" * 80)
        self._print("CURRENT STATUS", style="bold")
        self._print("=" * 80)
        self._print(f"User ID: {self.context.user_id}")
        self._print(f"Roles: {', '.join(self.context.roles)}")
        self._print(f"Tenant: {self.context.tenant_id}")
        
        if self.engine._snapshot_id:
            self._print(f"Snapshot ID: {self.engine._snapshot_id.id[:16]}...")
        
        # Show accessible entities (need to get API client first)
        try:
            api_client = self.engine.get_api_client()
            entities = api_client.get_all_entities()
            entity_names = [e.get("entity_name", e.get("entity_id", "")) for e in entities]
            self._print(f"Accessible Entities: {', '.join(entity_names) if entity_names else 'None'}")
        except Exception as e:
            self._print(f"Accessible Entities: Unable to determine ({e})")
        
        self._print("=" * 80 + "\n")
    
    def do_quit(self, arg: str):
        """Exit the shell.
        
        Usage: quit
        """
        self._print("👋 Goodbye!")
        return True
    
    def do_exit(self, arg: str):
        """Exit the shell (alias for quit).
        
        Usage: exit
        """
        return self.do_quit(arg)
    
    def do_EOF(self, arg: str):
        """Handle EOF (Ctrl+D)."""
        self._print("\n👋 Goodbye!")
        return True
    
    def default(self, line: str):
        """Handle unknown commands."""
        self._print(f"❌ Unknown command: {line}")
        self._print("   Type ? for help")


def main():
    """Main entry point for the CLI."""
    try:
        shell = DataSharkShell()
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
