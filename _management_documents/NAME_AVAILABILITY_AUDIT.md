# Product Name Availability Audit

**Date:** 2026-02-28 (Round 2)
**Candidates:** keel, axiom, datum, loom, pylon, sextant, meridian, bastion
**Product:** SQL safety layer / MCP server for database guardrails
**Previous round (2026-02-21):** Plumb (CAUTION), Codd (BLOCKED), Ferret (BLOCKED)

---

## Summary Table

| Name | PyPI | Domains | Trademark | Existing Products | Verdict |
|------|------|---------|-----------|-------------------|---------|
| keel | TAKEN (base) | keel.sh, keel.so active | Minor (ELECTRONIC KEEL only) | Keel ERP ($13M funded), Keel K8s operator, KEEL data mining | **RED** |
| axiom | TAKEN (base, abandoned) | axiom.co active ($41M) | Multiple active in Class 9/42 | Axiom observability ($41M), AxiomHQ ERP, Magnet Axiom forensics | **RED** |
| datum | TAKEN (base) | datum.net active ($13.6M), datum.org active | Autodesk Datum (active product) | Autodesk Datum (asset mgmt), Datum Cloud ($13.6M), Datum blockchain | **RED** |
| loom | TAKEN (base, abandoned) | loom.com (Atlassian) | Registered Class 9 by Loom/Atlassian (Reg #5274612) | Loom/Atlassian (14M+ users) | **RED** |
| pylon | TAKEN (base) | usepylon.com active ($51M) | PYLONTECH in software classes | Pylon B2B Support ($51M, a16z), Basler pylon cameras | **RED** |
| sextant | TAKEN (base, dormant) | No major .dev/.io conflicts | No software trademarks found | Scattered academic/niche tools only | **YELLOW** |
| meridian | TAKEN (base, dormant) | meridianapps.com active | AMI MERIDIAN (Class 42, software) | Google Meridian (open-source MMM), Accruent Meridian EDMS (350K users) | **RED** |
| bastion | NOT FOUND (base available) | bastion.dev active (consulting) | Bastion Technologies (6 marks) | Azure Bastion (Microsoft), BastionZero (Cloudflare) | **RED** |

---

## Detailed Analysis

### 1. KEEL -- RED

**PyPI:**
- `keel` -- TAKEN. Process killer utility (v0.1, likely dormant).
- `keel-ds` -- TAKEN. ML dataset loader (active, v0.2.5, Oct 2024).
- `keel-protocol`, `keel-sql`, `keel-db` -- Available.

**Domains:**
- `keel.sh` -- Active. Keel Kubernetes operator (2.6K GitHub stars).
- `keel.so` -- Active. Keel ERP platform (London startup, $13.1M total funding, Earlybird + LocalGlobe).
- `keel.dev`, `keel.io` -- Unknown/not confirmed active.

**Trademarks:**
- "ELECTRONIC KEEL" (Serial 77981496) -- Synexxus Inc, military vehicle data systems. Active, incontestable.
- "MOTOR & KEEL" -- Published for opposition.
- No standalone "KEEL" in Class 9/42 found, but the ERP company at keel.so likely has or will file.

**Existing Products:**
- Keel ERP (keel.so) -- Well-funded startup ($13.1M), direct tech/data conflict.
- Keel Kubernetes Operator (keel.sh) -- Moderate DevOps adoption.
- KEEL Data Mining Software (keel.es) -- Academic, open-source, 500+ algorithms.

**Assessment:** Three distinct, active software products named "Keel." The ERP product at keel.so is in the same enterprise/data space and is funded. High confusion risk.

---

### 2. AXIOM -- RED

**PyPI:**
- `axiom` -- TAKEN. In-process ORM/DB (v0.9.0, Aug 2020, Python 2.7 only, effectively dead).
- `axiom-protocol`, `axiom-sql`, `axiom-db` -- Not found (likely available).

**Domains:**
- `axiom.co` -- Active. Axiom observability platform ($41.4M funded, 40K+ orgs).
- `axiomsw.com` -- Active. Axiom ERP for electronics distributors.
- `axiomhighered.com` -- Active. Axiom ETL for higher education.

**Trademarks:**
- AXIOM (Reg #4460669) -- Active, Class 9 (Computer & Software Products).
- AXIOM LEGAL (Reg #3285584) -- Active, Class 42 (Software Services).
- Multiple other AXIOM marks across tech.

**Existing Products:**
- Axiom observability (axiom.co) -- $41.4M funded, data/developer tools.
- Magnet Axiom -- Digital forensics software.
- Axiom Healthcare -- Enterprise planning/analytics.
- Axiom by Canary -- Data visualization for manufacturing.

**Assessment:** Name is completely saturated in tech/software. Multiple active trademarks in Class 9 and 42. The axiom.co observability platform alone makes this untenable for any data-adjacent product.

---

### 3. DATUM -- RED

**PyPI:**
- `datum` -- TAKEN. Exists on PyPI (details not fully accessible; likely dormant).
- `django-datum` -- TAKEN.
- `datum-protocol`, `datum-sql`, `datum-db` -- Not found (likely available).

**Domains:**
- `datum.net` -- Active. Datum Cloud, open-source network cloud for AI ($13.6M funded, 2024-founded, CRV-backed).
- `datum.org` -- Active. Datum blockchain data storage.
- `datumlabs.io` -- Active. Data analytics consulting.

**Trademarks:**
- "DATUM" by Datum Network GmbH (Serial 87941891) -- Abandoned (failure to respond).
- Autodesk uses "Datum" as an active commercial product name (Autodesk Datum, asset lifecycle management).

**Existing Products:**
- Autodesk Datum -- Active commercial product (asset lifecycle management). Fortune 500 company.
- Datum Cloud (datum.net) -- $13.6M funded open-source infrastructure startup.
- Datum blockchain (datum.org) -- Crypto/data monetization.
- Datum Workstation -- GIS software.

**Assessment:** Autodesk has an active commercial product called "Datum" in the software/data management space. Datum Cloud is a well-funded recent startup. Too many conflicts, including a Fortune 500 company with an active product by this exact name.

---

### 4. LOOM -- RED

**PyPI:**
- `loom` -- TAKEN. Fabric/Puppet deployment tool (v0.0.18, May 2014, abandoned).

**Domains:**
- `loom.com` -- Active. Owned by Atlassian (acquired Loom in 2023).

**Trademarks:**
- "LOOM" (Reg #5274612) by Loom Inc -- ACTIVE, Class 9. Covers downloadable software for creating, editing, sharing, analyzing and transcribing video/sound recordings. Now owned by Atlassian.

**Existing Products:**
- Loom (Atlassian) -- 14M+ users, 200K+ companies. Major SaaS product.

**Assessment:** Completely blocked. Atlassian owns the trademark, the domain, and the product has massive market presence. Their legal department would oppose any Class 9/42 filing.

---

### 5. PYLON -- RED

**PyPI:**
- `Pylon` -- TAKEN. Electric power systems simulation (v0.4.1).
- `pypylon` -- TAKEN. Official Basler camera SDK wrapper.
- `pylon-app` -- TAKEN. Desktop app framework.
- `pylon-protocol`, `pylon-sql`, `pylon-db` -- Not found (likely available).

**Domains:**
- `usepylon.com` -- Active. Pylon B2B support platform ($51M total funding, a16z backed, 780+ customers).
- `getpylon.com` -- Active (Pylon developer hub).
- `pylon.cronit.io` -- Active. Pylon GraphQL framework.

**Trademarks:**
- PYLONTECH by Pylon Technologies Co. Ltd -- Active, covers software design/development and PAAS.

**Existing Products:**
- Pylon B2B Support (usepylon.com) -- $51M funded, a16z backed, 780+ customers.
- Basler pylon -- Industrial camera software suite.
- Pylon solar design software.
- Pylons Project -- Python web framework family (Pyramid).

**Assessment:** Heavily contested. A well-funded ($51M) startup in the tech/SaaS space already dominates the name.

---

### 6. SEXTANT -- YELLOW

**PyPI:**
- `sextant` -- TAKEN. Vector space search engine (v0.5.0, MIT license, likely dormant).
- `asdf-sextant` -- TAKEN. ASDF-related tool.
- `sextant-protocol`, `sextant-sql`, `sextant-db` -- Not found (available).

**Domains:**
- `sextant.di.uoa.gr` -- Active. Academic geospatial visualization (University of Athens).
- `sextantusa.com` -- Active. Back-office analytics company.
- `sextant.dev`, `sextant.io` -- Not confirmed active in search results.

**Trademarks:**
- No software-specific "SEXTANT" trademarks found in USPTO searches.
- Black Knight Technology uses "Sextant" as a product name (military 3D visualization) -- limited to defense sector.

**Existing Products:**
- SEXTANT Software Exploration Tool -- Academic (Eclipse IDE plugin, 2006 paper). Defunct.
- Sextant by Black Knight -- Military/Navy 3D visualization. Niche defense.
- Sextant USA -- Back-office analytics. Small company.
- Sextant ReactiveUI -- Xamarin navigation library (open source).
- Sextant by Matt Pocock -- Dev tool for charting app flows (npm package).

**Assessment:** Cleanest name on the list. No dominant product, no well-funded startups, no registered software trademarks found. The existing uses are scattered across unrelated niches (academia, military, small analytics). The PyPI base name is taken but dormant; suffix variants are all available. The metaphor (navigation instrument) maps well to a data-navigation product. Main risk: the word occasionally raises eyebrows due to phonetic associations.

---

### 7. MERIDIAN -- RED

**PyPI:**
- `meridian` -- TAKEN. Geospatial data processing (v0.4.0, Dec 2020, dormant/alpha).
- `google-meridian` -- TAKEN. Google's Marketing Mix Model (actively maintained by Google).
- `meridian-oss` -- TAKEN. RAG/vector search platform with pgvector.

**Domains:**
- `meridian.design` -- Active. Webflow design agency.
- `meridianapps.com` -- Active. Indoor positioning platform.

**Trademarks:**
- AMI MERIDIAN by American Megatrends International -- Active, Class 42, covers software design/development/installation/maintenance.
- MERIDIAN VERITY by Meridian Verity Group -- Active, covers AI governance software platforms.

**Existing Products:**
- Google Meridian -- Open-source MMM framework. Google-backed, major visibility.
- Accruent Meridian -- Engineering document management system (350K+ users).
- Meridian AI -- Private equity data/enrichment tools.

**Assessment:** Google using "Meridian" as an open-source product name is the dealbreaker. AMI has an active Class 42 trademark covering software services. Accruent Meridian is an enterprise incumbent.

---

### 8. BASTION -- RED

**PyPI:**
- `bastion` -- NOT FOUND as a standalone package (base name appears available!).
- Related taken: `aiobastion`, `ssh-bastion`, `bastion-host-poc`, `bastion7`, `bastion-safepost`, `bastion-key-client`.
- `bastion-protocol`, `bastion-sql`, `bastion-db` -- Available.

**Domains:**
- `bastion.dev` -- Active. Bastion Data, a data infrastructure consulting company (Atlanta, 15+ years).
- `bastionzero.com` -- Active. Zero-trust infrastructure platform (acquired by Cloudflare, May 2024).
- `bastion-software.com` -- Active. "Advanced System Monitoring Solutions."

**Trademarks:**
- Bastion Technologies Inc -- 6 trademark applications including "BASTION." Active company.

**Existing Products:**
- Azure Bastion -- Microsoft's managed PaaS for secure VM access. Massive enterprise presence.
- BastionZero -- Zero-trust infrastructure access (acquired by Cloudflare). Database access is a core feature.
- OVH The Bastion -- Open-source bastion host management.
- Bastion Data (bastion.dev) -- Data infrastructure consulting. Direct conflict with data tooling.
- Bastion Infotech -- License management software.

**Assessment:** "Bastion" is deeply entrenched in infrastructure/security terminology. Azure Bastion alone creates massive SEO confusion for any tech product. BastionZero (now Cloudflare) specifically handles database access. bastion.dev is a data consulting company. The base PyPI name being available is notable, but the namespace is too polluted with major tech brands.

---

## Overall Recommendation

**Only SEXTANT (YELLOW) has a viable path to trademark registration and market differentiation.**

All other names have at least one dealbreaker:
- Funded startup in the same space (keel, pylon, datum)
- Major tech company product (loom/Atlassian, meridian/Google, bastion/Microsoft Azure)
- Saturated trademark landscape (axiom)

For sextant, the registration path would be:
1. Register `sextant-protocol` on PyPI (base `sextant` is taken but dormant)
2. Acquire `sextant.dev` or `sextant.io` if available
3. File USPTO trademark in Class 9 (downloadable software) and Class 42 (SaaS)
4. The navigation metaphor ("instrument for determining position by measuring angles to known reference points") maps well to a semantic-layer / data-navigation product

**If sextant is rejected for branding reasons, a new batch of candidate names should be generated.** None of the other seven are workable.

---

## Appendix: Previous Round (2026-02-21)

| Name | Verdict | Reason |
|------|---------|--------|
| Plumb | CAUTION | PyPI taken (dormant), Plumb AI shutting down but recent, Plum Fintech phonetically identical |
| Codd | BLOCKED | Codd AI (codd.ai) is a directly competitive GenAI semantic layer with MCP integrations |
| Ferret | BLOCKED | FerretDB (major PostgreSQL project), GNU Ferret (SQL generator), Apple ml-ferret, 8+ active software projects |
