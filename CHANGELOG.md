# Changelog

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

### Security

- Existing note bodies are protected during indexing, analysis, and artifact
  ingest.
- Generated reports and context packs are restricted to `.linza`.
- Public package manifest excludes internal migration scripts, local agent
  instructions, test sidecars, and database files.

### Fixed

- Removed the deprecated MIT license classifier so setuptools 77+ can build the
  package with the SPDX `license = "MIT"` metadata.
- Added the remaining documented environment variables to `server.json`.
