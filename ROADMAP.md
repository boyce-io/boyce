# DataShark Strategic Roadmap (2026)

## 0. The Mission
Transition DataShark from an "Engineering Project" to a "Commercial Product" by shifting focus from factory construction to assembly line delivery.

## I. Strategic Pillars

### 1. Core Optimization: The "Dialect Gap" (Fidelity)
* **Current Status:** ~57% Connectivity (Mattermost Benchmark). Stable but partially blind to complex dialects (Snowflake/BigQuery).
* **Objective:** **95% Fidelity.**
* **Tactic:** Treat the Parser as a Language Server. Iterate on grammar to capture "Dialect-Specific" dependencies (e.g., `COPY INTO`, `UNNEST`, Jinja macros).
* **Metric:** Connectivity Rate > 90% on `DataShark_Lab` scenarios.

### 2. Architecture: The "Universal Adapter" (LSP)
* **Current Status:** Python-based Core library.
* **Objective:** **Model Context Protocol (MCP) & Language Server Protocol (LSP).**
* **Tactic:** Wrap `DataShark_Core` in a standard JSON-RPC server.
* **Outcome:** "Headless" DataShark that runs natively in VS Code, Neovim, and Cursor without custom plugins for each.

### 3. Product Delivery: "The Extension Fleet" (Reach)
* **Current Status:** Internal Scripts.
* **Objective:** **Zero-Config Installers.**
* **Tactic:** Package the Core into native extensions for where users live.

---

## II. Delivery Targets (The "Triple Threat")

### Target A: The "Modern" Standard (VS Code / Cursor)
* **Audience:** Data Engineers, dbt users (80% market share).
* **Build:** TypeScript wrapper around Core (via LSP).
* **Priority:** **Viral Vector.**

### Target B: The "Enterprise" Standard (DBeaver / Eclipse)
* **Audience:** SQL Analysts, DBAs, Legacy Enterprise.
* **Build:** Java/OSGi Extension (utilizing existing prototype).
* **Priority:** **Sticky Vector.** (Competitive Moat).

### Target C: The "Pro" Standard (JetBrains / DataGrip)
* **Audience:** Senior Engineers, Java/Kotlin shops.
* **Build:** Kotlin-based plugin wrapper.
* **Priority:** **Revenue Vector.**

---

## III. Immediate Next Steps
1.  **Fidelity Sprint:** Use `fidelity_probe.py` to identify and patch the missing 40% of connections in the Mattermost repo.
2.  **LSP Wrapper:** Encapsulate Python Core into an LSP server.
3.  **DBeaver Polish:** Prepare the Java extension for release.
