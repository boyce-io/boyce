# Benchmark Database Candidates — Boyce Goal 3 Validation

**Created:** 2026-03-30
**Purpose:** Evaluate real-world databases for Q2 Goal 3 — validate Boyce against 3+ databases where vanilla LLMs produce subtly wrong SQL.
**Constraint:** Not Pagila, not synthetic. PostgreSQL compatible. Published benchmarks.

---

## Context: What Breaks Vanilla LLMs

Research on LLM SQL generation failure modes (DataBrain evaluation of 50,000+ LLM-generated queries, Google Cloud "Six Failures of Text-to-SQL") identifies these recurring error classes:

1. **Wrong join paths** — LLM picks the obvious FK but misses that a better path exists through an intermediate table, or collapses many-to-many through a junction table incorrectly. Produces silently inflated or deflated row counts.
2. **NULL blindness** — LLM uses `=` or `IN` on nullable columns, silently dropping NULL rows. The classic Boyce null trap.
3. **Grain confusion** — LLM aggregates at the wrong level (e.g., GROUP BY customer when the question implies GROUP BY order), producing correct-looking but semantically wrong numbers.
4. **Schema hallucination** — LLM invents columns or tables that don't exist. Less relevant for Boyce (we compile from a snapshot, not hallucinate), but the inverse — LLM ignoring columns that DO exist — is relevant.
5. **Ambiguous column resolution** — Multiple tables have `name`, `status`, `type`, `id` columns. LLM picks the wrong one, especially without table qualification.
6. **Temporal logic errors** — Wrong date functions, missing timezone handling, incorrect interval arithmetic.

Boyce's competitive advantage maps directly to failures 1, 2, 3, and 5. The ideal benchmark databases are ones that trigger these failure modes in vanilla LLMs.

---

## Candidate Assessment

### Tier 1 — Strong Candidates (Recommended)

---

#### 1. AdventureWorks (Microsoft sample DB — PostgreSQL port)

**Domain:** Manufacturing / retail (bicycle company — sales, production, HR, purchasing)
**Schema stats:** ~68 tables across 5 schemas (HumanResources, Person, Production, Purchasing, Sales). Dense FK web. Multiple join paths between core entities.
**Why LLMs struggle:**
- **Person.BusinessEntity** is a supertype linking to Person, Employee, Customer, and Vendor — LLMs routinely pick the wrong subtype table or miss the intermediate join.
- **Multiple address types** per entity (billing, shipping, home) — LLMs default to the first address relationship and silently return wrong addresses.
- **Product hierarchy** (Product → ProductSubcategory → ProductCategory) with nullable subcategory — LLMs skip the intermediate join or lose NULLs.
- **SalesOrderHeader → SalesOrderDetail → Product** vs **SalesOrderHeader → Customer → Person** — two valid join trees, only one is correct per question.
- **Schema-qualified names** (Production.Product vs Sales.SalesOrderHeader) create namespace ambiguity.

**PostgreSQL availability:** Multiple maintained ports. Best: [lorint/AdventureWorks-for-Postgres](https://github.com/lorint/AdventureWorks-for-Postgres) — Ruby converter + SQL install script. Also: [timchapman/postgresql-adventureworks](https://github.com/timchapman/postgresql-adventureworks) — restorable pg_dump. Docker: [sripathikrishnan/adventureworks](https://github.com/sripathikrishnan/adventureworks).
**Setup effort:** 15-30 minutes (clone + run install.sql).
**Community recognition:** HIGH. The most widely used sample database in the Microsoft ecosystem. Developers who've touched SQL Server know it. Instant credibility in benchmarks.
**Semantic complexity:** HIGH. The supertype pattern, multi-schema layout, and nullable hierarchies make this the best candidate for demonstrating Boyce's join resolution and null trap detection.

**Rating: STRONG RECOMMEND**

---

#### 2. BIRD-Bench Financial Database (Czech banking — PKDD'99)

**Domain:** Banking / finance (accounts, transactions, loans, credit cards, clients)
**Schema stats:** 8 tables, 55 columns. Tables: account, card, client, disp (disposition), district, loan, order, trans (transaction).
**Why LLMs struggle:**
- **Disposition table** is a non-obvious junction between clients and accounts with a `type` column that determines relationship semantics (owner vs. disponent). LLMs skip it or join directly client→account.
- **District table** contains geographic and demographic data that must be joined through account, not directly to client — an indirect join path that LLMs routinely flatten.
- **Transaction table** has `type` and `operation` columns with Czech-language coded values (PRIJEM, VYDAJ, etc.) — LLMs either hallucinate English equivalents or ignore the filter entirely.
- **High NULL rates** in loan and card tables (most clients don't have loans/cards), making aggregate queries silently wrong with INNER JOIN.
- **Temporal density** — transactions span 1993-1998 with date-dependent semantics.

**PostgreSQL availability:** Originally SQLite in BIRD benchmark. Straightforward to convert (8 tables, clean schema). BIRD mini-dev V2 ships with PostgreSQL dialect support. Also available on [Kaggle](https://www.kaggle.com/datasets/mariammariamr/1999-czech-financial-dataset) and [data.world](https://data.world/lpetrocelli/czech-financial-dataset-real-anonymized-transactions).
**Setup effort:** 30-60 minutes (download BIRD dev set, convert SQLite→PG, or use CSV imports).
**Community recognition:** HIGH in ML/NLP research. The BIRD benchmark is the current standard for text-to-SQL evaluation (NeurIPS, ICLR papers). Using a BIRD database in Boyce's benchmark creates direct comparability with published results.
**Semantic complexity:** MEDIUM-HIGH. Only 8 tables, but the disposition indirection, coded values, and NULL-heavy optional tables create exactly the failure modes Boyce is built to catch.

**Rating: STRONG RECOMMEND** — Using a BIRD database gives us published baseline comparisons for free.

---

#### 3. IMDb (Internet Movie Database)

**Domain:** Entertainment (movies, actors, directors, genres, ratings)
**Schema stats:** ~15 tables in relational form. Main: movie, person, genre, language, country, company, role, certificate + 7 junction tables (castinfo, movietogenre, movietolanguage, etc.). Millions of rows.
**Why LLMs struggle:**
- **Multiple many-to-many relationships** — movie↔person (via castinfo with role), movie↔genre, movie↔language, movie↔country. LLMs frequently produce Cartesian products or miss the junction table.
- **Person table overload** — actors, directors, writers, producers are all in `person` with role distinguished only through `castinfo.role`. LLMs confuse actor joins with director joins.
- **NULL-heavy metadata** — budget, gross, runtime are frequently NULL. Queries like "average budget by genre" silently drop most movies.
- **Ambiguous column names** — `name` appears in person, company, genre. `id` everywhere.
- **Scale** — large enough that wrong joins produce visibly wrong row counts (millions vs thousands).

**PostgreSQL availability:** [RyanMarcus/imdb_pg_dataset](https://github.com/RyanMarcus/imdb_pg_dataset) — Vagrant box auto-loads into Postgres. [hakanersu/imdb-importer](https://github.com/hakanersu/imdb-importer) — direct PG import tool. Raw TSV data from [IMDb interfaces](https://www.imdb.com/interfaces/) (refreshed daily).
**Setup effort:** 1-2 hours (download ~1GB compressed TSVs, import, index). Docker option available.
**Community recognition:** VERY HIGH. Everyone knows IMDb. Using it in a benchmark is immediately relatable — "here's a query about Christopher Nolan movies that GPT-4 gets subtly wrong."
**Semantic complexity:** HIGH. The many-to-many junction tables and role-based person disambiguation are textbook cases where LLMs produce inflated counts.

**Rating: STRONG RECOMMEND** — The recognition factor alone makes this worth including. The many-to-many patterns are exactly where Boyce's Dijkstra join resolution shines.

---

### Tier 2 — Good Candidates (Viable alternatives)

---

#### 4. Stack Overflow Data Dump

**Domain:** Q&A / community (posts, users, votes, tags, badges, comments)
**Schema stats:** ~7-8 core tables. Posts (questions AND answers in one table, distinguished by PostTypeId), Users, Votes, Tags, Badges, Comments, PostHistory, PostLinks. Massive scale: 90M comments, 236M votes, 50M badges.
**Why LLMs struggle:**
- **Posts table dual nature** — questions and answers coexist in the same table. LLMs frequently query "all posts" when they mean "all questions," silently including answers in aggregates.
- **No foreign keys defined** — relationships are implicit (ParentId, OwnerUserId, etc.), meaning LLMs must infer join paths from column names alone.
- **VoteTypeId indirection** — votes have a type column that determines semantics (upvote, downvote, favorite, etc.). LLMs count all votes as "upvotes."
- **Tags as delimited strings** — tags are stored as `<python><pandas>` strings in Posts, not as a normalized join table. LLMs either parse this wrong or assume a tags table exists.

**PostgreSQL availability:** [Smart Postgres](https://smartpostgres.com/posts/announcing-early-access-to-the-stack-overflow-sample-database-download-for-postgres/) — dedicated PG download. [Networks-Learning/stackexchange-dump-to-postgres](https://github.com/Networks-Learning/stackexchange-dump-to-postgres) — Python import scripts.
**Setup effort:** 1-2 hours for full dump. Can use a subset (single StackExchange site) for faster setup.
**Community recognition:** VERY HIGH. Every developer knows Stack Overflow.
**Semantic complexity:** MEDIUM-HIGH. The dual-nature Posts table and implicit FKs are good failure triggers, but the schema is flatter than AdventureWorks or IMDb.

**Rating: GOOD** — Strong recognition, but the flat schema with no explicit FKs is less ideal for demonstrating Boyce's join resolution. Better for demonstrating null trap and grain confusion.

---

#### 5. Northwind (classic orders/products)

**Domain:** Wholesale distribution (customers, orders, products, suppliers, employees, shippers)
**Schema stats:** 14 tables. Core: Customers, Orders, OrderDetails, Products, Suppliers, Employees, Categories, Shippers, Territories, EmployeeTerritories, Region.
**Why LLMs struggle:**
- **Region column NULL rates** — only 6 countries have regions assigned. Queries filtering by region silently drop most records.
- **Employee hierarchy** — Employees.ReportsTo is a self-referential FK. LLMs struggle with recursive/hierarchical queries.
- **Territory many-to-many** — EmployeeTerritories junction table that LLMs skip.
- **Discontinued products** — boolean flag that changes the semantics of "all products" queries.

**PostgreSQL availability:** [pthom/northwind_psql](https://github.com/pthom/northwind_psql) — ready-to-use SQL file. Multiple other ports available.
**Setup effort:** 5-10 minutes. Trivial.
**Community recognition:** HIGH. The original Microsoft sample DB. Every SQL textbook references it.
**Semantic complexity:** MEDIUM. Well-known enough that LLMs have seen it extensively in training data, which may reduce error rates. Fewer tables and simpler relationships than AdventureWorks.

**Rating: GOOD** — Fast setup and high recognition, but may be too familiar to LLMs (trained on millions of Northwind queries). Best as a baseline/control rather than a primary challenge database.

---

#### 6. TPC-DS (Decision Support Benchmark)

**Domain:** Omnichannel retail (store sales, web sales, catalog sales, inventory, promotions)
**Schema stats:** 24 tables in a snowflake schema. 99 complex benchmark queries. Tables include store_sales, web_sales, catalog_sales (3 parallel fact tables), plus 20+ dimension tables (date_dim, customer, item, etc.).
**Why LLMs struggle:**
- **Three parallel fact tables** — store_sales, web_sales, and catalog_sales have similar but NOT identical schemas. LLMs pick the wrong fact table or union them incorrectly.
- **Snowflake dimensions** — customer_address is separate from customer_demographics, both joined through customer. LLMs flatten the snowflake.
- **Date dimension** — complex: fiscal year, quarter, month, week all as separate columns. LLMs use the wrong temporal grain.
- **GROUPING SETS, ROLLUP, window functions** — the 99 queries exercise advanced SQL that LLMs rarely generate correctly.

**PostgreSQL availability:** [pg_tpch](https://github.com/2ndQuadrant/pg-tpch) for TPC-H (8 tables, simpler). TPC-DS requires the official dbgen tool + manual PG adaptation.
**Setup effort:** 2-4 hours. Requires generating data with dbgen and adapting DDL for PostgreSQL.
**Community recognition:** HIGH in the database performance community. Less known among general developers.
**Semantic complexity:** VERY HIGH. But may be overkill — the 99 queries test SQL engine performance, not semantic compilation. Many queries use SQL features Boyce doesn't yet support (ROLLUP, GROUPING SETS).

**Rating: GOOD for future use** — Too complex for the initial 3-database benchmark. Excellent for Phase 10 (Full Benchmark Program). The three-fact-table pattern is a killer LLM failure mode worth testing eventually.

---

### Tier 3 — Investigated, Not Recommended

---

#### 7. Chinook (music store)

**Domain:** Digital media store (artists, albums, tracks, invoices, playlists)
**Schema stats:** 11 tables, ~15,000 rows.
**Why not:** Too simple. The schema is explicitly designed for beginners. Straightforward FK relationships, no NULL traps, no ambiguous join paths. LLMs handle it well. Same domain as Pagila (media rental). Adds no incremental value over what Phase 4 already tested.

#### 8. MIMIC-III/IV (medical ICU data)

**Domain:** Healthcare (patients, admissions, chart events, lab results)
**Schema stats:** 26 tables, 3.8 GB unstructured text, complex temporal data.
**Why not:** Requires credentialed access (CITI ethics training, data use agreement). Setup takes days, not hours. Medical domain requires domain expertise to write meaningful benchmark queries. The denormalized schema (SUBJECT_ID duplicated across tables) is interesting but the access barrier kills it for a public benchmark.

#### 9. Discourse (forum software)

**Domain:** Forum / community
**Schema stats:** 100+ tables (Rails migration-heavy schema).
**Why not:** No clean sample data dump. Would need to stand up a full Discourse instance and seed it. The schema is migration-artifact-heavy (plugin tables, cache tables) rather than semantically rich. Too much noise for a benchmark.

#### 10. Mastodon (social network)

**Domain:** Federated social media
**Schema stats:** 100+ tables.
**Why not:** Same issues as Discourse — Rails schema, no clean data dump, ActivityPub federation tables add irrelevant complexity. No community recognition as a benchmark database.

#### 11. World Bank Open Data

**Domain:** Development economics / indicators
**Why not:** Not a relational database. Available as CSV/API, would need to be modeled from scratch. The data is wide (thousands of indicators as columns or as EAV rows), not relationally complex. Poor fit for testing join resolution.

#### 12. GitLab (open source)

**Domain:** DevOps platform
**Schema stats:** 500+ tables, 12 TiB production database.
**Why not:** Far too large and complex for a benchmark. No clean sample data subset. The schema is a decade of Rails migrations — testing Boyce against it would require months of query curation. Excellent engineering study, terrible benchmark.

---

## Existing Benchmark Frameworks

| Framework | Databases | Size | Dialect | Key Feature |
|-----------|-----------|------|---------|-------------|
| **BIRD** | 95 real-world DBs, 37 domains | 33.4 GB total | SQLite (PG in V2) | Current SOTA benchmark. Real data, real schemas. 12,751 query pairs. |
| **Spider** | 200 DBs, 138 domains | Small per DB | SQLite | Cross-domain generalization. 10,181 questions. |
| **Spider 2.0** | Enterprise-scale | Terabyte-scale | Multiple | 700-800 columns per schema. Too large for Boyce's current scope. |
| **WikiSQL** | 26,521 tables | Simple | SQLite | Single-table only. No joins. Irrelevant for Boyce. |
| **BIRD-CRITIC** | 600+ tasks | Multiple dialects | MySQL, PG, SQL Server, Oracle | Focuses on SQL debugging, not generation. Interesting but different. |
| **LiveSQLBench** | 600 queries | Full SQL spectrum | Multiple | Hierarchical knowledge base. Recent (Sep 2025). |

**Key insight for Boyce:** BIRD is the most directly relevant framework. Its databases are real-world, its queries are complex, and using BIRD databases in our benchmark lets us cite published accuracy numbers for comparison. The Financial database (Czech banking) from BIRD's dev set is our strongest candidate from this ecosystem.

---

## Recommended Selection (3 databases)

| # | Database | Domain | Tables | Why |
|---|----------|--------|--------|-----|
| 1 | **AdventureWorks** | Manufacturing/retail | 68 | Supertype pattern, multi-schema, nullable hierarchies, multiple join paths. The hardest schema for LLMs. |
| 2 | **BIRD Financial** (Czech banking) | Finance | 8 | Disposition indirection, coded values, NULL-heavy optional tables. Direct comparability with published BIRD benchmark scores. |
| 3 | **IMDb** | Entertainment | 15+ | Many-to-many junctions, role-based disambiguation, massive NULL rates in metadata. Highest community recognition. |

**Alternate slot (if one of the above proves impractical):** Stack Overflow or Northwind.

**Rationale for this mix:**
- Three distinct domains (manufacturing, finance, entertainment) — no "all e-commerce" criticism.
- Range of schema sizes (8 to 68 tables) — proves Boyce works at different scales.
- Each database triggers different LLM failure modes — AdventureWorks (join path ambiguity), Financial (indirection + NULLs), IMDb (many-to-many inflation).
- All three have strong community recognition — the benchmark results will be immediately credible.
- All three have PostgreSQL availability — no porting required, just setup.
- Total setup estimate: 3-4 hours for all three.

---

## Query Design Guidance

For each database, design 5-10 ground-truth queries targeting these failure classes:

| Failure Class | Boyce Advantage | Example Pattern |
|---------------|-----------------|-----------------|
| **Wrong join path** | Dijkstra shortest path on SemanticGraph | "Total sales by product category" (requires Product → SubCategory → Category, not direct) |
| **NULL trap** | `_null_trap_check()` + `data_reality` | "Count of customers with loans" (most customers have NULL loan records) |
| **Grain confusion** | `grain_context` in StructuredFilter | "Average order value by customer" (GROUP BY customer, not by order line) |
| **Ambiguous columns** | Snapshot-based column resolution | "Show the name and status" (which table's name? which status?) |
| **Junction table skip** | Graph-based join resolution | "Movies by actor and genre" (requires castinfo + movietogenre junctions) |
| **Implicit filter** | Business definition injection | "Active accounts" (requires knowing disposition.type = 'OWNER') |
