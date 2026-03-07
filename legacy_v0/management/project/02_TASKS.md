# DataShark Master Roadmap: Operational Hardening & Semantic Expansion

## 🏗️ Architectural Definitions
*   **Agent Engine (`agent_engine/`):** The reusable "Sandwich Buns" (Ingestion & Reasoning).
    *   *Agent A (Ingestion):* Crawlers, Chunkers, Parsers.
    *   *Agent B (Reasoning):* Brain, RAG, Planners.
*   **DataShark (`src/datashark/`):** The Product Core (Schema, Graph, RPC Server).
*   **Evals (`agent_engine/tuning/`):** The Calibration Lab (Shadow Trap, Benchmarks).

## 📂 Phase 1: Foundation (Completed)
- [x] Kernel Pivot (Python Sidecar Architecture)
- [x] In-House Brain (DataSharkBrain) using OpenAI + ChromaDB
- [x] Server Wiring (RPC Server <-> Brain)
- [x] Architectural Split (Agent Engine vs. Product Core)

## 🚀 Category A: Multi-Platform Extension Strategy
*Goal: Broadest possible user footprint with high stability.*
- [ ] **A1: DBeaver Gold Standard (Mac)** - [ ] Real-time debugging loop for plugin/sidecar communication.
- [ ] **A2: UI/IDE Target List**
    - [ ] 1. DBeaver (Primary)
    - [ ] 2. VS Code (Data-extension focused)
    - [ ] 3. DataGrip/JetBrains (The Power User Tier)
    - [ ] 4. Azure Data Studio (MS Ecosystem)
- [ ] **A3: Windows Cross-Platform Implementation**
    - [ ] Compile sidecar as `.exe` via Nuitka.
    - [ ] Test plugin loading on Microsoft Surface/Windows 11 hardware.

## 🚀 Category B: The "Real-World" Gym (Data Platform Testing)
*Goal: Stress-test against heterogeneous metadata sources.*
- [ ] **B1: Baseline Repo Selection**
    - [ ] Select 4-5 open-source dbt/Looker repos (e.g., GitLab Data Team, Jaffle Shop).
- [ ] **B2: Scale & Complexity Matrix**
    - [ ] Test against 10-table (simple) vs. 500-table (enterprise) schemas.
- [ ] **B3: "Beyond-DB" Ingestion (The Semantic Layer)**
    - [ ] **dbt:** Parse `manifest.json` and `schema.yml` for business definitions.
    - [ ] **Looker:** Parse `.view` and `.model` files for "Golden Join" logic.
    - [ ] **Airflow:** Identify data freshness and lineage via DAG parsing.

## 🚀 Category C: Delivery & Commercial Moat
*Goal: IP protection and low-friction monetization.*
- [ ] **C1: Black Box Obfuscation**
    - [ ] Fully compile Python sidecar to machine code (Nuitka).
- [ ] **C2: Licensing & Metering**
    - [ ] Build a local-to-cloud license check (heartbeat).
- [ ] **C3: Cost Scaffolding**
    - [ ] Implement query-tiering (Mini for DDL, O1 for complex reasoning).
    - [ ] Balance "First 50 Free" logic vs. BYOK (Bring Your Own Key).

## 🚀 Category D: Agent A (The Context Engine) & Agent B (The Brain)
*Goal: Autonomous knowledge acquisition & reasoning.*
*Location: `agent_engine/capabilities/`*

- [x] **D1/D2: Brain & Wiring (Complete)**
- [ ] **D3: Agent A: The Context Engine (Ingestion)** (IN PROGRESS)
    - [x] Build recursive file crawler (`ingestion/ingestor.py`).
    - [x] Implement Smart Chunker (`ingestion/chunker.py`).
    - [ ] [D3.3] The Synapse (Connect Chunker to Brain).
    - [ ] Implement "First Installation" wizard to locate dbt/Looker repos.
- [ ] **D4: Agent B: The Reasoning Runtime (Brain)**
    - [ ] Implement watchdog to monitor identified repos for changes.
    - [ ] Incremental re-indexing (only re-train on changed files).

## 🚀 Category T: The Gauntlet (Calibration & Tuning)
*Goal: Prove performance via "Shadow Trap" benchmarks.*
*Location: `agent_engine/tuning/`*

- [ ] **T1: The Context Trap (Recall)**
    - [ ] Run `shadow_trap/initial_test` (Finance SQL).
    - [ ] Measure % Recall of schema elements.
- [ ] **T2: The Reasoning Benchmark (Accuracy)**
    - [ ] Run 20 "Golden Questions" against the Finance schema.
    - [ ] Pass threshold: >90% SQL Syntax Validity.
    - [ ] Pass threshold: >80% Semantic Accuracy.
