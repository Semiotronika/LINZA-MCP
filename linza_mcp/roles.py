"""Data-driven material type discovery for LINZA.

This module intentionally does not contain a fixed material-type ontology.
LINZA may read previously accepted YAML values for compatibility, but fresh
vault analysis starts from observed note structure and cluster evidence.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from .utils import get_linza_property, normalize_note_name, strip_frontmatter, tokenize


UNTYPED_ROLE = "untyped"


def normalize_role(role: str) -> str:
    value = normalize_note_name(str(role or "")).replace(" ", "-")
    return value or UNTYPED_ROLE


def public_role(role: str) -> str:
    return normalize_role(role)


def guess_note_role(title: str, body: str, folder: str, metadata: dict[str, Any]) -> dict:
    """Return only accepted metadata, never a hardcoded role guess.

    Older LINZA versions used title/body keyword heuristics here. That made the
    first analysis look more confident than it was. The new contract is clean
    slate: if the user has not accepted a `role`, the note is untyped until the
    data-driven material-type clustering proposes candidates.
    """

    accepted_role = get_linza_property(metadata, "role") if isinstance(metadata, dict) else None
    if accepted_role:
        role = normalize_role(str(accepted_role))
        return {
            "role": role,
            "raw_role": str(accepted_role),
            "confidence": "accepted",
            "reason": "accepted_yaml",
        }
    return {
        "role": UNTYPED_ROLE,
        "raw_role": UNTYPED_ROLE,
        "confidence": "none",
        "reason": "clean_slate_no_role_guess",
    }


def role_definition(role: str) -> dict[str, Any]:
    role_id = normalize_role(role)
    return {
        "id": role_id,
        "yaml_value": role_id,
        "label_ru": role_id,
        "definition_ru": (
            "Автоматически найденный тип материала в этой базе. Название является "
            "черновиком и должно быть принято или переименовано человеком."
        ),
        "review_question_ru": f"Этот найденный тип `{role_id}` подходит для этой заметки?",
    }


def role_review_metadata(role: str, label: str | None = None) -> dict[str, Any]:
    definition = role_definition(role)
    role_id = definition["id"]
    human_label = label or definition["label_ru"]
    return {
        "id": role_id,
        "kind": "material_type",
        "label": human_label,
        "definition": definition["definition_ru"],
        "question": f"Эта заметка действительно относится к найденному типу `{human_label}`?",
        "yaml_value": role_id,
        "storage_key": "role",
        "write_preview": f"Если принять, LINZA добавит в YAML только `role: {role_id}`. Текст заметки не меняется.",
    }


def material_type_vocabulary(type_counts: list[tuple[str, int]] | None = None) -> dict[str, Any]:
    counts = {
        normalize_role(role): int(count)
        for role, count in (type_counts or [])
        if normalize_role(role) != UNTYPED_ROLE
    }
    observed = [role for role, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
    return {
        "policy": "discover_from_vault_then_review",
        "storage_key": "role",
        "baseline_types": [],
        "optional_types": [],
        "observed_types": observed,
        "suggested_types": observed,
        "counts": counts,
        "note": (
            "LINZA does not ship a fixed material-type ontology. Types are "
            "discovered from this vault's structure and must be reviewed or renamed."
        ),
    }


def _bucket_count(value: int, edges: tuple[int, ...]) -> int:
    for index, edge in enumerate(edges):
        if value <= edge:
            return index
    return len(edges)


def material_type_features(title: str, body: str, folder: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a neutral structural fingerprint for one note.

    The feature names describe observable form, not an assumed note category.
    """

    metadata = metadata or {}
    lines = body.splitlines()
    nonempty = [line for line in lines if line.strip()]
    words = re.findall(r"\w+", body, flags=re.UNICODE)
    headings = re.findall(r"^#{1,6}\s+", body, flags=re.MULTILINE)
    list_lines = [line for line in nonempty if re.match(r"\s*(?:[-*+]|\d+[.)])\s+", line)]
    checkbox_lines = [line for line in nonempty if re.match(r"\s*[-*+]\s+\[[ xX]\]", line)]
    quote_lines = [line for line in nonempty if line.lstrip().startswith(">")]
    table_lines = [line for line in nonempty if "|" in line and line.count("|") >= 2]
    code_fences = len(re.findall(r"```", body))
    urls = len(re.findall(r"https?://\S+", body))
    wikilinks = len(re.findall(r"(?<!!)\[\[[^\]]+\]\]", body))
    tags = len(re.findall(r"(?<!\w)#[\w/_-]+", body))
    folder_depth = 0 if not folder else len([part for part in folder.split("/") if part])
    word_count = len(words)
    line_count = len(nonempty)

    numeric = {
        "word_bucket": _bucket_count(word_count, (40, 160, 600, 1800)),
        "line_bucket": _bucket_count(line_count, (6, 20, 80, 200)),
        "heading_bucket": _bucket_count(len(headings), (0, 2, 6, 12)),
        "list_ratio": round(len(list_lines) / max(1, line_count), 3),
        "checkbox_ratio": round(len(checkbox_lines) / max(1, line_count), 3),
        "quote_ratio": round(len(quote_lines) / max(1, line_count), 3),
        "table_ratio": round(len(table_lines) / max(1, line_count), 3),
        "code_bucket": _bucket_count(code_fences // 2, (0, 1, 3, 8)),
        "url_bucket": _bucket_count(urls, (0, 1, 4, 12)),
        "wikilink_bucket": _bucket_count(wikilinks, (0, 2, 8, 24)),
        "tag_bucket": _bucket_count(tags, (0, 2, 8, 24)),
        "folder_depth": min(folder_depth, 4),
        "metadata_bucket": _bucket_count(len(metadata), (0, 3, 8, 16)),
    }
    text_terms = tokenize(f"{title} {folder.replace('/', ' ')}")
    shape_tokens: list[str] = [
        f"words:{numeric['word_bucket']}",
        f"lines:{numeric['line_bucket']}",
        f"headings:{numeric['heading_bucket']}",
        f"code:{numeric['code_bucket']}",
        f"urls:{numeric['url_bucket']}",
        f"links:{numeric['wikilink_bucket']}",
        f"folder-depth:{numeric['folder_depth']}",
    ]
    if numeric["list_ratio"] >= 0.35:
        shape_tokens.append("list-dense")
    elif numeric["list_ratio"] >= 0.12:
        shape_tokens.append("mixed-list")
    else:
        shape_tokens.append("prose-dense")
    if checkbox_lines:
        shape_tokens.append("checkboxes")
    if quote_lines:
        shape_tokens.append("quotes")
    if table_lines:
        shape_tokens.append("tables")
    if urls:
        shape_tokens.append("external-links")
    if wikilinks:
        shape_tokens.append("internal-links")
    if tags:
        shape_tokens.append("inline-tags")

    vector: dict[str, float] = {key: float(value) for key, value in numeric.items()}
    for token in shape_tokens:
        vector[token] = 1.0
    return {
        "numeric": numeric,
        "vector": vector,
        "shape_tokens": shape_tokens,
        "title_folder_terms": sorted(text_terms),
        "counts": {
            "words": word_count,
            "lines": line_count,
            "headings": len(headings),
            "list_lines": len(list_lines),
            "checkbox_lines": len(checkbox_lines),
            "quote_lines": len(quote_lines),
            "table_lines": len(table_lines),
            "code_blocks": code_fences // 2,
            "urls": urls,
            "wikilinks": wikilinks,
            "tags": tags,
            "folder_depth": folder_depth,
        },
    }


def feature_cosine(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    dot = sum(left.get(key, 0.0) * right.get(key, 0.0) for key in keys)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def discover_material_types(records: list[dict[str, Any]], assigned_to: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Cluster notes by observed structure and return draft material types."""

    if not records:
        return {"policy": "discover_from_vault_then_review", "types": [], "assignments": {}}

    assigned_to = assigned_to or {}
    clusters: list[dict[str, Any]] = []
    threshold = 0.86 if len(records) < 30 else 0.82

    for record in sorted(records, key=lambda item: item["path"]):
        accepted = record.get("accepted_role")
        if accepted:
            cluster = next((item for item in clusters if item.get("accepted_label") == accepted), None)
            if cluster is None:
                cluster = {
                    "members": [],
                    "vectors": [],
                    "accepted_label": accepted,
                    "seed_reason": "accepted_yaml",
                }
                clusters.append(cluster)
            cluster["members"].append(record)
            cluster["vectors"].append(record["material_features"]["vector"])
            continue

        best_cluster = None
        best_score = -1.0
        for cluster in clusters:
            if cluster.get("accepted_label"):
                continue
            centroid = _cluster_centroid(cluster["vectors"])
            score = feature_cosine(record["material_features"]["vector"], centroid)
            if score > best_score:
                best_score = score
                best_cluster = cluster
        if best_cluster is not None and best_score >= threshold:
            best_cluster["members"].append(record)
            best_cluster["vectors"].append(record["material_features"]["vector"])
            best_cluster.setdefault("similarities", []).append(round(best_score, 3))
        else:
            clusters.append({
                "members": [record],
                "vectors": [record["material_features"]["vector"]],
                "similarities": [],
                "seed_reason": "structural_fingerprint",
            })

    clusters = sorted(
        clusters,
        key=lambda item: (-len(item["members"]), item["members"][0]["path"]),
    )
    types: list[dict[str, Any]] = []
    assignments: dict[str, str] = {}
    for index, cluster in enumerate(clusters, start=1):
        members = sorted(cluster["members"], key=lambda item: item["path"])
        type_id = normalize_role(cluster.get("accepted_label") or f"type-{index:03d}")
        label_terms = _label_terms(members)
        label = cluster.get("accepted_label") or type_id
        shape_tokens = Counter(
            token
            for member in members
            for token in member["material_features"].get("shape_tokens", [])
        )
        domain_ids = Counter(
            domain_id
            for member in members
            for domain_id in assigned_to.get(member["path"], [])
        )
        confidence = "medium" if len(members) >= 2 else "low"
        if cluster.get("accepted_label"):
            confidence = "accepted"
        type_info = {
            "id": type_id,
            "suggested_label": label,
            "confidence": confidence,
            "member_count": len(members),
            "representative_terms": label_terms[:8],
            "shape": shape_tokens.most_common(8),
            "domain_ids": domain_ids.most_common(5),
            "representative_notes": [
                {
                    "path": member["path"],
                    "title": member["title"],
                    "counts": member["material_features"]["counts"],
                }
                for member in members[:8]
            ],
            "why": "Grouped from structural fingerprints observed in this vault; label is a draft, not a built-in ontology.",
        }
        types.append(type_info)
        for member in members:
            assignments[member["path"]] = type_id

    return {
        "policy": "discover_from_vault_then_review",
        "types": types,
        "assignments": assignments,
        "threshold": threshold,
        "note": "No material-type names are hardcoded; type IDs and labels are draft review candidates.",
    }


def _cluster_centroid(vectors: list[dict[str, float]]) -> dict[str, float]:
    centroid: dict[str, float] = {}
    for vector in vectors:
        for key, value in vector.items():
            centroid[key] = centroid.get(key, 0.0) + value
    count = max(1, len(vectors))
    return {key: value / count for key, value in centroid.items()}


def _label_terms(members: list[dict[str, Any]]) -> list[str]:
    counts: Counter[str] = Counter()
    for member in members:
        counts.update(member["material_features"].get("title_folder_terms", []))
        counts.update(member.get("tokens", set()) & set(member["material_features"].get("title_folder_terms", [])))
    return [term for term, _ in counts.most_common(12)]


__all__ = [
    "UNTYPED_ROLE",
    "discover_material_types",
    "feature_cosine",
    "guess_note_role",
    "material_type_features",
    "material_type_vocabulary",
    "normalize_role",
    "public_role",
    "role_definition",
    "role_review_metadata",
]
