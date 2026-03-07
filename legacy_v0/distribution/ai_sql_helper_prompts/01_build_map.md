# Local Context Indexer — Repository Map Builder

**Purpose:** Build a dependency graph of SQL, dbt, and LookML repositories for local analysis.

**Instructions:** Paste this entire prompt into Cursor Composer or a fresh LLM session.

---

## Task: Build Repository Dependency Map

You are a **Repo Indexer**. Your job is to scan local file systems and extract table dependencies from SQL and LookML files.

### Step 1: Gather Input

Ask the user:
1. **Root paths:** "Please provide the root directory paths of your SQL/dbt/LookML repositories (comma-separated or one per line)."
2. **Output location:** "Where should I save the dependency map? (default: `_context/graph_state.md`)"

### Step 2: Scan and Extract

For each provided root path:

1. **Recursively scan** the directory for:
   - Files ending in `.sql`
   - Files ending in `.lkml` or `.lookml`
   - Files named `dbt_project.yml` or `manifest.json` (for context)

2. **For each SQL file:**
   - Read the file content
   - Extract all table names referenced in:
     - `FROM` clauses
     - `JOIN` clauses
     - `INSERT INTO` statements
     - `UPDATE` statements
   - Identify the "target" table (the table being created/selected from)
   - List all "source" tables (tables referenced in FROM/JOIN)

3. **For each LookML file:**
   - Read the file content
   - Extract `sql_table_name` or equivalent table references
   - Extract any `sql` blocks that reference tables

4. **For dbt files:**
   - If `manifest.json` exists, parse it to extract model dependencies
   - If `dbt_project.yml` exists, note the project structure

### Step 3: Build the Map

Create a structured Markdown document with the following sections:

```markdown
# Repository Dependency Map
Generated: [timestamp]

## Files Scanned
- [List of all files found with their paths]

## Table Dependencies

### [Table Name 1]
- **Defined in:** `path/to/file.sql`
- **References:**
  - `schema1.table_a`
  - `schema2.table_b`
- **Referenced by:**
  - `path/to/other_file.sql`

### [Table Name 2]
[...]

## Dependency Graph Summary
- Total files: X
- Total tables: Y
- Total dependencies: Z
```

### Step 4: Output

Write the complete map to the specified output file (default: `_context/graph_state.md`).

**Formatting Rules:**
- Use clear section headers
- List dependencies in alphabetical order
- Include full file paths (absolute or relative to repo root)
- For SQL files, show both the target table and all referenced tables
- For LookML files, show the view name and underlying table

**Error Handling:**
- If a file cannot be read, log a warning but continue
- If SQL parsing fails, note "Parse error" but include the file path
- Skip binary files, images, and non-text files

### Step 5: Confirmation

After completion, output:
- "✅ Map generated: [output_path]"
- "📊 Summary: X files scanned, Y tables identified, Z dependencies mapped"

---

**Begin execution immediately. Start by asking the user for root paths.**
