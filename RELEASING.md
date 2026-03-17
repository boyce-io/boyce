# RELEASING — Boyce

Release checklist for every version of Boyce published to PyPI and beyond.

Publish surfaces canonical list: `ConvergentMethods/ASSETS.md` → **Publish Surfaces → Boyce**.
Adding a new channel = one edit there; this file picks it up automatically.

---

## Pre-Release

- [ ] All tests passing: `python -m pytest boyce/tests/ -v`
- [ ] `verify_eyes.py` clean: `python boyce/tests/verify_eyes.py`
- [ ] Version bumped in `boyce/pyproject.toml` (`version = "X.Y.Z"`)
- [ ] `CHANGELOG.md` updated with release notes (what changed, breaking changes if any)
- [ ] Git tag created: `git tag vX.Y.Z && git push origin vX.Y.Z`

---

## Publish to PyPI

```bash
cd boyce/
uv build
uv publish
```

Verify at https://pypi.org/project/boyce/ — confirm version, description, classifiers.

---

## Update All Publish Surfaces

Work through the table in `ASSETS.md`. For each surface:

### GitHub README (`github.com/boyce-io/boyce`)
- Update version badge (if present)
- Update install examples if commands changed
- Update feature/tool count if added/removed

### Product Page (`convergentmethods.com/boyce/`)
- Update version references
- Update feature list, code examples, or MCP tool table if changed
- Deploy: commit + push `sites/convergentmethods/` → GitHub Pages auto-deploys

### Agent Docs — Index (`convergentmethods.com/boyce/llms.txt`)
- Update `Version:` line
- Update tool list if tools added/removed
- Sync with `llms-full.txt`

### Agent Docs — Full Reference (`convergentmethods.com/boyce/llms-full.txt`)
- Update `Version:` line
- Update tool parameters if signatures changed
- Update Known Limitations if resolved or added
- Deploy with product page commit above

### CM Root Page (`convergentmethods.com/`)
- Update product description if positioning changed (usually no-op)

### CM Agent Index (`convergentmethods.com/llms.txt`)
- Update Boyce entry if description changed (usually no-op)

### MCP Directories (Smithery, PulseMCP, mcp.so, Glama)
- Update version, description, tool count
- These are manual submissions — check each registry's update flow

### boyce.io (when live)
- Mirror product page or point redirect to convergentmethods.com/boyce/
- Currently deferred — domain in transfer (see `ASSETS.md` → boyce.io Transfer Status)

---

## Post-Release Verification

- [ ] `pip install boyce==X.Y.Z` succeeds in a clean environment
- [ ] MCP server starts: `boyce` (no args)
- [ ] `boyce init` runs without error
- [ ] Product page renders correct version
- [ ] `llms.txt` and `llms-full.txt` reflect new version

---

## Version Numbering

- `0.x.y` — pre-1.0, no stability guarantee
- `1.0.0` — first stable release (post Will's hands-on testing sprint)
- Increment patch (`0.1.x`) for bug fixes and minor additions
- Increment minor (`0.x.0`) for new tools, new parsers, or protocol changes
- Increment major (`x.0.0`) for breaking SemanticSnapshot schema changes
