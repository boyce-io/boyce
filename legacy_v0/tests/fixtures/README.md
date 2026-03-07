# Test Fixtures - Open Source Benchmarks

This directory contains heavyweight enterprise-scale test fixtures for validating DataShark's ingestion logic against real-world complexity using standard open source benchmarks.

## Git Ignore Policy

All files in this directory are git-ignored (except this README.md) to prevent committing large external repositories.

See `.gitignore` for details.

## Enterprise Scale Fixtures

### Mattermost Data Warehouse
**Location:** `mattermost/`  
**Source:** https://github.com/mattermost/mattermost-data-warehouse  
**Purpose:** "Full Stack" test - Airflow + dbt + Snowflake

**Contains:**
- Airflow DAGs (Python)
- dbt models (SQL, YAML)
- Complex Python extractors
- Real-world data warehouse patterns

**Use Cases:**
- Testing Airflow DAG ingestion
- Testing dbt project parsing
- Testing complex Python extractor logic
- Validating against real-world data warehouse structures

---

### GitLab Analytics
**Location:** `gitlab/`  
**Source:** https://github.com/gitlab-data/analytics  
**Purpose:** "Massive dbt Scale" test

**Contains:**
- Large-scale dbt project
- Hundreds of SQL models
- Complex dbt YAML configurations
- Enterprise dbt patterns

**Use Cases:**
- Testing dbt project parsing at scale
- Validating against massive dbt repositories
- Testing complex dbt dependency resolution

---

### TheLook
**Location:** `thelook/`  
**Source:** https://github.com/looker-open-source/thelook  
**Purpose:** "LookML Reference" test

**Contains:**
- Advanced LookML models
- Derived Tables
- Liquid Parameters
- Complex Looker patterns

**Use Cases:**
- Testing LookML ingestion
- Testing derived table parsing
- Testing liquid parameter resolution
- Validating against real-world Looker projects

---

### Mozilla Pipeline Schemas
**Location:** `mozilla/`  
**Source:** https://github.com/mozilla-services/mozilla-pipeline-schemas  
**Purpose:** "Complex JSON Schemas" test

**Contains:**
- Complex JSON schemas
- Nested data structures
- Schema evolution patterns
- Real-world schema definitions

**Use Cases:**
- Testing JSON schema parsing
- Testing complex nested structures
- Validating schema evolution handling

---

## Golden Baselines

**Location:** `golden_baselines/`  
**Purpose:** Reference SQL outputs for golden query tests

Contains:
- `Q1.sql` - Golden Query 1 baseline
- `Q2.sql` - Golden Query 2 baseline
- `Q3.sql` - Golden Query 3 baseline

---

## Usage

These fixtures are used by:
- Integration tests in `tests/integration/`
- Heavyweight ingestion tests
- Agentic ingestion validation tests
- Open Source Benchmark validation tests

**Note:** These repositories are cloned locally and git-ignored. They are not committed to the repository.

---

## Statistics

Run the following to see fixture sizes:
```bash
du -sh tests/fixtures/*
```

To count files in each fixture:
```bash
# Mattermost (Python, SQL, YAML)
find tests/fixtures/mattermost -name "*.py" -o -name "*.sql" -o -name "*.yml" | wc -l

# GitLab (SQL, YAML)
find tests/fixtures/gitlab -name "*.sql" -o -name "*.yml" | wc -l

# Mozilla (JSON)
find tests/fixtures/mozilla -name "*.json" | wc -l

# TheLook (LookML)
find tests/fixtures/thelook -name "*.lookml" -o -name "*.lkml" | wc -l
```
