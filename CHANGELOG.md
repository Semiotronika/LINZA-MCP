# Changelog

## 0.1.3 - 2026-05-20

Official MCP Registry identity fix.

### Fixed

- Updated the MCP server name and PyPI README ownership marker to the exact
  GitHub repository identity `io.github.Semiotronika/LINZA-MCP` required by the
  official Registry publisher.

## 0.1.2 - 2026-05-20

Registry metadata fix before catalog submission.

### Fixed

- Shortened the official MCP Registry `server.json` description so it passes
  the registry length limit while keeping the same package and safety contract.

## 0.1.1 - 2026-05-20

Release hardening before catalog submission.

### Added

- Runtime embedding-signature validation for stored vectors. Search, bridge
  rebuilds, and single-file indexing now refuse mixed provider/model/dimension
  states and ask for a full reindex instead.
- Quick vault sync status for `agent_workspace` and `doctor`, showing added,
  changed, or removed Markdown files before agents rely on stale sidecar data.
- `LINZA_MAX_BRIDGE_PAIRS` guard to skip expensive semantic bridge rebuilds on
  very large vaults instead of unexpectedly running an unbounded pairwise pass.

### Fixed

- Python 3.10 CI compatibility for release metadata tests.

## 0.1.0 - 2026-05-19

Initial public preparation of LINZA.

### Added

- Local SQLite sidecar at `.linza/linza.db`.
- Compact default MCP surface with `agent_workspace` as the main facade.
- Artifact ingest for pasted text, Markdown, TXT, JSON, DOCX, XLSX, and optional
  PDF extraction.
- Staged review cards for domains, material types, hierarchy, causal links,
  memory, patterns, and calibr traces.
- Supervised growth mode that stays dry-run by default.
- Synthetic private-safe example pack and regression tests.
- PyPI packaging metadata, official MCP Registry `server.json`, and Glama
  ownership metadata.
- Optional Dockerfile for isolated stdio runs.
- `py.typed` marker and a conservative Ruff lint configuration for development.

### Changed

- LM Studio is now the default embedding setup for real semantic work.
- Removed the old no-model embedding fallback from production code and public
  documentation. Tests use their own deterministic fake provider.
- `guide_next_steps` can render the human-facing onboarding view in Russian or
  English via `language` / `LINZA_LANGUAGE`.

### Security

- Existing note bodies are protected during indexing, analysis, and artifact
  ingest.
- Generated reports and context packs are restricted to `.linza`.
- DOCX/XLSX artifact XML parsing uses `defusedxml`.
- Public package manifest excludes internal migration scripts, local agent
  instructions, test sidecars, and database files.

### Fixed

- Removed the deprecated MIT license classifier so setuptools 77+ can build the
  package with the SPDX `license = "MIT"` metadata.
- Added the remaining documented environment variables to `server.json`.
- Repaired public demo and smoke scripts after removing the old embedding
  fallback.
