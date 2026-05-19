# Security Policy

LINZA is a local-first MCP server. It is designed to help an agent read,
index, and review a user-owned workspace without silently rewriting source
notes.

## Data Boundary

- LINZA reads files only from the configured `LINZA_VAULT` directory.
- The sidecar database is created inside that vault at `.linza/linza.db`.
- Imported artifacts, chunks, approvals, calibr traces, and generated context
  packs stay local unless the user exports or shares them.
- LINZA does not include browser automation, cloud synchronization, telemetry,
  or a hosted memory service.

## Write Boundary

- Indexing, searching, artifact ingest, map generation, and calibr review are
  read-only with respect to existing note bodies.
- Apply operations are dry-run by default and use exact review item IDs.
- Generated reports are restricted to `.linza/reports`.
- Generated context packs are restricted to `.linza/context-packs`.
- `write_file` creates Markdown notes by default and blocks overwriting existing
  files unless explicitly allowed.

## Untrusted Content

Treat every imported artifact as untrusted data. Web pages, chats, logs,
documents, and PDFs may contain instructions intended to manipulate an agent.
LINZA stores and analyzes these artifacts, but they do not become active rules,
skills, memory, or note edits without review.

## Reporting Issues

Please report security issues through the GitHub repository:

https://github.com/Semiotronika/LINZA-MCP/issues

Do not include private vault contents, API keys, or personal documents in public
issues.
