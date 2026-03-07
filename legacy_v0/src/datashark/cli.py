#!/usr/bin/env python3
"""
DataShark CLI - Model Agnostic Command Line Interface

Professional CLI for DataShark using Typer and Rich.
Supports Model Agnostic architecture via LiteLLM.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

try:
    import litellm
except ImportError:
    litellm = None

# Add src to path for imports
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from datashark.core.api import process_request
from datashark.core.graph import SemanticGraph
from datashark.core.parsers import detect_source_type, parse_dbt_manifest, parse_dbt_project_source, parse_lookml_file
from datashark.core.types import SemanticSnapshot
from datashark.core.validation import validate_snapshot
from datashark.runtime.planner.planner import QueryPlanner

# Initialize Rich console
console = Console()

# Typer app
app = typer.Typer(
    name="datashark",
    help="DataShark CLI - Model Agnostic Semantic SQL Generator",
    add_completion=False,
)

# Config directory (hidden in project root)
CONFIG_DIR_NAME = ".datashark"
CONFIG_FILE_NAME = "config.json"


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context, 
    server: bool = typer.Option(False, "--server", help="[DEPRECATED] Use 'serve' command instead.")
):
    """
    DataShark CLI Gateway.
    
    Use 'serve' to run in Headless Mode for VS Code / DBeaver integration.
    """
    if server:
        console.print("[yellow]Warning: --server is deprecated. Please use 'datashark serve' instead.[/yellow]")
        # Import server here to avoid loading heavy deps if not needed
        try:
            from datashark.core.server import DataSharkServer
            # Run server and exit
            DataSharkServer().run()
            raise typer.Exit()
        except Exception as e:
            console.print(f"[red]Server Error: {e}[/red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            raise typer.Exit(code=1)


@app.command()
def serve() -> None:
    """
    Start the DataShark JSON-RPC Server (Standard I/O).
    
    This command is used by the DBeaver plugin to communicate with the
    DataShark core. It reads JSON-RPC 2.0 requests from stdin and
    writes responses to stdout.
    """
    try:
        from datashark.core.server import DataSharkServer
        server = DataSharkServer()
        server.run()
    except Exception as e:
        # Log to stderr so we don't corrupt stdout JSON stream
        sys.stderr.write(f"Server Fatal Error: {e}\n")
        import traceback
        sys.stderr.write(traceback.format_exc())
        sys.exit(1)


def get_project_root() -> Path:
    """Detect project root by looking for .git, dbt_project.yml, or .lkml files."""
    current = Path.cwd()
    
    # Walk up from current directory
    check = current
    while check != check.parent:
        # Check for repository markers
        if (check / ".git").exists():
            return check
        # Check for dbt project
        if (check / "dbt_project.yml").exists():
            return check
        # Check for LookML files
        if list(check.glob("*.lkml")):
            return check
        check = check.parent
    
    # Fallback to current directory
    return current


def get_config_dir(project_root: Optional[Path] = None) -> Path:
    """Get the .datashark config directory path."""
    if project_root is None:
        project_root = get_project_root()
    return project_root / CONFIG_DIR_NAME


def get_config_file(project_root: Optional[Path] = None) -> Path:
    """Get the config.json file path."""
    return get_config_dir(project_root) / CONFIG_FILE_NAME


def load_config() -> dict:
    """Load configuration from .datashark/config.json."""
    config_file = get_config_file()
    
    if not config_file.exists():
        return {
            "provider": None,
            "model": None,
            "api_key": None,
            "offline": False,
        }
    
    try:
        with open(config_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        return {
            "provider": None,
            "model": None,
            "api_key": None,
            "offline": False,
        }


def save_config(config: dict) -> None:
    """Save configuration to .datashark/config.json."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    
    config_file = get_config_file()
    
    # Don't save API key in plain text if it's None
    config_to_save = config.copy()
    if config_to_save.get("api_key") is None:
        # Try to preserve existing API key if not being changed
        existing = load_config()
        if existing.get("api_key"):
            config_to_save["api_key"] = existing["api_key"]
    
    with open(config_file, "w") as f:
        json.dump(config_to_save, f, indent=2)
    
    # Set restrictive permissions on config file (owner read/write only)
    os.chmod(config_file, 0o600)


@app.command()
def init(
    project_root: Optional[Path] = typer.Option(None, "--root", "-r", help="Project root directory (auto-detected if not specified)"),
) -> None:
    """
    Initialize DataShark in the current project.
    
    Scans the directory for dbt_project.yml or *.lkml files and creates
    a hidden .datashark/ config folder.
    """
    console.print(Panel.fit("[bold blue]DataShark Initialization[/bold blue]", border_style="blue"))
    
    # Detect project root
    if project_root is None:
        project_root = get_project_root()
    else:
        project_root = project_root.resolve()
    
    console.print(f"[dim]Project root: {project_root}[/dim]")
    
    # Scan for source files
    dbt_project = project_root / "dbt_project.yml"
    lookml_files = list(project_root.glob("*.lkml"))
    manifest_file = None
    
    # Check for dbt manifest.json in common locations
    for manifest_path in [
        project_root / "target" / "manifest.json",
        project_root / "dbt" / "target" / "manifest.json",
    ]:
        if manifest_path.exists():
            manifest_file = manifest_path
            break
    
    detected_sources = []
    
    if dbt_project.exists():
        detected_sources.append(("dbt", str(dbt_project)))
    if manifest_file:
        detected_sources.append(("dbt manifest", str(manifest_file)))
    if lookml_files:
        detected_sources.append(("LookML", f"{len(lookml_files)} files"))
    
    # Create config directory
    config_dir = get_config_dir(project_root)
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize default config if it doesn't exist
    config_file = get_config_file(project_root)
    if not config_file.exists():
        default_config = {
            "provider": None,
            "model": None,
            "api_key": None,
            "offline": False,
            "project_root": str(project_root),
        }
        save_config(default_config)
        console.print(f"[green]✓[/green] Created config directory: {config_dir}")
    else:
        console.print(f"[yellow]⚠[/yellow] Config already exists: {config_file}")
    
    # Display detected sources
    if detected_sources:
        table = Table(title="Detected Sources", show_header=True, header_style="bold magenta")
        table.add_column("Type", style="cyan")
        table.add_column("Location", style="green")
        
        for source_type, location in detected_sources:
            table.add_row(source_type, location)
        
        console.print("\n")
        console.print(table)
    else:
        console.print("\n[yellow]⚠[/yellow] No dbt or LookML sources detected in project root.")
        console.print("[dim]You can still use DataShark by manually ingesting sources.[/dim]")
    
    console.print(f"\n[green]✓[/green] DataShark initialized in [bold]{project_root}[/bold]")


@app.command()
def config(
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="LLM provider (openai, anthropic, ollama, etc.)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name (e.g., gpt-4, claude-3-opus, llama3)"),
    api_key: Optional[str] = typer.Option(None, "--api-key", "-k", help="API key (or set via environment variable)"),
    offline: bool = typer.Option(False, "--offline", help="Disable LLM calls entirely (offline mode)"),
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
) -> None:
    """
    Configure DataShark's LLM provider and model settings.
    
    Supports Model Agnostic architecture via LiteLLM.
    Use --offline to disable LLM calls entirely.
    """
    if show:
        # Display current config
        config_data = load_config()
        
        table = Table(title="DataShark Configuration", show_header=True, header_style="bold magenta")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")
        
        provider_display = config_data.get("provider") or "[dim]Not set[/dim]"
        model_display = config_data.get("model") or "[dim]Not set[/dim]"
        api_key_display = "[dim]***[/dim]" if config_data.get("api_key") else "[dim]Not set[/dim]"
        offline_display = "[green]Yes[/green]" if config_data.get("offline") else "[red]No[/red]"
        
        table.add_row("Provider", provider_display)
        table.add_row("Model", model_display)
        table.add_row("API Key", api_key_display)
        table.add_row("Offline Mode", offline_display)
        
        console.print("\n")
        console.print(table)
        return
    
    # Load existing config
    config_data = load_config()
    
    # Update config with provided values
    if provider is not None:
        config_data["provider"] = provider
    if model is not None:
        config_data["model"] = model
    if api_key is not None:
        config_data["api_key"] = api_key
    elif api_key is None and not config_data.get("api_key"):
        # Try to get from environment
        env_key = os.environ.get("LITELLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if env_key:
            config_data["api_key"] = env_key
            console.print("[dim]Using API key from environment variable[/dim]")
    
    if offline:
        config_data["offline"] = True
        console.print("[yellow]⚠[/yellow] Offline mode enabled. LLM calls will be disabled.")
    
    # Prompt for missing required values (if not offline)
    if not config_data.get("offline"):
        if not config_data.get("provider"):
            config_data["provider"] = Prompt.ask(
                "LLM Provider",
                choices=["openai", "anthropic", "ollama", "azure", "google"],
                default="openai",
            )
        
        if not config_data.get("model"):
            # Suggest model based on provider
            provider = config_data.get("provider", "openai")
            default_models = {
                "openai": "gpt-4",
                "anthropic": "claude-3-opus",
                "ollama": "llama3",
                "azure": "gpt-4",
                "google": "gemini-pro",
            }
            default_model = default_models.get(provider, "gpt-4")
            
            config_data["model"] = Prompt.ask("Model name", default=default_model)
        
        if not config_data.get("api_key"):
            api_key_prompt = Prompt.ask(
                "API Key (or press Enter to use environment variable)",
                default="",
                password=True,
            )
            if api_key_prompt:
                config_data["api_key"] = api_key_prompt
    
    # Save config
    save_config(config_data)
    
    console.print("\n[green]✓[/green] Configuration saved successfully!")
    
    # Display summary
    table = Table(show_header=False, box=None)
    table.add_column("", style="cyan", width=15)
    table.add_column("", style="green")
    
    table.add_row("Provider:", config_data.get("provider") or "[dim]Not set[/dim]")
    table.add_row("Model:", config_data.get("model") or "[dim]Not set[/dim]")
    table.add_row("Offline Mode:", "[green]Yes[/green]" if config_data.get("offline") else "[red]No[/red]")
    
    console.print("\n")
    console.print(table)


@app.command()
def ask(
    query: str = typer.Argument(..., help="Natural language query to convert to SQL"),
    snapshot_name: Optional[str] = typer.Option("default", "--snapshot", "-s", help="Snapshot name to use"),
    project_root: Optional[Path] = typer.Option(None, "--root", "-r", help="Project root directory"),
) -> None:
    """
    Ask DataShark a question and generate SQL.
    
    This is the main entry point. For now, it loads the SemanticGraph
    and displays a "Thinking..." placeholder. The LiteLLM integration
    will be added in the next phase.
    """
    console.print(Panel.fit(f"[bold blue]DataShark Query[/bold blue]\n[dim]{query}[/dim]", border_style="blue"))
    
    # Load config
    config_data = load_config()
    
    if config_data.get("offline"):
        console.print("[yellow]⚠[/yellow] Offline mode enabled. LLM calls disabled.")
    
    # Detect project root
    if project_root is None:
        project_root = get_project_root()
    else:
        project_root = project_root.resolve()
    
    # Initialize graph
    graph = SemanticGraph()
    
    # Try to load snapshots from _local_context
    local_context_dir = project_root / "_local_context"
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Loading semantic graph...", total=None)
        
        snapshots_loaded = False
        
        if local_context_dir.exists():
            snapshot_files = list(local_context_dir.glob("*.json"))
            
            if snapshot_files:
                for snapshot_file in snapshot_files:
                    try:
                        with open(snapshot_file, "r") as f:
                            snapshot_data = json.load(f)
                        
                        # Validate snapshot
                        validation_errors = validate_snapshot(snapshot_data)
                        if validation_errors:
                            console.print(f"[yellow]⚠[/yellow] Skipping invalid snapshot: {snapshot_file.name}")
                            continue
                        
                        snapshot = SemanticSnapshot(**snapshot_data)
                        graph.add_snapshot(snapshot)
                        snapshots_loaded = True
                        
                    except Exception as e:
                        console.print(f"[yellow]⚠[/yellow] Error loading {snapshot_file.name}: {e}")
                        continue
        
        # If no snapshots were loaded, try to auto-ingest from project
        if not snapshots_loaded:
            progress.update(task, description="[cyan]No snapshots found. Auto-detecting sources...")
            
            # Try to ingest dbt or LookML
            dbt_project = project_root / "dbt_project.yml"
            manifest_file = None
            for manifest_path in [
                project_root / "target" / "manifest.json",
                project_root / "dbt" / "target" / "manifest.json",
            ]:
                if manifest_path.exists():
                    manifest_file = manifest_path
                    break
            
            lookml_files = list(project_root.glob("*.lkml"))
            
            if manifest_file:
                try:
                    progress.update(task, description="[cyan]Ingesting dbt manifest...")
                    snapshot = parse_dbt_manifest(manifest_file)
                    graph.add_snapshot(snapshot)
                    console.print(f"[green]✓[/green] Ingested dbt manifest: {manifest_file}")
                    snapshots_loaded = True
                except Exception as e:
                    console.print(f"[red]✗[/red] Error ingesting manifest: {e}")
            
            elif dbt_project.exists():
                try:
                    progress.update(task, description="[cyan]Ingesting dbt project...")
                    snapshot = parse_dbt_project_source(project_root)
                    graph.add_snapshot(snapshot)
                    console.print(f"[green]✓[/green] Ingested dbt project")
                    snapshots_loaded = True
                except Exception as e:
                    console.print(f"[red]✗[/red] Error ingesting dbt project: {e}")
            
            elif lookml_files:
                try:
                    progress.update(task, description="[cyan]Ingesting LookML files...")
                    for lkml_file in lookml_files[:10]:  # Increased limit for better coverage
                        snapshot = parse_lookml_file(lkml_file)
                        graph.add_snapshot(snapshot)
                    console.print(f"[green]✓[/green] Ingested {min(len(lookml_files), 10)} LookML files")
                    snapshots_loaded = True
                except Exception as e:
                    console.print(f"[red]✗[/red] Error ingesting LookML: {e}")
        
        progress.update(task, description="[cyan]Graph loaded successfully!")
    
    # Display graph statistics
    entity_count = len(graph.graph.nodes())
    edge_count = len(graph.graph.edges())
    
    console.print("\n")
    stats_table = Table(show_header=False, box=None)
    stats_table.add_column("", style="cyan", width=20)
    stats_table.add_column("", style="green")
    
    stats_table.add_row("Entities:", str(entity_count))
    stats_table.add_row("Relationships:", str(edge_count))
    
    console.print(stats_table)
    
    # Check if graph is empty
    if entity_count == 0:
        console.print("\n[red]✗[/red] No entities found in graph. Please run [bold]datashark init[/bold] or ingest sources first.")
        return
    
    # Phase 3: The Planner (The SQL Writer)
    offline_mode = config_data.get("offline", False)
    
    # Get a snapshot from the graph (needed for api.process_request)
    # Use the first snapshot from the graph
    snapshot = None
    if graph.snapshots:
        # Get the first snapshot
        snapshot = list(graph.snapshots.values())[0]
    else:
        # If no snapshots in graph, we can't proceed
        console.print("\n[red]✗[/red] No snapshots found in graph. Cannot generate SQL.")
        return
    
    if offline_mode:
        # Offline mode: Use simple pathfinding (fallback)
        console.print("\n[yellow]⚠[/yellow] Offline mode: Using simple pathfinding (Planner requires LLM)")
        
        # Extract all entity names (strip "entity:" prefix)
        all_entity_ids = graph.list_entities()
        entity_names = [eid.replace("entity:", "") for eid in all_entity_ids]
        
        # Simple keyword matching: look for entity names in query
        query_lower = query.lower()
        matched_entities = []
        
        for entity_name in entity_names:
            entity_lower = entity_name.lower()
            # Check if entity name appears in query (word boundary matching)
            if re.search(rf'\b{re.escape(entity_lower)}\b', query_lower):
                matched_entities.append(entity_name)
            else:
                # Also check for partial matches
                entity_base = re.sub(r's$', '', entity_lower)
                entity_base = re.sub(r'^dim_|^fct_|^stg_', '', entity_base)
                query_words = set(query_lower.split())
                if any(word in entity_lower or entity_base in word for word in query_words if len(word) > 2):
                    if entity_name not in matched_entities:
                        matched_entities.append(entity_name)
        
        if len(matched_entities) >= 2:
            if "orders" in matched_entities:
                source_table = "orders"
                target_table = next((e for e in matched_entities if e != "orders"), matched_entities[1])
            else:
                source_table = matched_entities[0]
                target_table = matched_entities[1]
        elif len(matched_entities) == 1:
            source_table = matched_entities[0]
            target_table = matched_entities[0]
        else:
            console.print("\n[red]✗[/red] Could not match any tables in query.")
            return
        
        # Use graph pathfinding for offline mode
        source_entity_id = f"entity:{source_table}"
        target_entity_id = f"entity:{target_table}"
        
        if source_entity_id not in graph.graph or target_entity_id not in graph.graph:
            console.print("\n[red]✗[/red] Entities not found in graph.")
            return
        
        try:
            if source_table == target_table:
                path = []
                sql = graph.generate_join_sql([], source_entity_id)
            else:
                path = graph.find_path(source_entity_id, target_entity_id)
                if not path:
                    console.print("\n[yellow]⚠[/yellow] No path found between tables.")
                    return
                sql = graph.generate_join_sql(path, source_entity_id)
            
            console.print("\n")
            console.print(Panel.fit("[bold green]✓ Validated SQL Generated[/bold green]", border_style="green"))
            console.print("\n")
            sql_syntax = Syntax(sql, "sql", theme="monokai", line_numbers=False)
            console.print(sql_syntax)
        except Exception as e:
            console.print(f"\n[red]✗[/red] Error: {e}")
        return
    
    # Online mode: Use QueryPlanner
    try:
        # Initialize Planner
        provider = config_data.get("provider")
        model = config_data.get("model")
        api_key = config_data.get("api_key") or os.environ.get("LITELLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        
        if not provider or not model:
            console.print("\n[red]✗[/red] LLM provider and model must be configured. Run: [bold]datashark config[/bold]")
            return
        
        if not api_key:
            console.print("\n[red]✗[/red] API key not found. Set it via [bold]datashark config --api-key[/bold] or environment variable.")
            return
        
        planner = QueryPlanner(provider=provider, model=model, api_key=api_key)
        
        # Plan the query
        with console.status("[bold green]Planning query...", spinner="dots"):
            structured_filter = planner.plan_query(query, graph)
        
        console.print(f"\n[cyan]✓ Query planned: {len(structured_filter.get('concept_map', {}).get('entities', []))} entities, {len(structured_filter.get('concept_map', {}).get('filters', []))} filters[/cyan]")
        
        # Generate SQL using the Kernel
        with console.status("[bold green]Generating SQL...", spinner="dots"):
            sql = process_request(snapshot, structured_filter)
        
        # Display SQL with syntax highlighting
        console.print("\n")
        console.print(Panel.fit(
            "[bold green]✓ Validated SQL Generated[/bold green]",
            border_style="green"
        ))
        console.print("\n")
        
        # Syntax highlight SQL
        sql_syntax = Syntax(sql, "sql", theme="monokai", line_numbers=False)
        console.print(sql_syntax)
        
        # Show query details
        concept_map = structured_filter.get("concept_map", {})
        entities = concept_map.get("entities", [])
        filters = concept_map.get("filters", [])
        metrics = concept_map.get("metrics", [])
        
        if entities or filters or metrics:
            console.print("\n[dim]Query components:[/dim]")
            if entities:
                entity_names = [e.get("entity_name", "") for e in entities]
                console.print(f"  [dim]Entities: {', '.join(entity_names)}[/dim]")
            if metrics:
                metric_names = [m.get("metric_name", "") for m in metrics]
                console.print(f"  [dim]Metrics: {', '.join(metric_names)}[/dim]")
            if filters:
                console.print(f"  [dim]Filters: {len(filters)} condition(s)[/dim]")
        
    except ValueError as e:
        console.print(f"\n[red]✗[/red] Planning error: {e}")
    except Exception as e:
        console.print(f"\n[red]✗[/red] Unexpected error: {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
