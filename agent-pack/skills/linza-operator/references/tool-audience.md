# LINZA Tool Audience

The canonical map is `TOOL_AUDIENCE` in `linza_mcp/operator.py`.

The default MCP `tools/list` is intentionally compact and is defined by
`DEFAULT_MCP_TOOLS`. `ADVANCED_MCP_TOOLS` remain callable for compatibility and
development, but are hidden unless the server is started with
`LINZA_TOOL_SURFACE=advanced`.

## User Entry

- `guide_next_steps`
- `agent_workspace(action="doctor")`
- review items from `build_review_apply_queue`
- review items from `agent_workspace(action="review_next")`

## Agent Facade

- `agent_workspace`

Use it for artifact inbox, trace review, memory search, review items, apply,
history, soft revoke, supervised growth, and context export.

## Agent Read Tools

Default read/explain tools:

- `search`
- `read_file`
- `explain_node`
- `explain_relationship`
- `who_depends`
- `show_flow`
- `scan_vault`
- `get_stats`
- `list_approved_items`

Advanced/internal read helpers:

- `suggest_links`
- `check_rule`
- `draft_vault_map`
- `audit_tags`
- `suggest_tag_candidates`
- `suggest_properties`
- profile read tools

## Agent Setup Tools

- `index_all`
- `index_file` (advanced)
- `create_profile`
- `switch_profile`
- `calibrate_embeddings`

Profiles are advanced/internal for v0. Prefer ordinary search and context
export until there is a proven need for persistent perspectives.

## Explicit Apply Gates

- `write_file`
- `patch_properties`
- `approve_draft_item`
- `approve_review_queue_items`
- `apply_learned_review_queue`

These are not casual tools. Use dry-run and exact IDs unless the user explicitly
approves the final write.

## Optional Generated Outputs

- report builders write under `.linza/reports`;
- `create_context_pack` writes under `.linza/context-packs`.
