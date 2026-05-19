# LINZA Tool Catalog

Status: v0 operator catalog, 2026-05-19.

LINZA has many callable MCP tools because the server grew from several layers:
indexing, graph inspection, review queues, reports, artifact inbox, and calibr
trace review. That does not mean a user or normal agent should see all of them.

The default MCP surface exposes 15 tools. The remaining tools are advanced,
internal, compatibility, or optional report helpers.

## Default Tools

These are visible in normal `tools/list`.

| Tool | Who Uses It | Why It Exists | Writes |
|---|---|---|---|
| `guide_next_steps` | Human via agent | Explains the current onboarding stage and next safe action. | No |
| `agent_workspace` | Agent | Main facade for workspace maps, teaching, supervised growth, artifact inbox, trace review, graph connect, memory search, review cards, apply, export, and doctor. | Sidecar; growth/apply actions are dry-run by default |
| `index_all` | Agent setup | Builds the sidecar index for the vault. | `.linza/linza.db` |
| `search` | Agent | Finds relevant notes/chunks by semantic and lexical search. | Search history in sidecar |
| `read_file` | Agent | Reads exact Markdown note text before answering or applying YAML. | No |
| `get_stats` | Agent | Quick health counts for indexed files, profiles, bridges, and active profile. | No |
| `scan_vault` | Agent | Read-only vault audit: broken links, orphans, duplicates, thin/long notes, properties. | No |
| `build_review_apply_queue` | Agent for human review | Creates stable `rq-*` review cards with dry-run approval payloads. | Optional report under `.linza/reports` |
| `approve_review_queue_items` | Agent after human selection | Applies exact accepted `rq-*` IDs, preview first. | YAML for approved domain/type cards or sidecar approvals |
| `list_approved_items` | Agent | Shows what has already been accepted into the sidecar. | No |
| `explain_node` | Agent | Explains one note: graph context, bridges, role/material hints, review context. | No |
| `explain_relationship` | Agent | Explains a possible relationship between two notes. | No |
| `who_depends` | Agent | Shows backlinks, dependents, dependencies, and semantic neighbors. | No |
| `show_flow` | Agent | Traces a route between notes or from a query into the graph. | No |
| `create_context_pack` | Agent | Builds a compact context packet for another agent or writing task. | Optional file under `.linza/context-packs` |

## Advanced Index/Search Tools

These are useful for debugging or local workflows, but not part of the normal
v0 surface.

| Tool | Why It Exists | Why Hidden By Default |
|---|---|---|
| `index_file` | Reindex one note or synthetic content after a local change. | `index_all` and `agent_workspace` cover most normal flows. |
| `suggest_links` | Suggest semantic neighbors for one note. | `explain_node`, `show_flow`, and review cards are easier to understand. |
| `get_bridges` | Read raw stored semantic bridge rows for a note. | Mostly debugging internals. |
| `calibrate_embeddings` | Inspect raw vs centered embedding quality and anisotropy. | Useful for maintainers, confusing for first contact. |
| `check_rule` | Run read-only graph/rule health checks. | Useful for audits, but not a first-contact action. |

## Advanced Profiles

Profiles are persistent search perspectives built from keywords and embeddings.
They are not core v0 because the real user need is not proven yet.

| Tool | Why It Exists | Current Decision |
|---|---|---|
| `create_profile` | Create a named search perspective from keywords. | Advanced/internal. |
| `list_profiles` | List stored profiles. | Advanced/internal. |
| `switch_profile` | Set the active default profile. | Advanced/internal. |
| `get_profile` | Inspect profile metadata and inheritance chain. | Advanced/internal. |

## Advanced Draft And Tag Helpers

These expose pieces of the onboarding engine directly. Normal agents should
prefer `guide_next_steps`, `build_review_apply_queue`, and `agent_workspace`.

| Tool | Why It Exists | Why Hidden By Default |
|---|---|---|
| `draft_vault_map` | Builds the raw first-pass map: domains, material types, hierarchy, event flow, memory, lenses. | Too large/noisy as a first-contact response. |
| `audit_tags` | Audits tag vocabulary, aliases, noisy inline tags, and long-tail tags. | Tag cleanup is not core v0 for everyone. |
| `suggest_tag_candidates` | Suggest tags for one note from chunks and accepted vocabulary. | Better as part of review cards later. |
| `suggest_properties` | Suggest compact LINZA YAML for one note. | Low-level preview, not a human entry point. |

## Apply Gates

These can change visible notes or accepted sidecar state. They stay advanced or
hidden unless the agent is performing an explicit reviewed action.

| Tool | Why It Exists | Safety Rule |
|---|---|---|
| `write_file` | Create a new Markdown note or explicitly overwrite generated content. | Dry-run by default; blocks existing notes unless overwrite is explicit. |
| `patch_properties` | Patch compact LINZA frontmatter while preserving the note body. | Dry-run by default; YAML only. |
| `approve_draft_item` | Apply one manually constructed domain/type/hierarchy/causal/memory item. | Low-level compatibility path; prefer stable review IDs. |
| `apply_learned_review_queue` | Select review cards using accepted examples. | Assisted mode only; preview by default. |

`approve_review_queue_items` is default-visible because it is the safer exact-ID
path from stable review cards.

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

## Why Keep Advanced Tools At All?

- They preserve compatibility with existing tests and local scripts.
- They let maintainers debug one layer without going through the whole facade.
- They are useful for development, but not good product surface.

The product interface is the workflow:

```text
doctor/guide -> ingest/index/search -> review cards -> explicit apply -> context export
```

Depth features now live inside the workflow rather than as extra tools:

- `agent_workspace(action="map")` gives a compact read-only workspace snapshot
  for humans and a structured next-action map for agents.
- `agent_workspace(action="teach")` selects a small read-only batch of seed
  cards so the human can teach LINZA what good domains, types, hierarchy, and
  causal links look like.
- `agent_workspace(action="grow")` lets an agent continue building the knowledge
  base after seed review by selecting cards supported by accepted examples and
  local learning rules. The response includes `selected_rules` so the agent can
  explain why each card entered the preview.
- `analysis_stage` focuses `draft_vault_map` and review queues on one stage.
- `evidence_trace` explains why a card exists.
- `pattern_draft` surfaces review-only insights such as repeated problems,
  terminology drift, possible conflicts, and evidence gaps.
