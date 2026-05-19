"""Indexing, calibrated search, and semantic bridge helpers for LINZA."""

from __future__ import annotations

import difflib
import hashlib
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .roles import guess_note_role
from .utils import (
    extract_tags,
    normalize_note_name,
    safe_vault_path,
    should_ignore_path,
    strip_frontmatter,
    tokenize,
)


def embedding_signature(core) -> tuple[str, str, int | None]:
    """Return the runtime embedding signature stored with indexed vectors."""
    provider_name = type(core.embed).__name__
    model = str(getattr(core.embed, "model", "") or "")
    dim = getattr(core.embed, "dim", None)
    return provider_name, model, int(dim) if dim is not None else None


def _record_matches_embedding_signature(record: dict[str, Any], core) -> bool:
    if not record.get("embedding"):
        return False
    provider_name, model, expected_dim = embedding_signature(core)
    if record.get("embedding_provider") != provider_name:
        return False
    if str(record.get("embedding_model") or "") != model:
        return False
    stored_dim = record.get("embedding_dim")
    if expected_dim is not None and int(stored_dim or 0) != expected_dim:
        return False
    if stored_dim is not None and len(record["embedding"]) != int(stored_dim):
        return False
    return True


def embedding_index_status(core, sample_limit: int = 20) -> dict[str, Any]:
    """Report whether stored vectors match the current embedding provider."""
    provider_name, model, expected_dim = embedding_signature(core)
    expected = {"provider": provider_name, "model": model, "dim": expected_dim}
    records = [
        record
        for record in core.storage.get_all_file_records()
        if record.get("embedding") is not None
    ]
    if not records:
        return {
            "status": "empty",
            "message": "No indexed embeddings are stored yet.",
            "expected": expected,
            "indexed_embeddings": 0,
            "mismatch_count": 0,
            "mismatches": [],
            "observed_signatures": [],
        }

    mismatches: list[dict[str, Any]] = []
    signature_counts: Counter[tuple[str, str, int | None]] = Counter()
    for record in records:
        vector = record.get("embedding") or []
        stored_dim = record.get("embedding_dim")
        actual_dim = len(vector)
        observed_dim = int(stored_dim) if stored_dim is not None else actual_dim
        signature = (
            str(record.get("embedding_provider") or ""),
            str(record.get("embedding_model") or ""),
            observed_dim,
        )
        signature_counts[signature] += 1

        reasons: list[str] = []
        if signature[0] != provider_name:
            reasons.append("provider")
        if signature[1] != model:
            reasons.append("model")
        if expected_dim is not None and observed_dim != expected_dim:
            reasons.append("dimension")
        if stored_dim is not None and actual_dim != int(stored_dim):
            reasons.append("stored_dimension")
        if reasons:
            mismatches.append({
                "path": record["path"],
                "reasons": reasons,
                "stored": {
                    "provider": signature[0],
                    "model": signature[1],
                    "dim": observed_dim,
                    "actual_dim": actual_dim,
                },
            })

    observed = [
        {"provider": provider, "model": observed_model, "dim": dim, "count": count}
        for (provider, observed_model, dim), count in signature_counts.most_common()
    ]
    if mismatches or len(signature_counts) > 1:
        return {
            "status": "needs_reindex",
            "message": "Stored embeddings do not match one embedding provider/model signature. Run index_all with force=true.",
            "expected": expected,
            "indexed_embeddings": len(records),
            "mismatch_count": len(mismatches),
            "mismatches": mismatches[:sample_limit],
            "observed_signatures": observed,
        }

    return {
        "status": "ok",
        "message": "Stored embeddings match the current provider/model signature.",
        "expected": expected,
        "indexed_embeddings": len(records),
        "mismatch_count": 0,
        "mismatches": [],
        "observed_signatures": observed,
    }


def vault_sync_status(core, sample_limit: int = 20) -> dict[str, Any]:
    """Return a quick source-folder vs sidecar freshness check."""
    vault = core.storage.vault_path
    indexed = {record["path"]: record for record in core.storage.get_all_file_records()}
    current: dict[str, Path] = {}
    for path in vault.glob("**/*.md"):
        if should_ignore_path(path, vault):
            continue
        rel = str(path.relative_to(vault)).replace("\\", "/")
        current[rel] = path

    added = sorted(set(current) - set(indexed))
    removed = sorted(set(indexed) - set(current))
    changed: list[str] = []
    hash_checked = 0
    for rel in sorted(set(current) & set(indexed)):
        record = indexed[rel]
        stored_hash = str(record.get("hash") or "")
        if not stored_hash:
            changed.append(rel)
            continue
        current_mtime = current[rel].stat().st_mtime
        stored_mtime = float(record.get("mtime") or 0)
        if abs(current_mtime - stored_mtime) <= 1e-6:
            continue
        content = current[rel].read_text(encoding="utf-8", errors="replace")
        hash_checked += 1
        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if file_hash != stored_hash:
            changed.append(rel)

    stale_count = len(added) + len(removed) + len(changed)
    if not current and not indexed:
        status = "empty"
        message = "No Markdown files are present and no index exists."
    elif current and not indexed:
        status = "needs_index"
        message = "Markdown files exist, but the sidecar has not indexed them yet."
    elif stale_count:
        status = "stale"
        message = "The Markdown folder changed after the last index. Run index_all before relying on graph/search results."
    else:
        status = "ok"
        message = "The sidecar index matches the current Markdown folder."

    return {
        "status": status,
        "message": message,
        "source_markdown_files": len(current),
        "indexed_files": len(indexed),
        "stale_count": stale_count,
        "hash_checked_files": hash_checked,
        "added": added[:sample_limit],
        "changed": changed[:sample_limit],
        "removed": removed[:sample_limit],
        "added_count": len(added),
        "changed_count": len(changed),
        "removed_count": len(removed),
    }


async def compute_embeddings(core, texts: List[str]) -> Tuple[List[List[float]], List[List[float]]]:
    """Return raw and current mean-centered embeddings for texts."""
    raw = await core.embed.embed(texts)
    if core.centerer.is_fitted:
        centered = core.centerer.transform(raw)
    else:
        centered = raw
    return raw, centered


def load_or_compute_corpus_mean(core) -> None:
    """Load corpus mean from storage into the core centerer if present."""
    loaded = core.storage.load_corpus_mean()
    if loaded:
        mean, count = loaded
        core.centerer.corpus_mean = np.array(mean)
        core.centerer.is_fitted = True
        logging.info("Loaded corpus mean from DB (%s files)", count)
    else:
        logging.info("No corpus mean in DB, will compute on first index")


def recompute_corpus_mean_and_recenter_index(core) -> None:
    """Recompute corpus mean exactly from currently indexed raw embeddings."""
    records = [
        record
        for record in core.storage.get_all_file_records()
        if record.get("embedding") is not None
    ]
    if not records:
        core.centerer.corpus_mean = None
        core.centerer.is_fitted = False
        core.storage.clear_corpus_mean()
        return

    raw_embeddings = [record["embedding"] for record in records]
    core.centerer.fit(raw_embeddings)
    core.storage.save_corpus_mean(core.centerer.corpus_mean.tolist(), len(raw_embeddings))
    centered_embeddings = core.centerer.transform(raw_embeddings)
    for record, centered in zip(records, centered_embeddings):
        core.storage.upsert_file(
            record["path"],
            record.get("content", ""),
            record.get("mtime") or 0,
            record["embedding"],
            centered,
            record.get("hash", ""),
            embedding_provider=record.get("embedding_provider"),
            embedding_model=record.get("embedding_model"),
            embedding_dim=record.get("embedding_dim"),
        )
    recenter_profiles(core)


def recenter_profiles(core) -> None:
    """Recompute stored profile vectors with the current corpus mean."""
    if not core.centerer.is_fitted:
        return
    for profile in core.storage.get_all_profile_records():
        raw_embedding = profile.get("raw_embedding")
        if not raw_embedding:
            continue
        centered = core.centerer.transform([raw_embedding])[0]
        core.storage.update_profile_centered_embedding(profile["name"], centered)


async def index_vault(core, force: bool = False) -> None:
    """Full reindex of vault: raw embeddings, corpus mean, centered embeddings, bridges."""
    vault = core.storage.vault_path
    if force:
        core.centerer.corpus_mean = None
        core.centerer.is_fitted = False

    files = [path for path in vault.glob("**/*.md") if not should_ignore_path(path, vault)]
    current_paths = {str(path.relative_to(vault)).replace("\\", "/") for path in files}
    for indexed_path in core.storage.list_files():
        if indexed_path not in current_paths:
            core.storage.delete_file(indexed_path)

    all_raw: list[list[float]] = []
    file_data: list[tuple[str, str, float, list[float], str]] = []
    provider_name, model, expected_dim = embedding_signature(core)

    for file_path in files:
        rel = str(file_path.relative_to(vault)).replace("\\", "/")
        mtime = file_path.stat().st_mtime
        content = file_path.read_text(encoding="utf-8", errors="replace")
        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        existing = core.storage.get_file_metadata(rel)
        if not force and existing and existing["hash"] == file_hash:
            if _record_matches_embedding_signature(existing, core):
                all_raw.append(existing["embedding"])
                file_data.append((rel, content, mtime, existing["embedding"], file_hash))
                continue

        raw, _ = await compute_embeddings(core, [content])
        all_raw.append(raw[0])
        file_data.append((rel, content, mtime, raw[0], file_hash))

    if all_raw:
        core.centerer.fit(all_raw)
        core.storage.save_corpus_mean(core.centerer.corpus_mean.tolist(), len(all_raw))
        centered_all = core.centerer.transform(all_raw)
        for item, centered_emb in zip(file_data, centered_all):
            rel, content, mtime, raw_emb, file_hash = item
            core.storage.upsert_file(
                rel,
                content,
                mtime,
                raw_emb,
                centered_emb,
                file_hash,
                embedding_provider=provider_name,
                embedding_model=model,
                embedding_dim=expected_dim or len(raw_emb),
            )
        recenter_profiles(core)
    else:
        core.centerer.corpus_mean = None
        core.centerer.is_fitted = False
        core.storage.clear_corpus_mean()

    await rebuild_bridges(core)
    logging.info("Indexed %s files, rebuilt bridges", len(file_data))


async def index_single_file(core, path: str, content: Optional[str] = None) -> None:
    """Incremental index of one file. Recomputes corpus mean for current indexed files."""
    rel_path, full_path = safe_vault_path(core.storage.vault_path, path)
    index_status = embedding_index_status(core)
    if index_status["status"] == "needs_reindex":
        raise RuntimeError(
            "Stored embeddings use a different provider/model signature. "
            "Run index_all with force=true before indexing a single file."
        )

    if content is None:
        if not full_path.exists():
            core.storage.delete_file(rel_path)
            recompute_corpus_mean_and_recenter_index(core)
            await rebuild_bridges(core)
            return
        content = full_path.read_text(encoding="utf-8", errors="replace")

    file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    existing = core.storage.get_file_metadata(rel_path)
    if existing and existing["hash"] == file_hash and _record_matches_embedding_signature(existing, core):
        return

    raw = await core.embed.embed([content])
    provider_name, model, expected_dim = embedding_signature(core)
    mtime = full_path.stat().st_mtime if full_path.exists() else 0
    core.storage.upsert_file(
        rel_path,
        content,
        mtime,
        raw[0],
        raw[0],
        file_hash,
        embedding_provider=provider_name,
        embedding_model=model,
        embedding_dim=expected_dim or len(raw[0]),
    )
    recompute_corpus_mean_and_recenter_index(core)
    await rebuild_bridges(core)


async def rebuild_bridges(core, threshold: Optional[float] = None) -> None:
    """Build semantic bridges between files using centered embeddings."""
    if threshold is None:
        threshold = core.config.get("bridge_threshold", 0.55)

    index_status = embedding_index_status(core)
    if index_status["status"] == "needs_reindex":
        core.storage.update_bridges([])
        logging.warning("Skipped bridges because stored embeddings need a full reindex")
        return

    all_emb = core.storage.get_all_embeddings(use_centered=True)
    if len(all_emb) < 2:
        core.storage.update_bridges([])
        return

    pair_count = (len(all_emb) * (len(all_emb) - 1)) // 2
    max_pairs = int(core.config.get("max_bridge_pairs", 1000000) or 0)
    if max_pairs > 0 and pair_count > max_pairs:
        core.storage.update_bridges([])
        logging.warning(
            "Skipped bridges for %s pairs; exceeds LINZA_MAX_BRIDGE_PAIRS=%s",
            pair_count,
            max_pairs,
        )
        return

    paths, vectors = zip(*all_emb)
    try:
        arr = np.array(vectors, dtype=float)
    except ValueError:
        core.storage.update_bridges([])
        logging.warning("Skipped bridges because stored embeddings have mixed dimensions")
        return
    if arr.ndim != 2:
        core.storage.update_bridges([])
        return
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    arr_norm = arr / (norms + 1e-9)
    sim = np.dot(arr_norm, arr_norm.T)

    bridges = []
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            score = float(sim[i, j])
            if score > threshold:
                bridges.append({
                    "source": paths[i],
                    "target": paths[j],
                    "score": score,
                    "type": "semantic",
                })

    core.storage.update_bridges(bridges)
    logging.info("Built %s bridges (threshold=%s)", len(bridges), threshold)


def get_profile_vector(core, profile_name: str) -> Optional[np.ndarray]:
    """Get effective profile vector, combining with parent if present."""
    profile = core.storage.get_profile(profile_name)
    if not profile:
        return None

    vec = np.array(profile["centered_embedding"], dtype=float) if profile["centered_embedding"] else None
    parent_name = profile.get("parent_profile")
    if parent_name:
        parent_vec = get_profile_vector(core, parent_name)
        if parent_vec is not None and vec is not None:
            vec = 0.7 * vec + 0.3 * parent_vec
        elif parent_vec is not None:
            vec = parent_vec
    return vec


def cosine_matrix(vectors: list[list[float]]) -> np.ndarray:
    arr = np.array(vectors, dtype=float)
    if arr.size == 0:
        return np.zeros((0, 0))
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    arr_norm = arr / (norms + 1e-9)
    return np.dot(arr_norm, arr_norm.T)


def pairwise_stats(vectors: list[list[float]]) -> Dict[str, Any]:
    if len(vectors) < 2:
        return {
            "count": len(vectors),
            "mean": None,
            "median": None,
            "p90": None,
            "p95": None,
            "std": None,
        }
    sim = cosine_matrix(vectors)
    upper = sim[np.triu_indices_from(sim, k=1)]
    return {
        "count": len(vectors),
        "mean": round(float(np.mean(upper)), 4),
        "median": round(float(np.median(upper)), 4),
        "p90": round(float(np.percentile(upper, 90)), 4),
        "p95": round(float(np.percentile(upper, 95)), 4),
        "std": round(float(np.std(upper)), 4),
    }


def calibrate_embeddings(core) -> Dict[str, Any]:
    """Report embedding anisotropy and action thresholds without domain/core etalons."""
    raw = [emb for _, emb in core.storage.get_all_embeddings(use_centered=False)]
    centered = [emb for _, emb in core.storage.get_all_embeddings(use_centered=True)]
    before = pairwise_stats(raw)
    after = pairwise_stats(centered)

    if before["mean"] is None or after["mean"] is None:
        return {
            "status": "not_enough_data",
            "message": "Index at least two notes before calibration.",
            "files": len(raw),
        }

    anisotropy_score = max(0.0, min(1.0, float(before["mean"])))
    improvement = round(float(before["mean"]) - float(after["mean"]), 4)
    p95 = float(after["p95"] or 0.55)
    p90 = float(after["p90"] or 0.45)

    return {
        "status": "ok",
        "files": len(raw),
        "anisotropy_score": round(anisotropy_score, 4),
        "mean_similarity_before": before["mean"],
        "mean_similarity_after": after["mean"],
        "improvement": improvement,
        "before": before,
        "after": after,
        "recommended_thresholds": {
            "possible_duplicate": round(max(0.78, p95 + 0.06), 3),
            "suggest_link": round(max(0.55, p90), 3),
            "context_pack": round(max(0.38, float(after["median"] or 0) + 0.08), 3),
        },
        "notes": [
            "LINZA uses corpus mean-centering to reduce embedding anisotropy.",
            "Treat cosine as a candidate signal, not truth: prefer mutual neighbors and lexical/tag support.",
        ],
    }


def lexical_score(query: str, content: str) -> Tuple[float, int]:
    q_tokens = tokenize(query)
    c_tokens = tokenize(content[:6000])
    if not q_tokens or not c_tokens:
        return 0.0, 0
    overlap = len(q_tokens & c_tokens)
    denom = math.sqrt(len(q_tokens) * len(c_tokens)) or 1.0
    return min(1.0, overlap / denom * 3.0), overlap


def similarity_confidence(
    semantic_score: float,
    score_gap: float,
    lexical_overlap: int,
    mutual_neighbor: bool,
    shared_tags: int = 0,
) -> str:
    support = 0
    if semantic_score >= 0.7:
        support += 2
    elif semantic_score >= 0.55:
        support += 1
    if score_gap >= 0.08:
        support += 1
    if lexical_overlap >= 3:
        support += 1
    if shared_tags:
        support += 1
    if mutual_neighbor:
        support += 1
    if support >= 5:
        return "strong"
    if support >= 3:
        return "medium"
    return "weak"


def file_features(core, path: str) -> Dict[str, Any]:
    full = core.storage.vault_path / path
    if not full.exists():
        meta = core.storage.get_file_metadata(path) or {}
        content = meta.get("content", "")
    else:
        content = full.read_text(encoding="utf-8", errors="replace")
    metadata, body = strip_frontmatter(content)
    try:
        folder = str(full.parent.relative_to(core.storage.vault_path)).replace("\\", "/")
    except ValueError:
        folder = str(Path(path).parent).replace("\\", "/")
    folder = "" if folder == "." else folder
    role_info = guess_note_role(Path(path).stem, body, folder, metadata)
    return {
        "content": content,
        "metadata": metadata,
        "tags": set(extract_tags(content, metadata)),
        "tokens": tokenize(f"{Path(path).stem} {body[:4000]}"),
        "role": role_info.get("role", "untyped"),
    }


def classify_relation_candidate(core, source: str, target: str, score: float) -> Dict[str, Any]:
    source_features = file_features(core, source)
    target_features = file_features(core, target)
    shared_terms = sorted(source_features["tokens"] & target_features["tokens"])[:12]
    shared_tags = sorted(source_features["tags"] & target_features["tags"])
    source_title = normalize_note_name(Path(source).stem)
    target_title = normalize_note_name(Path(target).stem)
    title_ratio = difflib.SequenceMatcher(None, source_title, target_title).ratio()
    duplicate_evidence = (
        title_ratio >= 0.88
        or (score >= 0.88 and (len(shared_terms) >= 8 or len(shared_tags) >= 2))
        or (score >= 0.82 and title_ratio >= 0.72 and (shared_terms or shared_tags))
    )

    action = "add_semantic_link"
    relation = "related_to"
    do = "Read both notes and add a reviewed semantic link if the relation is still useful."

    if duplicate_evidence:
        action = "review_duplicate"
        relation = "possible_duplicate"
        do = "Decide whether to merge, archive one note, or link them as draft/final versions."
    elif shared_terms or shared_tags:
        action = "attach_context"
        relation = "shared_context"
        do = "Use this as context, expansion, or a parent/child topic link if the direction is clear after review."

    return {
        "action": action,
        "relation": relation,
        "do": do,
        "shared_terms": shared_terms,
        "shared_tags": shared_tags,
        "title_similarity": round(title_ratio, 3),
        "source_role": source_features["role"],
        "target_role": target_features["role"],
    }


def get_snippet(core, path: str, max_len: int = 200) -> str:
    meta = core.storage.get_file_metadata(path)
    if not meta or not meta["content"]:
        return ""
    content = meta["content"]
    para = content.split("\n\n")[0].replace("\n", " ")
    return para[:max_len] + "..." if len(para) > max_len else para


def explain_search(core, query: str, profile_name: str, results: List[Dict], sim: np.ndarray) -> str:
    profile = core.storage.get_profile(profile_name)
    if not profile:
        return f"Profile '{profile_name}' not found."

    lines = [
        f"Search: '{query}'",
        f"Profile: '{profile_name}' (keywords: {profile['keywords']})",
        f"Found {len(results)} results from {len(sim)} indexed notes:",
        "",
    ]

    for i, result in enumerate(results, 1):
        lines.append(f"{i}. {result['path']} (score: {result['score']})")
        lines.append(f"   {result['snippet'][:100]}...")
        lines.append("")

    if profile.get("parent_profile"):
        lines.append(f"Note: Profile inherits from '{profile['parent_profile']}'")

    return "\n".join(lines)


async def search(
    core,
    query: str,
    profile_name: Optional[str] = None,
    top_k: int = 5,
    explain: bool = False,
) -> Dict[str, Any]:
    """Search files with calibrated semantic similarity plus lightweight lexical support."""
    _, centered = await compute_embeddings(core, [query])
    q_vec = np.array(centered[0], dtype=float)

    all_emb = core.storage.get_all_embeddings(use_centered=True)
    if not all_emb:
        return {"results": [], "profile": profile_name, "explanation": None}
    index_status = embedding_index_status(core)
    if index_status["status"] == "needs_reindex":
        return {
            "results": [],
            "profile": profile_name,
            "explanation": None,
            "error": "embedding_signature_mismatch",
            "message": index_status["message"],
            "embedding_index": index_status,
        }

    paths, vectors = zip(*all_emb)
    try:
        arr = np.array(vectors, dtype=float)
    except ValueError:
        return {
            "results": [],
            "profile": profile_name,
            "explanation": None,
            "error": "embedding_dimension_mismatch",
            "message": "Stored embeddings have mixed dimensions. Run index_all with force=true after changing embedding provider or model.",
        }
    if arr.ndim != 2 or arr.shape[1] != q_vec.shape[0]:
        return {
            "results": [],
            "profile": profile_name,
            "explanation": None,
            "error": "embedding_dimension_mismatch",
            "message": "Stored embeddings do not match the current embedding provider. Run index_all with force=true after changing provider or model.",
        }
    norms = np.linalg.norm(arr, axis=1)
    q_norm = np.linalg.norm(q_vec)

    if q_norm == 0:
        sim = np.zeros(len(paths))
    else:
        sim = np.dot(arr, q_vec) / (norms * q_norm + 1e-9)

    profile_vec = None
    if profile_name:
        profile_vec = get_profile_vector(core, profile_name)
        core.storage.increment_profile_usage(profile_name)

    if profile_vec is not None:
        if profile_vec.shape[0] != arr.shape[1]:
            profile_vec = None
        else:
            p_norm = np.linalg.norm(profile_vec)
            if p_norm > 0:
                p_sim = np.dot(arr, profile_vec) / (norms * p_norm + 1e-9)
                query_length = len(query.split())
                weight = 0.3 if query_length > 5 else 0.5
                sim = (1 - weight) * sim + weight * p_sim

    records = {record["path"]: record for record in core.storage.get_all_file_records()}
    lexical = np.zeros(len(paths))
    lexical_overlaps: dict[str, int] = {}
    for i, path in enumerate(paths):
        score, overlap = lexical_score(query, records.get(path, {}).get("content", ""))
        lexical[i] = score
        lexical_overlaps[path] = overlap

    semantic_blend = (0.78 * sim) + (0.22 * lexical)
    combined = np.maximum(semantic_blend, lexical)
    indices = np.argsort(-combined)
    top_window = combined[indices[: max(top_k * 2, 10)]]
    baseline = float(np.median(top_window)) if len(top_window) else 0.0
    results = []
    for idx in indices[:top_k]:
        if combined[idx] <= 0:
            break
        gap = float(combined[idx] - baseline)
        results.append({
            "path": paths[idx],
            "score": round(float(combined[idx]), 4),
            "semantic_score": round(float(sim[idx]), 4),
            "lexical_score": round(float(lexical[idx]), 4),
            "score_gap": round(gap, 4),
            "confidence": similarity_confidence(
                float(sim[idx]),
                gap,
                lexical_overlaps.get(paths[idx], 0),
                mutual_neighbor=False,
            ),
            "why": "hybrid semantic/lexical match; review before using as context",
            "snippet": get_snippet(core, paths[idx], 200),
        })

    core.storage.log_search(query, profile_name, results)

    explanation = None
    if explain and profile_name:
        explanation = explain_search(core, query, profile_name, results, sim)

    return {
        "results": results,
        "profile": profile_name,
        "total_indexed": len(paths),
        "retrieval": "mean-centered embeddings + lexical overlap",
        "explanation": explanation,
    }


async def suggest_links(
    core,
    file_path: str,
    profile_name: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Suggest similar notes for a given file, optionally through a profile."""
    file_meta = core.storage.get_file_metadata(file_path)
    if not file_meta or not file_meta["centered_embedding"]:
        return []

    vec = np.array(file_meta["centered_embedding"], dtype=float)
    all_emb = core.storage.get_all_embeddings(use_centered=True)
    if not all_emb:
        return []

    paths, vectors = zip(*all_emb)
    arr = np.array(vectors, dtype=float)
    norms = np.linalg.norm(arr, axis=1)
    v_norm = np.linalg.norm(vec)
    if v_norm == 0:
        sim = np.zeros(len(paths))
    else:
        sim = np.dot(arr, vec) / (norms * v_norm + 1e-9)

    profile_vec = None
    if profile_name:
        profile_vec = get_profile_vector(core, profile_name)
    if profile_vec is not None:
        p_norm = np.linalg.norm(profile_vec)
        if p_norm > 0:
            p_sim = np.dot(arr, profile_vec) / (norms * p_norm + 1e-9)
            sim = 0.7 * sim + 0.3 * p_sim

    source_features = file_features(core, file_path)
    matrix_norms = np.linalg.norm(arr, axis=1, keepdims=True)
    arr_norm = arr / (matrix_norms + 1e-9)
    path_index = {p: i for i, p in enumerate(paths)}
    source_idx = path_index.get(file_path)

    candidates = []
    for idx, path in enumerate(paths):
        if path == file_path:
            continue
        candidate_features = file_features(core, path)
        lexical_overlap = len(source_features["tokens"] & candidate_features["tokens"])
        denom = math.sqrt(len(source_features["tokens"]) * len(candidate_features["tokens"])) or 1.0
        lexical_support = min(1.0, (lexical_overlap / denom) * 3.0) if lexical_overlap else 0.0
        combined_score = (0.78 * float(sim[idx])) + (0.22 * lexical_support)
        if combined_score <= 0:
            continue
        candidates.append((combined_score, idx, candidate_features, lexical_support, lexical_overlap))

    top_scores = sorted((score for score, *_ in candidates), reverse=True)
    baseline = float(np.median(top_scores[: max(top_k * 2, 10)])) if top_scores else 0.0
    results = []
    for combined_score, idx, candidate_features, lexical_support, lexical_overlap in sorted(
        candidates,
        key=lambda item: (-item[0], paths[item[1]]),
    ):
        shared_tags = sorted(source_features["tags"] & candidate_features["tags"])
        shared_terms = sorted(source_features["tokens"] & candidate_features["tokens"])[:12]
        score_gap = float(combined_score - baseline)
        mutual_neighbor = False
        if source_idx is not None:
            reverse_sim = np.dot(arr_norm, arr_norm[idx])
            reverse_order = [i for i in np.argsort(-reverse_sim) if i != idx][:10]
            mutual_neighbor = source_idx in reverse_order
        confidence = similarity_confidence(
            float(sim[idx]),
            score_gap,
            lexical_overlap,
            mutual_neighbor,
            len(shared_tags),
        )
        relation = classify_relation_candidate(core, file_path, paths[idx], float(sim[idx]))["relation"]
        results.append({
            "path": paths[idx],
            "score": round(float(combined_score), 4),
            "semantic_score": round(float(sim[idx]), 4),
            "lexical_score": round(float(lexical_support), 4),
            "score_gap": round(score_gap, 4),
            "confidence": confidence,
            "mutual_neighbor": mutual_neighbor,
            "shared_tags": shared_tags,
            "shared_terms": shared_terms,
            "suggested_relation": relation,
            "why": "Candidate semantic link. Stronger when mutual, separated from the local baseline, and supported by tags/terms.",
            "snippet": get_snippet(core, paths[idx], 150),
        })
        if len(results) >= top_k:
            break

    return results


async def create_profile(
    core,
    name: str,
    keywords: str,
    description: str = "",
    parent_profile: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new profile/perspective from keywords."""
    raw, centered = await compute_embeddings(core, [keywords])
    if parent_profile and not core.storage.get_profile(parent_profile):
        return {"error": f"Parent profile '{parent_profile}' not found"}
    core.storage.set_profile(name, keywords, raw[0], centered[0], description, parent_profile)
    return {
        "name": name,
        "keywords": keywords,
        "description": description,
        "parent_profile": parent_profile,
        "status": "created",
    }


def build_context_pack_markdown(core, title: str, query: str, paths: list[str]) -> str:
    lines = [
        f"# Context Pack: {title}",
        "",
        f"Query: {query}",
        "",
        "## Main Notes",
        "",
    ]
    for path in paths:
        meta = core.storage.get_file_metadata(path)
        snippet = ""
        if meta and meta.get("content"):
            snippet = re.sub(r"\s+", " ", meta["content"]).strip()[:280]
        lines.append(f"- [[{Path(path).stem}]]")
        if snippet:
            lines.append(f"  - {snippet}")
    lines.extend([
        "",
        "## Open Questions",
        "",
        "- What decision or output should this context support?",
        "- Which notes are evidence, and which are speculation?",
        "- What is missing before handing this to an AI agent?",
    ])
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "build_context_pack_markdown",
    "calibrate_embeddings",
    "classify_relation_candidate",
    "compute_embeddings",
    "create_profile",
    "embedding_index_status",
    "embedding_signature",
    "file_features",
    "get_profile_vector",
    "get_snippet",
    "index_single_file",
    "index_vault",
    "lexical_score",
    "load_or_compute_corpus_mean",
    "pairwise_stats",
    "rebuild_bridges",
    "recenter_profiles",
    "recompute_corpus_mean_and_recenter_index",
    "search",
    "similarity_confidence",
    "suggest_links",
    "vault_sync_status",
]
