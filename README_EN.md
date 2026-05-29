# LINZA - Local MCP Server for Agent Work with Knowledge Folders

> *It does not change your data. It changes how you see it.*

LINZA works with Obsidian vaults, Markdown folders, documents, articles, logs, and drafts. It is useful when there is already too much material and you want to understand the knowledge base, identify its main areas, and teach an agent to navigate it well.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/protocol-MCP_stdio-lightgrey.svg)](https://modelcontextprotocol.io)
![Local first](https://img.shields.io/badge/storage-local--first-green.svg)
![Review gated](https://img.shields.io/badge/writes-review--gated-orange.svg)

[Russian version](README.md)

LINZA reads a selected folder, builds a local SQLite database next to it at `.linza/linza.db`, and gives the agent a working map: which topics exist in the material, which formats repeat, which notes may be related, where cause/effect chains appear, and what may be useful in future sessions.

Source files remain untouched. LINZA does not rewrite notes during indexing, does not turn a raw log into a rule, and does not teach the agent behind your back. It turns hypotheses into short intents - proposed actions with evidence. The user decides, the agent executes.

```text
doctor -> index -> map -> review intents -> teach -> grow preview -> explicit apply
```

---

## What LINZA Is For

LINZA collects several concrete things that help agents work with a knowledge base:

1. **Folder map**
   How many notes were found, whether the index is fresh, which areas are visible, and which materials are waiting for your review.

2. **Areas**
   Large semantic groups. Their names remain drafts until you accept or rename them.

3. **Material formats**
   Logs, drafts, specifications, research notes, cases, rules, and other recurring forms found in the folder.

4. **Relations**
   Possible neighborhoods, hierarchy, cause/effect, and routes between nodes. LINZA should show not only how documents are related, but also why.

5. **Memory for future agents**
   Short candidates: what to remember, when to recall it, what is stale, and what looks uncertain.

6. **Context packs**
   Compact selections for an agent: selected context with sources, relations, and boundaries.

---

## Material Formats

A material format is the user-facing name for a recurring note form. Examples: `diagnostic log`, `decision`, `article draft`, `research note`, `specification`.

LINZA first sees only structure: length, headings, lists, links, tables, folders, and recurring signals. That means the first result may have a neutral name: `type-001`. The user can say: "these are logs". LINZA then stores the mapping `type-001 -> logs` in `.linza`.

The internal API keeps the old compatibility keys `material_type`, `type_name`, and `role`. Externally, the documentation and review cards say "format" because that is closer to how users actually think about their material.

Important boundary:

- accepting a format name records a decision in `.linza`;
- writing `role: logs` to YAML is only possible through a separate review intent;
- note text does not change.

---

## What Review Looks Like

LINZA returns information roughly like this:

```text
LINZA is ready

Material:
- 42 notes indexed
- 3 incoming artifacts waiting for review
- service database: .linza/linza.db

Next step:
1. Review discovered areas
2. Accept, rename, or skip 3-5 review intents
3. Nothing is written without a dry-run and explicit apply

Review intent:
Accept material format "diagnostic logs" from 8 examples
Why: similar structure, repeated headings, nearby chunks
What changes: the format name is stored in .linza; Markdown notes do not change
```

Internally, each intent remains a structure with an ID, evidence, and the data needed to preview the change and then confirm/write it. To you, LINZA returns ready-to-display cards so the agent can show a clear answer instead of JSON.

A good intent always answers the main question: **why does LINZA think this?** It should include sources, chunks, relation type, confidence, and an honest description of what will change after applying it.

---

## Teaching And Growth

The autonomy model is:

1. `review_next` shows cards.
2. The user accepts, renames, or skips.
3. `apply_review_items` runs dry-run first.
4. After confirmation, the selected intent is written to `.linza` or to compact YAML, if that write type supports it.
5. `teach` selects good accepted examples.
6. `grow` proposes similar intents from those examples and explains `selected_rules`, the reasons they entered the batch.

If you accepted the wrong thing, the approval can be softly revoked:

```text
agent_workspace(action="history")
agent_workspace(action="revoke_approval", approval_id=17, dry_run=false)
```

LINZA does not delete the old record and does not try to automatically roll back YAML. It marks the approval as revoked, stops using it as an active example, and keeps a trace in history.

---

## Installation

### 1. Install the package

```powershell
python -m pip install linza-mcp
```

If you need LINZA to read PDFs directly:

```powershell
python -m pip install "linza-mcp[pdf]"
```

The regular install is already enough for Markdown, TXT, JSON, DOCX, and XLSX. `[pdf]` adds the local PDF extractor `pypdf`.

### 2. Choose a folder

LINZA works with any Markdown folder: an Obsidian vault, a project workspace, or a separate folder with documents.

In the examples below, replace `/absolute/path/to/workspace-or-vault` with your own path.

### 3. Connect an MCP client

Claude Desktop, Cursor, OpenCode, and other MCP clients usually use this format:

```json
{
  "mcpServers": {
    "linza": {
      "command": "linza-mcp",
      "env": {
        "LINZA_VAULT": "/absolute/path/to/workspace-or-vault"
      }
    }
  }
}
```

VS Code / Copilot MCP uses the `servers` key:

```json
{
  "servers": {
    "linza": {
      "type": "stdio",
      "command": "linza-mcp",
      "env": {
        "LINZA_VAULT": "/absolute/path/to/workspace-or-vault"
      }
    }
  }
}
```

`LINZA_VAULT` is not required for startup: without it, the server uses `./vault`. For real work, an explicit folder is better.

### 4. Check startup

```powershell
linza-mcp --version
```

After connecting, ask the agent:

```text
Check LINZA with agent_workspace(action="doctor").
Index the folder and show the first 3-5 review intents.
```

---

## Embeddings

LINZA can start and show tools without an embedding server. Embeddings are needed for semantic search, topic maps, and relation suggestions.

The simplest local path is LM Studio:

1. Open LM Studio.
2. Download an embedding model, for example `text-embedding-granite-embedding-278m-multilingual`, `nomic-embed-text-v1.5`, or another suitable model.
3. Start Local Server.
4. Check that the endpoint is available at `http://127.0.0.1:1234/v1`.

Example LM Studio variables:

```powershell
$env:LINZA_EMBED_PROVIDER="lmstudio"
$env:LINZA_EMBED_URL="http://127.0.0.1:1234/v1"
$env:LINZA_EMBED_MODEL="your-embedding-model-name"
```

Supported providers:

- `lmstudio` - recommended local mode;
- `ollama` - local mode through Ollama;
- `openai` - any OpenAI-compatible endpoint with `/embeddings`.

If you change provider, model, or dimension, run a full reindex. LINZA checks the embedding signature and stops graph/search workflows if the sidecar is stale or contains mixed vector spaces.

---

## Main MCP Tools

By default, LINZA shows only 7 MCP tools. That is enough for normal work: check status, index the folder, search, read a file, view counters, diagnose the vault, and guide the agent through `agent_workspace`.

| Tool | Purpose |
| --- | --- |
| `agent_workspace` | One entry point for diagnostics, map, ingest, review, teaching, growth, relations, memory, and context export |
| `guide_next_steps` | Show the next safe step in plain language |
| `index_all` | Index the Markdown folder into `.linza/linza.db` |
| `search` | Semantic and lexical search |
| `read_file` | Read an exact Markdown file |
| `get_stats` | Quick service database counters |
| `scan_vault` | Folder diagnostic without writing |

Low-level tools are implementation details and are available through `agent_workspace`, so the 7-tool set is a full mode.

### `agent_workspace` Modes

| Action | Mode |
| --- | --- |
| `doctor` | Check whether LINZA is ready and what is missing |
| `map` | Build a workspace map without writing |
| `teach` | Select strong accepted examples for learning |
| `grow` | Show or apply growth from accepted examples; dry-run by default |
| `review_next` | Show the next review cards; vault cards use `rq-*`, artifact and workspace cards use `aw-*` |
| `apply_review_items` | Show or apply exact selected IDs; dry-run by default |
| `history` | Show accepted and revoked approvals |
| `revoke_approval` | Softly revoke an approval without deleting history |
| `ingest_artifacts` | Store pasted or extracted material in the sidecar |
| `analyze_inbox` | Find events, memory candidates, and knowledge fragments in artifacts |
| `connect` | Explain a possible relation between two notes or nodes |
| `search_memory` | Search reviewed memory and artifact context |
| `export_context` | Build a compact context pack for another agent |
| `record_trace` | Store structured traces of agent work, not raw chain-of-thought |
| `analyze_trace` | Analyze a stored trace for review |
| `review_calibr` | Review calibration lessons derived from traces |

For maintainers, a separate low-level mode remains available for development and debugging. Full tool description: [Tool Catalog](LINZA_TOOL_CATALOG.md).

---

## Incoming Artifacts

LINZA can accept material that has not yet become a note:

- pasted text;
- local `.md`, `.txt`, `.json`;
- local `.docx`, `.xlsx`;
- local `.pdf`, if `pypdf` or `PyPDF2` is installed.

LINZA does not browse the web by itself. The agent uses its browser, web-fetch tool, or connector, extracts readable text, and passes it to LINZA as an artifact, for example `source_kind="web_article"` or `source_kind="browser_capture"`.

Imported text is treated as material for analysis, not as an instruction for the agent. This is the prompt-injection boundary: instructions inside an article, log, chat, or PDF are not executed. Memory, rules, and YAML appear only after review.

---

## Safety Model

LINZA is a local review-gated sidecar.

| Action | Writes To | Changes Note Text? |
| --- | --- | --- |
| Indexing, analysis, search | `.linza/linza.db` | No |
| Raw artifacts | `.linza/linza.db` | No |
| Material format name | `.linza/linza.db` | No |
| `domains` or `role` in YAML | Only compact YAML after review | No |
| Hierarchy, causal links, memory, calibration lessons | `.linza/linza.db` | No |
| Reports | `.linza/reports` | No |
| Context packs | `.linza/context-packs` | No |
| `write_file` | Markdown file only on explicit request | Can create/replace a file, dry-run by default |

Additional rules:

- `review_next` writes nothing;
- `apply_review_items` is dry-run by default;
- visible YAML edits are compact and require an exact selected ID;
- `history` shows what was accepted and what was revoked;
- `revoke_approval` softly revokes an approval: history remains, but active learning and graph helpers ignore it;
- `map`, `teach`, `grow`, and `connect` stop if source files changed after indexing.

---

## Agent Instructions

The repository includes a portable operator skill:

```text
agent-pack/skills/linza-operator/SKILL.md
agent-pack/skills/linza-operator/references/workflows.md
agent-pack/skills/linza-operator/references/safety-policy.md
agent-pack/skills/linza-operator/references/tool-audience.md
```

It explains to an agent how to start with `doctor`, when to show review intents, how to work with pages through an external browser/web-fetch tool, and why apply actions must first go through dry-run and exact IDs only.

---

## Stability

LINZA is alpha. The main safety contract should remain stable: indexing, artifact import, search, map, and grow preview do not rewrite source note bodies. Low-level advanced tools and internal code boundaries may still change while the server is being polished.

---

## Verification

Run the full test suite:

```powershell
python -m unittest discover -s tests
```

---

## Environment Variables

| Variable | Required for startup? | Description |
|---|---:|---|
| `LINZA_VAULT` | No | Path to the Markdown folder; defaults to `./vault` |
| `LINZA_EMBED_PROVIDER` | No | `lmstudio` for the recommended local mode; also `openai` and `ollama` |
| `LINZA_EMBED_URL` | No | Embeddings API URL; defaults to `http://127.0.0.1:1234/v1` |
| `LINZA_EMBED_MODEL` | No | Embedding model; set before semantic indexing/search |
| `LINZA_EMBED_KEY` | No | Optional key for an OpenAI-compatible embeddings API |
| `LINZA_BRIDGE_THRESHOLD` | No | Semantic bridge threshold; default `0.55` |
| `LINZA_MAX_BRIDGE_PAIRS` | No | Maximum note pairs for semantic bridge rebuilds; default `1000000`, `0` disables the guard |
| `LINZA_DEFAULT_PROFILE` | No | Base search profile name; default `general` |
| `LINZA_LANGUAGE` | No | Language for hints and review route in `guide_next_steps`: `auto`, `ru`, `en` |

---

## Links

- [semiotronika.ru](https://semiotronika.ru)
- [PyPI](https://pypi.org/project/linza-mcp/)
- [GitHub](https://github.com/Semiotronika/LINZA-MCP)

MIT License (c) 2026 Semiotronika

*Cosines are computed. Syntax changes. Semantics remains.*

<!-- mcp-name: io.github.Semiotronika/LINZA-MCP -->
