# LINZA - Local MCP Server for Agent Workspaces

> *It does not change your data. It changes how you see it.*

LINZA works with Obsidian, Markdown folders, documents, articles, chats, logs, and drafts. It is useful when the material is already too large for "just look through it", but you still do not want an agent freely rewriting your notes.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/protocol-MCP_stdio-lightgrey.svg)](https://modelcontextprotocol.io)
![Local first](https://img.shields.io/badge/storage-local--first-green.svg)
![Review gated](https://img.shields.io/badge/writes-review--gated-orange.svg)

[Russian version](README.md)

LINZA reads a folder, builds a local SQLite sidecar at `.linza/linza.db`, and gives the agent a working map: which themes exist, which material types repeat, which notes may be connected, where cause/effect chains appear, and what future sessions may need to remember.

Your source files remain yours. LINZA does not rewrite notes during indexing, does not turn a raw log into a rule, and does not teach the agent behind your back. It turns hypotheses into short review items: the human decides, the agent executes.

---

## What LINZA Is For

Search helps find a word. LINZA helps an agent understand the working situation.

You may have:

- an Obsidian vault with notes and drafts;
- a project folder with Markdown documents;
- articles, PDFs, DOCX, XLSX, JSON, chats, and logs;
- decision traces: problem, discussion, action, result;
- rules that future agents should remember, but should not invent on their own.

LINZA turns that into a careful working layer next to your files. First it shows a map and evidence. Then you approve a few good examples. Only after that can the agent continue in small, reviewable batches.

```text
doctor -> index -> map -> review items -> teach -> grow preview -> explicit apply
```

---

## What Appears After The First Run

LINZA does not try to become the owner of your knowledge base. It collects a few concrete things that help agents work more calmly.

1. **Folder map**
   How many notes were found, whether the index is fresh, which areas are visible, and which materials are waiting for review.

2. **Areas**
   Broad semantic groups. Their names are drafts until a human accepts or renames them.

3. **Material types**
   Notes, drafts, specifications, research notes, cases, logs, rules, and other recurring forms found in the folder.

4. **Relations**
   Possible neighbors, hierarchy, cause/effect, and routes between nodes. LINZA should show not only "connect these", but also "why".

5. **Memory for future agents**
   Short candidates: what to remember, when to recall it, where it may become stale, and what is uncertain.

6. **Context packs**
   Compact packets for agents: not the whole vault, but selected context with sources and boundaries.

---

## What Review Looks Like

LINZA tries not to show a human raw JSON or a long tool list. A normal first response should look more like this:

Internally, each review item is still structured data with an ID, evidence, and a preview/apply payload. Externally, LINZA returns ready-to-display lines through `display` and `human_message`, so an agent can write a clean answer instead of dumping JSON.

```text
LINZA is ready

Material:
- 42 notes indexed
- 3 incoming artifacts waiting for review
- sidecar: .linza/linza.db

Next step:
1. Review discovered areas
2. Accept, rename, or skip 3-5 review items
3. Nothing is written without dry-run/apply

Review item:
Proposal: connect "Retrieval Quality Note" and "Source Policy"
Why: shared vocabulary, review-flow references, nearby chunks
Write impact: none yet; accepting records a sidecar relation
```

A good review item always answers the human question: **why does LINZA think this?** It should carry sources, snippets/chunks, relation type, confidence, and a clear write impact.

---

## How It Differs

Obsidian Graph View shows links that already exist. LINZA looks for what has not been written down yet: hidden topics, recurring material types, possible relations, and gaps.

Dataview and auto-tagging are useful when the structure already lives in YAML. LINZA starts earlier: it proposes hypotheses, shows evidence, and keeps acceptance behind a review gate.

It is not an autopilot for rewriting a vault. It is a safer way to give an agent sight and memory without giving it permission to silently change meaning.

---

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

For semantic search, LINZA needs an embedding model. The simplest local path is LM Studio:

1. Open LM Studio.
2. Download an embedding model, for example `text-embedding-granite-embedding-278m-multilingual`, `nomic-embed-text-v1.5`, or another suitable embedding model.
3. Start Local Server.
4. Make sure the endpoint is available at `http://127.0.0.1:1234/v1`.

### 4. Connect an MCP client

Claude Desktop, Cursor, OpenCode, and other MCP clients usually use this format:

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
Index the folder and show the first 3-5 review items.
```

### Optional Docker Run

Docker is not required, but the repository includes a small image for isolated stdio runs:

```powershell
docker build -t linza-mcp .
docker run --rm -i `
  -v /absolute/path/to/workspace-or-vault:/data/vault `
  -e LINZA_EMBED_PROVIDER=lmstudio `
  -e LINZA_EMBED_URL=http://host.docker.internal:1234/v1 `
  -e LINZA_EMBED_MODEL=your-embedding-model-name `
  linza-mcp
```

Use `host.docker.internal` only when the embedding server runs on the host machine. Otherwise pass the embedding API URL that is reachable from inside the container.

---

## Embeddings

Embeddings are the quality of LINZA's sight. The main path is simple: a local model in LM Studio and an MCP server next to your folder.

- `lmstudio` is the recommended local setup for semantic search, topic maps, and links without cloud calls.
- `ollama` is a local Ollama setup.
- `openai` is any OpenAI-compatible endpoint with `/embeddings`.

Example LM Studio environment:

```powershell
$env:LINZA_EMBED_PROVIDER="lmstudio"
$env:LINZA_EMBED_URL="http://127.0.0.1:1234/v1"
$env:LINZA_EMBED_MODEL="your-embedding-model-name"
```

If you switch embedding provider, model, or dimension, run a full reindex. LINZA checks the embedding signature and stops graph/search workflows when the sidecar is stale or contains mixed vector spaces.

---

## Artifact Inputs

LINZA can accept material that has not yet become a note:

- pasted text;
- local `.md`, `.txt`, `.json`;
- local `.docx`, `.xlsx`;
- local `.pdf` when `pypdf` or `PyPDF2` is installed.

LINZA does not open web pages by itself. The agent uses its own browser/web-fetch tool, extracts readable text, and passes it to LINZA as an artifact, for example `source_kind="web_article"` or `source_kind="browser_capture"`.

Imported text is analysis material, not an agent instruction. This is the prompt-injection boundary: instructions inside an article, log, chat, or PDF are not executed. Memory, rules, and YAML appear only after review.

---

## MCP Tools

By default, LINZA exposes only 7 MCP tools. That is enough for normal work: check readiness, index the folder, search, read a file, get basic counts, scan the vault, and let `agent_workspace` lead the rest.

| Tool | Purpose |
| --- | --- |
| `agent_workspace` | One facade for doctor, map, ingest, review, teach, grow, connect, memory search, context export, and calibr |
| `guide_next_steps` | Show the next safe step in plain language |
| `index_all` | Index the Markdown folder into `.linza/linza.db` |
| `search` | Semantic and lexical search |
| `read_file` | Read an exact file from the vault |
| `get_stats` | Quick sidecar counters |
| `scan_vault` | Read-only folder diagnostic |

The other tools are not gone. They are hidden from the default surface:

- workflow actions are available through `agent_workspace`;
- low-level reports and debugging commands are available with `LINZA_TOOL_SURFACE=advanced`;
- direct `write_file` is advanced because LINZA should not encourage agents to write note bodies by default.

`agent_workspace(action="teach")` selects seed examples. `grow` returns a preview with `selected_rules`: why each review item entered the batch. The autonomy model is simple: **teach with examples, grow in preview, apply in small reviewed batches.**

If you accepted the wrong thing, revoke it softly:

```text
agent_workspace(action="history")
agent_workspace(action="revoke_approval", approval_id=17, dry_run=false)
```

LINZA does not erase the old row and does not try to automatically revert YAML. It marks the approval as revoked, stops using it as an active example, and keeps the action visible in history.

The advanced surface exists for development and debugging:

```powershell
$env:LINZA_TOOL_SURFACE="advanced"
```

See the full [Tool Catalog](LINZA_TOOL_CATALOG.md).

---

## Safety Model

LINZA is a local review-gated sidecar:

- indexing, analysis, search, and import do not change source note bodies;
- `index_all` and service operations write to `.linza/linza.db`;
- search may store search history in the sidecar;
- raw artifacts stay in local SQLite storage;
- generated reports write only under `.linza/reports`;
- context packs write only under `.linza/context-packs`;
- visible YAML edits are compact and require review/apply;
- hierarchy, causal links, memory, calibr lessons, and approvals stay in the sidecar until the human asks for export or apply;
- `agent_workspace(action="history")` shows accepted and revoked sidecar decisions;
- `agent_workspace(action="revoke_approval")` softly revokes an approval: the history remains, but active learning, map, and graph helpers ignore it;
- source-index preflight stops `map`, `teach`, `grow`, and `connect` when files changed after indexing.

LINZA is not a browser automation server, cloud memory, or an autopilot that silently rewrites rules, skills, memory, or notes.

---

## Agent Instructions

The repository includes a portable operator skill:

```text
agent-pack/skills/linza-operator/SKILL.md
agent-pack/skills/linza-operator/references/workflows.md
agent-pack/skills/linza-operator/references/safety-policy.md
agent-pack/skills/linza-operator/references/tool-audience.md
```

It tells an agent how to start with `doctor`, when to show review items, how to handle URLs through an external browser/web-fetch tool, and why apply actions must be dry-run first and exact-ID gated.

---

## Stability

`0.1.5` is an alpha MVP. The main safety contract is meant to be stable: indexing, artifact ingest, search, map, and grow preview do not rewrite source note bodies. Low-level advanced tools and internal module boundaries may still change while the server is being polished.

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
python -m unittest discover -s tests
```

Run one specific test:

```powershell
python -m unittest tests.test_agent_workspace.AgentWorkspaceTests.test_examples_sample_pack_runs_end_to_end
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
| `LINZA_TOOL_SURFACE` | `default` (7 tools) or `advanced` |
| `LINZA_LANGUAGE` | Language for guide/status/review-route output in `guide_next_steps`: `auto`, `en`, or `ru` |

---

## Links

- [semiotronika.ru](https://semiotronika.ru)
- [PyPI](https://pypi.org/project/linza-mcp/)
- [GitHub](https://github.com/Semiotronika/LINZA-MCP)

MCP Registry ID: `io.github.Semiotronika/LINZA-MCP`

MIT License © 2026 Semiotronika

*Cosines are computed. Syntax changes. Semantics remains.*

<!-- mcp-name: io.github.Semiotronika/LINZA-MCP -->
