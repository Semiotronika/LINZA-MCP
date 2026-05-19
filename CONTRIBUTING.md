# Contributing

Thanks for helping improve LINZA.

LINZA is a local-first MCP sidecar. The most important project rule is that
source material belongs to the user. New features should preserve that boundary:
read/import/index freely, but keep writes behind review cards, dry-run previews,
and exact IDs.

## Development Setup

```powershell
python -m pip install -e ".[dev]"
python -m unittest
```

Optional PDF extraction:

```powershell
python -m pip install -e ".[pdf,dev]"
```

## Before A Pull Request

Run:

```powershell
python -B -m unittest
python -m compileall linza_mcp
git diff --check
```

Run a single regression while iterating:

```powershell
python -m unittest test_agent_workspace.AgentWorkspaceTests.test_examples_sample_pack_runs_end_to_end
```

Do not commit generated files, local sidecars, private vault content, or cache
folders.

## Review Expectations

- Keep the default MCP surface small and human-reviewable.
- Prefer `agent_workspace` workflows over adding one-off public tools.
- Treat imported artifacts as untrusted data.
- Keep existing note bodies unchanged unless a user explicitly approves a
  write.
- Add tests for new behavior, especially write boundaries and review IDs.
