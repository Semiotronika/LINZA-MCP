# LINZA Tool Catalog

Status: v0 operator catalog.

Last updated: 2026-05-26.

LINZA has many callable MCP tools because the server has several layers:
indexing, graph inspection, review queues, reports, artifact inbox, and calibr
trace review. That does not mean a user or a normal agent should see all of
them.

The default MCP surface exposes 7 tools. The rest stay available in the
advanced surface or through `agent_workspace`.

## Default Tools

These are visible in normal `tools/list`.

| Tool | Who Uses It | Why It Exists | Writes |
|---|---|---|---|
| `guide_next_steps` | Human via agent | Explains the current onboarding stage and next safe action. | No |
| `agent_workspace` | Agent | Main facade for doctor, map, review, apply, teach, grow, connect, memory search, context export, artifact inbox, and calibr. | Sidecar; growth/apply actions are dry-run by default |
| `index_all` | Agent setup | Builds the sidecar index for the vault. | `.linza/linza.db` |
| `search` | Agent | Finds relevant notes/chunks by semantic and lexical search. | Search history in sidecar |
| `read_file` | Agent | Reads exact Markdown note text before answering or applying YAML. | No |
| `get_stats` | Agent | Quick health counts for indexed files, profiles, bridges, and active profile. | No |
| `scan_vault` | Agent | Read-only vault audit: broken links, orphans, duplicates, thin/long notes, properties. | No |

## Advanced Index/Search Tools

These are useful for debugging or local workflows, but not part of the normal
v0 surface.

| Tool | Why It Exists | Why Hidden By Default |
|---|---|---|
| `index_file` | Reindex one note or synthetic content after a local change. | `index_all` and `agent_workspace` cover most normal flows. |
| `suggest_links` | Suggest semantic neighbors for one note. | `agent_workspace(action="connect")` and review items are easier to understand. |
| `get_bridges` | Read raw stored semantic bridge rows for a note. | Mostly debugging internals. |
| `calibrate_embeddings` | Inspect raw vs centered embedding quality and anisotropy. | Useful for maintainers, confusing for first contact. |
| `check_rule` | Run read-only graph/rule health checks. | Useful for audits, but not a first-contact action. |

## Advanced Profiles

Profiles are persistent search perspectives built from keywords and embeddings.
They are not core v0 because the real user need is still being tested.

| Tool | Why It Exists | Current Decision |
|---|---|---|
| `create_profile` | Create a named search perspective from keywords. | Advanced/internal. |
| `list_profiles` | List stored profiles. | Advanced/internal. |
| `switch_profile` | Set the active default profile. | Advanced/internal. |
| `get_profile` | Inspect profile metadata and inheritance chain. | Advanced/internal. |

## Advanced Draft And Tag Helpers

These expose pieces of the onboarding engine directly. Normal agents should
prefer `guide_next_steps` and `agent_workspace`.

| Tool | Why It Exists | Why Hidden By Default |
|---|---|---|
| `draft_vault_map` | Builds the raw first-pass map: domains, material types, hierarchy, event flow, memory, lenses. | Too large/noisy as a first-contact response. |
| `build_review_apply_queue` | Creates stable `rq-*` review items with dry-run approval payloads and human display lines. | Normal agents should reach this through `agent_workspace` or `guide_next_steps`. |
| `audit_tags` | Audits tag vocabulary, aliases, noisy inline tags, and long-tail tags. | Tag cleanup is not core v0 for everyone. |
| `suggest_tag_candidates` | Suggest tags for one note from chunks and accepted vocabulary. | Better as part of review items later. |
| `suggest_properties` | Suggest compact LINZA YAML for one note. | Low-level preview, not a human entry point. |

## Apply Gates

These can change visible notes or accepted sidecar state. They stay advanced or
hidden unless the agent is performing an explicit reviewed action through the
facade.

| Tool | Why It Exists | Safety Rule |
|---|---|---|
| `write_file` | Create a new Markdown note or explicitly overwrite generated content. | Dry-run by default; hidden because LINZA should not encourage note-body writes. |
| `patch_properties` | Patch compact LINZA frontmatter while preserving the note body. | Dry-run by default; YAML only. |
| `approve_draft_item` | Apply one manually constructed domain/type/hierarchy/causal/memory item. | Low-level compatibility path; prefer stable review IDs. |
| `approve_review_queue_items` | Applies exact accepted `rq-*` IDs, preview first. | Hidden by default; `agent_workspace` routes reviewed apply actions. |
| `apply_learned_review_queue` | Select review items using accepted examples. | Assisted mode only; preview by default. |
| `list_approved_items` | Shows accepted sidecar approvals. | Useful for audits, but not a first-contact tool. |

## Optional Report Builders

Reports are generated artifacts. They are not required for normal operation.
When written, they are restricted to `.linza/reports`.

| Tool | Report |
|---|---|
| `build_bases_plan` | Obsidian Bases planning report. |
| `build_yaml_suggestions` | Markdown report of suggested YAML across notes. |
| `build_tag_vocabulary_report` | Tag vocabulary audit report. |
| `build_review_queue` | General human-readable review report. |
| `build_diagnostic_report` | Saved vault diagnostic snapshot. |
| `build_semantic_links` | Saved semantic link candidate report. |
| `create_context_pack` | Context packet for another agent or writing task. |

## Advanced Graph And Explanation Tools

These remain useful, but the default path is `agent_workspace(action="connect")`
or a plain user request.

| Tool | Why It Exists |
|---|---|
| `explain_node` | Explains one note: graph context, bridges, role/material hints, review context. |
| `explain_relationship` | Explains a possible relationship between two notes. |
| `who_depends` | Shows backlinks, dependents, dependencies, and semantic neighbors. |
| `show_flow` | Traces a route between notes or from a query into the graph. |

## Why Keep Advanced Tools At All?

- They preserve compatibility with existing tests and local scripts.
- They let maintainers debug one layer without going through the whole facade.
- They are useful for development, but not good product surface.

The product interface is the workflow:

```text
doctor/guide -> ingest/index/search -> review items -> explicit apply -> context export
```

Depth features now live inside the workflow rather than as extra tools:

- `agent_workspace(action="map")` gives a compact read-only workspace snapshot
  for humans and a structured next-action map for agents.
- `agent_workspace(action="review_next")` and review queues include `display`
  and `human_message`, so an agent can show readable text instead of raw JSON.
- `agent_workspace(action="teach")` selects a small read-only batch of seed
  items so the human can teach LINZA what good domains, types, hierarchy, and
  causal links look like.
- `agent_workspace(action="grow")` lets an agent continue building the knowledge
  base after seed review by selecting review items supported by accepted examples and
  local learning rules.
- `agent_workspace(action="history")` shows accepted and revoked approvals in a
  human-readable action log.
- `agent_workspace(action="revoke_approval")` softly revokes an approval without
  deleting the row; active learning and graph helpers stop using it.
- `analysis_stage` focuses draft maps and review queues on one stage.
- `evidence_trace` explains why a review item exists.
- `pattern_draft` surfaces review-only insights such as repeated problems,
  terminology drift, possible conflicts, and evidence gaps.
