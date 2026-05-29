# LINZA Internal Regression Fixture

This directory is an internal product fixture for regression tests. It is not
copied from a real vault.

Use it to verify the LINZA loop without exposing personal data:

1. Index `tests/fixtures/linza-sample-pack/sample-vault`.
2. Import the files in `tests/fixtures/linza-sample-pack/artifacts`.
3. Run inbox analysis and review cards.
4. Confirm that source Markdown notes stay unchanged.
5. Export a compact context pack for an agent.

The sample intentionally contains:

- product decisions;
- research notes;
- operating rules;
- a chat log;
- a browser research log with process noise;
- an agent trace for the calibr lens.

The regression test is:

```powershell
python -m unittest tests.test_agent_workspace.AgentWorkspaceTests.test_internal_sample_pack_runs_end_to_end
```

Expected safety behavior is listed in `expected/safety-checks.md`.
