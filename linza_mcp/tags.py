"""Tag vocabulary audit and candidate suggestion tools."""

from __future__ import annotations

import difflib
import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict

from .graph import read_note_index, resolve_one_note
from .utils import (
    COMMON_TAG_HINTS,
    FRONTMATTER_RE,
    HEX_COLOR_TAG_RE,
    STOPWORDS,
    TECHNICAL_TAG_NOISE,
    _raw_frontmatter_tags,
    extract_tag_details,
    normalize_tag,
    should_ignore_path,
    strip_frontmatter,
)


def split_text_chunks(text: str, max_chars: int = 1200) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            paragraph_break = text.rfind("\n\n", start, end)
            line_break = text.rfind("\n", start, end)
            if paragraph_break > start + 200:
                end = paragraph_break
            elif line_break > start + 200:
                end = line_break

        raw = text[start:end]
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        chunk_start = start + leading
        chunk_end = start + trailing
        chunk_text = text[chunk_start:chunk_end]
        if chunk_text:
            chunks.append({
                "chunk_id": f"chunk-{len(chunks):04d}",
                "start": chunk_start,
                "end": chunk_end,
                "text": chunk_text,
            })

        start = end
        while start < length and text[start].isspace():
            start += 1

    return chunks


def tag_phrase_pattern(tag: str) -> re.Pattern:
    pieces = [re.escape(piece) for piece in re.split(r"[-/]+", tag) if piece]
    core = r"[\s_/-]+".join(pieces) if len(pieces) > 1 else re.escape(tag)
    return re.compile(rf"(?<!\w){core}(?!\w)", re.IGNORECASE)


def tag_candidate_snippet(text: str, start: int, end: int, radius: int = 90) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    snippet = re.sub(r"\s+", " ", text[left:right]).strip()
    if left > 0:
        snippet = "..." + snippet
    if right < len(text):
        snippet = snippet + "..."
    return snippet


def find_chunk_evidence(
    chunks: list[dict[str, Any]],
    pattern: re.Pattern,
    body: str,
    body_offset: int,
    limit: int = 3,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for chunk in chunks:
        match = pattern.search(chunk["text"])
        if not match:
            continue
        local_start = chunk["start"] + match.start()
        local_end = chunk["start"] + match.end()
        evidence.append({
            "chunk_id": chunk["chunk_id"],
            "start": body_offset + local_start,
            "end": body_offset + local_end,
            "snippet": tag_candidate_snippet(body, local_start, local_end),
        })
        if len(evidence) >= limit:
            break
    return evidence


def tag_candidate_confidence(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def is_clean_new_tag_candidate(tag: str) -> bool:
    if not tag or len(tag) < 4:
        return False
    if tag in STOPWORDS or tag in COMMON_TAG_HINTS or tag in TECHNICAL_TAG_NOISE:
        return False
    if tag.isdigit() or HEX_COLOR_TAG_RE.fullmatch(tag):
        return False
    return True


def yaml_tag_vocabulary(core) -> Dict[str, Dict[str, Any]]:
    vocabulary: Dict[str, Dict[str, Any]] = {}
    vault = core.storage.vault_path
    for file_path in sorted(vault.glob("**/*.md")):
        if should_ignore_path(file_path, vault):
            continue
        content = file_path.read_text(encoding="utf-8", errors="replace")
        metadata, _ = strip_frontmatter(content)
        rel = str(file_path.relative_to(vault)).replace("\\", "/")
        for raw in _raw_frontmatter_tags(metadata):
            normalized = normalize_tag(raw)
            if not normalized:
                continue
            entry = vocabulary.setdefault(normalized, {
                "tag": normalized,
                "count": 0,
                "raw_variants": Counter(),
                "files": set(),
            })
            entry["count"] += 1
            entry["raw_variants"][raw] += 1
            entry["files"].add(rel)

    for entry in vocabulary.values():
        entry["raw_variants"] = entry["raw_variants"].most_common()
        entry["files"] = sorted(entry["files"])
    return vocabulary


def add_tag_candidate(
    candidates: Dict[str, Dict[str, Any]],
    tag: str,
    source: str,
    status: str,
    score: float,
    reason: str,
    evidence: list[dict[str, Any]],
    vocabulary_count: int = 0,
) -> None:
    if not evidence:
        return
    item = candidates.get(tag)
    if item is None:
        candidates[tag] = {
            "tag": tag,
            "status": status,
            "source": source,
            "score": round(score, 3),
            "confidence": tag_candidate_confidence(score),
            "vocabulary_count": vocabulary_count,
            "reason": reason,
            "evidence": evidence,
        }
        return
    if score > item["score"]:
        item["source"] = source
        item["status"] = status
        item["score"] = round(score, 3)
        item["confidence"] = tag_candidate_confidence(score)
        item["reason"] = reason
    seen = {(e["chunk_id"], e["start"], e["end"]) for e in item["evidence"]}
    for evidence_item in evidence:
        key = (evidence_item["chunk_id"], evidence_item["start"], evidence_item["end"])
        if key not in seen and len(item["evidence"]) < 5:
            item["evidence"].append(evidence_item)
            seen.add(key)


def suggest_tag_candidates(
    core,
    path: str,
    max_candidates: int = 20,
    include_new: bool = True,
) -> Dict[str, Any]:
    max_candidates = max(1, int(max_candidates))
    index = read_note_index(core)
    resolved, error = resolve_one_note(index, path)
    if error:
        return error

    assert resolved is not None
    full_path = core.storage.vault_path / resolved
    content = full_path.read_text(encoding="utf-8", errors="replace")
    metadata, body = strip_frontmatter(content)
    body_offset = len(content) - len(body)
    chunks = split_text_chunks(body)
    details = extract_tag_details(content, metadata)
    existing_tags = sorted({item["normalized"] for item in details["yaml"]})
    existing_set = set(existing_tags)
    vocabulary = yaml_tag_vocabulary(core)
    candidates: Dict[str, Dict[str, Any]] = {}

    for item in details["inline"]:
        tag = item["normalized"]
        if tag in existing_set:
            continue
        pattern = re.compile(rf"(?<!\w)#{re.escape(item['raw'])}(?!\w)", re.IGNORECASE)
        evidence = find_chunk_evidence(chunks, pattern, body, body_offset)
        if not evidence:
            evidence = [{
                "chunk_id": "chunk-unknown",
                "start": body_offset,
                "end": body_offset,
                "snippet": item["raw"],
            }]
        add_tag_candidate(
            candidates,
            tag,
            source="inline",
            status="candidate",
            score=0.86 if tag in vocabulary else 0.74,
            reason="Inline hashtag found in note body; review before accepting into YAML.",
            evidence=evidence,
            vocabulary_count=vocabulary.get(tag, {}).get("count", 0),
        )

    for tag, vocab in vocabulary.items():
        if tag in existing_set:
            continue
        pattern = tag_phrase_pattern(tag)
        evidence = find_chunk_evidence(chunks, pattern, body, body_offset)
        if not evidence:
            continue
        score = min(0.9, 0.62 + min(0.18, len(evidence) * 0.05) + min(0.1, vocab["count"] * 0.02))
        add_tag_candidate(
            candidates,
            tag,
            source="vocabulary_hit",
            status="candidate",
            score=score,
            reason="Accepted YAML vocabulary tag appears in chunk text; candidate only, not written.",
            evidence=evidence,
            vocabulary_count=vocab["count"],
        )

    if include_new:
        token_counts: Counter[str] = Counter()
        token_chunks: Dict[str, set[str]] = defaultdict(set)
        heading_tokens: set[str] = set()
        for chunk in chunks:
            for raw in re.findall(r"(?u)[\w/-]{3,}", chunk["text"]):
                tag = normalize_tag(raw)
                if not tag or tag in existing_set or tag in vocabulary:
                    continue
                if not is_clean_new_tag_candidate(tag):
                    continue
                token_counts[tag] += 1
                token_chunks[tag].add(chunk["chunk_id"])
            for heading in re.findall(r"(?m)^\s{0,3}#{1,6}\s+(.+)$", chunk["text"]):
                for raw in re.findall(r"(?u)[\w/-]{3,}", heading):
                    tag = normalize_tag(raw)
                    if tag and is_clean_new_tag_candidate(tag):
                        heading_tokens.add(tag)

        for tag, count in token_counts.most_common(max_candidates * 4):
            chunk_count = len(token_chunks[tag])
            if count < 2 and tag not in heading_tokens:
                continue
            pattern = tag_phrase_pattern(tag)
            evidence = find_chunk_evidence(chunks, pattern, body, body_offset)
            score = min(0.68, 0.36 + min(0.18, count * 0.03) + min(0.1, chunk_count * 0.04) + (0.08 if tag in heading_tokens else 0))
            add_tag_candidate(
                candidates,
                tag,
                source="term",
                status="proposed",
                score=score,
                reason="Repeated clean term in chunks; review before adding to the vocabulary.",
                evidence=evidence,
            )

    sorted_candidates = sorted(
        candidates.values(),
        key=lambda item: (-item["score"], -item.get("vocabulary_count", 0), item["tag"]),
    )[:max_candidates]
    return {
        "tool": "suggest_tag_candidates",
        "read_only": True,
        "path": resolved,
        "existing_tags": [{"tag": tag, "source": "yaml", "status": "accepted"} for tag in existing_tags],
        "candidate_tags": sorted_candidates,
        "chunk_count": len(chunks),
        "policy": [
            "Candidate tags are evidence for review, not accepted YAML tags.",
            "Only explicit accepted tags belong in note frontmatter.",
            "LINZA never writes tags from this tool.",
        ],
    }


def fuzzy_tag_pairs(tag_counts: Counter[str]) -> list[dict[str, Any]]:
    tags = sorted(tag_counts.keys())
    pairs: list[dict[str, Any]] = []
    for i, left in enumerate(tags):
        for right in tags[i + 1:]:
            if abs(len(left) - len(right)) > 4:
                continue
            ratio = difflib.SequenceMatcher(None, left, right).ratio()
            if ratio >= 0.86:
                pairs.append({
                    "left": left,
                    "right": right,
                    "score": round(ratio, 3),
                    "left_count": tag_counts[left],
                    "right_count": tag_counts[right],
                })
    return sorted(pairs, key=lambda item: (-item["score"], item["left"], item["right"]))


def audit_tag_vocabulary(core) -> Dict[str, Any]:
    vault = core.storage.vault_path
    yaml_raw_counts: Counter[str] = Counter()
    inline_raw_counts: Counter[str] = Counter()
    ignored_inline_counts: Counter[str] = Counter()
    normalized_counts: Counter[str] = Counter()
    raw_by_normalized: Dict[str, Counter[str]] = defaultdict(Counter)
    files_with_yaml_tags = 0
    files_with_inline_tags = 0
    parse_errors: list[dict[str, str]] = []
    scanned = 0

    for file_path in sorted(vault.glob("**/*.md")):
        if should_ignore_path(file_path, vault):
            continue
        scanned += 1
        rel = str(file_path.relative_to(vault)).replace("\\", "/")
        content = file_path.read_text(encoding="utf-8", errors="replace")
        metadata, _ = strip_frontmatter(content)
        frontmatter_match = FRONTMATTER_RE.match(content)
        if frontmatter_match:
            try:
                import yaml
                yaml.safe_load(frontmatter_match.group(1))
            except Exception as exc:
                parse_errors.append({"path": rel, "error": str(exc)})

        details = extract_tag_details(content, metadata)
        if details["yaml"]:
            files_with_yaml_tags += 1
        if details["inline"]:
            files_with_inline_tags += 1

        for source in ("yaml", "inline"):
            counter = yaml_raw_counts if source == "yaml" else inline_raw_counts
            for item in details[source]:
                raw = item["raw"]
                normalized = item["normalized"]
                counter[raw] += 1
                normalized_counts[normalized] += 1
                raw_by_normalized[normalized][raw] += 1

        for item in details["ignored_inline"]:
            ignored_inline_counts[item["raw"]] += 1

    variant_groups = []
    for normalized, variants in raw_by_normalized.items():
        if len(variants) > 1:
            variant_groups.append({
                "canonical": normalized,
                "total": sum(variants.values()),
                "variants": variants.most_common(),
            })
    variant_groups.sort(key=lambda item: (-item["total"], item["canonical"]))

    common_threshold = max(3, math.ceil(max(scanned, 1) * 0.05))
    common_tag_candidates = [
        {"tag": tag, "count": count}
        for tag, count in normalized_counts.most_common()
        if count >= common_threshold or tag in COMMON_TAG_HINTS
    ]
    singleton_tags = sorted(tag for tag, count in normalized_counts.items() if count == 1)
    fuzzy_pairs = fuzzy_tag_pairs(normalized_counts)

    return {
        "tool": "audit_tags",
        "read_only": True,
        "summary": {
            "notes_scanned": scanned,
            "files_with_yaml_tags": files_with_yaml_tags,
            "files_with_inline_tags": files_with_inline_tags,
            "yaml_tag_assignments": sum(yaml_raw_counts.values()),
            "inline_tag_assignments": sum(inline_raw_counts.values()),
            "ignored_inline_tags": sum(ignored_inline_counts.values()),
            "unique_yaml_raw_tags": len(yaml_raw_counts),
            "unique_normalized_tags": len(normalized_counts),
            "singleton_tags": len(singleton_tags),
            "common_threshold": common_threshold,
        },
        "top_yaml_tags": yaml_raw_counts.most_common(30),
        "top_normalized_tags": normalized_counts.most_common(40),
        "ignored_inline_tags": ignored_inline_counts.most_common(30),
        "variant_groups": variant_groups[:40],
        "alias_candidates": fuzzy_pairs[:40],
        "common_tag_candidates": common_tag_candidates[:40],
        "singleton_examples": singleton_tags[:80],
        "parse_errors": parse_errors[:50],
        "connection_policy": [
            "Treat tags as supporting evidence, not as final links.",
            "Do not use common tags as the only reason for a semantic bridge.",
            "Review alias candidates before changing YAML.",
            "Keep tag vocabulary/audit review-first; promote only generic, tested primitives to the core index.",
        ],
    }


def build_tag_vocabulary_markdown(core) -> str:
    audit = audit_tag_vocabulary(core)
    summary = audit["summary"]
    lines = [
        "# LINZA Tag Vocabulary Audit",
        "",
        "This report is read-only. It explains tag hygiene and relation risk; it does not change note YAML.",
        "",
        "## Snapshot",
        "",
        f"- Notes scanned: {summary['notes_scanned']}",
        f"- Files with YAML tags: {summary['files_with_yaml_tags']}",
        f"- YAML tag assignments: {summary['yaml_tag_assignments']}",
        f"- Unique normalized tags: {summary['unique_normalized_tags']}",
        f"- Singleton tags: {summary['singleton_tags']}",
        f"- Ignored inline false tags: {summary['ignored_inline_tags']}",
        "",
        "## What This Means",
        "",
        "- The vocabulary is usable, but it needs a review loop before tag-based links become trusted.",
        "- Common tags are good filters, but weak relation evidence by themselves.",
        "- Singleton tags may be precise concepts or typos; they should be reviewed, not bulk-merged.",
        "- Hex colors and other false inline hashtags are ignored by LINZA before relation checks.",
        "",
        "## Common Tags",
        "",
    ]
    for item in audit["common_tag_candidates"][:25]:
        lines.append(f"- `{item['tag']}` ({item['count']})")

    lines.extend(["", "## Alias Candidates", ""])
    if audit["alias_candidates"]:
        for item in audit["alias_candidates"][:25]:
            lines.append(
                f"- `{item['left']}` <-> `{item['right']}` "
                f"(similarity {item['score']}, counts {item['left_count']}/{item['right_count']})"
            )
    else:
        lines.append("- No obvious spelling/plural aliases found.")

    lines.extend(["", "## Raw Variants", ""])
    if audit["variant_groups"]:
        for group in audit["variant_groups"][:20]:
            variants = ", ".join(f"`{raw}` x{count}" for raw, count in group["variants"])
            lines.append(f"- `{group['canonical']}`: {variants}")
    else:
        lines.append("- No case/spacing variants after normalization.")

    lines.extend(["", "## Ignored Inline False Tags", ""])
    if audit["ignored_inline_tags"]:
        for tag, count in audit["ignored_inline_tags"][:20]:
            lines.append(f"- `#{tag}` ({count})")
    else:
        lines.append("- None.")

    lines.extend(["", "## Connection Policy", ""])
    for rule in audit["connection_policy"]:
        lines.append(f"- {rule}")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "split_text_chunks",
    "tag_phrase_pattern",
    "tag_candidate_snippet",
    "find_chunk_evidence",
    "tag_candidate_confidence",
    "is_clean_new_tag_candidate",
    "yaml_tag_vocabulary",
    "add_tag_candidate",
    "suggest_tag_candidates",
    "fuzzy_tag_pairs",
    "audit_tag_vocabulary",
    "build_tag_vocabulary_markdown",
]
