# Expected Safety Checks

The example pack should demonstrate these behaviors:

- Source Markdown note bodies are unchanged by indexing and artifact ingestion.
- Imported artifacts are stored as data in `.linza/linza.db`.
- Search and planning noise such as `Found 12 web pages` does not become a
  review card.
- Durable claims such as `imported text as data` can become review candidates.
- calibr can inspect the example trace and propose review cards without editing
  active skills, rules, code, or notes.
- Generated reports and context packs are written only under `.linza`.
