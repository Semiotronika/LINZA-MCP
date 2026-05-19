import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .utils import (
    normalize_note_name,
    COMMON_TAG_HINTS, DOMAIN_NOISE_TERMS, DOMAIN_TITLE_NOISE,
    STOPWORDS, TECHNICAL_TAG_NOISE,
)


def smooth_capped_idf(doc_freq: int, total_docs: int, cap: float = 3.5) -> float:
    """Legacy-compatible smooth capped IDF for draft map term scoring."""
    total = max(1, int(total_docs))
    df = min(total, max(0, int(doc_freq)))
    return min(cap, 1.0 + math.log((total + 1) / (df + 1)))


def token_weight(token: str, global_doc_counts: Optional[Counter[str]], total_docs: Optional[int]) -> float:
    if not global_doc_counts or not total_docs:
        return 1.0
    return smooth_capped_idf(global_doc_counts.get(token, 0), total_docs)


def record_similarity(
    left: dict[str, Any],
    right: dict[str, Any],
    global_doc_counts: Optional[Counter[str]] = None,
    total_docs: Optional[int] = None,
) -> float:
    """Score draft records using IDF-weighted lexical overlap plus folder/tag/role support."""
    left_tokens = left["tokens"]
    right_tokens = right["tokens"]
    if not left_tokens or not right_tokens:
        base = 0.0
    elif global_doc_counts and total_docs:
        shared = left_tokens & right_tokens
        shared_weight = sum(token_weight(token, global_doc_counts, total_docs) ** 2 for token in shared)
        left_norm = math.sqrt(sum(token_weight(token, global_doc_counts, total_docs) ** 2 for token in left_tokens))
        right_norm = math.sqrt(sum(token_weight(token, global_doc_counts, total_docs) ** 2 for token in right_tokens))
        denom = left_norm * right_norm or 1.0
        base = shared_weight / denom
    else:
        overlap = len(left_tokens & right_tokens)
        denom = math.sqrt(len(left_tokens) * len(right_tokens)) or 1.0
        base = overlap / denom

    if left.get("folder") and left.get("folder") == right.get("folder"):
        base += 0.25
    shared_tags = len(set(left.get("tags", [])) & set(right.get("tags", [])))
    base += min(0.2, shared_tags * 0.08)
    if left.get("role") == right.get("role") and left.get("role") not in {"note", "artifact"}:
        base += 0.04
    return round(min(1.0, base), 4)


def domain_terms(
    records: list[dict[str, Any]],
    global_doc_counts: Counter[str],
    total_docs: Optional[int] = None,
) -> list[str]:
    """Pick stable representative domain terms without letting one-off rare terms dominate."""
    term_scores: Counter[str] = Counter()
    total = total_docs or max(global_doc_counts.values(), default=len(records))
    for record in records:
        for token in record["tokens"]:
            if token in COMMON_TAG_HINTS or token in TECHNICAL_TAG_NOISE or token in DOMAIN_NOISE_TERMS or token in STOPWORDS:
                continue
            if len(token) < 4 or token.isdigit():
                continue
            term_scores[token] += smooth_capped_idf(global_doc_counts[token], total)
    return [
        term
        for term, _ in sorted(term_scores.items(), key=lambda item: (-item[1], item[0]))[:12]
    ]


def dedupe_draft_domain_names(domains: list[dict[str, Any]]) -> None:
    """Choose unique human display names for draft domains in place."""
    used: set[str] = set()
    for domain in domains:
        candidates = list(domain.get("name_candidates", []))
        if not candidates:
            candidates = [{"label": domain.get("display_name") or domain.get("name") or domain["id"], "reason": "current name"}]

        chosen = None
        primary = candidates[0]["label"]
        primary_key = normalize_note_name(primary)
        if primary_key and primary_key not in used:
            chosen = primary
        else:
            folder = ""
            for folder_item in domain.get("folders", []):
                folder_value = folder_item[0] if isinstance(folder_item, (list, tuple)) and folder_item else ""
                if folder_value and folder_value != "(root)":
                    folder = Path(str(folder_value)).name.replace("_", " ").replace("-", " ")
                    break
            if folder:
                suffix_name = f"{primary} ({folder})"
                if normalize_note_name(suffix_name) not in used:
                    chosen = suffix_name

        if chosen is None:
            for candidate in candidates[1:]:
                key = normalize_note_name(candidate.get("label", ""))
                if key and key not in used:
                    chosen = candidate["label"]
                    break

        if chosen is None:
            base = candidates[0]["label"]
            chosen = f"{base} {domain['id']}"

        domain["display_name"] = chosen
        domain["name"] = chosen
        used.add(normalize_note_name(chosen))


def vector_cosine(left: Optional[list[float]], right: Optional[list[float]]) -> Optional[float]:
    if left is None or right is None:
        return None
    left_arr = np.array(left, dtype=float)
    right_arr = np.array(right, dtype=float)
    denom = float(np.linalg.norm(left_arr) * np.linalg.norm(right_arr))
    if denom <= 1e-9:
        return None
    return float(np.dot(left_arr, right_arr) / denom)


def draft_record_text(record: dict[str, Any]) -> str:
    chunk_text = " ".join(chunk["text"][:700] for chunk in record.get("chunks", [])[:6])
    return "\n".join([
        record.get("title", ""),
        record.get("folder", ""),
        " ".join(record.get("tags", [])),
        " ".join(record.get("headings", [])),
        chunk_text,
    ])


def domain_centroid(domain: dict[str, Any], by_path: dict[str, dict[str, Any]]) -> Optional[list[float]]:
    vectors = [
        by_path[path].get("draft_embedding")
        for path in domain.get("member_paths", [])
        if path in by_path and by_path[path].get("draft_embedding") is not None
    ]
    if not vectors:
        return None
    arr = np.array(vectors, dtype=float)
    centroid = np.mean(arr, axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm
    return centroid.tolist()


def domain_name(terms: list[str], folders: Counter[str], roles: Counter[str]) -> str:
    folder = ""
    if folders:
        folder, folder_count = folders.most_common(1)[0]
        if folder and folder != "(root)" and folder_count >= 2:
            folder = Path(folder).name.replace("_", " ").replace("-", " ")
        else:
            folder = ""
    if folder and terms:
        return f"{folder}: {', '.join(terms[:2])}"
    if folder:
        return folder
    if terms:
        return ", ".join(terms[:3])
    if roles:
        return f"{roles.most_common(1)[0][0]} notes"
    return "untitled area"


def label_words(value: str) -> list[tuple[str, str]]:
    words: list[tuple[str, str]] = []
    for raw in re.findall(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9]{2,}", value):
        norm = raw.lower().replace("ё", "е")
        if norm in STOPWORDS or norm in DOMAIN_TITLE_NOISE or norm.isdigit():
            continue
        words.append((norm, raw))
    return words


def domain_name_candidates(
    records: list[dict[str, Any]],
    terms: list[str],
    folders: Counter[str],
    roles: Counter[str],
) -> list[dict[str, str]]:
    word_scores: Counter[str] = Counter()
    phrase_scores: Counter[str] = Counter()
    display: dict[str, str] = {}
    phrase_display: dict[str, str] = {}

    def add_words(pairs: list[tuple[str, str]], weight: int) -> None:
        for norm, raw in pairs:
            word_scores[norm] += weight
            display.setdefault(norm, raw)
        for (left_norm, left_raw), (right_norm, right_raw) in zip(pairs, pairs[1:]):
            phrase_key = f"{left_norm} {right_norm}"
            phrase_scores[phrase_key] += weight + 2
            phrase_display.setdefault(phrase_key, f"{left_raw} {right_raw}")

    for record in records:
        add_words(label_words(record.get("title", "")), 4)
        for heading in record.get("headings", [])[:5]:
            add_words(label_words(str(heading)), 2)
        for tag in record.get("tags", [])[:8]:
            add_words(label_words(str(tag).replace("-", " ")), 2)

    for folder, count in folders.most_common(3):
        if folder and folder != "(root)":
            add_words(label_words(Path(folder).name.replace("-", " ")), min(2, count))

    for term in terms[:8]:
        norm = term.lower().replace("ё", "е")
        if norm not in DOMAIN_TITLE_NOISE and norm not in STOPWORDS:
            word_scores[norm] += 2
            display.setdefault(norm, term)

    candidates: list[dict[str, str]] = []

    def add_candidate(label: str, reason: str) -> None:
        label = re.sub(r"\s+", " ", label).strip(" :-")
        if not label:
            return
        key = normalize_note_name(label)
        if not key or any(normalize_note_name(item["label"]) == key for item in candidates):
            return
        candidates.append({"label": label, "reason": reason})

    if phrase_scores:
        phrase, _ = sorted(
            phrase_scores.items(),
            key=lambda item: (-item[1], item[0]),
        )[0]
        add_candidate(phrase_display[phrase], "title phrase repeated or central in this draft area")

    product_like = [
        norm for norm, _ in sorted(word_scores.items(), key=lambda item: (-item[1], item[0]))
        if display.get(norm, "").isupper() or word_scores[norm] >= 7
    ]
    if product_like:
        head = product_like[0]
        companions = [
            norm for norm, _ in sorted(word_scores.items(), key=lambda item: (-item[1], item[0]))
            if norm != head
        ]
        label = display[head]
        if companions:
            label = f"{label} {display[companions[0]]}"
        add_candidate(label, "shared product/title term with strongest companion")

    for folder, count in folders.most_common(2):
        folder_words = label_words(Path(folder).name.replace("-", " ")) if folder and folder != "(root)" else []
        if folder_words and count >= 2:
            term = next((display[norm] for norm, _ in word_scores.most_common() if norm not in {folder_words[0][0]}), "")
            label = folder_words[0][1] if not term else f"{folder_words[0][1]}: {term}"
            add_candidate(label, "folder name plus strongest local term")

    if word_scores:
        top = [display[norm] for norm, _ in sorted(word_scores.items(), key=lambda item: (-item[1], item[0]))[:2]]
        add_candidate(" ".join(top), "top recurring title/body terms")

    if not candidates and roles:
        add_candidate(f"{roles.most_common(1)[0][0]} notes", "dominant draft role")

    return candidates[:4]


def refresh_draft_domain(
    domain: dict[str, Any],
    by_path: dict[str, dict[str, Any]],
    global_doc_counts: Counter[str],
    pair_scores: dict[tuple[str, str], float],
    total_docs: Optional[int] = None,
) -> None:
    members = [by_path[path] for path in domain.get("member_paths", []) if path in by_path]
    if not members:
        return
    folders = Counter(record["folder"] or "(root)" for record in members)
    roles = Counter(record["role"] for record in members)
    terms = domain_terms(members, global_doc_counts, total_docs=total_docs or len(by_path))
    domain["representative_terms"] = terms[:10]
    domain["folders"] = folders.most_common(5)
    domain["roles"] = roles.most_common()
    domain.setdefault("technical_name", domain.get("name", "untitled area"))
    name_candidates = domain_name_candidates(members, terms, folders, roles)
    if name_candidates:
        domain["display_name"] = name_candidates[0]["label"]
        domain["name"] = domain["display_name"]
        domain["name_candidates"] = name_candidates
    scored_members = []
    for record in members:
        others = [other for other in members if other["path"] != record["path"]]
        if others:
            score = sum(pair_scores.get((record["path"], other["path"]), 0.0) for other in others) / len(others)
        else:
            score = 1.0
        scored_members.append((record, score))
    domain["score"] = round(sum(score for _, score in scored_members) / max(1, len(scored_members)), 3)
    domain["representative_notes"] = [
        {
            "path": record["path"],
            "title": record["title"],
            "role": record["role"],
            "score": round(score, 3),
        }
        for record, score in sorted(scored_members, key=lambda item: (-item[1], item[0]["path"]))[:8]
    ]


def merge_draft_domains(
    domains: list[dict[str, Any]],
    by_path: dict[str, dict[str, Any]],
    global_doc_counts: Counter[str],
    pair_scores: dict[tuple[str, str], float],
    max_domains: int,
) -> tuple[list[dict[str, Any]], int]:
    kept: list[dict[str, Any]] = []
    merged_count = 0

    for domain in domains:
        target: Optional[dict[str, Any]] = None
        best_evidence: dict[str, Any] = {}
        domain_paths = set(domain.get("member_paths", []))
        domain_terms_set = set(domain.get("representative_terms", []))
        current_centroid = domain_centroid(domain, by_path)

        for existing in kept:
            existing_paths = set(existing.get("member_paths", []))
            existing_terms = set(existing.get("representative_terms", []))
            path_overlap = len(domain_paths & existing_paths) / max(1, len(domain_paths | existing_paths))
            term_overlap = len(domain_terms_set & existing_terms) / max(1, len(domain_terms_set | existing_terms))
            embedding_similarity = vector_cosine(current_centroid, domain_centroid(existing, by_path))
            emb = embedding_similarity if embedding_similarity is not None else 0.0
            domain_top_folders = {path.split("/", 1)[0] for path in domain_paths if "/" in path}
            existing_top_folders = {path.split("/", 1)[0] for path in existing_paths if "/" in path}
            same_top_folder = bool(domain_top_folders & existing_top_folders)
            should_merge = (
                path_overlap >= 0.42
                or (emb >= 0.62 and (term_overlap >= 0.18 or same_top_folder))
                or (emb >= 0.42 and term_overlap >= 0.28)
            )
            if should_merge:
                target = existing
                best_evidence = {
                    "candidate": domain["name"],
                    "member_overlap": round(path_overlap, 3),
                    "term_overlap": round(term_overlap, 3),
                    "embedding_similarity": round(emb, 3),
                }
                break

        if target is None:
            domain.setdefault("merged_from", [])
            domain.setdefault("merge_evidence", [])
            kept.append(domain)
            continue

        target["member_paths"] = sorted(set(target.get("member_paths", [])) | domain_paths)
        target.setdefault("merged_from", []).append(domain["name"])
        target.setdefault("merge_evidence", []).append(best_evidence)
        target["confidence"] = "medium"
        target["why"] = "Merged from overlapping draft areas using member overlap, terms, and embedding centroid similarity."
        refresh_draft_domain(target, by_path, global_doc_counts, pair_scores)
        merged_count += 1

    return kept[:max_domains], merged_count


__all__ = [
    "dedupe_draft_domain_names",
    "domain_centroid",
    "domain_name",
    "domain_name_candidates",
    "domain_terms",
    "draft_record_text",
    "label_words",
    "merge_draft_domains",
    "record_similarity",
    "refresh_draft_domain",
    "smooth_capped_idf",
    "token_weight",
    "vector_cosine",
]
