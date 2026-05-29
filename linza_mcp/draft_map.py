"""Draft vault-map builders for LINZA."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from .chunker import split_semantic_chunks, strip_generated_service_sections
from .roles import discover_material_types, material_type_features, material_type_vocabulary, public_role as normalize_public_role
from .utils import LINZA_EVENT_PATTERNS, normalize_note_name, tokenize


def preview_text(text: str, limit: int = 180) -> str:
    preview = re.sub(r"\s+", " ", text).strip()
    if len(preview) > limit:
        return preview[: limit - 3].rstrip() + "..."
    return preview


def percentile(values: list[float], percentile_value: float, fallback: float) -> float:
    if not values:
        return fallback
    return float(np.percentile(np.array(values, dtype=float), percentile_value))


def group_records_by_role_or_folder(records: list[Dict[str, Any]]) -> Dict[str, list[Dict[str, Any]]]:
    groups: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for record in sorted(records, key=lambda item: item["path"]):
        key = record.get("role") or "untyped"
        if key == "untyped" and record.get("folder"):
            key = f"folder:{record['folder']}"
        groups[key].append(record)
    return groups


def parent_score(
    record: Dict[str, Any],
    incoming: Dict[str, list[str]],
    outgoing: Dict[str, list[str]],
) -> float:
    title = normalize_note_name(record["title"])
    score = 0.0
    score += len(incoming.get(record["path"], [])) * 0.35
    score += len(outgoing.get(record["path"], [])) * 0.2
    if re.search(r"\b(index|moc|map|overview|обзор|карта|система|модуль)\b", title):
        score += 0.7
    if 80 <= record["word_count"] <= 1800:
        score += 0.2
    if "/" not in record["path"]:
        score += 0.08
    return round(score, 4)


def select_draft_notes(notes: list[Dict[str, Any]], max_notes: int) -> list[Dict[str, Any]]:
    if len(notes) <= max_notes:
        return notes
    by_area: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for note in sorted(notes, key=lambda item: item["path"]):
        top = note["path"].split("/", 1)[0] if "/" in note["path"] else "(root)"
        by_area[top].append(note)

    selected: list[Dict[str, Any]] = []
    area_names = sorted(by_area.keys())
    cursor = 0
    while len(selected) < max_notes and area_names:
        area = area_names[cursor % len(area_names)]
        bucket = by_area[area]
        if bucket:
            selected.append(bucket.pop(0))
        area_names = [name for name in area_names if by_area[name]]
        cursor += 1
    return selected


def public_role(role: str) -> str:
    return normalize_public_role(role)


def role_confidence(record: Dict[str, Any]) -> str:
    reason = str(record.get("role_reason", ""))
    role = str(record.get("role", "untyped"))
    if reason == "accepted_yaml":
        return "accepted"
    if role == "untyped":
        return "low"
    return str(record.get("material_type_confidence") or "medium")


def build_role_draft(records: list[Dict[str, Any]], assigned_to: Dict[str, list[str]]) -> Dict[str, Any]:
    discovery = discover_material_types(records, assigned_to)
    candidates_by_id = {item["id"]: item for item in discovery.get("types", [])}
    notes = []
    for record in sorted(records, key=lambda item: item["path"]):
        role = discovery.get("assignments", {}).get(record["path"], record.get("role", "untyped"))
        type_candidate = candidates_by_id.get(role, {})
        record["role"] = role
        record["raw_role"] = role
        record["role_reason"] = "accepted_yaml" if type_candidate.get("confidence") == "accepted" else "material_type_cluster"
        record["material_type_confidence"] = type_candidate.get("confidence", "low")
        notes.append({
            "path": record["path"],
            "title": record["title"],
            "role": role,
            "raw_role": role,
            "confidence": role_confidence(record),
            "reason": record.get("role_reason", "fallback"),
            "domain_ids": assigned_to.get(record["path"], []),
            "evidence": {
                "folder": record.get("folder", ""),
                "tags": record.get("tags", [])[:8],
                "headings": record.get("headings", [])[:5],
                "shape": record.get("material_features", {}).get("shape_tokens", [])[:10],
                "suggested_label": type_candidate.get("suggested_label", role),
            },
        })

    review = [
        {
            "path": item["path"],
            "role": item["role"],
            "why": "Role is generic or low-confidence; ask the user before writing any metadata.",
        }
        for item in notes
        if item["confidence"] == "low" or item["role"] == "untyped"
    ][:30]

    return {
        "policy": "discover_from_vault_then_review",
        "notes": notes,
        "role_counts": Counter(item["role"] for item in notes).most_common(),
        "material_type_counts": Counter(item["role"] for item in notes).most_common(),
        "material_type_candidates": discovery.get("types", []),
        "discovery": {
            "threshold": discovery.get("threshold"),
            "note": discovery.get("note"),
        },
        "review": review,
        "note": "Material types are discovered from this vault and remain review candidates until accepted.",
    }


def split_event_sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [piece.strip(" \t-") for piece in pieces if piece.strip(" \t-")]


def event_time_hint(value: str) -> Optional[str]:
    match = re.search(r"\b(20\d{2})[-_.](\d{2})[-_.](\d{2})\b", value)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    match = re.search(r"\b(20\d{2})(\d{2})(\d{2})\b", value)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None


def event_relation(left_type: str, right_type: str) -> Optional[str]:
    if left_type in {"fact", "hypothesis"} and right_type in {"decision", "action"}:
        return "basis_for"
    if left_type == "decision" and right_type == "action":
        return "led_to_action"
    if left_type == "action" and right_type == "result":
        return "led_to_result"
    if left_type == "result" and right_type in {"decision", "hypothesis"}:
        return "informed"
    return None


def build_event_flow_draft(
    records: list[Dict[str, Any]],
    assigned_to: Dict[str, list[str]],
    limit: int = 50,
) -> Dict[str, Any]:
    events: list[Dict[str, Any]] = []
    events_by_path: Dict[str, list[Dict[str, Any]]] = defaultdict(list)

    for record in sorted(records, key=lambda item: item["path"]):
        for chunk in record.get("chunks", []):
            for sentence in split_event_sentences(chunk.get("text", "")):
                matched: Optional[tuple[str, str, str]] = None
                for event_type, pattern, signal in LINZA_EVENT_PATTERNS:
                    if re.search(pattern, sentence, re.IGNORECASE):
                        matched = (event_type, pattern, signal)
                        break
                if not matched:
                    continue
                event_type, _pattern, signal = matched
                prefix_markers = {
                    "fact": r"fact|observation|факт|наблюдение|проверка",
                    "decision": r"decision|решение|решили|выбрали|принято",
                    "action": r"action|done|сделано|действие",
                    "result": r"result|outcome|итог|результат|следствие",
                    "hypothesis": r"hypothesis|assumption|гипотеза|предположение",
                }
                prefix_hit = bool(
                    re.match(rf"^\s*({prefix_markers[event_type]})\s*[:—-]", sentence, re.IGNORECASE)
                )
                event = {
                    "id": f"event-{len(events) + 1:03d}",
                    "type": event_type,
                    "path": record["path"],
                    "title": record["title"],
                    "role": record["role"],
                    "domain_ids": assigned_to.get(record["path"], []),
                    "chunk_id": chunk.get("chunk_id"),
                    "heading": chunk.get("heading"),
                    "time_hint": event_time_hint(" ".join([
                        record.get("path", ""),
                        record.get("title", ""),
                        str(chunk.get("heading") or ""),
                        sentence,
                    ])),
                    "confidence": "medium" if prefix_hit else "low",
                    "signal": signal,
                    "evidence": preview_text(sentence, 220),
                }
                events.append(event)
                events_by_path[record["path"]].append(event)
                if len(events) >= limit:
                    break
            if len(events) >= limit:
                break
        if len(events) >= limit:
            break

    causal_candidates: list[Dict[str, Any]] = []
    for path, path_events in events_by_path.items():
        for left, right in zip(path_events, path_events[1:]):
            relation = event_relation(left["type"], right["type"]) or "next_in_note"
            causal_candidates.append({
                "from": left["id"],
                "to": right["id"],
                "path": path,
                "relation": relation,
                "scope": "same_note",
                "confidence": "draft",
                "why": "Events appear in this order in the same note; LINZA treats this as a candidate, not a confirmed cause.",
            })

    events_by_domain: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for event in events:
        for domain_id in event.get("domain_ids", []):
            events_by_domain[domain_id].append(event)

    seen_cross_note: set[tuple[str, str, str]] = set()
    for domain_id, domain_events in events_by_domain.items():
        ordered = sorted(
            domain_events,
            key=lambda item: (
                item.get("time_hint") or "9999-99-99",
                item["path"],
                item["id"],
            ),
        )
        for left, right in zip(ordered, ordered[1:]):
            if left["path"] == right["path"]:
                continue
            relation = event_relation(left["type"], right["type"])
            if relation is None:
                continue
            key = (left["id"], right["id"], relation)
            if key in seen_cross_note:
                continue
            seen_cross_note.add(key)
            causal_candidates.append({
                "from": left["id"],
                "to": right["id"],
                "paths": [left["path"], right["path"]],
                "relation": relation,
                "scope": "cross_note",
                "shared_domain_ids": [domain_id],
                "confidence": "draft",
                "why": "Events share a draft domain and appear in a compatible order across notes; user review is required before treating this as causal.",
            })

    return {
        "policy": "evidence_first",
        "requires_review": True,
        "events": events,
        "event_counts": Counter(event["type"] for event in events).most_common(),
        "summary": {
            "events": len(events),
            "same_note_candidates": sum(1 for item in causal_candidates if item.get("scope") == "same_note"),
            "cross_note_candidates": sum(1 for item in causal_candidates if item.get("scope") == "cross_note"),
        },
        "causal_candidates": causal_candidates[:40],
        "note": "Causal links are draft hypotheses grounded in note evidence and order. Confirm before trusting them.",
    }


def memory_signals(text: str, role: str = "", event_type: str = "") -> list[str]:
    hay = str(text or "").lower()
    signals: list[str] = []
    if event_type:
        signals.append(event_type)
    if role:
        signals.append(f"role:{role}")
    if re.search(r"\b(decision|решение|decided|выбрали|принято)\b", hay):
        signals.append("decision")
    if re.search(r"\b(action|done|implemented|added|сделано|добавили|добавила|реализовали|реализовала)\b", hay):
        signals.append("action")
    if re.search(r"\b(result|outcome|итог|результат|therefore|получилось|теперь)\b", hay):
        signals.append("result")
    if re.search(r"\b(rule|policy|boundary|always|never|lesson|правило|политик|границ|урок|никогда|всегда)\b", hay):
        signals.append("procedural_rule")
    if re.search(r"- \[ \]|\b(todo|task|next action|задач|следующ[а-я]+ шаг)\b", hay):
        signals.append("prospective_task")
    if re.search(
        r"\b(lose|lost|missing|gap|failure|failed|confusing|drift|contradict|unexpected|surprise)\b"
        r"|потер|не хватает|ошиб|сбой|слом|дрифт|противореч|неожидан|рассоглас",
        hay,
    ):
        signals.append("prediction_error")
    return sorted(set(signals))


def record_memory_type(record: Dict[str, Any], body: str) -> Optional[str]:
    role = str(record.get("role", "note"))
    hay = f"{record.get('path', '')} {record.get('title', '')} {body[:2500]}".lower()
    if role == "task" or "- [ ]" in body:
        return "prospective"
    if re.search(r"\b(rule|policy|boundary|workflow|lesson|always|never|правило|границ|урок|процедур|никогда|всегда)\b", hay):
        return "procedural"
    words = re.findall(r"\w+", body, flags=re.UNICODE)
    has_reference_shape = "[[" in body or "http://" in body or "https://" in body
    has_definition_shape = re.search(r"\b(definition|means|is a|is an|это|означает|обозначает)\b", hay)
    if len(words) >= 80 and (has_reference_shape or has_definition_shape):
        return "semantic"
    return None


def memory_recall_context(memory_type: str, signals: list[str]) -> list[str]:
    normalized = str(memory_type or "").strip().lower()
    signal_set = {str(item) for item in signals if str(item).strip()}
    contexts: list[str] = []
    if normalized == "procedural":
        contexts.extend([
            "before changing related workflows",
            "when reviewing future agent behavior",
        ])
    elif normalized == "prospective":
        contexts.extend([
            "when planning next actions",
            "before closing or resuming a work session",
        ])
    elif normalized == "semantic":
        contexts.extend([
            "when answering questions about this topic",
            "when drafting related context or documentation",
        ])
    else:
        contexts.extend([
            "when continuing related work",
            "when explaining why a decision or result happened",
        ])
    if "prediction_error" in signal_set:
        contexts.append("when checking whether a past failure pattern is repeating")
    if "decision" in signal_set:
        contexts.append("when choosing between similar options")
    if "result" in signal_set:
        contexts.append("when evaluating whether the same approach worked")
    return list(dict.fromkeys(contexts))[:5]


def memory_review_after(memory_type: str, signals: list[str]) -> str:
    normalized = str(memory_type or "").strip().lower()
    signal_set = {str(item) for item in signals if str(item).strip()}
    if normalized == "prospective":
        return "14 days or when the task is completed"
    if normalized == "procedural":
        return "90 days or when the workflow changes"
    if normalized == "semantic":
        return "180 days or when source evidence changes"
    if "prediction_error" in signal_set:
        return "30 days or after the next related run"
    return "90 days or when related decisions change"


def memory_staleness_risk(memory_type: str, signals: list[str]) -> str:
    normalized = str(memory_type or "").strip().lower()
    signal_set = {str(item) for item in signals if str(item).strip()}
    if normalized == "prospective":
        return "high"
    if "prediction_error" in signal_set:
        return "medium"
    if normalized == "semantic":
        return "low"
    return "medium"


def memory_topic_terms(record: Dict[str, Any], summary: str, evidence: str) -> list[str]:
    text = " ".join([
        str(record.get("title", "")),
        str(record.get("folder", "")),
        str(summary or ""),
        str(evidence or ""),
    ])
    terms = sorted(tokenize(text))
    noise = {
        "decision", "result", "action", "fact", "lesson", "agents", "agent",
        "memory", "notes", "source", "review", "workflow", "context",
    }
    filtered = [term for term in terms if term not in noise]
    return filtered[:8] or terms[:8]


def memory_related_records(
    source_path: str,
    topic_terms: list[str],
    records: list[Dict[str, Any]],
    limit: int = 6,
) -> list[Dict[str, Any]]:
    source_folder = str(Path(source_path).parent).replace("\\", "/")
    source_folder = "" if source_folder == "." else source_folder
    topic_set = set(topic_terms)
    related: list[tuple[int, str, Dict[str, Any], str]] = []
    for record in records:
        path = str(record.get("path", ""))
        if not path or path == source_path:
            continue
        text = " ".join([
            str(record.get("title", "")),
            str(record.get("folder", "")),
            " ".join(chunk.get("text", "") for chunk in record.get("chunks", [])[:3]),
        ])
        terms = tokenize(text)
        overlap = len(topic_set.intersection(terms))
        same_folder = bool(source_folder and str(record.get("folder", "")) == source_folder)
        if overlap <= 0 and not same_folder:
            continue
        score = overlap + (1 if same_folder else 0)
        related.append((score, path, record, text))
    related.sort(key=lambda item: (-item[0], item[1]))
    return [
        {
            "path": path,
            "record": record,
            "text": text,
            "score": score,
        }
        for score, path, record, text in related[:limit]
    ]


def memory_conflict_candidates(
    summary: str,
    evidence: str,
    related_records: list[Dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    contrast_re = re.compile(
        r"\b(but|however|instead|contradict|conflict|not|never|obsolete|must not|no longer|may|must|should)\b",
        re.IGNORECASE,
    )
    source_has_contrast = bool(contrast_re.search(f"{summary} {evidence}"))
    for related in related_records:
        for sentence in split_event_sentences(str(related.get("text", ""))):
            if not sentence:
                continue
            if source_has_contrast or contrast_re.search(sentence):
                candidates.append({
                    "path": related.get("path", ""),
                    "evidence": preview_text(sentence, 180),
                    "reason": "Related source contains contrast, negation, modality, or possible outdated wording.",
                })
                break
        if len(candidates) >= limit:
            break
    return candidates


def memory_evolution(
    source_path: str,
    topic_terms: list[str],
    related_records: list[Dict[str, Any]],
    limit: int = 5,
) -> dict[str, Any]:
    source_time = event_time_hint(source_path)
    sources: list[dict[str, Any]] = []
    for related in related_records[:limit]:
        path = str(related.get("path", ""))
        sources.append({
            "path": path,
            "time_hint": event_time_hint(path),
            "evidence": preview_text(str(related.get("text", "")), 160),
        })
    dated = [item for item in sources if item.get("time_hint")]
    if source_time and dated:
        prior = [item for item in dated if str(item["time_hint"]) < source_time]
        later = [item for item in dated if str(item["time_hint"]) > source_time]
        if prior and later:
            hint = "sits_between_related_sources"
        elif later:
            hint = "has_related_later_sources"
        elif prior:
            hint = "has_related_prior_sources"
        else:
            hint = "dated_source_with_related_context"
    elif sources:
        hint = "has_related_context"
    else:
        hint = "first_seen"
    return {
        "hint": hint,
        "topic_terms": topic_terms[:6],
        "source_time_hint": source_time,
        "related_sources": sources,
    }


def memory_review_questions(
    memory_type: str,
    conflict_candidates: list[dict[str, Any]],
    evolution: dict[str, Any],
) -> list[str]:
    questions = [
        "When should future agents recall this?",
        "Is this still true and useful?",
    ]
    if conflict_candidates:
        questions.append("Does this supersede or conflict with the related source?")
    if evolution.get("related_sources"):
        questions.append("Is this an update in an evolving topic or only one local event?")
    if str(memory_type or "").strip().lower() == "prospective":
        questions.append("Has this task already been completed or abandoned?")
    return questions


def build_memory_draft(
    records: list[Dict[str, Any]],
    event_flow_draft: Dict[str, Any],
    review_queue: list[dict[str, Any]],
    limit: int = 40,
) -> Dict[str, Any]:
    candidates: list[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    records_by_path = {record["path"]: record for record in records}

    def add_candidate(
        memory_type: str,
        source_path: str,
        summary: str,
        evidence: str,
        signals: list[str],
        why: str,
        priority: str = "medium",
    ) -> None:
        if len(candidates) >= limit:
            return
        if not source_path or not summary:
            return
        key = (source_path, memory_type, normalize_note_name(summary[:120]))
        if key in seen:
            return
        seen.add(key)
        record = records_by_path.get(source_path, {})
        normalized_signals = sorted(set(signals))
        topic_terms = memory_topic_terms(record, summary, evidence)
        related_records = memory_related_records(source_path, topic_terms, records)
        conflict_candidates = memory_conflict_candidates(summary, evidence, related_records)
        evolution = memory_evolution(source_path, topic_terms, related_records)
        candidates.append({
            "id": f"memory-{len(candidates) + 1:03d}",
            "memory_type": memory_type,
            "source_path": source_path,
            "title": record.get("title") or Path(source_path).stem,
            "role": record.get("role", "note"),
            "domain_ids": record.get("domain_ids", []),
            "summary": preview_text(summary, 180),
            "evidence": preview_text(evidence, 240),
            "signals": normalized_signals,
            "recall_context": memory_recall_context(memory_type, normalized_signals),
            "review_after": memory_review_after(memory_type, normalized_signals),
            "staleness_risk": memory_staleness_risk(memory_type, normalized_signals),
            "conflict_candidates": conflict_candidates,
            "evolution": evolution,
            "review_questions": memory_review_questions(memory_type, conflict_candidates, evolution),
            "priority": priority,
            "status": "draft",
            "target_store": ".linza",
            "why": why,
        })

    for event in event_flow_draft.get("events", []):
        event_type = str(event.get("type", "fact"))
        evidence = str(event.get("evidence", ""))
        memory_type = "semantic" if event_type == "hypothesis" else "episodic"
        signals = memory_signals(evidence, event.get("role", ""), event_type)
        signals.append("event_flow")
        add_candidate(
            memory_type,
            str(event.get("path", "")),
            evidence,
            evidence,
            signals,
            "Event-flow evidence can become durable memory after review.",
            "high" if event_type in {"decision", "result"} else "medium",
        )
        if len(candidates) >= limit:
            break

    for record in sorted(records, key=lambda item: item["path"]):
        body = " ".join(chunk.get("text", "") for chunk in record.get("chunks", [])[:3])
        memory_type = record_memory_type(record, body)
        if not memory_type:
            continue
        signals = memory_signals(body, record.get("role", ""))
        if memory_type == "prospective":
            signals.append("future_intention")
            why = "Open task or next-action evidence should be available as prospective memory."
        elif memory_type == "procedural":
            signals.append("procedure")
            why = "Rules, lessons, or boundaries should be reviewed before becoming procedural memory."
        else:
            signals.append("semantic_candidate")
            why = "Reference-shaped notes can become semantic memory after review."
        add_candidate(
            memory_type,
            record["path"],
            body or record["title"],
            body or record["title"],
            signals,
            why,
            "high" if memory_type in {"procedural", "prospective"} else "medium",
        )
        if len(candidates) >= limit:
            break

    counts = Counter(item["memory_type"] for item in candidates)
    return {
        "policy": "consolidation_queue_review_first",
        "requires_review": True,
        "target_store": ".linza/linza.db:approved_items",
        "layers": [
            {"id": "working", "role": "current context pack; not stored as durable memory by default"},
            {"id": "episodic", "role": "facts, decisions, actions, results, and session history"},
            {"id": "semantic", "role": "stable reviewed knowledge extracted from evidence"},
            {"id": "procedural", "role": "rules, lessons, workflows, and boundaries"},
            {"id": "prospective", "role": "future tasks and reminders"},
        ],
        "summary": {
            "candidates": len(candidates),
            "by_type": counts.most_common(),
            "review_items": len(review_queue),
        },
        "consolidation_candidates": candidates[:limit],
        "note": "Memory candidates are draft consolidation cards. Accepting one records sidecar memory only; source notes stay unchanged.",
    }


def build_lens_suggestions(
    domains: list[Dict[str, Any]],
    role_draft: Dict[str, Any],
    event_flow_draft: Dict[str, Any],
    memory_draft: Dict[str, Any],
    review_queue: list[dict[str, Any]],
) -> list[Dict[str, Any]]:
    domain_names = [domain["name"] for domain in domains[:5]]
    event_counts = {kind: count for kind, count in event_flow_draft.get("event_counts", [])}
    memory_counts = {kind: count for kind, count in memory_draft.get("summary", {}).get("by_type", [])}
    material_type_count = len(role_draft.get("material_type_candidates", []))

    return [
        {
            "id": "find",
            "label": "Найти",
            "purpose": "Bring back the most relevant notes, chunks, and sources for a concrete question.",
            "uses": ["domains", "semantic_chunks", "links"],
            "starting_points": domain_names[:3],
        },
        {
            "id": "research",
            "label": "Исследовать",
            "purpose": "Show what the vault knows about a theme, what is connected, and what is still unclear.",
            "uses": ["candidate_domains", "hierarchy_draft", "semantic_neighbors"],
            "starting_points": domain_names,
        },
        {
            "id": "write",
            "label": "Написать",
            "purpose": "Collect draftable material, sources, and prior wording for an article, note, README, or message.",
            "uses": ["candidate_domains", "semantic_chunks", "material_types"],
            "signals": {"draft_material_types": material_type_count, "domains": len(domain_names)},
        },
        {
            "id": "act",
            "label": "Сделать",
            "purpose": "Surface decisions, actions, and next steps the agent can work from.",
            "uses": ["events", "memory_draft", "review_queue"],
            "signals": {
                "decisions": event_counts.get("decision", 0),
                "actions": event_counts.get("action", 0),
                "prospective_memory": memory_counts.get("prospective", 0),
            },
        },
        {
            "id": "verify",
            "label": "Проверить",
            "purpose": "Find weak evidence, contradictions, broken links, thin notes, and items needing user judgement.",
            "uses": ["review_queue", "event_confidence", "diagnostics"],
            "signals": {"review_items": len(review_queue)},
        },
        {
            "id": "organize",
            "label": "Упорядочить",
            "purpose": "Turn the raw vault map into approved domains, material types, parents, tags, and cleanup tasks.",
            "uses": ["role_draft", "candidate_domains", "review_queue"],
            "signals": {"role_review_items": len(role_draft.get("review", []))},
        },
        {
            "id": "event_flow",
            "label": "Ход дела",
            "purpose": "Trace facts, decisions, actions, results, hypotheses, and candidate cause-effect links.",
            "uses": ["events", "causal_candidates"],
            "signals": event_counts,
        },
        {
            "id": "memory",
            "label": "Память",
            "purpose": "Consolidate useful context into reviewed episodic, semantic, procedural, and prospective memory.",
            "uses": ["memory_draft", "approved_items", "context_packs"],
            "signals": memory_counts,
        },
    ]


DRAFT_ANALYSIS_STAGES = {
    "all",
    "domains",
    "material_types",
    "hierarchy",
    "event_flow",
    "memory",
    "patterns",
}


def normalize_analysis_stage(value: str | None) -> str:
    stage = str(value or "all").strip().lower().replace("-", "_")
    aliases = {
        "domain": "domains",
        "review_domains": "domains",
        "role": "material_types",
        "roles": "material_types",
        "material_type": "material_types",
        "review_roles": "material_types",
        "review_hierarchy": "hierarchy",
        "causal": "event_flow",
        "causal_links": "event_flow",
        "events": "event_flow",
        "review_causal_links": "event_flow",
        "review_memory": "memory",
        "pattern": "patterns",
        "insights": "patterns",
    }
    stage = aliases.get(stage, stage)
    return stage if stage in DRAFT_ANALYSIS_STAGES else "all"


def pattern_card(
    card_type: str,
    title: str,
    why: str,
    evidence: list[dict[str, Any]],
    priority: str = "medium",
) -> dict[str, Any]:
    raw = "|".join(
        [card_type, title]
        + [
            f"{item.get('path', '')}:{item.get('text', item.get('definition', ''))}"
            for item in evidence[:5]
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return {
        "id": f"pattern-{card_type.replace('_', '-')}-{digest}",
        "type": card_type,
        "title": title,
        "priority": priority,
        "why": why,
        "evidence": evidence[:6],
        "write_policy": "review_only_sidecar_or_context",
        "user_options": ["accept insight", "ask for more evidence", "dismiss"],
    }


def build_pattern_draft(
    records: list[Dict[str, Any]],
    domains: list[Dict[str, Any]],
    event_flow_draft: Dict[str, Any],
) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    problem_evidence: list[dict[str, Any]] = []
    contrast_evidence: list[dict[str, Any]] = []
    term_defs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    problem_re = re.compile(
        r"\b(problem|issue|risk|blocked|confusing|failure|bug|ошибк|проблем|риск|блок)\b",
        re.IGNORECASE,
    )
    contrast_re = re.compile(
        r"\b(but|however|instead|contradict|conflict|not|never|obsolete|но|однако|вместо|противореч|устар)\b",
        re.IGNORECASE,
    )
    term_re = re.compile(
        r"\b(?:term|термин)\s*[:=—-]\s*([A-Za-zА-Яа-яЁё0-9 _-]{3,40}?)\s+"
        r"(?:means|означает|это|=|as)\s+(.+)",
        re.IGNORECASE,
    )

    for record in records:
        text = " ".join(chunk.get("text", "") for chunk in record.get("chunks", []))
        for sentence in split_event_sentences(text):
            if problem_re.search(sentence):
                problem_evidence.append({"path": record["path"], "text": preview_text(sentence, 180)})
            if contrast_re.search(sentence):
                contrast_evidence.append({"path": record["path"], "text": preview_text(sentence, 180)})
            match = term_re.search(sentence)
            if match:
                term = normalize_note_name(match.group(1))
                if term:
                    term_defs[term].append({
                        "path": record["path"],
                        "term": term,
                        "definition": preview_text(match.group(2), 160),
                        "text": preview_text(sentence, 200),
                    })

    if len({item["path"] for item in problem_evidence}) >= 2:
        cards.append(pattern_card(
            "repeated_problem",
            "Repeated problem across notes",
            "Several notes mention similar problem/risk language. This may be a recurring operational issue worth reviewing.",
            problem_evidence,
            priority="high",
        ))

    for term, definitions in sorted(term_defs.items()):
        unique_defs = {item["definition"].lower() for item in definitions}
        if len(unique_defs) >= 2 and len({item["path"] for item in definitions}) >= 2:
            cards.append(pattern_card(
                "terminology_drift",
                f"Term drift: {term}",
                "The same term is defined differently in multiple notes. Review whether this is evolution, ambiguity, or conflict.",
                definitions,
            ))
            break

    if len({item["path"] for item in contrast_evidence}) >= 2:
        cards.append(pattern_card(
            "conflict",
            "Possible contradiction or outdated assumption",
            "Several notes contain contrast/negation language. This is not proof of a contradiction, but it is worth reviewing.",
            contrast_evidence,
        ))

    events_by_path: dict[str, set[str]] = defaultdict(set)
    for event in event_flow_draft.get("events", []):
        events_by_path[str(event.get("path", ""))].add(str(event.get("type", "")))
    for domain in domains:
        member_paths = [str(path) for path in domain.get("member_paths", []) if str(path).strip()]
        if len(member_paths) < 2:
            continue
        event_types: set[str] = set()
        for path in member_paths:
            event_types.update(events_by_path.get(path, set()))
        missing = [kind for kind in ("decision", "result") if kind not in event_types]
        if missing:
            cards.append(pattern_card(
                "gap",
                f"Evidence gap in domain: {domain.get('display_name') or domain.get('name')}",
                "This area has several related notes but lacks reviewed decision/result evidence. It may need synthesis, evaluation, or a summary note.",
                [
                    {"path": path, "text": f"member of domain; missing event types: {', '.join(missing)}"}
                    for path in member_paths[:6]
                ],
            ))
            break

    cards = cards[:12]
    return {
        "policy": "patterns_are_review_only",
        "cards": cards,
        "summary": {
            "cards": len(cards),
            "by_type": Counter(item["type"] for item in cards).most_common(),
        },
    }


def build_stage_view(
    analysis_stage: str,
    public_domains: list[dict[str, Any]],
    role_draft: Dict[str, Any],
    hierarchy_draft: list[dict[str, Any]],
    event_flow_draft: Dict[str, Any],
    memory_draft: Dict[str, Any],
    pattern_draft: Dict[str, Any],
) -> dict[str, Any]:
    stage = normalize_analysis_stage(analysis_stage)
    if stage == "domains":
        return {"id": stage, "sections": ["candidate_domains"], "items": public_domains[:5]}
    if stage == "material_types":
        return {
            "id": stage,
            "sections": ["role_draft.material_type_candidates", "role_draft.notes"],
            "items": role_draft.get("material_type_candidates", [])[:5],
        }
    if stage == "hierarchy":
        return {"id": stage, "sections": ["hierarchy_draft"], "items": hierarchy_draft[:5]}
    if stage == "event_flow":
        return {
            "id": stage,
            "sections": ["event_flow_draft.events", "event_flow_draft.causal_candidates"],
            "items": event_flow_draft.get("causal_candidates", [])[:5],
        }
    if stage == "memory":
        return {
            "id": stage,
            "sections": ["memory_draft.consolidation_candidates"],
            "items": memory_draft.get("consolidation_candidates", [])[:5],
        }
    if stage == "patterns":
        return {"id": stage, "sections": ["pattern_draft.cards"], "items": pattern_draft.get("cards", [])[:5]}
    return {
        "id": "all",
        "sections": [
            "candidate_domains",
            "role_draft",
            "hierarchy_draft",
            "event_flow_draft",
            "memory_draft",
            "pattern_draft",
        ],
        "items": [],
    }


async def draft_vault_map(
    core,
    max_notes: int = 120,
    max_domains: int = 8,
    max_chunks_per_note: int = 12,
    use_embedding_second_pass: bool = True,
    analysis_stage: str = "all",
) -> Dict[str, Any]:
    """Draft domains, hierarchy, thresholds, and review items from a raw vault. Read-only."""
    requested_stage = normalize_analysis_stage(analysis_stage)
    max_notes = max(1, int(max_notes))
    max_domains = max(1, int(max_domains))
    max_chunks_per_note = max(1, int(max_chunks_per_note))
    index = core._read_note_index()
    all_notes = list(index["notes"].values())
    selected_notes = core._select_draft_notes(all_notes, max_notes)
    records: list[Dict[str, Any]] = []
    global_doc_counts: Counter[str] = Counter()
    semantic_chunk_total = 0
    sample_chunks: list[dict[str, Any]] = []

    for note in selected_notes:
        folder = str(Path(note["path"]).parent).replace("\\", "/")
        folder = "" if folder == "." else folder
        analysis_body = strip_generated_service_sections(note["body"])
        chunks = split_semantic_chunks(analysis_body)[:max_chunks_per_note]
        semantic_chunk_total += len(chunks)
        headings = sorted({chunk["heading"] for chunk in chunks if chunk.get("heading")})
        token_text = " ".join([
            note["title"],
            folder.replace("/", " "),
            " ".join(note["tags"]),
            " ".join(headings),
            " ".join(chunk["text"][:500] for chunk in chunks[:4]),
        ])
        tokens = tokenize(token_text)
        global_doc_counts.update(tokens)
        accepted_role = note["role"] if note.get("role_reason") == "accepted_yaml" else ""
        record = {
            "path": note["path"],
            "title": note["title"],
            "folder": folder,
            "tags": note["tags"],
            "role": core._public_role(accepted_role),
            "raw_role": accepted_role or "untyped",
            "accepted_role": core._public_role(accepted_role) if accepted_role else "",
            "role_reason": note["role_reason"] if accepted_role else "clean_slate_no_role_guess",
            "word_count": note["word_count"],
            "tokens": tokens,
            "headings": headings,
            "chunks": chunks,
            "material_features": material_type_features(note["title"], analysis_body, folder, note.get("metadata", {})),
            "draft_embedding": None,
        }
        records.append(record)
        for chunk in chunks[:2]:
            if len(sample_chunks) >= 12:
                break
            sample_chunks.append({
                "path": note["path"],
                "chunk_id": chunk["chunk_id"],
                "kind": chunk["kind"],
                "heading": chunk.get("heading"),
                "preview": core._preview_text(chunk["text"]),
            })

    embedding_second_pass: Dict[str, Any] = {
        "status": "skipped",
        "provider": type(core.embed).__name__,
        "embedded_notes": 0,
        "merged_domains": 0,
        "note": "Disabled by request.",
    }
    if use_embedding_second_pass and records:
        try:
            texts = [core._draft_record_text(record) for record in records]
            embeddings = await core.embed.embed(texts)
            centered_embeddings = embeddings
            try:
                import numpy as np
                arr = np.array(embeddings, dtype=float)
                if arr.ndim == 2 and arr.shape[0] > 1:
                    centered_embeddings = (arr - np.mean(arr, axis=0)).tolist()
            except Exception:
                centered_embeddings = embeddings
            for record, embedding in zip(records, embeddings):
                record["raw_draft_embedding"] = embedding
            for record, embedding in zip(records, centered_embeddings):
                record["draft_embedding"] = embedding
            embedding_second_pass = {
                "status": "ok",
                "provider": type(core.embed).__name__,
                "embedded_notes": len(embeddings),
                "merged_domains": 0,
                "centering": "local_draft_mean",
                "note": "Embeddings were computed and mean-centered in memory for this draft only; no note or vector cache was written.",
            }
        except Exception as exc:
            embedding_second_pass = {
                "status": "error",
                "provider": type(core.embed).__name__,
                "embedded_notes": 0,
                "merged_domains": 0,
                "error": str(exc),
                "note": "Fell back to folder, lexical, tag, and graph signals.",
            }

    pair_scores: Dict[tuple[str, str], float] = {}
    score_values: list[float] = []
    for i, left in enumerate(records):
        for right in records[i + 1:]:
            lexical_score = core._record_similarity(left, right, global_doc_counts, total_docs=len(records))
            embedding_score = core._vector_cosine(left.get("draft_embedding"), right.get("draft_embedding"))
            if embedding_score is None:
                score = lexical_score
            else:
                blended = (lexical_score * 0.58) + (max(0.0, embedding_score) * 0.42)
                score = round(max(lexical_score, blended), 4)
            pair_scores[(left["path"], right["path"])] = score
            pair_scores[(right["path"], left["path"])] = score
            score_values.append(score)

    domain_threshold = round(max(0.18, core._percentile(score_values, 70, 0.18)), 3)
    review_threshold = round(max(0.12, core._percentile(score_values, 55, 0.12)), 3)
    strong_threshold = round(max(domain_threshold + 0.12, core._percentile(score_values, 90, 0.32)), 3)
    centrality = {
        record["path"]: sum(pair_scores.get((record["path"], other["path"]), 0.0) for other in records if other["path"] != record["path"])
        for record in records
    }
    by_path = {record["path"]: record for record in records}
    domains: list[Dict[str, Any]] = []
    used_domain_names: set[str] = set()
    candidate_domain_limit = max(max_domains * 2, max_domains)

    folder_groups: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record["folder"]:
            folder_groups[record["folder"]].append(record)

    for folder, member_records in sorted(folder_groups.items()):
        if len(member_records) < 2:
            continue
        folders = Counter(record["folder"] or "(root)" for record in member_records)
        roles = Counter(record["role"] for record in member_records)
        terms = core._domain_terms(member_records, global_doc_counts, total_docs=len(records))
        name = core._domain_name(terms, folders, roles)
        name_key = normalize_note_name(name)
        if name_key in used_domain_names:
            continue
        used_domain_names.add(name_key)
        member_paths = sorted(record["path"] for record in member_records)
        domain = {
            "id": f"domain-{len(domains) + 1:03d}",
            "name": name,
            "confidence": "draft",
            "score": 1.0,
            "representative_terms": terms[:10],
            "folders": folders.most_common(5),
            "roles": roles.most_common(),
            "member_paths": member_paths,
            "merged_from": [],
            "merge_evidence": [],
            "representative_notes": [],
            "why": "Seeded from an existing folder with several notes, then checked against semantic signals.",
        }
        core._refresh_draft_domain(domain, by_path, global_doc_counts, pair_scores, total_docs=len(records))
        domains.append(domain)
        if len(domains) >= max_domains:
            break

    for seed in sorted(records, key=lambda item: (-centrality.get(item["path"], 0), item["path"])):
        members = []
        for candidate in records:
            if candidate["path"] == seed["path"]:
                score = 1.0
            else:
                score = pair_scores.get((seed["path"], candidate["path"]), 0.0)
            same_folder = bool(seed["folder"] and seed["folder"] == candidate["folder"])
            if score >= domain_threshold or same_folder:
                members.append((candidate, score))
        if len(members) < 2:
            continue
        member_paths = {candidate["path"] for candidate, _ in members}
        member_records = [candidate for candidate, _ in members]
        folders = Counter(record["folder"] or "(root)" for record in member_records)
        roles = Counter(record["role"] for record in member_records)
        terms = core._domain_terms(member_records, global_doc_counts, total_docs=len(records))
        name = core._domain_name(terms, folders, roles)
        name_key = normalize_note_name(name)
        if name_key in used_domain_names:
            continue
        used_domain_names.add(name_key)
        domains.append({
            "id": f"domain-{len(domains) + 1:03d}",
            "name": name,
            "confidence": "medium" if len(member_records) >= 3 else "draft",
            "score": round(sum(score for _, score in members) / max(1, len(members)), 3),
            "representative_terms": terms[:10],
            "folders": folders.most_common(5),
            "roles": roles.most_common(),
            "member_paths": sorted(member_paths),
            "merged_from": [],
            "merge_evidence": [],
            "representative_notes": [
                {
                    "path": candidate["path"],
                    "title": candidate["title"],
                    "role": candidate["role"],
                    "score": round(score, 3),
                }
                for candidate, score in sorted(members, key=lambda item: (-item[1], item[0]["path"]))[:8]
            ],
            "why": "Grouped from shared folder, title/body terms, tags, and local similarity distribution.",
        })
        if len(domains) >= candidate_domain_limit:
            break

    domains, merged_domains = core._merge_draft_domains(
        domains,
        by_path,
        global_doc_counts,
        pair_scores,
        max_domains,
    )
    core._dedupe_draft_domain_names(domains)
    embedding_second_pass["merged_domains"] = merged_domains

    assigned_to: Dict[str, list[str]] = defaultdict(list)
    for domain in domains:
        for path in domain["member_paths"]:
            assigned_to[path].append(domain["id"])
    for record in records:
        record["domain_ids"] = assigned_to.get(record["path"], [])

    role_draft = core._build_role_draft(records, assigned_to)
    hierarchy_draft = []
    incoming = index["incoming"]
    outgoing = index["outgoing"]
    for domain in domains:
        members = [by_path[path] for path in domain["member_paths"] if path in by_path]
        parent_candidates = sorted(
            members,
            key=lambda item: (-core._parent_score(item, incoming, outgoing), item["path"]),
        )[:3]
        parent_paths = {item["path"] for item in parent_candidates[:1]}
        child_groups = []
        for group_name, grouped in sorted(group_records_by_role_or_folder(members).items()):
            child_groups.append({
                "group": group_name,
                "notes": [
                    {"path": item["path"], "title": item["title"], "role": item["role"]}
                    for item in grouped
                    if item["path"] not in parent_paths
                ][:8],
            })
        hierarchy_draft.append({
            "domain_id": domain["id"],
            "domain_name": domain["name"],
            "suggested_level": "top_area",
            "parent_candidates": [
                {
                    "path": item["path"],
                    "title": item["title"],
                    "role": item["role"],
                    "score": core._parent_score(item, incoming, outgoing),
                    "why": "Central note candidate: links, role, title, and readable size.",
                }
                for item in parent_candidates
            ],
            "child_groups": child_groups,
        })

    diagnostic = core.scan_vault()
    review_queue: list[dict[str, Any]] = []
    for path, domain_ids in sorted(assigned_to.items()):
        if len(domain_ids) > 1:
            review_queue.append({
                "type": "ambiguous_domain",
                "path": path,
                "domains": domain_ids,
                "why": "This note fits several draft areas; user naming or parent choice is needed.",
            })
    domainless = [record for record in records if record["path"] not in assigned_to]
    for record in domainless[:20]:
        review_queue.append({
            "type": "domainless_note",
            "path": record["path"],
            "why": "No confident draft area found. Keep as inbox, add links, or review manually.",
        })
    for key in ("broken_links", "orphan_notes", "thin_notes"):
        for item in diagnostic.get(key, [])[:10]:
            path = item.get("source") if isinstance(item, dict) else item
            review_queue.append({
                "type": key,
                "path": path,
                "why": "Imported from vault diagnostic; review before changing metadata or links.",
            })

    material_types = material_type_vocabulary(role_draft.get("role_counts", []))
    event_flow_draft = core._build_event_flow_draft(records, assigned_to)
    memory_draft = core._build_memory_draft(records, event_flow_draft, review_queue)
    pattern_draft = build_pattern_draft(records, domains, event_flow_draft)
    lens_suggestions = core._build_lens_suggestions(domains, role_draft, event_flow_draft, memory_draft, review_queue)
    public_domains = [
        {key: value for key, value in domain.items() if key != "member_paths"}
        for domain in domains
    ]
    stage_view = build_stage_view(
        requested_stage,
        public_domains,
        role_draft,
        hierarchy_draft,
        event_flow_draft,
        memory_draft,
        pattern_draft,
    )

    return {
        "tool": "draft_vault_map",
        "read_only": True,
        "analysis_stage": {
            "requested": requested_stage,
            "available": sorted(DRAFT_ANALYSIS_STAGES),
        },
        "stage_view": stage_view,
        "backend_choice": {
            "selected": type(core.embed).__name__,
            "fallback": "lexical_and_graph_signals",
            "note": "The current runtime provider is used when embeddings are requested; this draft map does not write embeddings or YAML.",
        },
        "embedding_second_pass": embedding_second_pass,
        "summary": {
            "notes": len(records),
            "vault_notes_seen": len(all_notes),
            "sampling": "balanced_by_top_folder" if len(all_notes) > len(records) else "full_vault",
            "semantic_chunks": semantic_chunk_total,
            "candidate_domains": len(domains),
            "hierarchy_candidates": sum(len(item["parent_candidates"]) for item in hierarchy_draft),
            "role_drafts": len(role_draft["notes"]),
            "event_flow_items": len(event_flow_draft["events"]),
            "memory_candidates": len(memory_draft["consolidation_candidates"]),
            "pattern_cards": len(pattern_draft["cards"]),
            "lens_suggestions": len(lens_suggestions),
            "review_items": len(review_queue),
        },
        "chunking": {
            "mode": "semantic_markdown",
            "unit": "heading section, paragraph/list/table/code/source block with offsets",
            "sample_chunks": sample_chunks,
        },
        "thresholds": {
            "method": "local_pairwise_distribution",
            "domain_membership": domain_threshold,
            "review_relation": review_threshold,
            "strong_relation": strong_threshold,
            "sample_pairs": len(score_values),
        },
        "onboarding_contract": {
            "root": {
                "policy": "implicit_vault_root",
                "expose_l0": False,
                "note": "LINZA treats the selected folder as the root of the map; it does not ask the user to create or understand an L0 entity during first contact.",
            },
            "entity_roles": {
                "policy": "compat_alias_for_material_types",
                "note": "The public first-contact term is material types. The legacy `role` name remains as a storage/API compatibility key.",
                "initial_roles": material_types["suggested_types"],
            },
            "material_types": material_types,
            "visible_axes": ["domains", "lenses", "event_flow", "memory", "confidence"],
            "hidden_engine_mechanics": ["L0-L5", "sign", "core_mix", "reference_etalons", "recalc_commands"],
        },
        "candidate_domains": public_domains,
        "role_draft": role_draft,
        "lens_suggestions": lens_suggestions,
        "event_flow_draft": event_flow_draft,
        "memory_draft": memory_draft,
        "pattern_draft": pattern_draft,
        "hierarchy_draft": hierarchy_draft,
        "review_queue": review_queue[:80],
        "policy": [
            "LINZA never writes to source notes from draft_vault_map.",
            "Domains and hierarchy are a draft, not accepted metadata.",
            "Use review_queue before applying parents, tags, levels, or properties.",
        ],
    }


__all__ = [
    "DRAFT_ANALYSIS_STAGES",
    "build_event_flow_draft",
    "build_lens_suggestions",
    "build_memory_draft",
    "build_pattern_draft",
    "build_role_draft",
    "build_stage_view",
    "draft_vault_map",
    "event_relation",
    "event_time_hint",
    "group_records_by_role_or_folder",
    "memory_signals",
    "normalize_analysis_stage",
    "parent_score",
    "percentile",
    "preview_text",
    "public_role",
    "record_memory_type",
    "role_confidence",
    "select_draft_notes",
    "split_event_sentences",
]
