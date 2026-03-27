# CC Execution Plan — Boyce Lifecycle Management
**CEO directive, 2026-03-21**  
**All tracks are pre-publish blockers.**

---

## Parallel Execution Strategy

Two Claude Code terminals, running simultaneously. They touch different files and can execute independently.

```
Terminal 1 (Track 1)              Terminal 2 (Track 2)
─────────────────────             ─────────────────────
connections.py (new)              init_wizard.py (modify)
doctor.py (new)                   test_init.py (modify)
server.py (modify)                test_cli_smoke.py (modify)
test_connections.py (new)         cli.py (init flags ONLY)
test_doctor.py (new)              docs/QUICK_START.md (new)
test_advertising.py (modify)
CLAUDE.md (modify)
cli.py (doctor subcommand ONLY)

~90-120 min                       ~60-90 min
```

### File Contention Rules

Both tracks modify `cli.py`. To prevent merge conflicts:
- **Track 1** adds the `doctor` subcommand only
- **Track 2** adds init flags (`--non-interactive`, `--json`, `--editors`, etc.) only
- Neither track refactors shared CLI infrastructure

Both tracks should run `verify_eyes.py` at start and end.

---

## Handoff Documents

Each terminal reads exactly ONE handoff document:

- **Terminal 1:** `CC_HANDOFF_TRACK_1.md` — Foundation + Doctor + MCP Health Tool + Advertising
- **Terminal 2:** `CC_HANDOFF_TRACK_2.md` — Init Redesign + Agent-Guided Docs

Place both handoffs in `.claude/handoffs/` before launching.

---

## Launch Commands

### Terminal 1
```bash
cd ~/ConvergentMethods/products/Boyce
claude --model opus "Read .claude/handoffs/CC_HANDOFF_TRACK_1.md and execute all blocks in order. Start with verify_eyes, then build connections.py, then doctor.py, then the check_health MCP tool, then the advertising layer integration. Run tests after each block. Do not touch init_wizard.py or test_init.py."
```

### Terminal 2
```bash
cd ~/ConvergentMethods/products/Boyce  
claude --model sonnet "Read .claude/handoffs/CC_HANDOFF_TRACK_2.md and execute all blocks in order. Start with verify_eyes, then add non-interactive mode to init_wizard.py, then idempotent re-run logic, then --json output, then write docs/QUICK_START.md, then update tests. Do not touch server.py or doctor.py."
```

---

## Integration Step (After Both Tracks Complete)

Once both terminals report clean test runs, open a third terminal for integration:

```bash
claude --model opus "Both lifecycle tracks are complete. Run the full test suite: python -m pytest boyce/tests/ -v. Then test the cross-command flow: 1) boyce init --non-interactive --skip-db --skip-sources --json, 2) boyce doctor --json, 3) verify both produce valid JSON. If any test fails, fix it. Then update _strategy/MASTER.md to reflect that the lifecycle management layer is complete."
```

---

## What "Done" Looks Like

- [ ] `boyce doctor` exists, runs clean, outputs JSON
- [ ] `boyce doctor` exit codes: 0 (healthy), 1 (warnings), 2 (errors)
- [ ] `check_health` MCP tool is visible and returns structured diagnostics
- [ ] `boyce init --non-interactive --json` works for agent invocation
- [ ] DSN persists across server restarts via `_local_context/connections.json`
- [ ] `environment_suggestions` appears in advertising layer on first session call
- [ ] `docs/QUICK_START.md` has platform-specific agent-guided setup instructions
- [ ] All tests pass: `python -m pytest boyce/tests/ -v`
- [ ] CLAUDE.md updated with new tools, files, and advertising schema
- [ ] No regressions: `verify_eyes.py` clean
