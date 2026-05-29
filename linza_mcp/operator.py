"""Operator guidance for LINZA onboarding and review flow."""

from __future__ import annotations

import os
from collections import Counter
from typing import Any


WORKFLOW_STEPS = [
    {
        "id": "review_domains",
        "label": "Review domains",
        "kind": "domain",
        "why": "Domains give the vault a first semantic map before detailed review.",
    },
    {
        "id": "review_roles",
        "label": "Review material formats",
        "kind": "material_type",
        "kinds": ["material_type", "role"],
        "why": "Material formats are named first, then written as note roles only after review.",
    },
    {
        "id": "review_hierarchy",
        "label": "Review hierarchy links",
        "kind": "hierarchy_link",
        "why": "Hierarchy links identify central notes and children inside accepted domains.",
    },
    {
        "id": "review_causal_links",
        "label": "Review cause/effect links",
        "kind": "causal_link",
        "why": "Causal links are higher-risk conclusions and should be reviewed only after domains, material formats, and hierarchy have context.",
    },
    {
        "id": "review_memory",
        "label": "Review memory candidates",
        "kind": "memory_item",
        "why": "Memory candidates are durable context for future agents and remain opt-in.",
    },
]


STAGE_PRESENTATION = {
    "review_domains": {
        "title": "Разобрать основные области",
        "question": "Какие крупные темы реально есть в базе?",
        "plain_next": "LINZA покажет несколько групп заметок. Ты решаешь: это одна область, как ее назвать, или пока пропустить.",
        "writes": "После подтверждения в YAML появится только короткое `domains`; текст заметок не меняется.",
    },
    "review_roles": {
        "title": "Разобрать форматы материалов",
        "question": "Какие форматы материалов реально есть в этой базе, и как их назвать?",
        "plain_next": "LINZA сначала покажет группы найденных материалов и попросит назвать формат. После этого появятся отдельные интенты ревью на запись `role` в YAML.",
        "writes": "Название формата сначала сохраняется в `.linza`; YAML `role: ...` появляется только отдельным подтвержденным шагом. Текст заметки не меняется.",
    },
    "review_hierarchy": {
        "title": "Собрать мягкую иерархию",
        "question": "Какие заметки центральные, а какие относятся к ним?",
        "plain_next": "LINZA покажет интенты для главных заметок внутри областей. Ты подтверждаешь только те связи, которые совпадают с твоей картой.",
        "writes": "Подтвержденная иерархия сохраняется в `.linza`, а не вписывается в Markdown.",
    },
    "review_causal_links": {
        "title": "Проверить причину и следствие",
        "question": "Что действительно привело к чему, а что просто стоит рядом?",
        "plain_next": "LINZA покажет осторожные гипотезы по фактам, решениям, действиям и результатам. Здесь лучше принимать мало и уверенно.",
        "writes": "Причинные связи сохраняются в `.linza` только после подтверждения.",
    },
    "review_memory": {
        "title": "Выбрать память для будущих агентов",
        "question": "Что стоит помнить между сессиями как устойчивый контекст?",
        "plain_next": "LINZA покажет короткие интенты памяти. Ты можешь принять, переформулировать или пропустить.",
        "writes": "Память сохраняется в `.linza`; исходные заметки не меняются.",
    },
    "maintenance": {
        "title": "Поддерживать карту",
        "question": "Что изменилось в базе и нужно ли пересмотреть карту?",
        "plain_next": "Когда добавятся новые заметки, LINZA снова покажет только следующий небольшой шаг.",
        "writes": "Без подтверждения LINZA ничего не меняет в заметках.",
    },
}


STAGE_PRESENTATION_EN = {
    "review_domains": {
        "title": "Review the main areas",
        "question": "What broad themes are actually present in this folder?",
        "plain_next": "LINZA will show a few groups of notes. You decide whether each group is a real area, how to name it, or whether to skip it for now.",
        "writes": "After approval, LINZA may write only compact `domains` YAML. Note bodies are not changed.",
    },
    "review_roles": {
        "title": "Review material formats",
        "question": "What kinds of material are actually present here, and how should they be named?",
        "plain_next": "LINZA first shows discovered material groups and asks for a user-provided format name. Only after that does it create separate review intents for writing `role` into YAML.",
        "writes": "The material-format name is stored in `.linza` first. Visible YAML `role: ...` appears only through a separate approved item. Note bodies are not changed.",
    },
    "review_hierarchy": {
        "title": "Build a soft hierarchy",
        "question": "Which notes are central, and which notes belong under them?",
        "plain_next": "LINZA will suggest central notes inside accepted areas. Approve only the links that match your map.",
        "writes": "Approved hierarchy is stored in `.linza`; it is not written into Markdown note bodies.",
    },
    "review_causal_links": {
        "title": "Check cause and effect",
        "question": "What actually led to what, and what is only nearby?",
        "plain_next": "LINZA will show cautious hypotheses over facts, decisions, actions, and results. Accept a small number confidently.",
        "writes": "Causal links are stored in `.linza` only after explicit approval.",
    },
    "review_memory": {
        "title": "Choose memory for future agents",
        "question": "What should future sessions remember as durable context?",
        "plain_next": "LINZA will suggest short memory fragments. You can accept, rephrase, or skip them.",
        "writes": "Memory is stored in `.linza`; source notes are not changed.",
    },
    "maintenance": {
        "title": "Maintain the map",
        "question": "What changed in the folder, and does the map need another review?",
        "plain_next": "When new notes arrive, LINZA will again show only the next small step.",
        "writes": "Without approval, LINZA changes nothing in your notes.",
    },
}


HOW_TO_ANSWER = {
    "ru": [
        "принять пункт",
        "попросить заменить название или формат материала",
        "пропустить пункт",
        "попросить показать доказательства",
    ],
    "en": [
        "accept the item",
        "ask to rename the area or material format",
        "skip the item",
        "ask to show the evidence",
    ],
}


def _resolve_language(core: Any, language: str | None) -> str:
    requested = str(language or "").strip().lower()
    if requested.startswith("ru"):
        return "ru"
    if requested.startswith("en"):
        return "en"

    config = getattr(core, "config", {}) or {}
    configured = str(config.get("language") or os.environ.get("LINZA_LANGUAGE") or "").strip().lower()
    if configured.startswith("ru"):
        return "ru"
    if configured.startswith("en"):
        return "en"
    return "ru"


def _presentation(stage_id: str, language: str) -> dict[str, str]:
    source = STAGE_PRESENTATION if language == "ru" else STAGE_PRESENTATION_EN
    return source.get(stage_id, source["maintenance"])


TOOL_GUIDE = {
    "index_all": {
        "when": "After connecting a vault, after large imports, or before broad semantic search.",
        "does": "Indexes Markdown notes into the LINZA sidecar and rebuilds semantic bridges.",
        "default_mode": "write_sidecar",
        "write_scope": ".linza/linza.db only",
    },
    "index_file": {
        "when": "After one note changes or when a tool created a temporary indexed note.",
        "does": "Indexes one file or provided content.",
        "default_mode": "write_sidecar",
        "write_scope": ".linza/linza.db only",
    },
    "search": {
        "when": "When the user asks to find context across the vault.",
        "does": "Runs semantic/lexical search using the active profile.",
        "default_mode": "read_only",
        "write_scope": "none, except search history in sidecar",
    },
    "suggest_links": {
        "when": "When reviewing semantic neighbors for one note.",
        "does": "Suggests related notes with semantic and lexical evidence.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "create_profile": {
        "when": "When a user wants a search perspective such as general, research, product, or writing.",
        "does": "Creates an embedding profile from keywords.",
        "default_mode": "write_sidecar",
        "write_scope": ".linza/linza.db profiles",
    },
    "list_profiles": {
        "when": "Before switching search perspective or debugging retrieval.",
        "does": "Lists available search profiles.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "switch_profile": {
        "when": "When the next searches should use another perspective.",
        "does": "Sets the active default profile.",
        "default_mode": "write_sidecar",
        "write_scope": ".linza/linza.db active profile setting",
    },
    "get_profile": {
        "when": "When explaining or debugging a search perspective.",
        "does": "Returns profile metadata and inheritance chain.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "read_file": {
        "when": "When the agent needs exact note text before answering or applying YAML.",
        "does": "Reads one Markdown note.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "write_file": {
        "when": "Only when creating a new Markdown note or explicitly replacing a generated note.",
        "does": "Creates or overwrites Markdown when explicitly allowed.",
        "default_mode": "dry_run",
        "write_scope": "Markdown file plus sidecar reindex after real write",
    },
    "get_bridges": {
        "when": "When inspecting semantic bridge suggestions for one note.",
        "does": "Reads stored semantic bridges for a note.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "get_stats": {
        "when": "Health check or quick status.",
        "does": "Returns counts for indexed files, profiles, bridges, and active profile.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "calibrate_embeddings": {
        "when": "After indexing or when diagnosing anisotropy/retrieval quality.",
        "does": "Reports raw vs centered embedding calibration.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "scan_vault": {
        "when": "First contact or health audit.",
        "does": "Finds vault-level issues such as broken links, orphans, duplicates, long/thin notes, and properties.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "draft_vault_map": {
        "when": "First meaningful map of a raw vault.",
        "does": "Builds domains, material formats, hierarchy candidates, event flow, lenses, and memory candidates.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "guide_next_steps": {
        "when": "After first scan, after domains, and whenever the user asks what to do next.",
        "does": "Explains current onboarding stage and points the agent to the next safe agent_workspace action.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "agent_workspace": {
        "when": "Default facade for workspace maps, teaching, supervised growth, artifact inbox, trace review, graph connect, memory search, and context export.",
        "does": "Routes typed actions such as map, teach, grow, ingest_artifacts, analyze_inbox, review_next, apply_review_items, connect, search_memory, export_context, calibr, and doctor. review_next/apply_review_items also handle vault rq-* review intents.",
        "default_mode": "mixed; read-only actions stay read-only and apply actions dry-run by default",
        "write_scope": ".linza sidecar for raw artifacts, traces, chunks, approved items, and audit events",
    },
    "audit_tags": {
        "when": "Before trusting tags as relation evidence or normalizing a messy vault.",
        "does": "Audits tag vocabulary, aliases, noisy inline tags, and long-tail tags.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "suggest_tag_candidates": {
        "when": "When reviewing possible tags for one note.",
        "does": "Suggests tags from chunks, inline hashtags, and accepted vocabulary.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "suggest_properties": {
        "when": "Before patching one note's compact LINZA YAML.",
        "does": "Suggests material format, state, and properties with a YAML preview.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "patch_properties": {
        "when": "Only after reviewing one note's suggested compact LINZA YAML.",
        "does": "Safely patches nested LINZA frontmatter while preserving note body.",
        "default_mode": "dry_run",
        "write_scope": "frontmatter YAML only; never note body",
    },
    "approve_draft_item": {
        "when": "When applying exactly one reviewed material-format, domain, hierarchy, causal, or memory item.",
        "does": "Applies one draft item or records it in sidecar.",
        "default_mode": "dry_run",
        "write_scope": "material formats/domains write compact YAML; hierarchy/causal/memory write sidecar",
    },
    "approve_review_queue_items": {
        "when": "When applying a small set of reviewed stable rq-* IDs.",
        "does": "Rebuilds the queue, matches exact IDs, previews by default, and applies only matched items.",
        "default_mode": "dry_run",
        "write_scope": "material-format/domain YAML or sidecar approvals depending on review kind",
    },
    "apply_learned_review_queue": {
        "when": "After accepted examples exist and the user wants assisted review intents.",
        "does": "Selects review intents supported by accepted examples; preview by default.",
        "default_mode": "dry_run",
        "write_scope": "same as approve_review_queue_items only when dry_run=false",
    },
    "list_approved_items": {
        "when": "To see what LINZA has already learned or accepted.",
        "does": "Lists reviewed sidecar approvals.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "build_bases_plan": {
        "when": "When the user wants an Obsidian Bases plan.",
        "does": "Builds a Markdown plan report.",
        "default_mode": "read_only unless write=true",
        "write_scope": ".linza/reports by default when write=true",
    },
    "build_yaml_suggestions": {
        "when": "When reviewing possible LINZA YAML across many notes.",
        "does": "Builds a Markdown suggestions report.",
        "default_mode": "read_only unless write=true",
        "write_scope": ".linza/reports by default when write=true",
    },
    "build_tag_vocabulary_report": {
        "when": "When reviewing tag cleanup as a document.",
        "does": "Builds a tag vocabulary Markdown report.",
        "default_mode": "read_only unless write=true",
        "write_scope": ".linza/reports by default when write=true",
    },
    "build_review_queue": {
        "when": "When reviewing general vault health/action items.",
        "does": "Builds a user-readable review queue report.",
        "default_mode": "read_only unless write=true",
        "write_scope": ".linza/reports by default when write=true",
    },
    "build_review_apply_queue": {
        "when": "Main review tool after draft_vault_map; use by kind: domains, then material formats, hierarchy, causal, memory.",
        "does": "Builds stable rq-* review intents with dry-run approval payloads.",
        "default_mode": "read_only unless write=true",
        "write_scope": ".linza/reports by default when write=true; source notes unchanged",
    },
    "build_diagnostic_report": {
        "when": "When the user wants a saved vault diagnostic snapshot.",
        "does": "Builds a diagnostic Markdown report.",
        "default_mode": "read_only unless write=true",
        "write_scope": ".linza/reports by default when write=true",
    },
    "build_semantic_links": {
        "when": "When reviewing semantic link candidates as a report.",
        "does": "Builds a Markdown report of semantic link candidates.",
        "default_mode": "read_only unless write=true",
        "write_scope": ".linza/reports by default when write=true",
    },
    "explain_relationship": {
        "when": "When deciding whether two notes should be linked.",
        "does": "Explains possible relation type and evidence.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "explain_node": {
        "when": "When inspecting one note's material format, graph context, bridges, and review suggestions.",
        "does": "Explains a single node.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "who_depends": {
        "when": "When checking impact or dependencies for one note.",
        "does": "Shows explicit dependents, dependencies, and semantic neighbors.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "show_flow": {
        "when": "When tracing a route between notes or from a query into the graph.",
        "does": "Shows a node-to-node or query flow.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "check_rule": {
        "when": "When auditing graph/rule health.",
        "does": "Runs read-only graph and rule checks.",
        "default_mode": "read_only",
        "write_scope": "none",
    },
    "create_context_pack": {
        "when": "When preparing a compact context bundle for an agent or article draft.",
        "does": "Builds a context pack from search results.",
        "default_mode": "read_only unless write=true",
        "write_scope": ".linza/context-packs by default when write=true",
    },
}


TOOL_AUDIENCE = {
    "guide_next_steps": "human_entry",
    "build_review_apply_queue": "human_review_via_agent",
    "agent_workspace": "agent_facade",
    "search": "agent_read",
    "suggest_links": "agent_read",
    "read_file": "agent_read",
    "get_bridges": "agent_read",
    "get_stats": "agent_read",
    "scan_vault": "agent_read",
    "draft_vault_map": "agent_read",
    "audit_tags": "agent_read",
    "suggest_tag_candidates": "agent_read",
    "suggest_properties": "agent_read",
    "list_approved_items": "agent_read",
    "explain_relationship": "agent_read",
    "explain_node": "agent_read",
    "who_depends": "agent_read",
    "show_flow": "agent_read",
    "check_rule": "agent_read",
    "list_profiles": "agent_read",
    "get_profile": "agent_read",
    "index_all": "agent_setup",
    "index_file": "agent_setup",
    "create_profile": "agent_setup",
    "switch_profile": "agent_setup",
    "calibrate_embeddings": "agent_setup",
    "write_file": "explicit_apply_gate",
    "patch_properties": "explicit_apply_gate",
    "approve_draft_item": "explicit_apply_gate",
    "approve_review_queue_items": "explicit_apply_gate",
    "apply_learned_review_queue": "explicit_apply_gate",
    "build_bases_plan": "optional_report",
    "build_yaml_suggestions": "optional_report",
    "build_tag_vocabulary_report": "optional_report",
    "build_review_queue": "optional_report",
    "build_diagnostic_report": "optional_report",
    "build_semantic_links": "optional_report",
    "create_context_pack": "optional_agent_export",
}


DEFAULT_MCP_TOOLS = (
    "guide_next_steps",
    "agent_workspace",
    "index_all",
    "search",
    "read_file",
    "get_stats",
    "scan_vault",
)


ADVANCED_MCP_TOOLS = tuple(
    tool_name
    for tool_name in TOOL_GUIDE
    if tool_name not in DEFAULT_MCP_TOOLS
)


def _approved_counts(core) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in core.storage.list_approved_items(limit=10000):
        counts[str(item.get("item_type", "unknown"))] += 1
    return {
        "domain": counts.get("domain", 0),
        "material_type": counts.get("material_type", 0),
        "role": counts.get("role", 0),
        "hierarchy_link": counts.get("hierarchy_link", 0),
        "causal_link": counts.get("causal_link", 0),
        "memory_item": counts.get("memory_item", 0),
    }


def _pending_counts(queue: dict[str, Any], draft_summary: dict[str, Any]) -> dict[str, int]:
    pending = {
        "domain": 0,
        "material_type": 0,
        "role": 0,
        "hierarchy_link": 0,
        "causal_link": 0,
        "memory_item": 0,
    }
    by_kind = queue.get("summary", {}).get("by_kind", [])
    for pair in by_kind:
        if len(pair) >= 2:
            pending[str(pair[0])] = int(pair[1])
    if "memory_item" not in pending or not pending["memory_item"]:
        pending["memory_item"] = int(draft_summary.get("memory_candidates", 0) or 0)
    return pending


def _choose_stage(approved: dict[str, int], pending: dict[str, int]) -> str:
    if approved.get("domain", 0) <= 0 and pending.get("domain", 0) > 0:
        return "review_domains"
    for step in WORKFLOW_STEPS[1:]:
        if any(pending.get(kind, 0) > 0 for kind in step.get("kinds", [step["kind"]])):
            return step["id"]
    return "maintenance"


def _analysis_stage_for_workflow(stage_id: str) -> str:
    return {
        "review_domains": "domains",
        "review_roles": "material_types",
        "review_hierarchy": "hierarchy",
        "review_causal_links": "event_flow",
        "review_memory": "memory",
    }.get(stage_id, "all")


def _stage_sequence(stage_id: str, approved: dict[str, int], pending: dict[str, int], language: str) -> list[dict[str, Any]]:
    order = [step["id"] for step in WORKFLOW_STEPS]
    current_index = order.index(stage_id) if stage_id in order else len(order)
    result = []
    for index, step in enumerate(WORKFLOW_STEPS):
        if index < current_index:
            status = "done"
        elif index == current_index:
            status = "current"
        elif any(pending.get(kind, 0) > 0 for kind in step.get("kinds", [step["kind"]])):
            status = "upcoming"
        else:
            status = "waiting"
        stage_pending = sum(pending.get(kind, 0) for kind in step.get("kinds", [step["kind"]]))
        stage_approved = sum(approved.get(kind, 0) for kind in step.get("kinds", [step["kind"]]))
        presentation = _presentation(step["id"], language)
        result.append({
            "id": step["id"],
            "label": step["label"],
            "label_human": presentation.get("title", step["label"]),
            "question_human": presentation.get("question", step["why"]),
            "kind": step["kind"],
            "status": status,
            "approved": stage_approved,
            "pending": stage_pending,
        })
    return result


def _human_route(stage_id: str, approved: dict[str, int], pending: dict[str, int], language: str) -> list[dict[str, Any]]:
    return [
        {
            "id": step["id"],
            "title": _presentation(step["id"], language).get("title", step["label"]),
            "question": _presentation(step["id"], language).get("question", step["why"]),
            "status": item["status"],
            "accepted": item["approved"],
            "pending": item["pending"],
        }
        for item, step in zip(_stage_sequence(stage_id, approved, pending, language), WORKFLOW_STEPS)
    ]


def _next_step(stage_id: str, pending: dict[str, int], max_notes: int, max_domains: int, limit: int, include_memory: bool, language: str) -> dict[str, Any]:
    step = next((item for item in WORKFLOW_STEPS if item["id"] == stage_id), None)
    if step is None:
        presentation = _presentation("maintenance", language)
        return {
            "id": "maintenance",
            "label": "Maintain the map",
            "label_human": presentation["title"],
            "why": "No immediate review intents are pending in the current guide window.",
            "primary_tool": "guide_next_steps",
            "approval_tool": None,
            "suggested_action": "Re-run guide_next_steps after adding or changing notes.",
            "writes": "none",
        }
    presentation = _presentation(step["id"], language)
    return {
        "id": step["id"],
        "label": step["label"],
        "label_human": presentation.get("title", step["label"]),
        "kind": step["kind"],
        "why": step["why"],
        "question_human": presentation.get("question", step["why"]),
        "plain_next": presentation.get("plain_next", ""),
        "write_preview": presentation.get("writes", ""),
        "pending": sum(pending.get(kind, 0) for kind in step.get("kinds", [step["kind"]])),
        "primary_tool": "agent_workspace",
        "primary_arguments": {
            "action": "review_next",
            "kind": step["kind"],
            "max_notes": max_notes,
            "max_domains": max_domains,
            "limit": min(5, limit),
            "include_memory": include_memory,
        },
        "review_filter": {"kind": step["kind"], "kinds": step.get("kinds", [step["kind"]]), "suggested_batch_size": 5},
        "approval_tool": "agent_workspace",
        "approval_arguments": {
            "action": "apply_review_items",
            "item_ids": ["rq-..."],
            "dry_run": True,
            "allow_overwrite": False,
            "include_memory": include_memory,
        },
        "suggested_action": f"Call agent_workspace(action=\"review_next\", kind=\"{step['kind']}\", limit=5), ask the user to accept/skip/change, then call agent_workspace(action=\"apply_review_items\", item_ids=[...], dry_run=true) before applying.",
        "writes": TOOL_GUIDE["approve_review_queue_items"]["write_scope"],
    }


def _user_view(stage_id: str, approved: dict[str, int], pending: dict[str, int], recommended_cards: list[dict[str, Any]], language: str) -> dict[str, Any]:
    presentation = _presentation(stage_id, language)
    return {
        "mode": "human_onboarding",
        "language": language,
        "title": presentation["title"],
        "question": presentation["question"],
        "plain_next": presentation["plain_next"],
        "what_changes": presentation["writes"],
        "how_to_answer": HOW_TO_ANSWER[language],
        "progress": {
            "accepted_domains": approved.get("domain", 0),
            "accepted_roles": approved.get("role", 0),
            "accepted_material_formats": approved.get("material_type", 0),
            "accepted_material_types": approved.get("material_type", 0),
            "pending_now": sum(
                pending.get(kind, 0)
                for kind in next((step.get("kinds", [step["kind"]]) for step in WORKFLOW_STEPS if step["id"] == stage_id), [])
            ),
        },
        "route": _human_route(stage_id, approved, pending, language),
        "cards_preview": [
            {
                "id": card.get("id"),
                "kind": card.get("kind"),
                "label": card.get("human", {}).get("label", card.get("kind")),
                "question": card.get("human", {}).get("question", ""),
                "write_preview": card.get("human", {}).get("write_preview", ""),
                "evidence_trace": card.get("evidence_trace", []),
                "role": card.get("human", {}).get("role"),
            }
            for card in recommended_cards
        ],
        "technical": {
            "read_cards_tool": "agent_workspace(action=\"review_next\")",
            "apply_cards_tool": "agent_workspace(action=\"apply_review_items\")",
        },
    }


async def guide_next_steps(
    core,
    max_notes: int = 120,
    max_domains: int = 8,
    limit: int = 40,
    include_memory: bool = False,
    include_tool_guide: bool = False,
    language: str = "auto",
) -> dict[str, Any]:
    """Explain the current LINZA onboarding stage and safe next actions."""
    resolved_language = _resolve_language(core, language)
    guide_limit = max(1, int(limit))
    queue = await core.build_review_apply_queue(
        max_notes=max_notes,
        max_domains=max_domains,
        limit=guide_limit,
        redact=True,
        include_memory=include_memory,
    )
    draft_summary = queue.get("summary", {}).get("source_map", {})
    approved = _approved_counts(core)
    pending = _pending_counts(queue, draft_summary)
    stage_id = _choose_stage(approved, pending)
    stage = next(
        (
            {
                "id": item["id"],
                "label": item["label"],
                "label_human": _presentation(item["id"], resolved_language).get("title", item["label"]),
                "kind": item["kind"],
                "kinds": item.get("kinds", [item["kind"]]),
                "why": item["why"],
                "question_human": _presentation(item["id"], resolved_language).get("question", item["why"]),
            }
            for item in WORKFLOW_STEPS
            if item["id"] == stage_id
        ),
        {
            "id": "maintenance",
            "label": "Maintain the map",
            "label_human": _presentation("maintenance", resolved_language)["title"],
            "kind": "maintenance",
            "why": "No immediate review intents are pending in the current guide window.",
            "question_human": _presentation("maintenance", resolved_language)["question"],
        },
    )
    next_step = _next_step(stage_id, pending, max_notes, max_domains, guide_limit, include_memory, resolved_language)
    current_kinds = set(stage.get("kinds", [stage.get("kind")]))
    stage_queue = queue
    if stage_id != "maintenance":
        stage_queue = await core.build_review_apply_queue(
            max_notes=max_notes,
            max_domains=max_domains,
            limit=guide_limit,
            redact=True,
            include_memory=include_memory,
            analysis_stage=_analysis_stage_for_workflow(stage_id),
        )
    recommended_cards = [
        item for item in stage_queue.get("items", [])
        if item.get("kind") in current_kinds
    ][:5]

    indexed_files = 0
    try:
        indexed_files = int(core.storage.get_file_count())
    except Exception:
        indexed_files = 0

    semantic_bridges = 0
    try:
        semantic_bridges = len(core.storage.get_all_bridges())
    except Exception:
        semantic_bridges = 0

    return {
        "tool": "guide_next_steps",
        "read_only": True,
        "language": resolved_language,
        "stage": stage,
        "next_step": next_step,
        "user_view": _user_view(stage_id, approved, pending, recommended_cards, resolved_language),
        "stage_sequence": _stage_sequence(stage_id, approved, pending, resolved_language),
        "approved": approved,
        "pending": pending,
        "progress": {
            "indexed_files": indexed_files,
            "semantic_bridges": semantic_bridges,
            "draft_summary": draft_summary,
            "queue_items": queue.get("summary", {}).get("items", len(queue.get("items", []))),
            "include_memory": include_memory,
        },
        "review_window": {
            "stage": stage_id,
            "analysis_stage": _analysis_stage_for_workflow(stage_id),
            "items": len(stage_queue.get("items", [])),
        },
        "recommended_cards": recommended_cards,
        "tool_guide": TOOL_GUIDE if include_tool_guide else {},
        "tool_audience": TOOL_AUDIENCE if include_tool_guide else {},
        "tool_surface": {
            "default": list(DEFAULT_MCP_TOOLS),
            "advanced_hidden": list(ADVANCED_MCP_TOOLS),
        } if include_tool_guide else {},
        "policies": [
            "This guide is read-only.",
            "Review order is domains -> material formats -> hierarchy -> causal links -> memory.",
            "Material-format/domain items may write compact YAML only after approval; hierarchy, causal, and memory approvals live in .linza sidecar.",
            "Causal links are never silently created during normal indexing.",
            "Visible Markdown reports are opt-in; default report writes go to .linza.",
        ],
    }


__all__ = [
    "ADVANCED_MCP_TOOLS",
    "DEFAULT_MCP_TOOLS",
    "HOW_TO_ANSWER",
    "STAGE_PRESENTATION",
    "STAGE_PRESENTATION_EN",
    "TOOL_AUDIENCE",
    "TOOL_GUIDE",
    "WORKFLOW_STEPS",
    "guide_next_steps",
]
