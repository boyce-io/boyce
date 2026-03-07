# Naming Brief: Database Semantic Protocol Product

## What the Product Is

An open-source protocol and reference implementation for how AI agents understand databases. It sits between an LLM and a database, providing:

1. **A semantic protocol** — a JSON format (called "SemanticSnapshot") that describes not just database structure (tables, columns, types) but database *meaning* (business definitions, join confidence weights, data quality profiles, policy rules). Think "OpenAPI but for databases."

2. **A deterministic SQL kernel** — same structured input produces the same SQL output byte-for-byte, every time. No LLM in the SQL generation path. The LLM only translates natural language into a structured intent; everything downstream is deterministic.

3. **A safety layer** — pre-flight SQL validation (EXPLAIN before execution), NULL trap detection (warns when equality filters silently discard NULL rows), dialect-specific linting (Redshift 1.0 compatibility).

The product is exposed as an MCP (Model Context Protocol) server — the emerging standard for connecting AI agents to tools. It's also a pip-installable Python library.

**The core bet:** In 12-18 months, AI models will handle simple NL-to-SQL natively. The durable value is the *protocol* (structured semantic metadata), the *deterministic kernel* (reproducibility guarantee), and the *safety/governance layer* (audit, policy, data quality). The NL-to-SQL pipeline is the demo that gets people in the door. The protocol is what makes them stay.

**Target users:** AI engineers building agents that touch production databases, data platform leads giving LLM access to company data, and developers who need safety guarantees on AI-generated SQL.

**Competitive positioning:** Privacy-first (self-hosted, BYOK), vendor-neutral (works with any database, any LLM, any agent), open protocol (MIT licensed). Competitors are dbt MCP (requires dbt adoption), Vanna AI (RAG-based, non-deterministic), and various thin database MCP bridges (no semantic understanding).

---

## Naming Requirements

### Must Have
- **4-6 characters ideal, 7 absolute max** — this will be a CLI command (`name scan ./`), a PyPI package (`pip install name`), and a Python import (`import name`). Every character counts.
- **Not trademarked in software** (USPTO Class 9 or Class 42). Search TESS or equivalent before suggesting.
- **Available or near-available on PyPI** — check https://pypi.org/project/{name}/. If the base name is taken but dormant/abandoned, note that. Suffix variants like `{name}-protocol` or `{name}-db` are acceptable fallbacks.
- **No major existing software product with this name** — no funded startups, no products from FAANG/major tech companies. Google "{name} software" and "{name} database" before suggesting.
- **Professional enough for enterprise** — a CTO should feel comfortable saying this in a board meeting. No memes, no puns, no cutesy names.

### Should Have
- **Evocative of function** — semantic understanding, navigation, structure, safety, measurement, protocol/standard, foundational infrastructure
- **Works as a protocol name** — "The _____ Protocol" should sound like an established industry standard
- **Agent-discoverable** — an AI agent searching for "database semantic protocol" or "SQL safety layer" should naturally associate the name with this domain
- **Domain availability** — .dev, .io, or .com. Check if the obvious domains are parked/available.

### Nice to Have
- Mathematical or scientific resonance (the founder has a PhD in mathematics)
- Nautical/navigation/cartographic metaphors work well (the product helps agents *navigate* databases)
- The name should age well — still appropriate in 5 years when the product has evolved

### Already Checked and Rejected
These names are ALL taken — do not suggest them:
- Keel (ERP, $13M funded), Axiom (observability, $41M), Datum (Autodesk product), Loom (Atlassian), Pylon ($51M, a16z), Meridian (Google OSS project), Bastion (Azure + Cloudflare), DataShark (trademarked), Helm (Kubernetes), Atlas (MongoDB), Prism (various), Cortex (various), Compass (various), Beacon (various), Forge (various), Sonar (SonarQube), Radar (various), Gauge (ThoughtWorks), Lattice (HR company), Carta (cap table), Nexus (Sonatype), Rivet (Vercel)

### Candidates Under Consideration (not yet fully vetted)
- **Cairn** (5) — trail marker stones used for navigation. Strong metaphor. Needs availability check.
- **Sextant** (7) — navigational instrument. Metaphor is perfect. Proven available. But 7 letters.
- **Sheaf** (5) — mathematical structure for organizing local data into global consistency. Precise but opaque.
- **Tarn** (4) — mountain lake. Clean, short, but weak metaphor connection.

---

## What I Need From You

Give me **5-10 name candidates** that meet the requirements above. For each:
1. The name and character count
2. Why it works (metaphor, etymology, associations)
3. A quick availability check (PyPI, notable software products, obvious trademark conflicts)
4. How "The _____ Protocol" sounds
5. Any risks or downsides

Prioritize names that are 4-6 characters, demonstrably available, and evocative of the product's function. I'd rather have 3 thoroughly vetted names than 10 unresearched ones.
