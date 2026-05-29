# Changelog

## 0.1.9 - 2026-05-29

### Documentation

- Clarified the public user-facing language in README, operator docs, and
  user-visible status strings.
- Marked `LINZA_VAULT` as optional in `server.json`, matching the server's
  `./vault` startup default, and documented that embedding settings are only
  needed for semantic indexing/search.
- Removed the standalone contributing guide to keep the public package surface
  focused on README, SECURITY, tool docs, examples, and tests.

## 0.1.8 - 2026-05-29

### Fixed

- Added MCP server capabilities to stdio initialization so LINZA starts with
  current Python MCP SDK releases that require `InitializationOptions.capabilities`.

## 0.1.7 - 2026-05-29

### Fixed

- Added the MCP Registry `runtimeHint: "uvx"` for the PyPI package so hosted
  catalog runners can start LINZA through the Python package runtime instead of
  spawning a bare `linza-mcp` command outside the virtual environment.

## 0.1.6 - 2026-05-27

### Fixed

- LINZA cold start no longer creates the default search profile by calling the
  embedding provider. Hosted runners can now start the MCP server and list tools
  even when LM Studio or another embedding endpoint is unavailable.
- Empty semantic search now returns a setup message before probing the embedding
  provider when no searchable embeddings are stored yet.

## 0.1.5 - 2026-05-26

User-facing review and release cleanup.

### Added

- `agent_workspace(action="history")` for a readable local log of applied
  approvals and follow-up actions.
- `agent_workspace(action="revoke_approval")` and storage-level soft revoke, so
  an approved item can be removed from active learning without deleting its
  audit trail.
- User display lines for review items, making agent output easier to show
  without dumping raw JSON.

### Changed

- Default MCP surface is now limited to the main 7 tools; specialized review
  helpers remain available through `agent_workspace` or the advanced surface.
- Active learning and map helpers ignore revoked approvals by default, while
  audit views can include them explicitly.
- Regression tests now live under `tests/`.

### Documentation

- Reworked Russian and English README wording around review items, local
  history, and safe apply/revoke flow.

## 0.1.4 - 2026-05-20

Index safety hardening before broader catalog submission.

### Added

- Runtime embedding dimension pinning after the first provider call, so a
  sidecar reindexes even when the configured model name stays the same but the
  returned vector dimension changes.
- Source-index preflight for graph-dependent `agent_workspace` actions. `map`,
  `teach`, `grow`, and `connect` now stop before using stale source files or
  mixed embedding signatures.

### Fixed

- `search` now refuses stale Markdown indexes instead of returning results from
  old file content after source notes were edited, added, or removed.

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
- `guide_next_steps` can render the user-facing onboarding view in Russian or
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
