"""Artifact analysis for the LINZA agent workspace."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any

from .artifacts import ARTIFACT_POLICY
from .draft_map import build_event_flow_draft, preview_text, split_event_sentences
from .roles import material_type_features
from .utils import tokenize


PROCESS_NOISE_PATTERNS = [
    (
        "search_count",
        re.compile(
            r"^\s*(found|read|opened|viewed)\s+\d+\s+"
            r"(web\s+pages?|pages?|results?|links?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "search_ui",
        re.compile(
            r"^\s*(view all|search results?|web results?|результаты поиска|"
            r"найден[оы]?\s+\d+|прочитан[оы]?\s+\d+)",
            re.IGNORECASE,
        ),
    ),
    (
        "agent_planning",
        re.compile(
            r"\b("
            r"now i need|now we need|i need to|we need to|i should|i will|"
            r"i plan to|we should|need to search|need to open|"
            r"теперь\s+(нужно|надо|необходимо|я|у меня|мы)|"
            r"мне\s+(нужно|надо|необходимо|следует)|"
            r"я\s+(планирую|должен|должна|буду)|"
            r"нужно\s+(выполнить|открыть|проанализировать|структурировать)"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "outline_planning",
        re.compile(
            r"^\s*(let'?s|next|then|давай|затем|потом)\s+"
            r"(break down|explain|look at|write|outline|structure|"
            r"разбер|объясн|посмотр|напиш|накида|сформулир|структур)",
            re.IGNORECASE,
        ),
    ),
]

MARKDOWN_LINK_ONLY_RE = re.compile(r"^\s*(?:[-*]\s*)?\[[^\]]+\]\([^)]+\)\s*$")

DURABLE_SIGNAL_PATTERNS = [
    (
        "explicit_review_prefix",
        re.compile(
            r"^\s*(decision|result|outcome|hypothesis|assumption|fact|"
            r"observation|risk|rule|policy|insight|вывод|итог|результат|"
            r"решение|гипотеза|предположение|факт|наблюдение|риск|правило|"
            r"важно)\s*[:—-]",
            re.IGNORECASE,
        ),
    ),
    (
        "causal_or_explanatory",
        re.compile(
            r"\b(because|therefore|so that|leads? to|causes?|enables?|"
            r"prevents?|blocks?|requires?|means that|due to|"
            r"потому что|поэтому|из-за|приводит|мешает|позволяет|требует|"
            r"означает|объясняет|связано|возникает)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "definition",
        re.compile(
            r"\b(is|are|means|called|defined as|это|называется|является|"
            r"означает|определяется)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "normative_boundary",
        re.compile(
            r"\b(should|must|never|always|only|immutable|review|gate|"
            r"безопасн|нельзя|всегда|только|границ|провер|"
            r"не должен|не должна|должен|должна)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "evidence_or_source",
        re.compile(
            r"\b(evidence|source|measured|verified|observed|исследован|"
            r"измерен|проверен|источник|доказательств|показывает)\b|https?://",
            re.IGNORECASE,
        ),
    ),
]


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def artifact_type_for(artifact: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify an imported artifact shape without writing ontology into YAML."""
    source_kind = str(artifact.get("source_kind") or "").strip().lower()
    title = str(artifact.get("title") or "")
    body = "\n".join(chunk.get("text", "") for chunk in chunks[:20])
    text = f"{title}\n{body}".lower()
    headings = [chunk.get("heading") for chunk in chunks if chunk.get("heading")]
    url_count = len(re.findall(r"https?://", text))
    signals: list[str] = []

    if source_kind:
        signals.append(f"source_kind:{source_kind}")
    if headings:
        signals.append("has_headings")
    if url_count:
        signals.append("has_sources")

    if "calibr" in source_kind or "trace" in source_kind:
        artifact_type = "agent_trace"
    elif "chat" in source_kind or "conversation" in source_kind or "dialog" in source_kind:
        artifact_type = "chat_log"
    elif "log" in source_kind:
        artifact_type = "activity_log"
    elif "research" in source_kind or url_count >= 3:
        artifact_type = "research_log"
    elif len(headings) >= 3 and len(body.split()) > 700:
        artifact_type = "draft_or_longform"
    elif re.search(r"\b(todo|task|checklist|задач|план)\b", text):
        artifact_type = "task_note"
    else:
        artifact_type = "artifact"

    return {
        "type": artifact_type,
        "confidence": "medium" if signals else "low",
        "signals": signals[:8],
    }


def review_quality(
    text: str,
    event_type: str = "",
    confidence: str = "",
    artifact_type: str = "",
) -> dict[str, Any]:
    """Score whether a text fragment is useful enough to show as a review card."""
    clean = compact_text(text)
    if not clean:
        return {"status": "blocked", "score": 0, "reasons": ["empty"]}
    if MARKDOWN_LINK_ONLY_RE.match(clean):
        return {
            "status": "blocked",
            "score": 0,
            "reasons": ["source_link_only"],
            "artifact_type": artifact_type,
        }

    noise_reasons = [
        name for name, pattern in PROCESS_NOISE_PATTERNS
        if pattern.search(clean)
    ]
    if noise_reasons:
        return {
            "status": "blocked",
            "score": 0,
            "reasons": noise_reasons,
            "artifact_type": artifact_type,
        }

    reasons: list[str] = []
    score = 0
    for name, pattern in DURABLE_SIGNAL_PATTERNS:
        if pattern.search(clean):
            reasons.append(name)
            score += 2 if name == "explicit_review_prefix" else 1
    if event_type in {"decision", "hypothesis", "fact", "result", "action"}:
        reasons.append(f"event:{event_type}")
        score += 1
    if confidence == "medium":
        reasons.append("explicit_marker")
        score += 1
    if len(clean) >= 80:
        reasons.append("substantive_length")
        score += 1
    if artifact_type and artifact_type != "artifact":
        reasons.append(f"artifact_type:{artifact_type}")

    strong_reasons = {
        "explicit_review_prefix",
        "causal_or_explanatory",
        "definition",
        "normative_boundary",
    }
    if score < 3 or not (set(reasons) & strong_reasons):
        return {
            "status": "blocked",
            "score": score,
            "reasons": reasons or ["low_information_density"],
            "artifact_type": artifact_type,
        }
    return {
        "status": "reviewable",
        "score": score,
        "reasons": sorted(set(reasons)),
        "artifact_type": artifact_type,
    }


def artifact_record(artifact: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    title = artifact.get("title") or artifact.get("id") or "Artifact"
    headings = sorted({chunk.get("heading") for chunk in chunks if chunk.get("heading")})
    token_text = " ".join([
        title,
        artifact.get("source_kind", ""),
        " ".join(headings),
        " ".join(chunk.get("text", "")[:500] for chunk in chunks[:4]),
    ])
    body = str(artifact.get("content") or "")
    artifact_type = artifact_type_for(artifact, chunks)
    return {
        "path": artifact["id"],
        "title": title,
        "folder": artifact.get("source_kind", ""),
        "artifact_type": artifact_type["type"],
        "artifact_type_evidence": artifact_type,
        "tags": [],
        "role": "untyped",
        "raw_role": "untyped",
        "role_reason": "clean_slate_no_role_guess",
        "word_count": len(body.split()),
        "tokens": tokenize(token_text),
        "headings": headings,
        "chunks": [
            {
                "chunk_id": chunk.get("id") or chunk.get("chunk_id") or f"{artifact['id']}-{index:04d}",
                "heading": chunk.get("heading") or "",
                "kind": chunk.get("kind") or "text",
                "text": chunk.get("text") or "",
            }
            for index, chunk in enumerate(chunks)
        ],
        "material_features": material_type_features(title, body, artifact.get("source_kind", ""), {}),
        "domain_ids": [],
        "draft_embedding": None,
    }


def summarize_artifact(artifact: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any]:
    text = "\n".join(chunk.get("text", "") for chunk in chunks[:3]).strip()
    artifact_type = artifact_type_for(artifact, chunks)
    return {
        "artifact_id": artifact["id"],
        "source_kind": artifact.get("source_kind", ""),
        "artifact_type": artifact_type["type"],
        "artifact_type_evidence": artifact_type,
        "title": artifact.get("title", ""),
        "batch_id": artifact.get("batch_id", ""),
        "privacy": artifact.get("privacy", "private"),
        "chunks": len(chunks),
        "summary": preview_text(text or artifact.get("content", ""), 260),
    }


def build_quant_candidates(
    artifact: dict[str, Any],
    chunks: list[dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    artifact_type = artifact_type_for(artifact, chunks)["type"]
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks:
        for sentence in split_event_sentences(chunk.get("text", "")):
            quality = review_quality(sentence, artifact_type=artifact_type)
            if quality["status"] != "reviewable":
                continue
            summary = preview_text(sentence, 320)
            key = summary.lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "artifact_id": artifact["id"],
                "title": artifact.get("title", ""),
                "source_kind": artifact.get("source_kind", ""),
                "artifact_type": artifact_type,
                "chunk_id": chunk.get("id") or chunk.get("chunk_id", ""),
                "heading": chunk.get("heading", ""),
                "summary": summary,
                "evidence": summary,
                "review_quality": quality,
            })
    candidates.sort(
        key=lambda item: (
            -int(item["review_quality"].get("score", 0)),
            item.get("title", ""),
            item.get("chunk_id", ""),
        )
    )
    return candidates[: max(0, int(limit))]


def analyze_inbox(
    core,
    source_kind: str = "",
    batch_id: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    safe_limit = max(1, int(limit))
    artifacts = core.storage.list_artifacts(
        source_kind=source_kind or None,
        batch_id=batch_id or None,
        limit=max(safe_limit, 100),
    )

    records: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    quant_candidates: list[dict[str, Any]] = []
    chunk_total = 0
    for artifact in artifacts:
        chunks = core.storage.list_artifact_chunks(artifact["id"], limit=200)
        chunk_total += len(chunks)
        summaries.append(summarize_artifact(artifact, chunks))
        records.append(artifact_record(artifact, chunks))
        quant_candidates.extend(build_quant_candidates(artifact, chunks, limit=3))

    event_flow = build_event_flow_draft(records, {}, limit=safe_limit)
    artifact_types = {
        record["path"]: record.get("artifact_type", "artifact")
        for record in records
    }
    reviewable_events: list[dict[str, Any]] = []
    for event in event_flow.get("events", []):
        quality = review_quality(
            str(event.get("evidence") or ""),
            event_type=str(event.get("type") or ""),
            confidence=str(event.get("confidence") or ""),
            artifact_type=artifact_types.get(str(event.get("path") or ""), "artifact"),
        )
        event["review_quality"] = quality
        if quality["status"] == "reviewable":
            reviewable_events.append(event)

    relation_candidates = event_flow.get("causal_candidates", [])
    event_counts = Counter(event.get("type") for event in event_flow.get("events", []))

    return {
        "tool": "agent_workspace",
        "action": "analyze_inbox",
        "read_only": True,
        "summary": {
            "artifacts": len(artifacts),
            "chunks": chunk_total,
            "events": len(event_flow.get("events", [])),
            "reviewable_events": len(reviewable_events),
            "quant_candidates": len(quant_candidates),
            "relation_candidates": len(relation_candidates),
        },
        "summaries": summaries,
        "events": event_flow.get("events", []),
        "reviewable_events": reviewable_events,
        "quant_candidates": quant_candidates[:safe_limit],
        "event_counts": event_counts.most_common(),
        "relation_candidates": relation_candidates,
        "causal_candidates": relation_candidates,
        "policy": ARTIFACT_POLICY + [
            "Event and relation outputs are hypotheses for review, not confirmed causes.",
        ],
    }


__all__ = [
    "analyze_inbox",
    "artifact_record",
    "artifact_type_for",
    "build_quant_candidates",
    "review_quality",
    "summarize_artifact",
]
