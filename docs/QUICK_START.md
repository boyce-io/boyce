# Quick Start

## Install

```bash
pip install boyce
```

For live database queries (recommended):

```bash
pip install boyce[postgres]
```

## Set up (choose your editor)

### Claude Code

Paste this into your terminal:

```
claude "Install Boyce for this project. My database is at postgresql://user:pass@host:5432/mydb"
```

### Cursor

Open Composer (Cmd+I / Ctrl+I) and type:

```
Set up the Boyce MCP server for my project. Connect it to my PostgreSQL
database at postgresql://user:pass@host:5432/mydb
```

### VS Code Copilot

Open Copilot Chat and type:

```
Run `boyce init --non-interactive --editors vscode --db-url "postgresql://user:pass@host:5432/mydb" --json` and tell me if it worked
```

### JetBrains / DataGrip

Open AI Assistant and type:

```
Run `boyce init --non-interactive --editors jetbrains --db-url "postgresql://user:pass@host:5432/mydb" --json` and tell me if it worked
```

Then: Settings > Tools > AI Assistant > Model Context Protocol > Add the boyce server.

### Manual setup

```bash
boyce init
```

The wizard walks you through editor detection, database connection, and
data source discovery interactively.

## Verify

```bash
boyce doctor
```

## Non-interactive mode (for scripts and agents)

All `boyce init` flags:

```
--non-interactive     Skip all prompts. Requires explicit flags.
--json                Output structured JSON instead of human-readable text.
--editors EDITORS     Comma-separated: claude_code, cursor, vscode, jetbrains, windsurf, claude_desktop
--db-url DSN          PostgreSQL connection string.
--skip-db             Skip database connection step.
--skip-sources        Skip data source discovery step.
--skip-existing       Skip editors that already have Boyce configured.
```

Example — configure Claude Code and Cursor with a database:

```bash
boyce init --non-interactive --editors claude_code,cursor \
  --db-url "postgresql://user:pass@localhost:5432/mydb" --json
```

Example — agent re-run that only configures new editors:

```bash
boyce init --non-interactive --skip-db --skip-sources --skip-existing --json
```

## What happens next

Once configured, open your editor and try:

```
"Show me the database schema"
"What tables have revenue data?"
"Total revenue by customer last 12 months"
```

Boyce compiles validated SQL from natural language. Every query gets:
- NULL trap detection (warns when filters silently exclude NULL rows)
- EXPLAIN pre-flight validation
- Redshift compatibility checks
