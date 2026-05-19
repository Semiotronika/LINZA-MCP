# LINZA — Local MCP Server for Agent Workspaces

**It does not change your data. It changes how you see it.**

You have a folder full of notes, articles, logs, drafts, chats, and documents.
There is already structure in it: relations, recurring problems, decisions,
topic drift, and the evolution of thought. Most of it is just hidden by volume.
LINZA makes the hidden structure visible.

It does not rewrite your files. It does not impose a fixed ontology. It does not
decide meaning for you. It observes, finds patterns, shows evidence, and lets
the human decide what is worth keeping.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/protocol-MCP_stdio-lightgrey.svg)](https://modelcontextprotocol.io)
![Local first](https://img.shields.io/badge/storage-local--first-green.svg)
![Review gated](https://img.shields.io/badge/writes-review--gated-orange.svg)

🇷🇺 [Русская версия](README.md)

---

## What You Will See

- **Domains** — LINZA finds meaning clusters in a raw workspace and asks you to
  name them.
- **Material types** — templates, cases, notes, specs, and other recurring forms
  are discovered from structure, not hardcoded upfront.
- **Relations** — which notes belong together, and which decisions appear to
  lead to which actions or results.
- **Patterns** — repeated problems, terminology drift, possible contradictions,
  and gaps in topic coverage.
- **Memory** — what future agents should recall, when it should be reviewed
  again, and what might be stale.

Every proposal should come with evidence: source notes, snippets, shape signals,
relation labels, and confidence. You see not only the conclusion, but why LINZA
thinks it may be useful.

---

## How It Works

1. You point LINZA at a Markdown vault or workspace directory through
   `LINZA_VAULT`.
2. LINZA creates a local sidecar at `.linza/linza.db`.
3. The agent indexes notes or imports new artifacts through
   `agent_workspace(action="ingest_artifacts")`.
4. The server builds chunks, connections, staged analysis, and review queues.
5. The human accepts or rejects cards. Apply actions are `dry_run` by default.
6. The agent receives a context pack or connection map without rewriting source
   text.

The core contract:

```text
load/index -> analyze -> review cards -> explicit apply -> context export
```

---

## Quick Start

Install from PyPI:

```powershell
pip install linza-mcp
$env:LINZA_VAULT="C:\path\to\workspace-or-vault"
linza-mcp
```

For PDF extraction, install the optional extra:

```powershell
pip install "linza-mcp[pdf]"
```

For local verification or development, run it from source:

```powershell
cd "C:\path\to\LINZA-MCP"
$env:LINZA_VAULT="C:\path\to\workspace-or-vault"
python -m server
```

Connect it to Claude Desktop, Cursor, OpenCode, or any MCP client:

```json
{
  "mcpServers": {
    "linza": {
      "command": "linza-mcp",
      "env": {
        "LINZA_VAULT": "/absolute/path/to/workspace-or-vault",
        "LINZA_EMBED_PROVIDER": "hash",
        "LINZA_EMBED_URL": "http://127.0.0.1:1234/v1",
        "LINZA_TOOL_SURFACE": "default"
      }
    }
  }
}
```

VS Code / Copilot MCP uses `servers` instead of `mcpServers`:

```json
{
  "servers": {
    "linza": {
      "type": "stdio",
      "command": "linza-mcp",
      "env": {
        "LINZA_VAULT": "/absolute/path/to/workspace-or-vault",
        "LINZA_EMBED_PROVIDER": "hash"
      }
    }
  }
}
```

By default, LINZA uses offline hashing embeddings so the server can start without
network access or an external embedding API. For stronger semantic search, set
`LINZA_EMBED_PROVIDER=openai` or `LINZA_EMBED_PROVIDER=ollama` explicitly.

---

## First Output Example

Agents usually start with `agent_workspace(action="doctor")` or
`guide_next_steps`. The human should see a short status and a next step, not a
raw JSON wall:

```text
LINZA is ready

Material:
- 42 notes indexed
- 3 incoming artifacts waiting for review
- sidecar: .linza/linza.db

Next step:
1. Review discovered domains
2. Accept, rename, or skip 3-5 cards
3. Nothing is written without dry-run/apply

Example card:
Proposal: connect "Retrieval Quality Note" and "Source Policy"
Why: shared vocabulary, review-flow references, nearby chunks
Write impact: none yet; accepting records a sidecar relation
```

---

## MCP Tools

LINZA exposes a compact default surface of 15 tools. Normal operation starts
from `agent_workspace` or `guide_next_steps`, not from a raw tool list.

| Tool | Purpose |
| --- | --- |
| `agent_workspace` | One facade for map, ingest, review, grow, connect, memory search, context export, calibr, and doctor |
| `guide_next_steps` | Show the next safe human-readable step |
| `index_all` | Index the Markdown workspace into `.linza/linza.db` |
| `search` | Semantic search across notes |
| `read_file` | Read a vault file |
| `get_stats` | Sidecar statistics |
| `scan_vault` | Read-only vault diagnostic |
| `build_review_apply_queue` | Build cards with stable `rq-*` IDs |
| `approve_review_queue_items` | Dry-run or apply selected review cards |
| `list_approved_items` | List accepted items |
| `explain_node` | Explain one node: links, bridges, and warnings |
| `explain_relationship` | Explain a relation between two nodes |
| `who_depends` | Show dependencies and neighbors |
| `show_flow` | Find a route or flow between nodes |
| `create_context_pack` | Export a compact context packet for an agent |

The advanced surface exists for local development and compatibility:

```powershell
$env:LINZA_TOOL_SURFACE="advanced"
```

See the full [Tool Catalog](LINZA_TOOL_CATALOG.md).

---

## Artifact Inputs

Current text-like inputs:

- pasted text;
- local `.md`;
- local `.txt`;
- local `.json`;
- local `.docx`;
- local `.xlsx`;
- local `.pdf` when `pypdf` or `PyPDF2` is installed.

Logs do not need a special file format: paste them as text or save them as
`.txt`. LINZA does not open web pages by itself. The agent uses its own browser
or web-fetch tool, extracts readable text, and passes it to LINZA as
`source_kind="web_article"` or `source_kind="browser_capture"`.

---

## Safety Model

LINZA is a local, review-gated sidecar:

- source note bodies are not changed during indexing, analysis, or import;
- raw artifacts stay in local SQLite storage;
- generated reports write only under `.linza/reports`;
- context packs write only under `.linza/context-packs`;
- visible YAML edits are compact and require explicit review/apply;
- hierarchy, causal links, memory, calibr lessons, and approvals stay in the
  sidecar unless the human asks for export.

LINZA is not a browser automation server, cloud memory, or an autopilot that
silently rewrites rules, skills, memory, or notes.

---

## Agent Pack

The repository includes portable instructions for agents:

```text
agent-pack/skills/linza-operator/SKILL.md
agent-pack/skills/linza-operator/references/workflows.md
agent-pack/skills/linza-operator/references/safety-policy.md
agent-pack/skills/linza-operator/references/tool-audience.md
```

The skill tells an agent what to show humans, when to use `agent_workspace`, how
to handle URLs through an external browser/web-fetch tool, and why apply actions
must be dry-run or exact-ID gated.

---

## Example And Verification

The synthetic private-safe example pack lives in:

```text
examples/sample-vault/
examples/artifacts/
examples/expected/
```

Run the full regression suite:

```powershell
python -m unittest
```

Run the example-pack regression:

```powershell
python -m unittest test_agent_workspace.AgentWorkspaceTests.test_examples_sample_pack_runs_end_to_end
```

Current tests cover MCP surface registration, artifact flow, review-card
filtering, generated-write safety, the example pack, and calibr trace review.

---

## Environment Variables

| Variable | Description |
|---|---|
| `LINZA_VAULT` | Path to the Markdown workspace or vault |
| `LINZA_EMBED_PROVIDER` | `hash` (offline default), `openai`, or `ollama` |
| `LINZA_EMBED_URL` | Embeddings API URL |
| `LINZA_EMBED_MODEL` | Embedding model name or hash dimension |
| `LINZA_EMBED_KEY` | Optional key for an OpenAI-compatible embeddings API |
| `LINZA_BRIDGE_THRESHOLD` | Semantic bridge threshold; default `0.55` |
| `LINZA_DEFAULT_PROFILE` | Default search profile name; default `general` |
| `LINZA_TOOL_SURFACE` | `default` (15 tools) or `advanced` (full surface) |

---

<sub>Cosines do not converge because everything is the same. They converge when meaning finds its angle.</sub>

<!-- mcp-name: io.github.semiotronika/linza-mcp -->
