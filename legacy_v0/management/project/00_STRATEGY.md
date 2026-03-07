# DataShark — Master Strategy

## 1. Product Vision: "Cursor for Data Engineering"

DataShark is an agentic IDE layer that functions as a **Senior Data Engineer**. It goes beyond "Text-to-SQL" by acting as a fully aware teammate that understands the broader business logic, lineage, and safety constraints of the data warehouse.

**The "Senior" Standard:**
A Junior Engineer writes code that runs. A Senior Engineer writes code that is correct, performant, and safe. DataShark enforces the Senior Standard via the **Verification Loop**.

### The Core Value Proposition
1.  **Context-Awareness:** We ingest the *entire* stack (dbt, LookML, Airflow, PowerBI), not just the database schema.
2.  **Determinism:** We verify code against a rigorous Semantic Graph before showing it to the user.
3.  **Safety:** We catch "blast radius" issues (fan-outs, schema breaks) before they hit production.

---

## 2. Architecture: "The Universal Sidecar"

To achieve maximum market reach (VS Code + DBeaver) while maintaining a single "Brain," we utilize the **Headless Kernel** architecture.

### The Stack
* **The Kernel (Brain):** A standalone **Python Binary** (`datashark-core`) that holds the Logic, the Graph, and the Verification Engine.
    * *Interface:* JSON-RPC over Stdio/HTTP.
    * *Storage:* Embedded SQLite/DuckDB (to scale to 30,000+ nodes locally).
* **The Skins (Distribution):**
    * **VS Code Extension:** A lightweight TypeScript wrapper for modern engineering workflows.
    * **DBeaver Plugin:** A lightweight Java wrapper for traditional enterprise workflows.
    * **CI/CD Bot (Phase 1.5):** The *same* Kernel running in GitHub Actions to review PRs.

### The "Agentic Sandwich" (Refined)
1.  **Layer 1 (Ingestion Agent):** Scans the repo (dbt, LookML, etc.) and builds a **Semantic Graph**. It handles the messiness of parsing human intent.
2.  **Layer 2 (The Kernel):** A deterministic, logic-based compiler. It takes the Graph + User Request and produces verified SQL. **No LLM hallucinations allowed here.**
3.  **Layer 3 (Interface Agent):** The chat window that translates User Intent into Kernel Requests.

---

## 3. Ingestion Strategy: "The Graph of Truth"

Our moat is the ability to ingest the "Business Brain" of the company, regardless of format.

**Target Sources (Prioritized):**
1.  **The Logic Layer (dbt):** `manifest.json`, `schema.yml`. (Source of Truth for Transformations).
2.  **The Metric Layer (Looker/PowerBI):** `*.lkml`, `*.bim`. (Source of Truth for Joins & Metrics).
3.  **The Orchestration Layer (Airflow):** DAG files. (Source of Truth for Freshness).
4.  **The Physical Layer (Database):** Information Schema. (The Ground Truth).

**Scale Strategy:**
* **Small Teams (<500 tables):** Graph resides purely in-memory for speed.
* **Enterprises (>10k tables):** Graph resides in local embedded SQL engine with "Neighborhood Loading" (only load relevant domains).

---

## 4. Execution Roadmap (The 8-Week Sprint)

### Phase 1: The "Tool" (Stealth MVP)
*Goal: A single developer can install DataShark in VS Code or DBeaver and instantly query their data faster and safer than writing SQL manually.*

* **Milestone 1: The Kernel Pivot.** Refactor `cli.py` into a persistent JSON-RPC Server.
* **Milestone 2: The VS Code Skin.** Release a `.vsix` that talks to the Kernel.
* **Milestone 3: The Ingestion Hardening.** Support "Docker Universe" testbeds (Postgres+dbt, Looker emulation).
* **Milestone 4: The DBeaver Skin.** Release a Plugin that talks to the *same* Kernel.

### Phase 1.5: The "Teammate" (Fast Follow)
*Goal: The user pushes code, and DataShark automatically reviews it for safety.*

* **Milestone 5:** Wrap the Kernel in a Docker container for GitHub Actions.
* **Milestone 6:** Implement "Dry Run" capabilities (running `EXPLAIN` against the DB to check costs).

---

## 5. Success Criteria

1.  **Distribution:** Validated running in **both** VS Code and DBeaver.
2.  **Intelligence:** Successfully answers **Golden Queries 1-5** using context derived from *files* (not just DB schema).
3.  **Scale:** Ingestion takes <30 seconds for the "Small Universe" and <5 minutes for the "Enterprise Universe."
4.  **Economics:** Zero marginal cost to us (User provides API Key).

---

## 6. Distribution Strategy

The "One Brain" invariant dictates that `src/datashark/core/` and `concepts/` are the Universal Source of Truth. Logic changes here must propagate to the distribution channel.

**Channel 1: The Public Harness (Market / General)**
*   **Target User:** General users wanting "Plug-and-Play."
*   **Mechanism:** Standard VS Code Extension (`.vsix`).
*   **Artifacts:** `extension/package.json`, `extension/src/extension.ts`.
*   **Behavior:**
    *   Bundles the Python logic inside the extension folder.
    *   Manages its own isolated Python venv.
    *   Appears in the Extensions Sidebar with Logo and Version.
    *   **Constraint:** Must be self-contained (batteries included).

**Development Protocol**
*   **When modifying Core Logic:** You must verify that the `mcp_server.py` entrypoint remains compatible with the *Bundled Path* (Public).
