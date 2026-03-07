# Product Naming — Requirements Brief

**Purpose:** Concise reference for evaluating name candidates in a separate conversation.

---

## What the product is (one paragraph)

An open-source (MIT) Python library and MCP server that acts as a semantic safety layer between AI agents and databases. It ingests schema metadata from any source (dbt, LookML, Django, Prisma, DDL, etc.), builds a semantic graph, and compiles natural language into deterministic SQL with data quality checks. Not a BI tool, not a query UI — a headless protocol and engine that agents call programmatically.

---

## Hard Requirements (all must pass)

| # | Requirement | Why it matters |
|---|-------------|----------------|
| 1 | **PyPI name available** | `pip install <name>` is the primary distribution channel. Check at pypi.org/project/<name>. Hyphenated variants (e.g., `<name>-protocol`) are acceptable but the base name being available is strongly preferred. |
| 2 | **No active USPTO trademark in Class 9 or 42** | Class 9 = downloadable software. Class 42 = SaaS/software services. Search at tsdr.uspto.gov. Abandoned marks are OK; active or pending marks are blockers. |
| 3 | **No funded startup or major tech product using the name** | If someone has raised $5M+ or a FAANG company ships a product with this name, SEO is lost and confusion is guaranteed. Google the name + "software" or "data" to check. |
| 4 | **Viable .dev or .io domain** | Doesn't need to be available for $12 — but shouldn't be an active, established site for a competing product. |
| 5 | **No phonetic or spelling confusion with existing dev tools** | "Prism" vs "Prisma", "Pylon" vs "Pylons" — this kind of collision erodes discoverability. |

## Soft Preferences (nice to have)

| # | Preference | Notes |
|---|------------|-------|
| A | Short (1-2 syllables, ≤8 characters) | Easier CLI typing: `<name> scan ./` |
| B | Evokes navigation, structure, precision, or safety | The product helps agents navigate databases safely. Metaphors from cartography, engineering, optics, or measurement land well. |
| C | Not a common English word used in programming | Avoid names that collide with variable names, function names, or language keywords. |
| D | Works as both a noun and a verb | "Run <name> on your project" / "Let me <name> the schema" |
| E | No awkward phonetics or abbreviations | Will be spoken in demos and conference talks. |

---

## What we've already eliminated

Two rounds of evaluation (16 candidates total). Everything was RED except **sextant** (YELLOW — viable but has phonetic baggage).

**Round 1:** Plumb (CAUTION), Codd (BLOCKED), Ferret (BLOCKED)

**Round 2:** keel, axiom, datum, loom, pylon, meridian, bastion (all RED), sextant (YELLOW)

Full details in `_management_documents/NAME_AVAILABILITY_AUDIT.md`.

---

## Quick validation checklist for a new candidate

1. Search `pypi.org/project/<name>` — is it available or dormant?
2. Search `tsdr.uspto.gov` for the name — any active Class 9/42 marks?
3. Google `"<name>" software` — any well-funded competitors?
4. Check `<name>.dev` and `<name>.io` — who owns them?
5. Search GitHub for `<name>` — any major repos (1K+ stars)?
6. Say it out loud three times. Does it sound like a product?
