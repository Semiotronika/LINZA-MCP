"""Review queue for LINZA agent workspace artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .artifacts import ARTIFACT_POLICY
from .draft_map import memory_signals, preview_text
from .events import analyze_inbox


REVIEW_POLICY = ARTIFACT_POLICY + [
    "Accepted review intents are written to sidecar storage only.",
    "Review intents never execute imported text and never change source artifact content.",
]


def review_id(kind: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(f"{kind}:{body}".encode("utf-8")).hexdigest()[:14]
    labels = {
        "memory_candidate": "memory",
        "knowledge_candidate": "knowledge",
        "quant_candidate": "knowledge",
        "calibr_card": "calibr",
    }
    label = labels.get(kind, "review")
    return f"aw-{label}-{digest}"


def _approved_review_ids(core) -> set[str]:
    ids: set[str] = set()
    for item in core.storage.list_approved_items(limit=1000):
        payload = item.get("payload") or {}
        review = payload.get("review_id")
        if review:
            ids.add(str(review))
    return ids


def _kind_matches(item_kind: str, requested: str) -> bool:
    normalized = str(requested or "all").strip().lower()
    if normalized in {"", "all", "*"}:
        return True
    aliases = {
        "memory": "memory_candidate",
        "memories": "memory_candidate",
        "knowledge": "knowledge_candidate",
        "knowledge_item": "knowledge_candidate",
        "knowledge_items": "knowledge_candidate",
        "claim": "knowledge_candidate",
        "claims": "knowledge_candidate",
        "quant": "knowledge_candidate",
        "quanta": "knowledge_candidate",
        "quant_candidate": "knowledge_candidate",
        "calibr": "calibr_card",
        "self_check": "calibr_card",
        "self-check": "calibr_card",
    }
    return item_kind == aliases.get(normalized, normalized)


def _display_lines(item_id: str, title: str, evidence: str, effect: str) -> dict[str, Any]:
    lines = [
        f"Пункт ревью: {item_id}",
        f"Интент ревью: {preview_text(title, 140)}",
        f"Основание: {preview_text(evidence, 220)}",
        f"Что изменится: {effect}",
    ]
    return {
        "lines": lines,
        "text": "\n".join(lines),
    }


def _human_message(items: list[dict[str, Any]], limit: int = 5) -> str:
    texts = [
        str((item.get("display") or {}).get("text") or "").strip()
        for item in items[: max(1, int(limit))]
    ]
    texts = [text for text in texts if text]
    if not texts:
        return "LINZA не нашла пунктов для ревью."
    return "\n\n".join(texts)


def _review_item(kind: str, payload: dict[str, Any], priority: str, title: str, summary: str, evidence: str) -> dict[str, Any]:
    stable_id = review_id(kind, payload)
    payload = {**payload, "review_id": stable_id}
    effect = "LINZA сохранит подтверждение в `.linza`; исходные материалы и заметки не меняются."
    return {
        "id": stable_id,
        "kind": kind,
        "priority": priority,
        "title": preview_text(title, 120),
        "summary": preview_text(summary, 220),
        "evidence": preview_text(evidence, 280),
        "payload": payload,
        "approval": {
            "tool": "agent_workspace",
            "arguments": {
                "action": "apply_review_items",
                "item_ids": [stable_id],
                "dry_run": True,
            },
        },
        "human": {
            "question": "Принять этот пункт в локальную память LINZA?",
            "effect": effect,
            "write_preview": effect,
        },
        "display": _display_lines(stable_id, title, evidence, effect),
    }


def build_review_items(
    core,
    kind: str = "all",
    limit: int = 20,
    source_kind: str = "",
    batch_id: str = "",
    trace_id: str = "",
) -> list[dict[str, Any]]:
    safe_limit = max(1, int(limit))
    approved_ids = _approved_review_ids(core)
    items: list[dict[str, Any]] = []

    include_artifacts = (
        _kind_matches("memory_candidate", kind)
        or _kind_matches("knowledge_candidate", kind)
    )
    if include_artifacts:
        analysis = analyze_inbox(
            core,
            source_kind=source_kind,
            batch_id=batch_id,
            limit=max(50, safe_limit * 4),
        )

        for event in analysis.get("reviewable_events", []):
            evidence = str(event.get("evidence") or "")
            if not evidence:
                continue
            event_type = str(event.get("type") or "fact")
            memory_type = "semantic" if event_type == "hypothesis" else "episodic"
            signals = memory_signals(evidence, event.get("role", ""), event_type)
            signals.append("artifact_event")
            quality = event.get("review_quality") or {}
            payload = {
                "artifact_id": event.get("path", ""),
                "memory_type": memory_type,
                "summary": evidence,
                "evidence": evidence,
                "event_type": event_type,
                "signals": sorted(set(signals)),
                "review_quality": quality,
                "source": "agent_workspace",
            }
            item = _review_item(
                "memory_candidate",
                payload,
                "high" if event_type in {"decision", "result"} or int(quality.get("score", 0)) >= 5 else "medium",
                f"{event_type}: {event.get('title') or event.get('path')}",
                evidence,
                evidence,
            )
            if item["id"] not in approved_ids and _kind_matches(item["kind"], kind):
                items.append(item)
            if len(items) >= safe_limit and kind not in {"all", "", "*"}:
                return items[:safe_limit]

        for summary in analysis.get("knowledge_candidates", analysis.get("quant_candidates", [])):
            text = str(summary.get("summary") or "")
            if not text:
                continue
            quality = summary.get("review_quality") or {}
            payload = {
                "artifact_id": summary.get("artifact_id", ""),
                "title": summary.get("title", ""),
                "summary": text,
                "evidence": summary.get("evidence", text),
                "source_kind": summary.get("source_kind", ""),
                "artifact_type": summary.get("artifact_type", ""),
                "chunk_id": summary.get("chunk_id", ""),
                "heading": summary.get("heading", ""),
                "review_quality": quality,
                "source": "agent_workspace",
            }
            item = _review_item(
                "knowledge_candidate",
                payload,
                "high" if int(quality.get("score", 0)) >= 5 else "medium",
                f"Knowledge: {summary.get('title') or summary.get('artifact_id')}",
                text,
                str(summary.get("evidence") or text),
            )
            if item["id"] not in approved_ids and _kind_matches(item["kind"], kind):
                items.append(item)

    if _kind_matches("calibr_card", kind):
        from .calibr import build_calibr_cards

        for item in build_calibr_cards(core, trace_id=trace_id, limit=safe_limit):
            if item["id"] not in approved_ids:
                items.append(item)
    return items[:safe_limit]


def review_next(
    core,
    kind: str = "all",
    limit: int = 20,
    source_kind: str = "",
    batch_id: str = "",
    trace_id: str = "",
) -> dict[str, Any]:
    items = build_review_items(
        core,
        kind=kind,
        limit=limit,
        source_kind=source_kind,
        batch_id=batch_id,
        trace_id=trace_id,
    )
    return {
        "tool": "agent_workspace",
        "action": "review_next",
        "read_only": True,
        "requires_review": True,
        "items": items,
        "human_message": _human_message(items),
        "summary": {
            "items": len(items),
            "kind": kind or "all",
        },
        "policy": REVIEW_POLICY,
    }


def _item_type_for_item(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "")
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    if kind == "memory_candidate":
        return "agent_memory"
    if kind in {"knowledge_candidate", "quant_candidate"}:
        return "agent_knowledge"
    if kind == "calibr_card":
        return str(payload.get("target_item_type") or "calibr_lesson")
    return "agent_review_item"


def apply_review_items(
    core,
    item_ids: list[str],
    dry_run: bool = True,
    kind: str = "all",
    source_kind: str = "",
    batch_id: str = "",
    trace_id: str = "",
    limit: int = 500,
) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(str(item_id) for item_id in (item_ids or []) if str(item_id).strip()))
    if not unique_ids:
        raise ValueError("apply_review_items requires item_ids")

    available = {
        item["id"]: item
        for item in build_review_items(
            core,
            kind=kind,
            limit=max(limit, len(unique_ids)),
            source_kind=source_kind,
            batch_id=batch_id,
            trace_id=trace_id,
        )
    }
    results: list[dict[str, Any]] = []
    matched = 0
    applied = 0

    for item_id in unique_ids:
        item = available.get(item_id)
        if not item:
            results.append({
                "id": item_id,
                "status": "not_found",
                "reason": "No current unapproved review intent has this id.",
            })
            continue
        matched += 1
        item_type = _item_type_for_item(item)
        payload = dict(item["payload"])
        if dry_run:
            results.append({
                "id": item_id,
                "status": "preview",
                "item_type": item_type,
                "payload": payload,
            })
            continue
        record_id = core.storage.record_approved_item(item_type, payload, status="approved")
        core.storage.record_audit_event("agent_workspace_review_applied", {
            "review_id": item_id,
            "item_type": item_type,
            "approved_item_id": record_id,
            "artifact_id": payload.get("artifact_id", ""),
        })
        applied += 1
        results.append({
            "id": item_id,
            "status": "applied",
            "item_type": item_type,
            "approved_item_id": record_id,
            "payload": payload,
        })

    return {
        "tool": "agent_workspace",
        "action": "apply_review_items",
        "status": "preview" if dry_run else "applied",
        "read_only": bool(dry_run),
        "dry_run": bool(dry_run),
        "summary": {
            "requested": len(unique_ids),
            "matched": matched,
            "applied": applied,
        },
        "results": results,
        "policy": REVIEW_POLICY,
    }


__all__ = [
    "REVIEW_POLICY",
    "apply_review_items",
    "build_review_items",
    "review_id",
    "review_next",
]
