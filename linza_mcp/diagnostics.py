"""Vault diagnostics and review suggestion helpers."""

from __future__ import annotations

import difflib
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict

from .roles import guess_note_role
from .utils import (
    extract_tags,
    extract_wikilinks,
    format_yaml_block,
    get_linza_metadata as utils_get_linza_metadata,
    get_linza_property as utils_get_linza_property,
    normalize_note_name,
    now_ts,
    safe_vault_path,
    set_linza_metadata,
    should_ignore_path,
    strip_frontmatter,
    tokenize,
)


def get_linza_property(metadata: Dict[str, Any], key: str, default: Any = None) -> Any:
    return utils_get_linza_property(metadata, key, default)


def build_linza_block(values: Dict[str, Any]) -> Dict[str, Any]:
    block: Dict[str, Any] = {}
    for key, value in values.items():
        target_key = str(key)
        if target_key == "type":
            target_key = "role"
        elif target_key == "role_confidence":
            target_key = "confidence"
        block[target_key] = value
    return set_linza_metadata({}, block)


def build_action_suggestions(
    core,
    notes: Dict[str, Dict[str, Any]],
    backlinks: Dict[str, int],
    broken_links: list[dict[str, str]],
    near_duplicate_titles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []

    for item in broken_links[:20]:
        suggestions.append({
            "action": "fix_link",
            "source": item["source"],
            "target": item["target"],
            "priority": "high",
            "why": "The note points to a page that does not exist. This breaks navigation and AI context gathering.",
        })

    for item in near_duplicate_titles[:20]:
        suggestions.append({
            "action": "review_duplicate",
            "source": item["a"],
            "target": item["b"],
            "priority": "medium",
            "why": "The titles are nearly identical. These notes may be duplicates or split versions of one topic.",
        })

    for bridge in sorted(core.storage.get_all_bridges(), key=lambda item: item.get("score", 0), reverse=True)[:30]:
        source = bridge.get("source")
        target = bridge.get("target")
        if source not in notes or target not in notes:
            continue
        score = float(bridge.get("score", 0))
        relation = core.classify_relation_candidate(source, target, score)
        priority = "medium" if relation["action"] != "add_semantic_link" or score >= 0.72 else "low"
        suggestions.append({
            "action": relation["action"],
            "source": source,
            "target": target,
            "priority": priority,
            "score": round(score, 4),
            "relation": relation["relation"],
            "shared_terms": relation["shared_terms"],
            "shared_tags": relation["shared_tags"],
            "why": (
                f"Embedding similarity {score:.3f}"
                + (f", shared tags: {', '.join(relation['shared_tags'][:5])}" if relation["shared_tags"] else "")
                + (f", shared terms: {', '.join(relation['shared_terms'][:5])}" if relation["shared_terms"] else "")
                + f". Suggested action: {relation['do']}"
            ),
        })

    paths = list(notes.keys())
    token_index = {path: notes[path]["tokens"] for path in paths}
    tag_index = {path: set(notes[path]["tags"]) for path in paths}

    candidate_links = []
    for i, left in enumerate(paths):
        left_tokens = token_index[left]
        if not left_tokens:
            continue
        for right in paths[i + 1:]:
            right_tokens = token_index[right]
            if not right_tokens:
                continue
            token_overlap = len(left_tokens & right_tokens)
            tag_overlap = len(tag_index[left] & tag_index[right])
            if token_overlap < 5 and tag_overlap == 0:
                continue
            denom = math.sqrt(len(left_tokens) * len(right_tokens)) or 1
            score = (token_overlap / denom) + (tag_overlap * 0.08)
            if score >= 0.18:
                candidate_links.append((score, token_overlap, tag_overlap, left, right))

    for score, token_overlap, tag_overlap, left, right in sorted(candidate_links, reverse=True)[:30]:
        suggestions.append({
            "action": "suggest_link",
            "source": left,
            "target": right,
            "priority": "low",
            "score": round(score, 3),
            "why": (
                f"These notes share {token_overlap} meaningful title/body terms"
                + (f" and {tag_overlap} tag(s)" if tag_overlap else "")
                + ". Review the relation before adding a link."
            ),
        })

    for path, note in notes.items():
        incoming = backlinks.get(note["title_key"], 0)
        if incoming == 0 and not note["links"] and note["word_count"] >= 80:
            suggestions.append({
                "action": "connect_or_archive",
                "source": path,
                "priority": "medium",
                "why": "This note has enough content but no graph contact. Link it, turn it into an inbox item, or archive it.",
            })
        if note["word_count"] > 1800:
            suggestions.append({
                "action": "split",
                "source": path,
                "priority": "medium",
                "why": "This note is long enough to hide multiple ideas. Split sections into focused notes or create a MOC.",
            })
    priority_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(suggestions, key=lambda item: (priority_order.get(item.get("priority"), 9), item.get("source", "")))


def scan_vault(core) -> Dict[str, Any]:
    """Read the vault as a note system: links, tags, properties, material types, and cleanup signals."""
    vault = core.storage.vault_path
    notes: Dict[str, Dict[str, Any]] = {}
    title_to_paths: Dict[str, list[str]] = defaultdict(list)
    link_targets: Counter[str] = Counter()
    property_keys: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    folder_counts: Counter[str] = Counter()

    for file_path in sorted(vault.glob("**/*.md")):
        if should_ignore_path(file_path, vault):
            continue

        rel = str(file_path.relative_to(vault)).replace("\\", "/")
        content = file_path.read_text(encoding="utf-8", errors="replace")
        metadata, body = strip_frontmatter(content)
        title = file_path.stem
        title_key = normalize_note_name(title)
        links = extract_wikilinks(content)
        tags = extract_tags(content, metadata)
        folder = str(file_path.parent.relative_to(vault)).replace("\\", "/")
        folder = "" if folder == "." else folder
        role_info = guess_note_role(title, body, folder, metadata)
        role = role_info.get("role", "note")
        role_reason = role_info.get("reason", "fallback")
        tokens = tokenize(f"{title} {body[:4000]}")
        word_count = len(re.findall(r"\w+", body, flags=re.UNICODE))

        for link in links:
            link_targets[link] += 1
        for key in metadata.keys():
            property_keys[str(key)] += 1
        for tag in tags:
            tag_counts[tag] += 1
        folder_counts[folder or "(root)"] += 1
        title_to_paths[title_key].append(rel)

        notes[rel] = {
            "path": rel,
            "title": title,
            "title_key": title_key,
            "folder": folder,
            "content": content,
            "body": body,
            "metadata": metadata,
            "links": links,
            "tags": tags,
            "role": role,
            "role_reason": role_reason,
            "tokens": tokens,
            "word_count": word_count,
            "mtime": file_path.stat().st_mtime,
        }

    existing_titles = {note["title_key"] for note in notes.values()}
    backlinks: Dict[str, int] = defaultdict(int)
    broken_links: list[dict[str, str]] = []
    for source, note in notes.items():
        for target in note["links"]:
            if target in existing_titles:
                backlinks[target] += 1
            else:
                broken_links.append({"source": source, "target": target})

    exact_duplicate_titles = {
        title: paths for title, paths in title_to_paths.items() if title and len(paths) > 1
    }

    title_keys = sorted(title_to_paths.keys())
    near_duplicate_titles = []
    for i, left in enumerate(title_keys):
        for right in title_keys[i + 1:]:
            if not left or not right:
                continue
            ratio = difflib.SequenceMatcher(None, left, right).ratio()
            if ratio >= 0.88:
                near_duplicate_titles.append({
                    "a": title_to_paths[left][0],
                    "b": title_to_paths[right][0],
                    "score": round(ratio, 3),
                    "reason": "very similar titles",
                })

    orphan_notes = []
    dead_ends = []
    source_only = []
    thin_notes = []
    long_notes = []
    stale_notes = []
    now = time.time()
    for path, note in notes.items():
        incoming = backlinks.get(note["title_key"], 0)
        outgoing = len(note["links"])
        if incoming == 0 and outgoing == 0:
            orphan_notes.append(path)
        elif outgoing == 0:
            dead_ends.append(path)
        elif incoming == 0:
            source_only.append(path)
        if note["word_count"] < 40:
            thin_notes.append(path)
        if note["word_count"] > 1800:
            long_notes.append(path)
        if now - note["mtime"] > 180 * 24 * 60 * 60:
            stale_notes.append(path)

    role_counts = Counter(note["role"] for note in notes.values())
    suggestions = build_action_suggestions(core, notes, backlinks, broken_links, near_duplicate_titles)

    return {
        "summary": {
            "notes": len(notes),
            "links": sum(len(note["links"]) for note in notes.values()),
            "broken_links": len(broken_links),
            "orphans": len(orphan_notes),
            "dead_ends": len(dead_ends),
            "source_only": len(source_only),
            "thin_notes": len(thin_notes),
            "long_notes": len(long_notes),
            "stale_notes": len(stale_notes),
            "tags": len(tag_counts),
            "properties": len(property_keys),
        },
        "top_tags": tag_counts.most_common(25),
        "top_properties": property_keys.most_common(25),
        "folders": folder_counts.most_common(25),
        "roles": role_counts.most_common(),
        "orphan_notes": orphan_notes[:100],
        "dead_ends": dead_ends[:100],
        "source_only": source_only[:100],
        "thin_notes": thin_notes[:100],
        "long_notes": long_notes[:100],
        "stale_notes": stale_notes[:100],
        "broken_links": broken_links[:100],
        "exact_duplicate_titles": exact_duplicate_titles,
        "near_duplicate_titles": near_duplicate_titles[:100],
        "suggestions": suggestions[:100],
    }


def build_review_queue_markdown(core, limit: int = 30) -> str:
    diagnostic = scan_vault(core)
    suggestions = diagnostic["suggestions"][:limit]
    lines = [
        "# LINZA Review Queue",
        "",
        "This file is generated by LINZA. It is a review queue, not an automatic edit log.",
        "",
        "## Why Links Matter",
        "",
        "- Links make related notes available to humans and agents without loading the whole vault.",
        "- A link is a decision: same topic, evidence, dependency, duplicate, or next action.",
        "- LINZA suggestions are candidates. Accept only the ones that still make sense when you read both notes.",
        "",
        "## Vault Snapshot",
        "",
    ]
    for key, value in diagnostic["summary"].items():
        lines.append(f"- **{key}**: {value}")

    sections = [
        ("High Priority", "high"),
        ("Medium Priority", "medium"),
        ("Low Priority", "low"),
    ]
    for title, priority in sections:
        lines.extend(["", f"## {title}", ""])
        matching = [item for item in suggestions if item.get("priority") == priority]
        if not matching:
            lines.append("- Nothing in this bucket.")
            continue
        for item in matching:
            source = item.get("source", "")
            target = item.get("target", "")
            action = item.get("action", "review")
            why = item.get("why", "")
            if target:
                lines.append(f"- [ ] `{action}`: [[{Path(source).stem}]] <-> [[{Path(target).stem}]]")
            else:
                lines.append(f"- [ ] `{action}`: [[{Path(source).stem}]]")
            lines.append(f"  - why: {why}")

    return "\n".join(lines).rstrip() + "\n"


def build_diagnostic_markdown(core) -> str:
    diagnostic = scan_vault(core)
    calibration = core.calibrate_embeddings()
    lines = [
        "# LINZA Vault Diagnostic",
        "",
        "LINZA reads the vault as a working knowledge system: files, links, properties, material types, and semantic candidates.",
        "",
        "## Snapshot",
        "",
    ]
    for key, value in diagnostic["summary"].items():
        lines.append(f"- **{key}**: {value}")
    lines.extend(["", "## Embedding Calibration", ""])
    if calibration.get("status") == "ok":
        lines.extend([
            f"- **files**: {calibration['files']}",
            f"- **anisotropy_score**: {calibration['anisotropy_score']}",
            f"- **mean_similarity_before**: {calibration['mean_similarity_before']}",
            f"- **mean_similarity_after**: {calibration['mean_similarity_after']}",
            f"- **improvement**: {calibration['improvement']}",
            "",
            "Recommended thresholds:",
        ])
        for key, value in calibration["recommended_thresholds"].items():
            lines.append(f"- **{key}**: {value}")
    else:
        lines.append(calibration.get("message", "Embeddings are not calibrated yet."))
    lines.extend(["", "## Material Type Counts", ""])
    for role, count in diagnostic.get("roles", []):
        lines.append(f"- **{role}**: {count}")
    lines.extend(["", "## First Actions", ""])
    for item in diagnostic.get("suggestions", [])[:15]:
        target = item.get("target")
        if target:
            lines.append(f"- `{item.get('action')}` [[{Path(item.get('source', '')).stem}]] <-> [[{Path(target).stem}]]")
        else:
            lines.append(f"- `{item.get('action')}` [[{Path(item.get('source', '')).stem}]]")
        lines.append(f"  - {item.get('why', '')}")
    return "\n".join(lines).rstrip() + "\n"


def build_semantic_links_markdown(core, limit: int = 50) -> str:
    bridges = sorted(core.storage.get_all_bridges(), key=lambda item: item.get("score", 0), reverse=True)[:limit]
    lines = [
        "# LINZA Semantic Link Candidates",
        "",
        "These are candidate links from calibrated embeddings. They are not automatic truth; read both notes before accepting a link.",
        "",
        "## How To Read This",
        "",
        "- `review_duplicate`: decide whether to merge/archive/link as draft-final.",
        "- `attach_context`: connect notes that share terms, tags, or semantic neighborhood.",
        "- `add_semantic_link`: ordinary related-note candidate; accept only if it helps navigation.",
        "",
    ]
    if not bridges:
        lines.append("No semantic bridges are available. Run `index_all` first or lower the bridge threshold.")
        return "\n".join(lines).rstrip() + "\n"

    buckets = [
        ("Possible Duplicates / Versions", {"review_duplicate"}),
        ("Context Links", {"attach_context"}),
        ("Suggested Semantic Links", {"add_semantic_link"}),
    ]
    enriched = []
    for bridge in bridges:
        source = bridge["source"]
        target = bridge["target"]
        relation = core.classify_relation_candidate(source, target, float(bridge["score"]))
        enriched.append((bridge, relation))

    for title, actions in buckets:
        bucket_items = [(bridge, relation) for bridge, relation in enriched if relation["action"] in actions]
        lines.extend(["", f"## {title}", ""])
        if not bucket_items:
            lines.append("- Nothing in this bucket.")
            continue
        for bridge, relation in bucket_items:
            source = bridge["source"]
            target = bridge["target"]
            lines.append(f"- [ ] [[{Path(source).stem}]] <-> [[{Path(target).stem}]]")
            lines.append(f"  - action: `{relation['action']}`")
            lines.append(f"  - relation: `{relation['relation']}`")
            lines.append(f"  - score: {bridge['score']:.4f}")
            if relation["shared_tags"]:
                lines.append(f"  - shared tags: {', '.join(relation['shared_tags'][:8])}")
            if relation["shared_terms"]:
                lines.append(f"  - shared terms: {', '.join(relation['shared_terms'][:8])}")
            lines.append(f"  - do: {relation['do']}")
    return "\n".join(lines).rstrip() + "\n"


def explain_relationship(core, source: str, target: str) -> Dict[str, Any]:
    vault = core.storage.vault_path
    source_path = vault / source
    target_path = vault / target
    if not source_path.exists() or not target_path.exists():
        return {"error": "source or target not found"}

    source_content = source_path.read_text(encoding="utf-8", errors="replace")
    target_content = target_path.read_text(encoding="utf-8", errors="replace")
    source_meta, source_body = strip_frontmatter(source_content)
    target_meta, target_body = strip_frontmatter(target_content)
    source_tokens = tokenize(f"{source_path.stem} {source_body[:4000]}")
    target_tokens = tokenize(f"{target_path.stem} {target_body[:4000]}")
    shared_tokens = sorted((source_tokens & target_tokens))[:20]
    shared_tags = sorted(set(extract_tags(source_content, source_meta)) & set(extract_tags(target_content, target_meta)))
    direct_links = normalize_note_name(target_path.stem) in extract_wikilinks(source_content)
    reverse_links = normalize_note_name(source_path.stem) in extract_wikilinks(target_content)

    suggested_relation = "related_to"
    if direct_links or reverse_links:
        suggested_relation = "existing_link"
    elif normalize_note_name(source_path.stem) == normalize_note_name(target_path.stem):
        suggested_relation = "duplicates"
    elif shared_tags:
        suggested_relation = "same_tag_cluster"
    elif len(shared_tokens) >= 8:
        suggested_relation = "semantic_neighbor"

    return {
        "source": source,
        "target": target,
        "suggested_relation": suggested_relation,
        "evidence": {
            "direct_link": direct_links,
            "reverse_link": reverse_links,
            "shared_tags": shared_tags,
            "shared_tokens": shared_tokens,
        },
        "policy": "explanation_only; LINZA does not write links from this tool",
    }


def build_bases_plan_markdown(core) -> str:
    diagnostic = scan_vault(core)
    lines = [
        "# LINZA Bases Plan",
        "",
        "LINZA does not need to invent a database UI. Obsidian Bases can use properties; LINZA prepares cleaner properties and review queues.",
        "",
        "## Suggested Views",
        "",
        "| View | Filter | Useful Columns |",
        "|---|---|---|",
        "| Type candidates | discovered from this vault | role, confidence, file.mtime |",
        "| Domain candidates | discovered from semantic clusters | domains, file.links |",
        "| Review queue | generated from draft map | evidence, confidence, next action |",
        "",
        "## Current Material Type Counts",
        "",
    ]
    for role, count in diagnostic.get("roles", []):
        lines.append(f"- **{role}**: {count}")
    lines.extend([
        "",
        "## Property Policy",
        "",
        "- LINZA writes only small human-facing YAML properties by default.",
        "- Existing user/project fields stay untouched unless the user explicitly asks for plain YAML edits.",
        "- Existing LINZA properties stay untouched unless the user approves overwrite.",
        "- Properties should stay small and machine-readable; longer explanation belongs in note body.",
        "",
        "## YAML Shape",
        "",
        "```yaml",
        "role: reviewed-type",
        "confidence: high",
        "```",
    ])
    return "\n".join(lines).rstrip() + "\n"


def suggest_properties_for_note(core, path: str) -> Dict[str, Any]:
    try:
        rel, full = safe_vault_path(core.storage.vault_path, path)
    except ValueError as exc:
        return {"error": str(exc), "path": path}
    if not full.exists() or not full.is_file():
        return {"error": "file not found", "path": path}

    content = full.read_text(encoding="utf-8", errors="replace")
    metadata, body = strip_frontmatter(content)
    folder = str(full.parent.relative_to(core.storage.vault_path)).replace("\\", "/")
    folder = "" if folder == "." else folder
    role_info = guess_note_role(full.stem, body, folder, metadata)
    role = role_info.get("role", "note")
    role_reason = role_info.get("reason", "fallback")
    word_count = len(re.findall(r"\w+", body, flags=re.UNICODE))
    age_days = int((now_ts() - full.stat().st_mtime) / (24 * 60 * 60))

    suggestions = []
    proposed_linza: Dict[str, Any] = {}
    if role != "untyped" and get_linza_property(metadata, "role") is None:
        proposed_linza["role"] = role
        suggestions.append({
            "property": "role",
            "value": role,
            "why": f"LINZA classified this note as {role} ({role_reason}).",
        })
    if role != "untyped" and get_linza_property(metadata, "confidence") is None:
        confidence = role_info.get("confidence", "low")
        proposed_linza["confidence"] = confidence
        suggestions.append({
            "property": "confidence",
            "value": confidence,
            "why": "Machine confidence for the suggested material type.",
        })
    yaml_patch = build_linza_block(proposed_linza) if proposed_linza else {}

    return {
        "path": rel,
        "role": role,
        "role_reason": role_reason,
        "confidence": role_info.get("confidence", "low"),
        "word_count": word_count,
        "age_days": age_days,
        "existing_properties": sorted(str(k) for k in metadata.keys()),
        "linza_properties": sorted(utils_get_linza_metadata(metadata).keys()),
        "suggestions": suggestions,
        "yaml_patch": yaml_patch,
        "yaml_preview": format_yaml_block(yaml_patch) if yaml_patch else "",
        "yaml_schema": {
            "role": "accepted human material type name discovered and named for this vault",
            "confidence": "optional confidence for machine suggestions",
            "domains": "reviewed domain labels",
        },
        "write_policy": "read-only suggestion; write only small human-facing YAML properties after user approval",
    }


def build_yaml_suggestions_markdown(core, limit: int = 50) -> str:
    diagnostic = scan_vault(core)
    suggestions = diagnostic.get("suggestions", [])
    paths: list[str] = []
    for item in suggestions:
        source = item.get("source")
        if source and source not in paths:
            paths.append(source)
        if len(paths) >= limit:
            break

    lines = [
        "# LINZA YAML Suggestions",
        "",
        "These are proposed human-facing YAML properties. This report does not modify notes.",
        "",
        "LINZA YAML stores only compact reviewed material type/domain hints; processing state, temporary link candidates, and embedding scores stay in reports or `.linza/linza.db`.",
        "",
    ]
    if not paths:
        lines.append("No YAML suggestions right now.")
        return "\n".join(lines).rstrip() + "\n"

    for path in paths:
        suggestion = suggest_properties_for_note(core, path)
        yaml_preview = suggestion.get("yaml_preview", "")
        if not yaml_preview:
            continue
        lines.extend([
            f"## [[{Path(path).stem}]]",
            "",
            "```yaml",
            yaml_preview,
            "```",
            "",
            f"- role reason: {suggestion.get('role_reason')}",
            f"- word count: {suggestion.get('word_count')}",
            "",
        ])

    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "build_action_suggestions",
    "build_bases_plan_markdown",
    "build_diagnostic_markdown",
    "build_linza_block",
    "build_review_queue_markdown",
    "build_semantic_links_markdown",
    "build_yaml_suggestions_markdown",
    "explain_relationship",
    "get_linza_property",
    "scan_vault",
    "suggest_properties_for_note",
]
