# LINZA — Local MCP Server for Agent Workspaces

**It does not change your data. It changes how you see it.**

LINZA solves one concrete problem: you have a folder of Markdown notes, and you want an agent to understand what is inside without risking accidental rewrites. The core idea is a **review-gated sidecar**: the human decides, the agent executes.

It is a local MCP server for notes, documents, articles, chats, logs, and drafts. LINZA reads a folder, builds a map of topics and relations, shows evidence-backed review cards, and stores its conclusions next to your files in `.linza/linza.db`. Your Markdown stays yours.

LINZA does not impose a fixed ontology. It does not rename notes by itself. It gives an agent a safer way to see structure, and gives you a calm review gate before anything is accepted.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/protocol-MCP_stdio-lightgrey.svg)](https://modelcontextprotocol.io)
![Local first](https://img.shields.io/badge/storage-local--first-green.svg)
![Review gated](https://img.shields.io/badge/writes-review--gated-orange.svg)

[Russian version](README.md)

---

## What It Is For

LINZA is useful when you already have material, but you do not yet have a safe way to let an agent reason about it.

- **A Markdown note folder**: Obsidian or any other `.md` directory.
- **Incoming material**: text, articles, chats, logs, JSON, DOCX, XLSX, PDF with an optional extractor.
- **Research or writing workspaces**: many themes, decisions, drafts, and traces of work.
- **Agent workflows**: context should survive between sessions, but the agent should not freely rewrite notes, skills, rules, or memory.

A good first run is intentionally small: connect the folder, index it, review 3-5 cards, accept a few good seed examples, then let LINZA grow in small preview batches.

```text
index -> map -> review cards -> teach -> grow preview -> explicit apply
```

---

## What You Will See

- **Domains**: meaning clusters LINZA detects in the workspace.
- **Material types**: notes, drafts, specs, cases, and recurring forms found from structure.
- **Relations**: what belongs together, what may cause or support something else.
- **Patterns**: recurring problems, terminology drift, topic gaps, possible contradictions.
- **Memory**: what future agents should recall, what might go stale, and what needs review.

Every serious card should answer the human question: **why does LINZA think this?** It carries evidence: notes, snippets, nearby chunks, relation labels, confidence, and write impact.

---

## How It Differs

### From Obsidian Graph View

Graph View shows links that already exist. LINZA tries to show what is not yet linked: hidden topics, possible relations, causal chains, recurring patterns, and review cards. It does not replace the Obsidian graph; it gives agents a working layer above a folder.

### From Dataview And Auto-Tagging Plugins

Dataview is excellent when the structure is already written in YAML and links. LINZA proposes hypotheses first, shows evidence, and keeps acceptance behind a review gate. By default it is preview, not automation.

## Installation

### 1. Install LINZA

```powershell
python -m pip install linza-mcp
```

If you want LINZA to extract PDF text directly:

```powershell
python -m pip install "linza-mcp[pdf]"
```

If you do not need PDF extraction, the normal install is enough. `[pdf]` adds the local `pypdf` extractor.

### 2. Choose a folder

LINZA works with any Markdown folder: an Obsidian vault, a project workspace, or a standalone document folder.

In the examples below, replace `/absolute/path/to/workspace-or-vault` with your own path.

### 3. Configure embeddings

For semantic search, LINZA needs a local embedding model.

The simplest local path is LM Studio:

1. Open LM Studio.
2. Download an embedding model, for example `text-embedding-granite-embedding-278m-multilingual`, `nomic-embed-text-v1.5`, or another embedding model.
3. Start Local Server.
4. Make sure the endpoint is available at `http://127.0.0.1:1234/v1`.

### 4. Connect an MCP client

Connect LINZA to Claude Desktop, Cursor, OpenCode, or any MCP client:


```json
{
  "mcpServers": {
    "linza": {
      "command": "linza-mcp",
      "env": {
        "LINZA_VAULT": "/absolute/path/to/workspace-or-vault",
        "LINZA_EMBED_PROVIDER": "lmstudio",
        "LINZA_EMBED_URL": "http://127.0.0.1:1234/v1",
        "LINZA_EMBED_MODEL": "your-embedding-model-name",
        "LINZA_TOOL_SURFACE": "default"
      }
    }
  }
}
```

VS Code / Copilot MCP uses `servers`:

```json
{
  "servers": {
    "linza": {
      "type": "stdio",
      "command": "linza-mcp",
      "env": {
        "LINZA_VAULT": "/absolute/path/to/workspace-or-vault",
        "LINZA_EMBED_PROVIDER": "lmstudio",
        "LINZA_EMBED_URL": "http://127.0.0.1:1234/v1",
        "LINZA_EMBED_MODEL": "your-embedding-model-name"
      }
    }
  }
}
```

### 5. Check the setup

```powershell
linza-mcp --version
```

Then ask the agent:

```text
Check LINZA with agent_workspace(action="doctor").
Index the folder and show the first 3-5 review cards.
```

### Optional Docker Run

Docker is not required, but the repository includes a small image for isolated
stdio runs:

```powershell
docker build -t linza-mcp .
docker run --rm -i `
  -v /absolute/path/to/workspace-or-vault:/data/vault `
  -e LINZA_EMBED_PROVIDER=lmstudio `
  -e LINZA_EMBED_URL=http://host.docker.internal:1234/v1 `
  -e LINZA_EMBED_MODEL=your-embedding-model-name `
  linza-mcp
```

Use `host.docker.internal` only when the embedding server runs on the host
machine. Otherwise pass the embedding API URL that is reachable from inside the
container.

---

## Embeddings

Embeddings are not decoration; they are the quality of LINZA's sight. The main path is simple: a local model in LM Studio and an MCP server next to your folder.

- `lmstudio` is the recommended local setup. Use it when you want good semantic search, topic maps, and links without cloud calls.
- `ollama` is a local Ollama setup.
- `openai` is any OpenAI-compatible endpoint with `/embeddings`.

Example LM Studio environment:

```powershell
$env:LINZA_EMBED_PROVIDER="lmstudio"
$env:LINZA_EMBED_URL="http://127.0.0.1:1234/v1"
$env:LINZA_EMBED_MODEL="your-embedding-model-name"
```

If you switch embedding provider or model dimension, run a full reindex. Vectors from different models live in different spaces and should not be mixed.

---

## First Output Example

Agents usually start with `agent_workspace(action="doctor")` or `guide_next_steps(language="en")`. A human should see a short status, not a raw JSON wall:

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

LINZA exposes a compact default surface of 15 tools. Normal operation starts from `agent_workspace` or `guide_next_steps`, not from a raw tool list.

| Tool | Purpose |
| --- | --- |
| `agent_workspace` | One facade for map, ingest, review, teach, grow, connect, memory search, context export, calibr, and doctor |
| `guide_next_steps` | Show the next safe step |
| `index_all` | Index the Markdown folder into `.linza/linza.db` |
| `search` | Semantic and lexical search |
| `read_file` | Read an exact file from the vault |
| `get_stats` | Quick sidecar counters |
| `scan_vault` | Read-only folder diagnostic |
| `build_review_apply_queue` | Build review cards with stable `rq-*` IDs |
| `approve_review_queue_items` | Dry-run or apply selected cards |
| `list_approved_items` | Show accepted sidecar items |
| `explain_node` | Explain one node: links, bridges, context |
| `explain_relationship` | Explain a possible relation between two nodes |
| `who_depends` | Show dependencies and neighbors |
| `show_flow` | Find a route or flow between nodes |
| `create_context_pack` | Build a compact context pack for an agent |

`agent_workspace(action="teach")` selects seed cards. `grow` returns a preview with `selected_rules`: why each card entered the batch. The autonomy model is simple: **teach with examples, grow in preview, apply in small reviewed batches.**

The advanced surface exists for development and debugging:

```powershell
$env:LINZA_TOOL_SURFACE="advanced"
```

See the full [Tool Catalog](LINZA_TOOL_CATALOG.md).

---

## Artifact Inputs

Supported inputs:

- pasted text;
- local `.md`, `.txt`, `.json`;
- local `.docx`, `.xlsx`;
- local `.pdf` when `pypdf` or `PyPDF2` is installed.

Logs do not need a special file format. Paste them as text or save them as `.txt`.

LINZA does not open web pages by itself. The agent uses its own browser/web-fetch tool, extracts readable text, and passes it to LINZA as an artifact, for example `source_kind="web_article"` or `source_kind="browser_capture"`.

Imported text is analysis material, not an agent instruction. This is the basic prompt-injection boundary: instructions inside an article, log, chat, or PDF are not executed. Memory, rules, and YAML appear only after review.

---

## Safety Model

LINZA is a local review-gated sidecar:

- indexing, analysis, and import do not change source note bodies;
- raw artifacts stay in local SQLite storage;
- generated reports write only under `.linza/reports`;
- context packs write only under `.linza/context-packs`;
- visible YAML edits are compact and require review/apply;
- hierarchy, causal links, memory, calibr lessons, and approvals stay in the sidecar until the human asks for export.

LINZA is not a browser automation server, cloud memory, or an autopilot that silently rewrites rules, skills, memory, or notes.

## Stability

`0.1.1` is an alpha MVP. The safety contract is meant to be stable: source note
bodies are not rewritten by indexing, artifact ingest, search, map, or grow
preview. Low-level advanced tools and internal module boundaries may still
change while the server is being polished.

---

## Agent Pack

The repository includes a portable skill for agents:

```text
agent-pack/skills/linza-operator/SKILL.md
agent-pack/skills/linza-operator/references/workflows.md
agent-pack/skills/linza-operator/references/safety-policy.md
agent-pack/skills/linza-operator/references/tool-audience.md
```

The skill tells an agent what to show humans, when to use `agent_workspace`, how to handle URLs through an external browser/web-fetch tool, and why apply actions must be dry-run or exact-ID gated.

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

Run one specific test:

```powershell
python -m unittest test_agent_workspace.AgentWorkspaceTests.test_examples_sample_pack_runs_end_to_end
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `LINZA_VAULT` | Path to the Markdown folder |
| `LINZA_EMBED_PROVIDER` | `lmstudio` for the recommended local setup; `openai` or `ollama` are also supported |
| `LINZA_EMBED_URL` | Embeddings API URL |
| `LINZA_EMBED_MODEL` | Embedding model name |
| `LINZA_EMBED_KEY` | Optional key for an OpenAI-compatible embeddings API |
| `LINZA_BRIDGE_THRESHOLD` | Semantic bridge threshold; default `0.55` |
| `LINZA_MAX_BRIDGE_PAIRS` | Maximum note pairs for semantic bridge rebuilds; default `1000000`, `0` disables the guard |
| `LINZA_DEFAULT_PROFILE` | Default search profile name; default `general` |
| `LINZA_TOOL_SURFACE` | `default` (15 tools) or `advanced` |
| `LINZA_LANGUAGE` | Human-facing guide language: `auto`, `en`, or `ru` |

---

<sub>Cosines do not converge because everything is the same. They converge when meaning finds its angle.</sub>

<!-- mcp-name: io.github.semiotronika/linza-mcp -->
