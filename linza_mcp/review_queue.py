"""Review/apply queue safety helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any, Dict

from .draft_map import normalize_analysis_stage
from .roles import role_review_metadata
from .utils import get_linza_metadata, safe_vault_path, strip_frontmatter


def approval_payload(item_type: str, **arguments: Any) -> Dict[str, Any]:
    payload = {"item_type": item_type, "dry_run": True}
    payload.update({key: value for key, value in arguments.items() if value not in (None, "", [])})
    return {"tool": "approve_draft_item", "arguments": payload}


def stable_queue_item_id(item: Dict[str, Any]) -> str:
    arguments = dict(item.get("approval", {}).get("arguments", {}))
    stable_arguments = {
        key: value
        for key, value in arguments.items()
        if key not in {"dry_run", "allow_overwrite"}
    }
    raw = json.dumps(
        {
            "kind": item.get("kind", ""),
            "approval": stable_arguments,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    kind = str(item.get("kind", "item")).replace("_link", "").replace("_", "-")
    return f"rq-{kind}-{digest}"


def assign_queue_item_ids(items: list[Dict[str, Any]]) -> None:
    seen: Counter[str] = Counter()
    for item in items:
        base_id = stable_queue_item_id(item)
        seen[base_id] += 1
        item["id"] = base_id if seen[base_id] == 1 else f"{base_id}-{seen[base_id]}"


def redacted_queue_item(item: Dict[str, Any]) -> Dict[str, Any]:
    arguments = item.get("approval", {}).get("arguments", {})
    safe: Dict[str, Any] = {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "priority": item.get("priority"),
        "note_count": len([path for path in item.get("paths", []) if path]),
        "has_evidence": bool(item.get("evidence")),
        "evidence_count": len(item.get("evidence_trace", []) or []),
        "payload_redacted": True,
        "approval_item_type": arguments.get("item_type"),
    }
    if item.get("kind") == "role" and arguments.get("role"):
        safe["proposed_role"] = arguments.get("role")
    if item.get("kind") == "material_type":
        safe["type_id"] = arguments.get("type_id")
        safe["requires_name"] = not bool(arguments.get("type_name"))
    if item.get("kind") == "causal_link" and arguments.get("relation"):
        safe["relation"] = arguments.get("relation")
    if item.get("kind") == "hierarchy_link":
        safe["relation"] = arguments.get("relation", "parent_of")
        safe["child_count"] = len(arguments.get("child_paths", []) or [])
    if item.get("kind") == "memory_item" and arguments.get("memory_type"):
        safe["memory_type"] = arguments.get("memory_type")
    if item.get("human"):
        safe["human"] = item["human"]
    return safe


def redacted_queue_items(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return [redacted_queue_item(item) for item in items]


def evidence_trace_entry(label: str, value: Any, weight: str = "medium") -> dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "weight": weight,
    }


def stage_bucket_order(analysis_stage: str, include_memory: bool) -> tuple[str, ...]:
    stage = normalize_analysis_stage(analysis_stage)
    if stage == "domains":
        return ("domain",)
    if stage == "material_types":
        return ("material_type", "role")
    if stage == "hierarchy":
        return ("hierarchy_link",)
    if stage == "event_flow":
        return ("causal_link",)
    if stage == "memory":
        return ("memory_item",)
    return (
        ("domain", "material_type", "hierarchy_link", "memory_item", "causal_link", "role")
        if include_memory
        else ("domain", "material_type", "hierarchy_link", "causal_link", "role")
    )


def human_review_metadata(kind: str, role: str = "", memory_type: str = "", relation: str = "", type_id: str = "") -> dict[str, Any]:
    """Return the user-facing review contract for a queue card."""
    if kind == "material_type":
        label = type_id or "найденный тип"
        return {
            "kind": "material_type",
            "label": "название типа материала",
            "question": f"Как назвать найденный тип `{label}` для этой базы?",
            "user_options": ["назвать тип", "разделить группу", "объединить с другим типом", "пропустить"],
            "write_preview": "Если принять, LINZA сохранит название типа в `.linza`; Markdown-заметки не меняются. YAML `role` появится только отдельной review-карточкой после этого.",
        }
    if kind == "role":
        role_info = role_review_metadata(role)
        return {
            "kind": "role",
            "label": "тип материала",
            "question": role_info["question"],
            "role": role_info,
            "material_type": role_info,
            "user_options": ["принять", "выбрать другой тип", "переименовать тип для этой базы", "пропустить"],
            "write_preview": role_info["write_preview"],
        }
    if kind == "domain":
        return {
            "kind": "domain",
            "label": "область",
            "question": "Эти заметки действительно относятся к одной крупной теме?",
            "user_options": ["принять", "переименовать", "разделить или пропустить"],
            "write_preview": "Если принять, LINZA добавит короткий список `domains` в YAML выбранных заметок. Текст заметок не меняется.",
        }
    if kind == "hierarchy_link":
        return {
            "kind": "hierarchy_link",
            "label": "иерархия",
            "question": "Эта заметка должна быть главной для остальных в этой области?",
            "user_options": ["принять", "выбрать другого родителя", "пропустить"],
            "write_preview": "Если принять, связь сохранится в `.linza` как подтвержденная структура. Markdown-заметки не меняются.",
        }
    if kind == "causal_link":
        relation_text = f" ({relation})" if relation else ""
        return {
            "kind": "causal_link",
            "label": "причина и следствие",
            "question": f"Одна запись действительно повлияла на другую{relation_text}?",
            "user_options": ["принять", "изменить тип связи", "пропустить"],
            "write_preview": "Если принять, причинная связь сохранится в `.linza`. LINZA не пишет такие связи в текст заметок.",
        }
    if kind == "memory_item":
        memory_label = memory_type or "memory"
        return {
            "kind": "memory_item",
            "label": "память агента",
            "question": f"Это стоит запомнить как долговременный контекст ({memory_label})?",
            "user_options": ["принять", "переформулировать", "пропустить"],
            "write_preview": "Если принять, память сохранится в `.linza`; исходная заметка не меняется.",
        }
    return {
        "kind": kind,
        "label": "карточка",
        "question": "Эту карточку стоит принять?",
        "user_options": ["принять", "изменить", "пропустить"],
        "write_preview": "LINZA покажет preview перед любой записью.",
    }


def _note_metadata(core, path: str) -> dict[str, Any]:
    try:
        _, full = safe_vault_path(core.storage.vault_path, path)
    except ValueError:
        return {}
    if not full.exists() or not full.is_file():
        return {}
    metadata, _ = strip_frontmatter(full.read_text(encoding="utf-8", errors="replace"))
    return metadata if isinstance(metadata, dict) else {}


def _role_already_in_yaml(core, path: str, role: str) -> bool:
    metadata = _note_metadata(core, path)
    linza = get_linza_metadata(metadata)
    return bool(role and str(linza.get("role", "")) == str(role))


def _domain_already_in_yaml(core, paths: list[str], domain_name: str) -> bool:
    if not paths or not domain_name:
        return False
    for path in paths:
        metadata = _note_metadata(core, path)
        linza = get_linza_metadata(metadata)
        existing = linza.get("domains", [])
        if isinstance(existing, str):
            domains = [existing]
        elif isinstance(existing, list):
            domains = [str(item) for item in existing if str(item).strip()]
        else:
            domains = []
        if domain_name not in domains:
            return False
    return True


def queue_item_already_resolved(core, item: Dict[str, Any], approved_signatures: set[str]) -> bool:
    arguments = item.get("approval", {}).get("arguments", {})
    item_type = str(arguments.get("item_type") or item.get("kind", ""))
    signature = queue_item_signature(item_type, arguments)
    if signature and signature in approved_signatures:
        return True
    if item_type == "role":
        return _role_already_in_yaml(core, str(arguments.get("path", "")), str(arguments.get("role", "")))
    if item_type == "domain":
        return _domain_already_in_yaml(
            core,
            [str(path) for path in arguments.get("paths", []) if str(path).strip()],
            str(arguments.get("domain_name", "")),
        )
    return False


def material_type_names_from_storage(storage) -> dict[str, str]:
    """Return accepted draft type-id -> human type-name mappings."""
    names: dict[str, str] = {}
    for item in storage.list_approved_items("material_type", limit=1000):
        payload = item.get("payload", {})
        type_id = str(payload.get("type_id", "")).strip()
        type_name = str(payload.get("type_name", "")).strip()
        if type_id and type_name:
            names[type_id] = type_name
    return names


def apply_queue_markdown(items: list[Dict[str, Any]], summary: Dict[str, Any], redact: bool = False) -> str:
    lines = [
        "# LINZA Review / Apply Queue" + (" (Redacted)" if redact else ""),
        "",
        "This is a human review queue. It does not change source notes.",
    ]
    if redact:
        lines.extend([
            "This redacted view hides note paths, titles, evidence text, and approval payloads.",
            "Use a full local report for actual review/apply actions.",
        ])
    else:
        lines.extend([
            "Each item contains a dry-run `approve_draft_item` payload. Run dry-run first, then set `dry_run=false` only for the exact item you accept.",
            "For selected cards, use `approve_review_queue_items` with the stable IDs shown below.",
        ])
    lines.extend(["", "## Map Snapshot", ""])
    for key in ("notes", "candidate_domains", "role_drafts", "event_flow_items", "review_items"):
        if key in summary:
            lines.append(f"- **{key}**: {summary[key]}")
    if "memory_candidates" in summary:
        lines.append(f"- **memory_candidates**: {summary['memory_candidates']}")

    grouped: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[item["kind"]].append(item)

    section_titles = {
        "domain": "Domains",
        "material_type": "Material Type Names",
        "hierarchy_link": "Hierarchy",
        "memory_item": "Memory",
        "role": "Material Types",
        "causal_link": "Cause / Effect Links",
    }
    for kind in ("domain", "material_type", "hierarchy_link", "memory_item", "role", "causal_link"):
        lines.extend(["", f"## {section_titles[kind]}", ""])
        if not grouped.get(kind):
            lines.append("- Nothing in this section.")
            continue
        for item in grouped[kind]:
            if redact:
                lines.append(f"### {item['id']} - {item['kind']} candidate")
                lines.append("")
                lines.append(f"- priority: {item['priority']}")
                lines.append(f"- note_count: {len([path for path in item.get('paths', []) if path])}")
                lines.append(f"- has_evidence: {bool(item.get('evidence'))}")
                lines.append("- approval_payload: redacted")
                lines.append("")
                continue
            lines.append(f"### {item['id']} - {item['title']}")
            lines.append("")
            lines.append(f"- priority: {item['priority']}")
            lines.append(f"- why: {item['why']}")
            if item.get("human"):
                human = item["human"]
                if human.get("question"):
                    lines.append(f"- user_question: {human['question']}")
                if human.get("write_preview"):
                    lines.append(f"- will_change: {human['write_preview']}")
            if item.get("paths"):
                lines.append(f"- notes: {', '.join(f'`{path}`' for path in item['paths'])}")
            if item.get("evidence"):
                lines.append(f"- evidence: {item['evidence']}")
            if item.get("evidence_trace"):
                lines.append("- evidence_trace:")
                for entry in item["evidence_trace"][:6]:
                    lines.append(
                        f"  - {entry.get('label')}: {entry.get('value')} ({entry.get('weight', 'medium')})"
                    )
            lines.extend([
                "",
                "```json",
                json.dumps(item["approval"], ensure_ascii=False, indent=2),
                "```",
                "",
            ])

    return "\n".join(lines).rstrip() + "\n"


async def build_review_apply_queue(
    core,
    max_notes: int = 120,
    max_domains: int = 8,
    limit: int = 40,
    redact: bool = False,
    include_memory: bool = False,
    analysis_stage: str = "all",
) -> Dict[str, Any]:
    """Build a human-readable apply queue from the draft map. Read-only."""
    limit = max(1, int(limit))
    requested_stage = normalize_analysis_stage(analysis_stage)
    draft = await core.draft_vault_map(
        max_notes=max_notes,
        max_domains=max_domains,
        analysis_stage=requested_stage,
    )
    buckets: Dict[str, list[Dict[str, Any]]] = {
        "domain": [],
        "material_type": [],
        "memory_item": [],
        "causal_link": [],
        "role": [],
    }
    material_type_names = material_type_names_from_storage(core.storage)

    def add_item(
        kind: str,
        title: str,
        priority: str,
        why: str,
        approval: Dict[str, Any],
        paths: list[str] | None = None,
        evidence: str = "",
        human: dict[str, Any] | None = None,
        evidence_trace: list[dict[str, Any]] | None = None,
    ) -> None:
        buckets.setdefault(kind, []).append({
            "kind": kind,
            "title": title,
            "priority": priority,
            "why": why,
            "paths": paths or [],
            "evidence": evidence,
            "evidence_trace": evidence_trace or [],
            "approval": approval,
            "human": human or human_review_metadata(kind),
        })

    for domain in draft.get("candidate_domains", []):
        paths = [note["path"] for note in domain.get("representative_notes", [])]
        if not paths:
            continue
        name = domain.get("display_name") or domain.get("name")
        add_item(
            "domain",
            f"Область: {name}",
            "high" if domain.get("confidence") == "medium" else "medium",
            "Accept this draft domain for the representative notes if the name and grouping are right.",
            approval_payload("domain", domain_name=name, paths=paths),
            paths=paths,
            evidence=", ".join(domain.get("representative_terms", [])[:6]),
            human=human_review_metadata("domain"),
            evidence_trace=[
                evidence_trace_entry("representative_terms", domain.get("representative_terms", [])[:8], "high"),
                evidence_trace_entry("representative_notes", paths[:6], "high"),
                evidence_trace_entry("confidence", domain.get("confidence", "draft"), "medium"),
                evidence_trace_entry("score", domain.get("score", 0), "medium"),
            ],
        )

    for candidate in draft.get("role_draft", {}).get("material_type_candidates", []):
        type_id = str(candidate.get("id", "")).strip()
        if not type_id or type_id in material_type_names:
            continue
        paths = [
            str(note.get("path", "")).strip()
            for note in candidate.get("representative_notes", [])
            if str(note.get("path", "")).strip()
        ]
        if not paths:
            continue
        terms = [str(term) for term in candidate.get("representative_terms", [])[:8] if str(term).strip()]
        shape = [
            f"{token}:{count}"
            for token, count in candidate.get("shape", [])[:8]
            if str(token).strip()
        ]
        evidence = "; ".join(part for part in [
            f"terms={', '.join(terms)}" if terms else "",
            f"shape={', '.join(shape)}" if shape else "",
            f"notes={candidate.get('member_count', len(paths))}",
        ] if part)
        add_item(
            "material_type",
            f"Название найденного типа: {type_id}",
            "high" if candidate.get("confidence") == "medium" else "medium",
            candidate.get("why", "LINZA found a reusable material shape in this vault."),
            approval_payload("material_type", type_id=type_id, paths=paths, evidence=evidence),
            paths=paths,
            evidence=evidence,
            human=human_review_metadata("material_type", type_id=type_id),
            evidence_trace=[
                evidence_trace_entry("terms", terms, "high"),
                evidence_trace_entry("shape", shape, "medium"),
                evidence_trace_entry("representative_notes", paths[:6], "high"),
                evidence_trace_entry("member_count", candidate.get("member_count", len(paths)), "medium"),
            ],
        )

    for hierarchy in draft.get("hierarchy_draft", []):
        parent_candidates = hierarchy.get("parent_candidates", [])
        if not parent_candidates:
            continue
        parent = parent_candidates[0]
        parent_path = parent.get("path", "")
        child_paths: list[str] = []
        for group in hierarchy.get("child_groups", []):
            for note in group.get("notes", []):
                child_path = note.get("path", "")
                if child_path and child_path != parent_path and child_path not in child_paths:
                    child_paths.append(child_path)
        if not parent_path or not child_paths:
            continue
        domain_name = hierarchy.get("domain_name", "")
        add_item(
            "hierarchy_link",
            f"Главная заметка для области: {parent.get('title')}",
            "medium",
            "LINZA found a central note candidate for this draft domain. Accept only if this parent-child grouping matches the human map.",
            approval_payload(
                "hierarchy_link",
                parent_path=parent_path,
                child_paths=child_paths[:12],
                domain_name=domain_name,
                relation="parent_of",
                evidence=parent.get("why", ""),
            ),
            paths=[parent_path] + child_paths[:12],
            evidence=parent.get("why", ""),
            human=human_review_metadata("hierarchy_link"),
            evidence_trace=[
                evidence_trace_entry("parent_candidate", parent_path, "high"),
                evidence_trace_entry("child_candidates", child_paths[:12], "medium"),
                evidence_trace_entry("parent_score", parent.get("score", 0), "medium"),
                evidence_trace_entry("domain", domain_name, "low"),
            ],
        )

    for note in draft.get("role_draft", {}).get("notes", []):
        role = str(note.get("role") or "").strip()
        if not role or role in {"note", "untyped"}:
            continue
        if role.startswith("type-"):
            role = material_type_names.get(role, "")
        if not role or role.startswith("type-"):
            continue
        add_item(
            "role",
            f"Тип материала: {note.get('title')}",
            "high" if note.get("confidence") == "high" else "medium",
            f"LINZA inferred this material type from {note.get('reason', 'local evidence')}.",
            approval_payload("role", path=note.get("path"), role=role),
            paths=[note.get("path", "")],
            evidence=", ".join(str(h) for h in note.get("evidence", {}).get("headings", [])[:3]),
            human=human_review_metadata("role", role=role),
            evidence_trace=[
                evidence_trace_entry("folder", note.get("evidence", {}).get("folder", ""), "medium"),
                evidence_trace_entry("headings", note.get("evidence", {}).get("headings", [])[:5], "medium"),
                evidence_trace_entry("shape", note.get("evidence", {}).get("shape", [])[:8], "medium"),
                evidence_trace_entry("confidence", note.get("confidence", "draft"), "medium"),
            ],
        )

    if include_memory:
        for candidate in draft.get("memory_draft", {}).get("consolidation_candidates", []):
            source_path = candidate.get("source_path")
            memory_type = candidate.get("memory_type")
            summary = candidate.get("summary")
            if not source_path or not memory_type or not summary:
                continue
            add_item(
                "memory_item",
                f"Память: {summary}",
                candidate.get("priority", "medium"),
                candidate.get("why", "Consolidate this memory only after review."),
                approval_payload(
                    "memory_item",
                    source_path=source_path,
                    memory_type=memory_type,
                    summary=summary,
                    evidence=candidate.get("evidence", ""),
                    signals=candidate.get("signals", []),
                    recall_context=candidate.get("recall_context", []),
                    review_after=candidate.get("review_after", ""),
                    staleness_risk=candidate.get("staleness_risk", ""),
                    conflict_candidates=candidate.get("conflict_candidates", []),
                    evolution=candidate.get("evolution", {}),
                    review_questions=candidate.get("review_questions", []),
                ),
                paths=[source_path],
                evidence=candidate.get("evidence", ""),
                human=human_review_metadata("memory_item", memory_type=memory_type),
                evidence_trace=[
                    evidence_trace_entry("source_path", source_path, "high"),
                    evidence_trace_entry("signals", candidate.get("signals", []), "medium"),
                    evidence_trace_entry("memory_type", memory_type, "medium"),
                    evidence_trace_entry("recall_context", candidate.get("recall_context", []), "high"),
                    evidence_trace_entry("review_after", candidate.get("review_after", ""), "medium"),
                    evidence_trace_entry("staleness_risk", candidate.get("staleness_risk", ""), "medium"),
                    evidence_trace_entry("conflict_candidates", candidate.get("conflict_candidates", []), "medium"),
                    evidence_trace_entry("evolution", candidate.get("evolution", {}), "medium"),
                    evidence_trace_entry("evidence", candidate.get("evidence", ""), "high"),
                ],
            )

    events = {event["id"]: event for event in draft.get("event_flow_draft", {}).get("events", [])}
    for candidate in draft.get("event_flow_draft", {}).get("causal_candidates", []):
        left = events.get(candidate.get("from"))
        right = events.get(candidate.get("to"))
        if not left or not right:
            continue
        if left.get("path") == right.get("path"):
            continue
        relation = candidate.get("relation", "related_to")
        evidence = " -> ".join(filter(None, [left.get("evidence", ""), right.get("evidence", "")]))
        add_item(
            "causal_link",
            f"Причина и следствие: {left.get('title')} / {right.get('title')}",
            "medium",
            candidate.get("why", "Candidate cause/effect link from event flow."),
            approval_payload(
                "causal_link",
                source_path=left.get("path"),
                target_path=right.get("path"),
                relation=relation,
                evidence=evidence,
            ),
            paths=[left.get("path", ""), right.get("path", "")],
            evidence=core._preview_text(evidence, 260),
            human=human_review_metadata("causal_link", relation=relation),
            evidence_trace=[
                evidence_trace_entry("source_event", left.get("evidence", ""), "high"),
                evidence_trace_entry("target_event", right.get("evidence", ""), "high"),
                evidence_trace_entry("relation", relation, "medium"),
                evidence_trace_entry("shared_domain", candidate.get("domain_id", ""), "low"),
            ],
        )

    items: list[Dict[str, Any]] = []
    bucket_order = stage_bucket_order(requested_stage, include_memory)
    while len(items) < limit and any(buckets.get(kind) for kind in bucket_order):
        for kind in bucket_order:
            if len(items) >= limit:
                break
            bucket = buckets.get(kind)
            if bucket:
                items.append(bucket.pop(0))
    approved_signatures = set(learning_examples_from_storage(core.storage).get("approved_signatures", []))
    items = [
        item for item in items
        if not queue_item_already_resolved(core, item, approved_signatures)
    ]
    assign_queue_item_ids(items)

    kind_counts = Counter(item["kind"] for item in items)
    response_items = redacted_queue_items(items) if redact else items
    markdown = apply_queue_markdown(items, draft.get("summary", {}), redact=redact)
    return {
        "tool": "build_review_apply_queue",
        "read_only": True,
        "redacted": redact,
        "analysis_stage": {
            "requested": requested_stage,
            "bucket_order": list(bucket_order),
        },
        "items": response_items,
        "summary": {
            "items": len(items),
            "by_kind": kind_counts.most_common(),
            "source_map": draft.get("summary", {}),
            "redacted": redact,
            "include_memory": include_memory,
        },
        "markdown": markdown,
        "policy": [
            "This queue does not apply changes by itself.",
            "Memory cards are opt-in; pass include_memory=true to review durable memory candidates.",
            "Redacted queues hide approval payloads and are for safe summaries, not apply actions." if redact else "Every approval payload keeps dry_run=true.",
            "Use a full local queue before applying selected IDs." if redact else "Set dry_run=false only for one reviewed item at a time.",
        ],
    }


def approval_written_paths(result: Dict[str, Any]) -> list[str]:
    paths: set[str] = set()
    for path in result.get("written_paths", []):
        if path:
            paths.add(str(path))
    if result.get("status") == "written":
        for path in result.get("applied_to", []):
            if path:
                paths.add(str(path))
    return sorted(paths)


def merge_linza_domains(metadata: Dict[str, Any], domain_name: str) -> list[str]:
    linza = get_linza_metadata(metadata)
    existing = linza.get("domains", [])
    if isinstance(existing, str):
        domains = [existing]
    elif isinstance(existing, list):
        domains = [str(item) for item in existing if str(item).strip()]
    else:
        domains = []
    if domain_name not in domains:
        domains.append(domain_name)
    return domains


def approve_role_item(
    core,
    path: str,
    role: str,
    dry_run: bool,
    allow_overwrite: bool,
) -> Dict[str, Any]:
    if not role:
        return {"error": "missing_role", "item_type": "role"}
    result = core.patch_note_properties(
        path,
        {"role": role},
        dry_run=dry_run,
        allow_overwrite=allow_overwrite,
        namespace="linza",
    )
    result.update({
        "tool": "approve_draft_item",
        "item_type": "role",
        "applied_to": [path],
        "approval_policy": "single_item_review",
    })
    if result.get("status") == "written":
        approval_id = core.storage.record_approved_item(
            "role",
            {"path": path, "role": role, "changes": result.get("changes", [])},
        )
        result["approval_id"] = approval_id
    return result


def approve_domain_item(
    core,
    domain_name: str,
    paths: list[str],
    dry_run: bool,
    allow_overwrite: bool,
) -> Dict[str, Any]:
    if not domain_name:
        return {"error": "missing_domain_name", "item_type": "domain"}
    if not paths:
        return {"error": "missing_paths", "item_type": "domain"}

    file_results = []
    for path in paths:
        try:
            rel, full = safe_vault_path(core.storage.vault_path, path)
        except ValueError as exc:
            file_results.append({"path": path, "error": str(exc)})
            continue
        if not full.exists() or not full.is_file():
            file_results.append({"path": path, "error": "file not found"})
            continue
        original = full.read_text(encoding="utf-8", errors="replace")
        metadata, _ = strip_frontmatter(original)
        next_domains = merge_linza_domains(metadata, domain_name)
        linza = get_linza_metadata(metadata)
        existing = linza.get("domains", [])
        if isinstance(existing, str):
            existing_domains = [existing]
        elif isinstance(existing, list):
            existing_domains = [str(item) for item in existing if str(item).strip()]
        else:
            existing_domains = []
        already_present = domain_name in existing_domains
        result = core.patch_note_properties(
            rel,
            {"domains": next_domains},
            dry_run=dry_run,
            allow_overwrite=True if already_present or next_domains else allow_overwrite,
            namespace="linza",
        )
        if already_present:
            result["changes"] = []
            result["status"] = "preview" if dry_run else "unchanged"
        file_results.append(result)

    written = [item for item in file_results if item.get("status") == "written"]
    approval_result = {
        "tool": "approve_draft_item",
        "item_type": "domain",
        "domain_name": domain_name,
        "dry_run": dry_run,
        "status": "preview" if dry_run else ("written" if written else "unchanged"),
        "file_results": file_results,
        "applied_to": [item.get("path") for item in file_results if item.get("path")],
        "written_paths": [item.get("path") for item in written if item.get("path")],
        "body_preserved": True,
        "approval_policy": "single_domain_multi_note_review",
    }
    if not dry_run and written:
        approval_id = core.storage.record_approved_item(
            "domain",
            {"domain_name": domain_name, "paths": paths, "file_results": file_results},
        )
        approval_result["approval_id"] = approval_id
    return approval_result


def approve_causal_link_item(
    core,
    source_path: str,
    target_path: str,
    relation: str,
    evidence: str,
    dry_run: bool,
) -> Dict[str, Any]:
    if not source_path or not target_path or not relation:
        return {"error": "missing_causal_link_fields", "item_type": "causal_link"}
    payload = {
        "source_path": source_path,
        "target_path": target_path,
        "relation": relation,
        "evidence": evidence or "",
        "confidence": "accepted_by_human" if not dry_run else "preview",
    }
    result = {
        "tool": "approve_draft_item",
        "item_type": "causal_link",
        "dry_run": dry_run,
        "status": "preview" if dry_run else "recorded",
        "payload": payload,
        "body_preserved": True,
        "writes_source_notes": False,
        "storage": ".linza/linza.db:approved_items",
        "approval_policy": "record_relation_only_after_review",
    }
    if not dry_run:
        result["approval_id"] = core.storage.record_approved_item("causal_link", payload)
    return result


def approve_hierarchy_link_item(
    core,
    parent_path: str,
    child_paths: list[str],
    domain_name: str,
    relation: str,
    evidence: str,
    dry_run: bool,
) -> Dict[str, Any]:
    normalized_children = []
    for path in child_paths or []:
        child_path = str(path).strip()
        if child_path and child_path != parent_path and child_path not in normalized_children:
            normalized_children.append(child_path)
    if not parent_path or not normalized_children:
        return {"error": "missing_hierarchy_link_fields", "item_type": "hierarchy_link"}
    payload = {
        "parent_path": parent_path,
        "child_paths": normalized_children,
        "domain_name": domain_name or "",
        "relation": relation or "parent_of",
        "evidence": evidence or "",
        "confidence": "accepted_by_human" if not dry_run else "preview",
    }
    result = {
        "tool": "approve_draft_item",
        "item_type": "hierarchy_link",
        "dry_run": dry_run,
        "status": "preview" if dry_run else "recorded",
        "payload": payload,
        "body_preserved": True,
        "writes_source_notes": False,
        "storage": ".linza/linza.db:approved_items",
        "approval_policy": "record_hierarchy_only_after_review",
    }
    if not dry_run:
        result["approval_id"] = core.storage.record_approved_item("hierarchy_link", payload)
    return result


def approve_memory_item(
    core,
    source_path: str,
    memory_type: str,
    summary: str,
    evidence: str,
    signals: Any,
    dry_run: bool,
    recall_context: Any = None,
    review_after: str = "",
    staleness_risk: str = "",
    conflict_candidates: Any = None,
    evolution: Any = None,
    review_questions: Any = None,
) -> Dict[str, Any]:
    normalized_type = str(memory_type or "").strip().lower()
    if normalized_type not in {"episodic", "semantic", "procedural", "prospective"}:
        return {
            "error": "unsupported_memory_type",
            "item_type": "memory_item",
            "supported_memory_types": ["episodic", "semantic", "procedural", "prospective"],
        }
    if not source_path or not summary:
        return {"error": "missing_memory_item_fields", "item_type": "memory_item"}
    if isinstance(signals, str):
        parsed_signals = [signals] if signals.strip() else []
    elif isinstance(signals, list):
        parsed_signals = [str(item) for item in signals if str(item).strip()]
    else:
        parsed_signals = []
    if isinstance(recall_context, str):
        parsed_recall_context = [recall_context] if recall_context.strip() else []
    elif isinstance(recall_context, list):
        parsed_recall_context = [str(item) for item in recall_context if str(item).strip()]
    else:
        parsed_recall_context = []
    if isinstance(review_questions, str):
        parsed_review_questions = [review_questions] if review_questions.strip() else []
    elif isinstance(review_questions, list):
        parsed_review_questions = [str(item) for item in review_questions if str(item).strip()]
    else:
        parsed_review_questions = []
    parsed_staleness = str(staleness_risk or "").strip().lower()
    if parsed_staleness not in {"low", "medium", "high"}:
        parsed_staleness = "medium"
    parsed_conflicts = conflict_candidates if isinstance(conflict_candidates, list) else []
    parsed_evolution = evolution if isinstance(evolution, dict) else {}
    payload = {
        "source_path": source_path,
        "memory_type": normalized_type,
        "summary": summary,
        "evidence": evidence or "",
        "signals": sorted(set(parsed_signals)),
        "recall_context": list(dict.fromkeys(parsed_recall_context)),
        "review_after": str(review_after or ""),
        "staleness_risk": parsed_staleness,
        "conflict_candidates": parsed_conflicts,
        "evolution": parsed_evolution,
        "review_questions": list(dict.fromkeys(parsed_review_questions)),
        "confidence": "accepted_by_human" if not dry_run else "preview",
    }
    result = {
        "tool": "approve_draft_item",
        "item_type": "memory_item",
        "dry_run": dry_run,
        "status": "preview" if dry_run else "recorded",
        "payload": payload,
        "body_preserved": True,
        "writes_source_notes": False,
        "storage": ".linza/linza.db:approved_items",
        "approval_policy": "record_memory_only_after_review",
    }
    if not dry_run:
        result["approval_id"] = core.storage.record_approved_item("memory_item", payload)
    return result


def approve_material_type_item(
    core,
    type_id: str,
    type_name: str,
    paths: list[str],
    evidence: str,
    dry_run: bool,
) -> Dict[str, Any]:
    """Accept a human name for a discovered draft material type.

    This records only the mapping in the sidecar. YAML `role` writes are a
    separate review step so the draft cluster id never becomes user metadata.
    """
    normalized_id = str(type_id or "").strip()
    normalized_name = str(type_name or "").strip()
    normalized_paths = []
    for path in paths or []:
        note_path = str(path).strip()
        if note_path and note_path not in normalized_paths:
            normalized_paths.append(note_path)
    if not normalized_id:
        return {"error": "missing_type_id", "item_type": "material_type"}
    if not normalized_name and not dry_run:
        return {
            "tool": "approve_draft_item",
            "item_type": "material_type",
            "dry_run": dry_run,
            "status": "blocked_missing_type_name",
            "type_id": normalized_id,
            "applied_to": normalized_paths,
            "body_preserved": True,
            "writes_source_notes": False,
            "approval_policy": "name_material_type_before_yaml_roles",
        }

    payload = {
        "type_id": normalized_id,
        "type_name": normalized_name,
        "paths": normalized_paths,
        "evidence": evidence or "",
        "confidence": "accepted_by_human" if not dry_run else "preview",
    }
    result = {
        "tool": "approve_draft_item",
        "item_type": "material_type",
        "dry_run": dry_run,
        "status": "preview" if dry_run else "recorded",
        "payload": payload,
        "requires_type_name": not bool(normalized_name),
        "applied_to": normalized_paths,
        "written_paths": [],
        "body_preserved": True,
        "writes_source_notes": False,
        "storage": ".linza/linza.db:approved_items",
        "approval_policy": "name_material_type_before_yaml_roles",
    }
    if not dry_run:
        result["approval_id"] = core.storage.record_approved_item("material_type", payload)
    return result


def approve_draft_item(
    core,
    item_type: str,
    dry_run: bool = True,
    allow_overwrite: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Approve one LINZA draft item at a time; dry-run by default."""
    normalized_type = str(item_type or "").strip().lower()
    if normalized_type == "role":
        return approve_role_item(
            core,
            str(kwargs.get("path", "")),
            str(kwargs.get("role", "")),
            dry_run,
            allow_overwrite,
        )
    if normalized_type == "domain":
        raw_paths = kwargs.get("paths") or ([] if not kwargs.get("path") else [kwargs.get("path")])
        paths = [str(path) for path in raw_paths if str(path).strip()]
        return approve_domain_item(
            core,
            str(kwargs.get("domain_name", "")),
            paths,
            dry_run,
            allow_overwrite,
        )
    if normalized_type == "causal_link":
        return approve_causal_link_item(
            core,
            str(kwargs.get("source_path", "")),
            str(kwargs.get("target_path", "")),
            str(kwargs.get("relation", "")),
            str(kwargs.get("evidence", "")),
            dry_run,
        )
    if normalized_type == "hierarchy_link":
        return approve_hierarchy_link_item(
            core,
            str(kwargs.get("parent_path", "")),
            [str(path) for path in kwargs.get("child_paths", []) if str(path).strip()],
            str(kwargs.get("domain_name", "")),
            str(kwargs.get("relation", "parent_of")),
            str(kwargs.get("evidence", "")),
            dry_run,
        )
    if normalized_type == "memory_item":
        return approve_memory_item(
            core,
            str(kwargs.get("source_path", "")),
            str(kwargs.get("memory_type", "")),
            str(kwargs.get("summary", "")),
            str(kwargs.get("evidence", "")),
            kwargs.get("signals", []),
            dry_run,
            kwargs.get("recall_context", []),
            str(kwargs.get("review_after", "")),
            str(kwargs.get("staleness_risk", "")),
            kwargs.get("conflict_candidates", []),
            kwargs.get("evolution", {}),
            kwargs.get("review_questions", []),
        )
    if normalized_type == "material_type":
        raw_paths = kwargs.get("paths") or ([] if not kwargs.get("path") else [kwargs.get("path")])
        return approve_material_type_item(
            core,
            str(kwargs.get("type_id", "")),
            str(kwargs.get("type_name", "")),
            [str(path) for path in raw_paths if str(path).strip()],
            str(kwargs.get("evidence", "")),
            dry_run,
        )
    return {
        "error": "unsupported_item_type",
        "item_type": item_type,
        "supported_item_types": ["role", "domain", "material_type", "hierarchy_link", "causal_link", "memory_item"],
    }


def learning_examples_from_storage(storage) -> Dict[str, Any]:
    """Summarize accepted sidecar/YAML decisions as local learning examples."""
    items = storage.list_approved_items(limit=1000)
    counts = Counter(item.get("item_type", "unknown") for item in items)
    roles: set[str] = set()
    domains: set[str] = set()
    hierarchy_domains: set[str] = set()
    relations: set[str] = set()
    hierarchy_relations: set[str] = set()
    causal_relations: set[str] = set()
    memory_types: set[str] = set()
    material_types: dict[str, str] = {}
    path_prefixes: set[str] = set()
    approved_signatures: set[str] = set()
    for item in items:
        payload = item.get("payload", {})
        item_type = item.get("item_type")
        approved_signatures.add(queue_item_signature(str(item_type), payload))
        path_prefixes.update(approved_path_prefixes(str(item_type), payload))
        if item_type == "role" and payload.get("role"):
            roles.add(str(payload["role"]))
        elif item_type == "domain" and payload.get("domain_name"):
            domains.add(str(payload["domain_name"]))
        elif item_type == "hierarchy_link":
            if payload.get("domain_name"):
                hierarchy_domains.add(str(payload["domain_name"]))
            if payload.get("relation"):
                relation = str(payload["relation"])
                relations.add(relation)
                hierarchy_relations.add(relation)
        elif item_type == "causal_link" and payload.get("relation"):
            relation = str(payload["relation"])
            relations.add(relation)
            causal_relations.add(relation)
        elif item_type == "memory_item" and payload.get("memory_type"):
            memory_types.add(str(payload["memory_type"]))
        elif item_type == "material_type" and payload.get("type_id") and payload.get("type_name"):
            material_types[str(payload["type_id"])] = str(payload["type_name"])
    rules = {
        "role_values": sorted(roles),
        "domain_names": sorted(domains),
        "material_type_names": sorted(set(material_types.values())),
        "hierarchy_domains": sorted(hierarchy_domains),
        "hierarchy_relations": sorted(hierarchy_relations),
        "causal_relations": sorted(causal_relations),
        "memory_types": sorted(memory_types),
        "path_prefixes": sorted(path_prefixes),
    }
    return {
        "counts": dict(sorted(counts.items())),
        "roles": sorted(roles),
        "domains": sorted(domains),
        "hierarchy_domains": sorted(hierarchy_domains),
        "relations": sorted(relations),
        "memory_types": sorted(memory_types),
        "material_types": dict(sorted(material_types.items())),
        "rules": rules,
        "approved_signatures": sorted(sig for sig in approved_signatures if sig),
        "total_examples": sum(counts.values()),
    }


def approved_path_prefixes(item_type: str, payload: Dict[str, Any]) -> set[str]:
    paths: list[str] = []
    if item_type == "role" and payload.get("path"):
        paths.append(str(payload["path"]))
    elif item_type in {"domain", "material_type"}:
        paths.extend(str(path) for path in payload.get("paths", []) if str(path).strip())
    elif item_type == "hierarchy_link":
        paths.append(str(payload.get("parent_path", "")))
        paths.extend(str(path) for path in payload.get("child_paths", []) if str(path).strip())
    elif item_type == "causal_link":
        paths.extend([str(payload.get("source_path", "")), str(payload.get("target_path", ""))])
    elif item_type == "memory_item" and payload.get("source_path"):
        paths.append(str(payload["source_path"]))

    prefixes: set[str] = set()
    for path in paths:
        rel = path.replace("\\", "/").strip("/")
        if "/" in rel:
            prefix = rel.split("/", 1)[0].strip()
            if prefix:
                prefixes.add(prefix)
    return prefixes


def queue_item_signature(item_type: str, arguments: Dict[str, Any]) -> str:
    normalized_type = str(item_type or "").strip().lower()
    if normalized_type == "role":
        return f"role|{arguments.get('path', '')}|{arguments.get('role', '')}"
    if normalized_type == "material_type":
        type_id = str(arguments.get("type_id", "")).strip()
        if not type_id:
            return ""
        return f"material_type|{type_id}"
    if normalized_type == "domain":
        paths = sorted(str(path) for path in arguments.get("paths", []) if str(path).strip())
        if not paths:
            return ""
        return f"domain|{arguments.get('domain_name', '')}|{','.join(paths)}"
    if normalized_type == "hierarchy_link":
        children = sorted(str(path) for path in arguments.get("child_paths", []) if str(path).strip())
        if not arguments.get("parent_path") or not children:
            return ""
        return (
            f"hierarchy_link|{arguments.get('parent_path', '')}|"
            f"{arguments.get('relation', 'parent_of')}|{','.join(children)}"
        )
    if normalized_type == "causal_link":
        if not arguments.get("source_path") or not arguments.get("target_path"):
            return ""
        return (
            f"causal_link|{arguments.get('source_path', '')}|"
            f"{arguments.get('target_path', '')}|{arguments.get('relation', '')}"
        )
    if normalized_type == "memory_item":
        if not arguments.get("source_path") or not arguments.get("summary"):
            return ""
        return (
            f"memory_item|{arguments.get('source_path', '')}|"
            f"{arguments.get('memory_type', '')}|{arguments.get('summary', '')}"
        )
    return ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", str(text or ""), flags=re.UNICODE))


def _is_generic_memory_summary(summary: str) -> bool:
    normalized = str(summary or "").strip().lower()
    if not normalized:
        return True
    if normalized.endswith(":"):
        return True
    if re.match(r"^[a-z_ -]{2,24}:\s*[a-z_ -]{2,40}$", normalized, re.IGNORECASE):
        return True
    if re.search(r"\b(name|title|type|kind|label)\s*:", normalized, re.IGNORECASE):
        return True
    if re.search(r"\b(something|some kind of|unknown|todo|placeholder)\b", normalized, re.IGNORECASE):
        return True
    if re.search(r"\bкакие-то\b|\bкакая-то\b|\bчто-то\b|\bнепонятно\b|\bзаглушк", normalized, re.IGNORECASE):
        return True
    return False


def _memory_growth_quality_reasons(arguments: Dict[str, Any]) -> list[str]:
    summary = str(arguments.get("summary", "")).strip()
    evidence = str(arguments.get("evidence", "")).strip()
    memory_type = str(arguments.get("memory_type", "")).strip().lower()
    signals = set(_string_list(arguments.get("signals", [])))
    recall_context = _string_list(arguments.get("recall_context", []))
    evolution = arguments.get("evolution", {})
    related_sources = evolution.get("related_sources", []) if isinstance(evolution, dict) else []

    if _is_generic_memory_summary(summary):
        return []
    if _word_count(summary) < 8 or len(summary) < 50:
        return []
    if _word_count(evidence) < 10 or len(evidence) < 80:
        return []

    durable_signals = sorted(signals & {
        "decision",
        "action",
        "result",
        "procedural_rule",
        "prospective_task",
        "prediction_error",
        "procedure",
        "future_intention",
    })
    quality_reasons = ["memory_quality:specific_summary", "memory_quality:specific_evidence"]
    if recall_context:
        quality_reasons.append("memory_quality:recall_context")
    if related_sources:
        quality_reasons.append("memory_quality:related_sources")

    if memory_type in {"procedural", "prospective"} and durable_signals:
        quality_reasons.append(f"memory_quality:durable_signal:{durable_signals[0]}")
        return quality_reasons
    if len(durable_signals) >= 2:
        quality_reasons.append(f"memory_quality:durable_signal:{durable_signals[0]}")
        quality_reasons.append("memory_quality:multiple_durable_signals")
        return quality_reasons
    if memory_type == "semantic" and "semantic_candidate" in signals and len(evidence) >= 160:
        quality_reasons.append("memory_quality:semantic_candidate")
        return quality_reasons
    return []


def _memory_learning_base_reasons(
    arguments: Dict[str, Any],
    examples: Dict[str, Any],
    mode: str,
    priority: str,
    shared_prefixes: list[str],
) -> list[str]:
    memory_type = str(arguments.get("memory_type", ""))
    memory_types = set(examples.get("memory_types", []))
    counts = examples.get("counts", {})
    if (
        mode == "assisted"
        and memory_type in memory_types
        and counts.get("memory_item", 0) >= 2
        and shared_prefixes
        and priority in {"high", "medium"}
    ):
        return [f"accepted_memory_type:{memory_type}", f"accepted_memory_prefix:{shared_prefixes[0]}"]
    if mode == "autopilot" and memory_type in memory_types:
        return [f"autopilot_memory_type_example:{memory_type}"]
    return []


def _memory_learning_rejection_reasons(item: Dict[str, Any], examples: Dict[str, Any], mode: str) -> list[str]:
    if mode == "review":
        return []
    arguments = item.get("approval", {}).get("arguments", {})
    item_type = arguments.get("item_type") or item.get("kind")
    if item_type != "memory_item":
        return []
    if queue_item_signature(str(item_type), arguments) in set(examples.get("approved_signatures", [])):
        return []
    rules = examples.get("rules", {}) if isinstance(examples.get("rules", {}), dict) else {}
    learned_prefixes = set(rules.get("path_prefixes", []))
    shared_prefixes = sorted(approved_path_prefixes(str(item_type), arguments) & learned_prefixes)
    base_reasons = _memory_learning_base_reasons(
        arguments,
        examples,
        mode,
        str(item.get("priority", "medium")),
        shared_prefixes,
    )
    if base_reasons and not _memory_growth_quality_reasons(arguments):
        return ["blocked_memory_quality_gate", *base_reasons]
    return []


def _learning_match_reasons(item: Dict[str, Any], examples: Dict[str, Any], mode: str) -> list[str]:
    if mode == "review":
        return []
    arguments = item.get("approval", {}).get("arguments", {})
    item_type = arguments.get("item_type") or item.get("kind")
    if queue_item_signature(str(item_type), arguments) in set(examples.get("approved_signatures", [])):
        return []
    priority = str(item.get("priority", "medium"))
    roles = set(examples.get("roles", []))
    domains = set(examples.get("domains", []))
    hierarchy_domains = set(examples.get("hierarchy_domains", []))
    relations = set(examples.get("relations", []))
    counts = examples.get("counts", {})
    rules = examples.get("rules", {}) if isinstance(examples.get("rules", {}), dict) else {}
    material_type_names = set(rules.get("material_type_names", []))
    hierarchy_relations = set(rules.get("hierarchy_relations", []))
    causal_relations = set(rules.get("causal_relations", []))
    learned_prefixes = set(rules.get("path_prefixes", []))
    shared_prefixes = sorted(approved_path_prefixes(str(item_type), arguments) & learned_prefixes)
    reasons: list[str] = []

    if item_type == "role":
        role = str(arguments.get("role", ""))
        if role in roles and priority in {"high", "medium"}:
            reasons.append(f"accepted_role_example:{role}")
        if role in material_type_names and priority in {"high", "medium"}:
            reasons.append(f"accepted_material_type_name:{role}")
    if item_type == "domain":
        domain_name = str(arguments.get("domain_name", ""))
        if domain_name in domains:
            reasons.append(f"accepted_domain_example:{domain_name}")
        if mode == "autopilot" and counts.get("domain", 0) >= 1 and priority == "high":
            reasons.append("autopilot_domain_after_examples")
    if item_type == "hierarchy_link":
        domain_name = str(arguments.get("domain_name", ""))
        relation = str(arguments.get("relation", "parent_of"))
        if relation in hierarchy_relations and (not domain_name or domain_name in domains or domain_name in hierarchy_domains):
            reasons.append(f"accepted_hierarchy_relation:{relation}")
        if counts.get("hierarchy_link", 0) >= 1 and (not domain_name or domain_name in domains or domain_name in hierarchy_domains):
            reasons.append("accepted_hierarchy_example")
        if relation in hierarchy_relations and counts.get("hierarchy_link", 0) >= 2 and shared_prefixes and priority in {"high", "medium"}:
            if f"accepted_hierarchy_relation:{relation}" not in reasons:
                reasons.append(f"accepted_hierarchy_relation:{relation}")
            reasons.append(f"accepted_hierarchy_prefix:{shared_prefixes[0]}")
        if mode == "autopilot" and counts.get("hierarchy_link", 0) >= 1:
            reasons.append("autopilot_hierarchy_after_examples")
    if item_type == "causal_link":
        relation = str(arguments.get("relation", ""))
        if relation and relation in causal_relations:
            reasons.append(f"accepted_causal_relation:{relation}")
        if relation and relation in causal_relations and shared_prefixes:
            reasons.append(f"accepted_causal_prefix:{shared_prefixes[0]}")
        if mode == "autopilot" and counts.get("causal_link", 0) >= 1 and (not relation or relation in relations):
            reasons.append("autopilot_causal_after_examples")
    if item_type == "memory_item":
        base_reasons = _memory_learning_base_reasons(arguments, examples, mode, priority, shared_prefixes)
        quality_reasons = _memory_growth_quality_reasons(arguments)
        if base_reasons and quality_reasons:
            reasons.extend(base_reasons)
            reasons.extend(quality_reasons)
    return reasons


def select_learned_queue_matches(
    items: list[Dict[str, Any]],
    examples: Dict[str, Any],
    mode: str = "review",
) -> Dict[str, list[str]]:
    normalized_mode = str(mode or "review").strip().lower()
    if normalized_mode not in {"review", "assisted", "autopilot"}:
        raise ValueError("mode must be review, assisted, or autopilot")
    matches: Dict[str, list[str]] = {}
    for item in items:
        item_id = str(item.get("id", ""))
        reasons = _learning_match_reasons(item, examples, normalized_mode)
        if item_id and reasons:
            matches[item_id] = reasons
    return matches


def select_learned_queue_items(
    items: list[Dict[str, Any]],
    examples: Dict[str, Any],
    mode: str = "review",
) -> list[str]:
    normalized_mode = str(mode or "review").strip().lower()
    if normalized_mode not in {"review", "assisted", "autopilot"}:
        raise ValueError("mode must be review, assisted, or autopilot")
    return list(select_learned_queue_matches(items, examples, normalized_mode))


async def apply_learned_review_queue(
    core,
    mode: str = "review",
    max_notes: int = 120,
    max_domains: int = 8,
    limit: int = 40,
    dry_run: bool = True,
    allow_overwrite: bool = False,
    include_memory: bool = False,
) -> Dict[str, Any]:
    """Select queue cards from accepted examples, then preview/apply them."""
    normalized_mode = str(mode or "review").strip().lower()
    if normalized_mode not in {"review", "assisted", "autopilot"}:
        return {
            "tool": "apply_learned_review_queue",
            "status": "blocked_invalid_mode",
            "error": "mode must be review, assisted, or autopilot",
            "supported_modes": ["review", "assisted", "autopilot"],
        }
    batch_limit = max(1, int(limit))
    queue_scan_limit = max(batch_limit, min(200, max(40, batch_limit * 4)))
    queue = await core.build_review_apply_queue(
        max_notes=max_notes,
        max_domains=max_domains,
        limit=queue_scan_limit,
        include_memory=include_memory,
    )
    examples = learning_examples_from_storage(core.storage)
    all_selected_matches = select_learned_queue_matches(queue.get("items", []), examples, normalized_mode)
    skipped_matches: Dict[str, list[str]] = {}
    for item in queue.get("items", []):
        item_id = str(item.get("id", ""))
        rejection_reasons = _memory_learning_rejection_reasons(item, examples, normalized_mode)
        if item_id and rejection_reasons:
            skipped_matches[item_id] = rejection_reasons
    selected_ids = list(all_selected_matches)[:batch_limit]
    selected_matches = {
        item_id: all_selected_matches[item_id]
        for item_id in selected_ids
    }
    response: Dict[str, Any] = {
        "tool": "apply_learned_review_queue",
        "status": "review" if normalized_mode == "review" else ("no_learned_matches" if not selected_ids else ("preview" if dry_run else "applied")),
        "mode": normalized_mode,
        "dry_run": dry_run,
        "selected_ids": selected_ids,
        "selected_rules": [
            {"id": item_id, "reasons": reasons}
            for item_id, reasons in selected_matches.items()
        ],
        "skipped_rules": [
            {"id": item_id, "reasons": reasons}
            for item_id, reasons in list(skipped_matches.items())[:20]
        ],
        "learning": examples,
        "queue_summary": queue.get("summary", {}),
        "selection_window": {
            "batch_limit": batch_limit,
            "queue_scan_limit": queue_scan_limit,
            "matched_before_batch_limit": len(all_selected_matches),
        },
        "policy": [
            "review mode never selects or applies items automatically.",
            "assisted mode selects only cards supported by accepted examples and local learning rules.",
            "autopilot can select more sidecar relations after examples, but still supports dry_run.",
            "Existing note bodies must remain unchanged; source-note content is not rewritten.",
        ],
    }
    if normalized_mode == "review" or not selected_ids:
        return response
    apply_result = await core.approve_review_queue_items(
        item_ids=selected_ids,
        max_notes=max_notes,
        max_domains=max_domains,
        limit=queue_scan_limit,
        dry_run=dry_run,
        allow_overwrite=allow_overwrite,
        include_memory=include_memory,
    )
    response["apply_result"] = apply_result
    response["status"] = apply_result.get("status", response["status"])
    response["written_paths"] = apply_result.get("written_paths", [])
    return response


async def approve_review_queue_items(
    core,
    item_ids: list[str],
    max_notes: int = 120,
    max_domains: int = 8,
    limit: int = 40,
    dry_run: bool = True,
    allow_overwrite: bool = False,
    include_memory: bool = False,
) -> Dict[str, Any]:
    """Approve selected stable IDs from build_review_apply_queue; dry-run by default."""
    raw_ids = [] if item_ids is None else ([item_ids] if isinstance(item_ids, str) else item_ids)
    requested_ids: list[str] = []
    seen_requested: set[str] = set()
    for item_id in raw_ids:
        normalized_id = str(item_id).strip().lower()
        if not normalized_id or normalized_id in seen_requested:
            continue
        seen_requested.add(normalized_id)
        requested_ids.append(normalized_id)

    if not requested_ids:
        return {
            "tool": "approve_review_queue_items",
            "status": "missing_item_ids",
            "dry_run": dry_run,
            "read_only": True,
            "error": "missing_item_ids",
            "policy": ["Pass exact IDs from build_review_apply_queue.items[].id."],
        }

    queue = await core.build_review_apply_queue(
        max_notes=max_notes,
        max_domains=max_domains,
        limit=limit,
        include_memory=include_memory,
    )
    items_by_id = {str(item["id"]).lower(): item for item in queue.get("items", [])}
    missing_ids = [item_id for item_id in requested_ids if item_id not in items_by_id]
    if missing_ids:
        return {
            "tool": "approve_review_queue_items",
            "status": "blocked_missing_items",
            "dry_run": dry_run,
            "read_only": True,
            "requested_ids": requested_ids,
            "missing_ids": missing_ids,
            "available_ids": [item["id"] for item in queue.get("items", [])],
            "results": [],
            "summary": {
                "requested": len(requested_ids),
                "matched": 0,
                "applied": 0,
                "previewed": 0,
            },
            "policy": ["Nothing was applied because at least one requested ID was not in the rebuilt queue."],
        }

    selected_items = [items_by_id[item_id] for item_id in requested_ids]
    preview_results: list[Dict[str, Any]] = []
    if not dry_run:
        for item in selected_items:
            arguments = dict(item.get("approval", {}).get("arguments", {}))
            arguments["dry_run"] = True
            arguments["allow_overwrite"] = allow_overwrite
            preview = approve_draft_item(core, **arguments)
            preview_results.append({
                "id": item["id"],
                "kind": item["kind"],
                "title": item["title"],
                "human": item.get("human", {}),
                "approval_result": preview,
            })
        failed_previews = [
            result for result in preview_results
            if result.get("approval_result", {}).get("error")
        ]
        if failed_previews:
            return {
                "tool": "approve_review_queue_items",
                "status": "blocked_preview_failed",
                "dry_run": dry_run,
                "read_only": True,
                "requested_ids": requested_ids,
                "missing_ids": [],
                "results": preview_results,
                "summary": {
                    "requested": len(requested_ids),
                    "matched": len(selected_items),
                    "applied": 0,
                    "previewed": len(preview_results),
                },
                "policy": ["Nothing was applied because a dry-run preview failed."],
            }

    results: list[Dict[str, Any]] = []
    written_paths: set[str] = set()
    for item in selected_items:
        arguments = dict(item.get("approval", {}).get("arguments", {}))
        arguments["dry_run"] = dry_run
        arguments["allow_overwrite"] = allow_overwrite
        approval_result = approve_draft_item(core, **arguments)
        for path in approval_written_paths(approval_result):
            written_paths.add(path)
        results.append({
            "id": item["id"],
            "kind": item["kind"],
            "title": item["title"],
            "human": item.get("human", {}),
            "approval_result": approval_result,
        })

    applied_count = sum(
        1 for result in results
        if result.get("approval_result", {}).get("status") in {"written", "recorded"}
    )
    previewed_count = sum(
        1 for result in results
        if result.get("approval_result", {}).get("status") == "preview"
    )
    return {
        "tool": "approve_review_queue_items",
        "status": "preview" if dry_run else "applied",
        "dry_run": dry_run,
        "read_only": dry_run,
        "requested_ids": requested_ids,
        "missing_ids": [],
        "results": results,
        "written_paths": sorted(written_paths),
        "summary": {
            "requested": len(requested_ids),
            "matched": len(selected_items),
            "applied": applied_count,
            "previewed": previewed_count,
        },
        "policy": [
            "Approves only explicitly selected stable IDs.",
            "Dry-run is the default; use dry_run=false only after reviewing the preview.",
        ],
    }


__all__ = [
    "approval_payload",
    "stable_queue_item_id",
    "assign_queue_item_ids",
    "redacted_queue_item",
    "redacted_queue_items",
    "human_review_metadata",
    "apply_queue_markdown",
    "build_review_apply_queue",
    "approval_written_paths",
    "merge_linza_domains",
    "approve_role_item",
    "approve_domain_item",
    "approve_causal_link_item",
    "approve_hierarchy_link_item",
    "approve_memory_item",
    "approve_draft_item",
    "approve_review_queue_items",
    "approved_path_prefixes",
    "learning_examples_from_storage",
    "queue_item_signature",
    "select_learned_queue_matches",
    "select_learned_queue_items",
    "apply_learned_review_queue",
]
