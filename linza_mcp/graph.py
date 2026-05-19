"""Read-only graph inspection tools for LINZA."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .roles import guess_note_role
from .utils import (
    extract_tags,
    extract_wikilinks,
    get_linza_metadata,
    normalize_note_name,
    should_ignore_path,
    strip_frontmatter,
)


def read_note_index(core) -> Dict[str, Any]:
    vault = core.storage.vault_path
    notes: Dict[str, Dict[str, Any]] = {}
    title_to_paths: Dict[str, List[str]] = defaultdict(list)

    for file_path in sorted(vault.glob("**/*.md")):
        if should_ignore_path(file_path, vault):
            continue

        rel = str(file_path.relative_to(vault)).replace("\\", "/")
        content = file_path.read_text(encoding="utf-8", errors="replace")
        metadata, body = strip_frontmatter(content)
        title = file_path.stem
        title_key = normalize_note_name(title)
        folder = str(file_path.parent.relative_to(vault)).replace("\\", "/")
        folder = "" if folder == "." else folder
        role_info = guess_note_role(title, body, folder, metadata)
        notes[rel] = {
            "path": rel,
            "title": title,
            "title_key": title_key,
            "metadata": metadata,
            "body": body,
            "links": extract_wikilinks(content),
            "tags": extract_tags(content, metadata),
            "role": role_info.get("role", "note"),
            "role_reason": role_info.get("reason", "fallback"),
            "word_count": len(re.findall(r"\w+", body, flags=re.UNICODE)),
            "mtime": file_path.stat().st_mtime,
        }
        title_to_paths[title_key].append(rel)

    incoming: Dict[str, List[str]] = defaultdict(list)
    outgoing: Dict[str, List[str]] = defaultdict(list)
    broken_links: list[dict[str, str]] = []
    for source, note in notes.items():
        seen_targets: set[str] = set()
        for target_key in note["links"]:
            matches = title_to_paths.get(target_key, [])
            if not matches:
                broken_links.append({"source": source, "target": target_key})
                continue
            for target in matches:
                if target in seen_targets:
                    continue
                seen_targets.add(target)
                outgoing[source].append(target)
                incoming[target].append(source)

    return {
        "notes": notes,
        "title_to_paths": title_to_paths,
        "incoming": incoming,
        "outgoing": outgoing,
        "broken_links": broken_links,
    }


def match_note_paths(index: Dict[str, Any], value: str) -> List[str]:
    normalized_path = str(value).replace("\\", "/").strip()
    notes = index["notes"]
    if normalized_path in notes:
        return [normalized_path]

    title_key = normalize_note_name(normalized_path)
    matches = index["title_to_paths"].get(title_key, [])
    if matches:
        return sorted(matches)

    lowered = normalized_path.lower()
    return sorted(path for path in notes if path.lower().endswith(lowered))


def resolve_one_note(index: Dict[str, Any], value: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    matches = match_note_paths(index, value)
    if not matches:
        return None, {"error": "node_not_found", "query": value}
    if len(matches) > 1:
        return None, {"error": "ambiguous_node", "query": value, "matches": matches[:20]}
    return matches[0], None


def node_suggestions(diagnostic: Dict[str, Any], path: str, limit: int = 10) -> list[dict[str, Any]]:
    related = []
    for item in diagnostic.get("suggestions", []):
        if item.get("source") == path or item.get("target") == path:
            related.append(item)
        if len(related) >= limit:
            break
    return related


def explain_node(core, path: str) -> Dict[str, Any]:
    index = read_note_index(core)
    resolved, error = resolve_one_note(index, path)
    if error:
        return error

    assert resolved is not None
    note = index["notes"][resolved]
    diagnostic = core.scan_vault()
    incoming = sorted(index["incoming"].get(resolved, []))
    outgoing = sorted(index["outgoing"].get(resolved, []))
    broken = [item for item in index["broken_links"] if item["source"] == resolved]
    bridges = sorted(
        core.storage.get_bridges_for_file(resolved),
        key=lambda item: item.get("score", 0),
        reverse=True,
    )[:12]

    metadata = note["metadata"]
    linza_block = get_linza_metadata(metadata) or None
    return {
        "tool": "explain_node",
        "read_only": True,
        "path": resolved,
        "title": note["title"],
        "role": note["role"],
        "role_reason": note["role_reason"],
        "word_count": note["word_count"],
        "tags": note["tags"],
        "frontmatter_keys": sorted(str(key) for key in metadata.keys()),
        "linza": linza_block,
        "explicit_graph": {
            "incoming_count": len(incoming),
            "outgoing_count": len(outgoing),
            "incoming": incoming[:20],
            "outgoing": outgoing[:20],
            "broken_outgoing_links": broken[:20],
        },
        "semantic_bridges": bridges,
        "review_suggestions": node_suggestions(diagnostic, resolved),
        "why_this_matters": "This node can be used as agent context when its explicit links, semantic bridges, and review warnings support the current task.",
    }


def who_depends(core, path: str, depth: int = 1) -> Dict[str, Any]:
    depth = max(1, min(int(depth), 4))
    index = read_note_index(core)
    resolved, error = resolve_one_note(index, path)
    if error:
        return error

    assert resolved is not None
    visited = {resolved}
    frontier = [resolved]
    layers = []
    for level in range(1, depth + 1):
        next_frontier: list[str] = []
        for current in frontier:
            for parent in sorted(index["incoming"].get(current, [])):
                if parent in visited:
                    continue
                visited.add(parent)
                next_frontier.append(parent)
        if not next_frontier:
            break
        layers.append({"depth": level, "nodes": next_frontier})
        frontier = next_frontier

    bridges = core.storage.get_bridges_for_file(resolved)
    bridge_neighbors = sorted({
        item["target"] if item["source"] == resolved else item["source"]
        for item in bridges
    })

    return {
        "tool": "who_depends",
        "read_only": True,
        "path": resolved,
        "explicit_dependents": sorted(index["incoming"].get(resolved, [])),
        "this_depends_on": sorted(index["outgoing"].get(resolved, [])),
        "dependent_layers": layers,
        "semantic_neighbors": bridge_neighbors,
        "note": "Explicit dependents are backlinks. Semantic neighbors are candidates, not confirmed dependency edges.",
    }


def flow_adjacency(core, index: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    adjacency: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for source, targets in index["outgoing"].items():
        for target in targets:
            adjacency[source].append({
                "path": target,
                "edge": "wikilink_out",
                "relation": "links_to",
                "confidence": "EXTRACTED",
            })
            adjacency[target].append({
                "path": source,
                "edge": "wikilink_in",
                "relation": "linked_from",
                "confidence": "EXTRACTED",
            })

    for bridge in core.storage.get_all_bridges():
        source = bridge.get("source")
        target = bridge.get("target")
        if source not in index["notes"] or target not in index["notes"]:
            continue
        edge = {
            "edge": "semantic_bridge",
            "score": round(float(bridge.get("score", 0)), 4),
            "type": bridge.get("type"),
            "relation": bridge.get("type") or "semantic_bridge",
            "confidence": "INFERRED",
        }
        adjacency[source].append({"path": target, **edge})
        adjacency[target].append({"path": source, **edge})

    for item in core.storage.list_approved_items("hierarchy_link", limit=10000):
        payload = item.get("payload", {})
        parent = str(payload.get("parent_path", "")).strip()
        children = [str(path).strip() for path in payload.get("child_paths", []) if str(path).strip()]
        if parent not in index["notes"]:
            continue
        for child in children:
            if child not in index["notes"]:
                continue
            edge = {
                "edge": "approved_hierarchy",
                "relation": payload.get("relation", "parent_of"),
                "confidence": "APPROVED",
                "domain_name": payload.get("domain_name", ""),
                "evidence": payload.get("evidence", ""),
            }
            adjacency[parent].append({"path": child, "direction": "parent_to_child", **edge})
            adjacency[child].append({"path": parent, "direction": "child_to_parent", **edge})

    for item in core.storage.list_approved_items("causal_link", limit=10000):
        payload = item.get("payload", {})
        source = str(payload.get("source_path", "")).strip()
        target = str(payload.get("target_path", "")).strip()
        if source not in index["notes"] or target not in index["notes"]:
            continue
        edge = {
            "edge": "approved_causal",
            "relation": payload.get("relation", "related_to"),
            "confidence": "APPROVED",
            "evidence": payload.get("evidence", ""),
        }
        adjacency[source].append({"path": target, "direction": "source_to_target", **edge})
        adjacency[target].append({"path": source, "direction": "target_to_source", **edge})
    return adjacency


def find_flow_path(core, source: str, target: str, max_depth: int = 4) -> Optional[List[Dict[str, Any]]]:
    max_depth = max(1, min(int(max_depth), 6))
    index = read_note_index(core)
    adjacency = flow_adjacency(core, index)
    queue: list[tuple[str, list[dict[str, Any]]]] = [(source, [{"path": source, "edge": "start"}])]
    visited = {source}

    while queue:
        current, route = queue.pop(0)
        if current == target:
            return route
        if len(route) - 1 >= max_depth:
            continue
        for edge in sorted(adjacency.get(current, []), key=lambda item: item["path"]):
            neighbor = edge["path"]
            if neighbor in visited:
                continue
            visited.add(neighbor)
            queue.append((neighbor, route + [edge]))
    return None


async def show_flow(
    core,
    source: Optional[str] = None,
    target: Optional[str] = None,
    query: Optional[str] = None,
    profile_name: Optional[str] = None,
    top_k: int = 8,
    max_depth: int = 4,
) -> Dict[str, Any]:
    if source and target:
        index = read_note_index(core)
        source_path, source_error = resolve_one_note(index, source)
        if source_error:
            return source_error
        target_path, target_error = resolve_one_note(index, target)
        if target_error:
            return target_error
        assert source_path is not None and target_path is not None
        route = find_flow_path(core, source_path, target_path, max_depth=max_depth)
        return {
            "tool": "show_flow",
            "read_only": True,
            "mode": "node_to_node",
            "source": source_path,
            "target": target_path,
            "found": route is not None,
            "route": route or [],
            "max_depth": max_depth,
        }

    if query:
        search = await core.search(query, profile_name=profile_name, top_k=int(top_k), explain=True)
        results = search.get("results", [])
        return {
            "tool": "show_flow",
            "read_only": True,
            "mode": "query_context_flow",
            "query": query,
            "profile": profile_name,
            "nodes": [
                {
                    "rank": idx + 1,
                    "path": item.get("path"),
                    "score": item.get("score"),
                    "confidence": item.get("confidence"),
                    "why": item.get("why"),
                }
                for idx, item in enumerate(results)
            ],
            "explanation": search.get("explanation"),
            "note": "Use create_context_pack when this flow should become a handoff artifact.",
        }

    if source:
        return who_depends(core, source, depth=1)

    return {"error": "source_target_or_query_required"}


def filter_rule_items(items: Any, path: Optional[str]) -> Any:
    if not path:
        return items
    if isinstance(items, dict):
        filtered = {}
        for key, value in items.items():
            if isinstance(value, list) and path in value:
                filtered[key] = value
        return filtered
    if not isinstance(items, list):
        return items

    filtered_items = []
    for item in items:
        if isinstance(item, str) and item == path:
            filtered_items.append(item)
        elif isinstance(item, dict):
            values = {item.get(key) for key in ("path", "source", "target", "a", "b")}
            if path in values:
                filtered_items.append(item)
    return filtered_items


def check_rule(core, rule: str = "all", path: Optional[str] = None) -> Dict[str, Any]:
    diagnostic = core.scan_vault()
    resolved_path = None
    if path:
        index = read_note_index(core)
        resolved_path, error = resolve_one_note(index, path)
        if error:
            return error

    aliases = {
        "orphans": "orphan_notes",
        "orphan": "orphan_notes",
        "duplicates": "near_duplicate_titles",
        "duplicate_titles": "near_duplicate_titles",
        "all": "all",
    }
    selected = aliases.get(rule, rule)
    rule_map = {
        "broken_links": diagnostic.get("broken_links", []),
        "orphan_notes": diagnostic.get("orphan_notes", []),
        "dead_ends": diagnostic.get("dead_ends", []),
        "source_only": diagnostic.get("source_only", []),
        "thin_notes": diagnostic.get("thin_notes", []),
        "long_notes": diagnostic.get("long_notes", []),
        "stale_notes": diagnostic.get("stale_notes", []),
        "near_duplicate_titles": diagnostic.get("near_duplicate_titles", []),
        "exact_duplicate_titles": diagnostic.get("exact_duplicate_titles", {}),
        "suggestions": diagnostic.get("suggestions", []),
    }

    if selected != "all" and selected not in rule_map:
        return {
            "error": "unknown_rule",
            "rule": rule,
            "known_rules": sorted(rule_map.keys()) + ["all", "orphans", "duplicates"],
        }

    selected_rules = rule_map if selected == "all" else {selected: rule_map[selected]}
    results = {
        name: filter_rule_items(items, resolved_path)
        for name, items in selected_rules.items()
    }
    issue_count = 0
    for items in results.values():
        if isinstance(items, dict):
            issue_count += len(items)
        elif isinstance(items, list):
            issue_count += len(items)
        elif items:
            issue_count += 1

    return {
        "tool": "check_rule",
        "read_only": True,
        "rule": rule,
        "path": resolved_path,
        "status": "ok" if issue_count == 0 else "warning",
        "issue_count": issue_count,
        "summary": diagnostic.get("summary", {}),
        "results": results,
    }


__all__ = [
    "read_note_index",
    "match_note_paths",
    "resolve_one_note",
    "node_suggestions",
    "explain_node",
    "who_depends",
    "flow_adjacency",
    "find_flow_path",
    "show_flow",
    "filter_rule_items",
    "check_rule",
]
