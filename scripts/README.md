# LINZA Scripts

This folder contains publishable operator and CI helpers. End users normally
start LINZA through the `linza-mcp` console command; these scripts are for
developers, CI, and careful local smoke checks.

| Script | Purpose |
| --- | --- |
| `linza_doctor.py` | Human-readable health check over safe smoke checks. |
| `smoke_mcp_tools.py` | Smoke every MCP tool on a temporary Markdown-only vault copy. |
| `smoke_copy_vault.py` | Run a private-output-safe smoke test against a copied vault. |
| `demo_core.ps1` | Optional local demo of core read/review flows. |

Migration, recovery, copy-onboarding, YAML cleanup, and dangerous vault-cleaning
helpers are intentionally not part of the publishable script surface.

Script audience:

- user-facing: `linza_doctor.py`, because it gives a short readiness summary;
- developer/CI-facing: `smoke_mcp_tools.py`, `smoke_copy_vault.py`, and
  `demo_core.ps1`, because they exercise temporary copies and test fixtures.
