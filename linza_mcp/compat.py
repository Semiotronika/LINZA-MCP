"""Compatibility layer for the public LINZA core API."""

from pathlib import Path
from typing import Any

from .chunker import split_semantic_chunks as chunk_markdown
from .diagnostics import build_bases_plan_markdown as build_bases_plan_markdown_from_module
from .diagnostics import build_diagnostic_markdown as build_diagnostic_markdown_from_module
from .diagnostics import build_review_queue_markdown as build_review_queue_markdown_from_module
from .diagnostics import build_semantic_links_markdown as build_semantic_links_markdown_from_module
from .diagnostics import build_yaml_suggestions_markdown as build_yaml_suggestions_markdown_from_module
from .diagnostics import explain_relationship as explain_relationship_from_module
from .diagnostics import scan_vault as scan_vault_from_module
from .diagnostics import suggest_properties_for_note as suggest_properties_for_note_from_module
from .domains import dedupe_draft_domain_names as dedupe_draft_domain_names_from_module
from .domains import domain_centroid as domain_centroid_from_module
from .domains import domain_name as domain_name_from_module
from .domains import domain_name_candidates as domain_name_candidates_from_module
from .domains import domain_terms as domain_terms_from_module
from .domains import draft_record_text as draft_record_text_from_module
from .domains import label_words as label_words_from_module
from .domains import merge_draft_domains as merge_draft_domains_from_module
from .domains import record_similarity as record_similarity_from_module
from .domains import refresh_draft_domain as refresh_draft_domain_from_module
from .domains import smooth_capped_idf as smooth_capped_idf_from_module
from .domains import token_weight as token_weight_from_module
from .domains import vector_cosine as vector_cosine_from_module
from .draft_map import build_event_flow_draft as build_event_flow_draft_from_module
from .draft_map import build_lens_suggestions as build_lens_suggestions_from_module
from .draft_map import build_memory_draft as build_memory_draft_from_module
from .draft_map import build_role_draft as build_role_draft_from_module
from .draft_map import draft_vault_map as draft_vault_map_from_module
from .draft_map import event_relation as event_relation_from_module
from .draft_map import event_time_hint as event_time_hint_from_module
from .draft_map import group_records_by_role_or_folder as group_records_by_role_or_folder_from_module
from .draft_map import memory_signals as memory_signals_from_module
from .draft_map import parent_score as parent_score_from_module
from .draft_map import percentile as percentile_from_module
from .draft_map import preview_text as preview_text_from_module
from .draft_map import public_role as public_role_from_module
from .draft_map import record_memory_type as record_memory_type_from_module
from .draft_map import role_confidence as role_confidence_from_module
from .draft_map import select_draft_notes as select_draft_notes_from_module
from .draft_map import split_event_sentences as split_event_sentences_from_module
from .embed import MeanCenteredEmbeddings
from .graph import check_rule as check_rule_from_module
from .graph import explain_node as explain_node_from_module
from .graph import read_note_index as read_note_index_from_module
from .graph import show_flow as show_flow_from_module
from .graph import who_depends as who_depends_from_module
from .indexing import build_context_pack_markdown as build_context_pack_markdown_from_module
from .indexing import calibrate_embeddings as calibrate_embeddings_from_module
from .indexing import classify_relation_candidate as classify_relation_candidate_from_module
from .indexing import compute_embeddings as compute_embeddings_from_module
from .indexing import create_profile as create_profile_from_module
from .indexing import file_features as file_features_from_module
from .indexing import get_profile_vector as get_profile_vector_from_module
from .indexing import get_snippet as get_snippet_from_module
from .indexing import index_single_file as index_single_file_from_module
from .indexing import index_vault as index_vault_from_module
from .indexing import lexical_score as lexical_score_from_module
from .indexing import load_or_compute_corpus_mean as load_or_compute_corpus_mean_from_module
from .indexing import pairwise_stats as pairwise_stats_from_module
from .indexing import rebuild_bridges as rebuild_bridges_from_module
from .indexing import recompute_corpus_mean_and_recenter_index as recompute_corpus_mean_from_module
from .indexing import search as search_from_module
from .indexing import similarity_confidence as similarity_confidence_from_module
from .indexing import suggest_links as suggest_links_from_module
from .operator import guide_next_steps as guide_next_steps_from_module
from .properties import patch_note_properties as patch_note_properties_from_module
from .review_queue import approve_draft_item as approve_draft_item_from_module
from .review_queue import approve_review_queue_items as approve_review_queue_items_from_module
from .review_queue import apply_learned_review_queue as apply_learned_review_queue_from_module
from .review_queue import build_review_apply_queue as build_review_apply_queue_from_module
from .storage import LINZA_SCHEMA_VERSION, LinzaStorage, Storage
from .tags import audit_tag_vocabulary as audit_tag_vocabulary_from_module
from .tags import build_tag_vocabulary_markdown as build_tag_vocabulary_markdown_from_module
from .tags import suggest_tag_candidates as suggest_tag_candidates_from_module
from .tags import yaml_tag_vocabulary as yaml_tag_vocabulary_from_module
from .workflows import agent_workspace as agent_workspace_from_module
from .roles import guess_note_role, material_type_vocabulary
from .utils import (
    FRONTMATTER_RE,
    IGNORED_DIRS,
    LINZA_EVENT_PATTERNS,
    WIKILINK_RE,
    extract_tag_details,
    extract_tags,
    extract_wikilinks,
    format_yaml_block,
    is_legacy_graph_metadata,
    normalize_tag,
    parse_frontmatter,
    patch_frontmatter,
    strip_frontmatter,
    tokenize,
)


__version__ = "0.1.3"


class LinzaCore:
    """Core wrapper accepting both legacy and new constructor shapes."""

    def __init__(self, *args: Any, **kwargs: Any):
        config = kwargs.pop("config", None)
        if len(args) >= 3 and isinstance(args[0], (str, Path)):
            vault_path = Path(args[0])
            storage = args[1]
            embed_provider = args[2]
            storage.vault_path = vault_path
            if len(args) > 3:
                config = args[3]
        elif len(args) >= 2:
            storage = args[0]
            embed_provider = args[1]
            if len(args) > 2:
                config = args[2]
        else:
            storage = kwargs.pop("storage")
            embed_provider = kwargs.pop("embed_provider")

        if kwargs:
            unexpected = ", ".join(sorted(kwargs.keys()))
            raise TypeError(f"Unexpected LinzaCore arguments: {unexpected}")

        if hasattr(embed_provider, "provider") and not hasattr(embed_provider, "embed"):
            embed_provider = embed_provider.provider
        self.storage = storage
        self.embed = embed_provider
        self.config = config or {}
        self.centerer = MeanCenteredEmbeddings()
        self._load_or_compute_corpus_mean()

    async def index_vault(self, force: bool = False, with_embeddings: bool = True):
        if not with_embeddings:
            return {"status": "skipped", "with_embeddings": False}
        return await index_vault_from_module(self, force=force)

    async def index_single_file(self, path: str, content: str | None = None):
        return await index_single_file_from_module(self, path, content=content)

    async def rebuild_bridges(self, threshold: float | None = None):
        return await rebuild_bridges_from_module(self, threshold=threshold)

    def _load_or_compute_corpus_mean(self):
        return load_or_compute_corpus_mean_from_module(self)

    async def _compute_embeddings(self, texts: list[str]):
        return await compute_embeddings_from_module(self, texts)

    def _recompute_corpus_mean_and_recenter_index(self):
        return recompute_corpus_mean_from_module(self)

    def _get_profile_vector(self, profile_name: str):
        return get_profile_vector_from_module(self, profile_name)

    @staticmethod
    def _pairwise_stats(vectors: list[list[float]]) -> dict[str, Any]:
        return pairwise_stats_from_module(vectors)

    def calibrate_embeddings(self) -> dict[str, Any]:
        return calibrate_embeddings_from_module(self)

    @staticmethod
    def _lexical_score(query: str, content: str):
        return lexical_score_from_module(query, content)

    def _similarity_confidence(
        self,
        semantic_score: float,
        score_gap: float,
        lexical_overlap: int,
        mutual_neighbor: bool,
        shared_tags: int = 0,
    ) -> str:
        return similarity_confidence_from_module(
            semantic_score,
            score_gap,
            lexical_overlap,
            mutual_neighbor,
            shared_tags=shared_tags,
        )

    def classify_relation_candidate(self, source: str, target: str, score: float) -> dict[str, Any]:
        return classify_relation_candidate_from_module(self, source, target, score)

    def _file_features(self, path: str) -> dict[str, Any]:
        return file_features_from_module(self, path)

    async def search(
        self,
        query: str,
        profile_name: str | None = None,
        top_k: int = 5,
        explain: bool = False,
    ) -> dict[str, Any]:
        return await search_from_module(
            self,
            query,
            profile_name=profile_name,
            top_k=top_k,
            explain=explain,
        )

    def _get_snippet(self, path: str, max_len: int = 200) -> str:
        return get_snippet_from_module(self, path, max_len=max_len)

    def _explain_search(self, query: str, profile_name: str, results: list[dict], sim, top_indices=None) -> str:
        from .indexing import explain_search

        return explain_search(self, query, profile_name, results, sim)

    async def suggest_links(
        self,
        file_path: str,
        profile_name: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        return await suggest_links_from_module(
            self,
            file_path,
            profile_name=profile_name,
            top_k=top_k,
        )

    async def create_profile(
        self,
        name: str,
        keywords: str,
        description: str = "",
        parent_profile: str | None = None,
    ) -> dict[str, Any]:
        return await create_profile_from_module(
            self,
            name,
            keywords,
            description=description,
            parent_profile=parent_profile,
        )

    def build_context_pack_markdown(self, title: str, query: str, paths: list[str]) -> str:
        return build_context_pack_markdown_from_module(self, title, query, paths)

    @staticmethod
    def _smooth_capped_idf(doc_freq: int, total_docs: int, cap: float = 3.5) -> float:
        return smooth_capped_idf_from_module(doc_freq, total_docs, cap=cap)

    @staticmethod
    def _token_weight(token: str, global_doc_counts, total_docs) -> float:
        return token_weight_from_module(token, global_doc_counts, total_docs)

    @staticmethod
    def _record_similarity(left: dict[str, Any], right: dict[str, Any], global_doc_counts=None, total_docs=None) -> float:
        return record_similarity_from_module(left, right, global_doc_counts, total_docs)

    @staticmethod
    def _domain_terms(records: list[dict[str, Any]], global_doc_counts, total_docs=None) -> list[str]:
        return domain_terms_from_module(records, global_doc_counts, total_docs=total_docs)

    @staticmethod
    def _dedupe_draft_domain_names(domains: list[dict[str, Any]]) -> None:
        return dedupe_draft_domain_names_from_module(domains)

    @staticmethod
    def _vector_cosine(left: list[float] | None, right: list[float] | None) -> float | None:
        return vector_cosine_from_module(left, right)

    @staticmethod
    def _draft_record_text(record: dict[str, Any]) -> str:
        return draft_record_text_from_module(record)

    @staticmethod
    def _domain_centroid(domain: dict[str, Any], by_path: dict[str, dict[str, Any]]) -> list[float] | None:
        return domain_centroid_from_module(domain, by_path)

    def _refresh_draft_domain(
        self,
        domain: dict[str, Any],
        by_path: dict[str, dict[str, Any]],
        global_doc_counts,
        pair_scores: dict[tuple[str, str], float],
        total_docs: int | None = None,
    ) -> None:
        return refresh_draft_domain_from_module(
            domain,
            by_path,
            global_doc_counts,
            pair_scores,
            total_docs=total_docs,
        )

    def _merge_draft_domains(
        self,
        domains: list[dict[str, Any]],
        by_path: dict[str, dict[str, Any]],
        global_doc_counts,
        pair_scores: dict[tuple[str, str], float],
        max_domains: int,
    ) -> tuple[list[dict[str, Any]], int]:
        return merge_draft_domains_from_module(
            domains,
            by_path,
            global_doc_counts,
            pair_scores,
            max_domains,
        )

    @staticmethod
    def _percentile(values: list[float], percentile: float, fallback: float) -> float:
        return percentile_from_module(values, percentile, fallback)

    @staticmethod
    def _domain_name(terms: list[str], folders, roles) -> str:
        return domain_name_from_module(terms, folders, roles)

    @staticmethod
    def _label_words(value: str) -> list[tuple[str, str]]:
        return label_words_from_module(value)

    @staticmethod
    def _domain_name_candidates(
        records: list[dict[str, Any]],
        terms: list[str],
        folders,
        roles,
    ) -> list[dict[str, str]]:
        return domain_name_candidates_from_module(records, terms, folders, roles)

    @staticmethod
    def _parent_score(record: dict[str, Any], incoming: dict[str, list[str]], outgoing: dict[str, list[str]]) -> float:
        return parent_score_from_module(record, incoming, outgoing)

    @staticmethod
    def _select_draft_notes(notes: list[dict[str, Any]], max_notes: int) -> list[dict[str, Any]]:
        return select_draft_notes_from_module(notes, max_notes)

    @staticmethod
    def _group_records_by_role_or_folder(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        return group_records_by_role_or_folder_from_module(records)

    @staticmethod
    def _public_role(role: str) -> str:
        return public_role_from_module(role)

    @staticmethod
    def _role_confidence(record: dict[str, Any]) -> str:
        return role_confidence_from_module(record)

    def _build_role_draft(self, records: list[dict[str, Any]], assigned_to: dict[str, list[str]]) -> dict[str, Any]:
        return build_role_draft_from_module(records, assigned_to)

    @staticmethod
    def _preview_text(text: str, limit: int = 180) -> str:
        return preview_text_from_module(text, limit=limit)

    @staticmethod
    def _split_event_sentences(text: str) -> list[str]:
        return split_event_sentences_from_module(text)

    @staticmethod
    def _event_time_hint(value: str) -> str | None:
        return event_time_hint_from_module(value)

    @staticmethod
    def _event_relation(left_type: str, right_type: str) -> str | None:
        return event_relation_from_module(left_type, right_type)

    def _build_event_flow_draft(
        self,
        records: list[dict[str, Any]],
        assigned_to: dict[str, list[str]],
        limit: int = 50,
    ) -> dict[str, Any]:
        return build_event_flow_draft_from_module(records, assigned_to, limit=limit)

    @staticmethod
    def _memory_signals(text: str, role: str = "", event_type: str = "") -> list[str]:
        return memory_signals_from_module(text, role=role, event_type=event_type)

    @staticmethod
    def _record_memory_type(record: dict[str, Any], body: str) -> str | None:
        return record_memory_type_from_module(record, body)

    def _build_memory_draft(
        self,
        records: list[dict[str, Any]],
        event_flow_draft: dict[str, Any],
        review_queue: list[dict[str, Any]],
        limit: int = 40,
    ) -> dict[str, Any]:
        return build_memory_draft_from_module(records, event_flow_draft, review_queue, limit=limit)

    @staticmethod
    def _build_lens_suggestions(
        domains: list[dict[str, Any]],
        role_draft: dict[str, Any],
        event_flow_draft: dict[str, Any],
        memory_draft: dict[str, Any],
        review_queue: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return build_lens_suggestions_from_module(domains, role_draft, event_flow_draft, memory_draft, review_queue)

    def _read_note_index(self) -> dict[str, Any]:
        return read_note_index_from_module(self)

    async def draft_vault_map(
        self,
        max_notes: int = 120,
        max_domains: int = 8,
        max_chunks_per_note: int = 12,
        use_embedding_second_pass: bool = True,
        analysis_stage: str = "all",
    ) -> dict[str, Any]:
        return await draft_vault_map_from_module(
            self,
            max_notes=max_notes,
            max_domains=max_domains,
            max_chunks_per_note=max_chunks_per_note,
            use_embedding_second_pass=use_embedding_second_pass,
            analysis_stage=analysis_stage,
        )

    def explain_node(self, path: str) -> dict[str, Any]:
        return explain_node_from_module(self, path)

    def who_depends(self, path: str, depth: int = 1) -> dict[str, Any]:
        return who_depends_from_module(self, path, depth=depth)

    async def show_flow(
        self,
        source: str | None = None,
        target: str | None = None,
        query: str | None = None,
        profile_name: str | None = None,
        top_k: int = 8,
        max_depth: int = 4,
    ) -> dict[str, Any]:
        return await show_flow_from_module(
            self,
            source=source,
            target=target,
            query=query,
            profile_name=profile_name,
            top_k=top_k,
            max_depth=max_depth,
        )

    def check_rule(self, rule: str = "all", path: str | None = None) -> dict[str, Any]:
        return check_rule_from_module(self, rule=rule, path=path)

    def scan_vault(self) -> dict[str, Any]:
        return scan_vault_from_module(self)

    def build_review_queue_markdown(self, limit: int = 30) -> str:
        return build_review_queue_markdown_from_module(self, limit=limit)

    def build_diagnostic_markdown(self) -> str:
        return build_diagnostic_markdown_from_module(self)

    def build_semantic_links_markdown(self, limit: int = 50) -> str:
        return build_semantic_links_markdown_from_module(self, limit=limit)

    def explain_relationship(self, source: str, target: str) -> dict[str, Any]:
        return explain_relationship_from_module(self, source, target)

    def build_bases_plan_markdown(self) -> str:
        return build_bases_plan_markdown_from_module(self)

    def suggest_properties_for_note(self, path: str) -> dict[str, Any]:
        return suggest_properties_for_note_from_module(self, path)

    def build_yaml_suggestions_markdown(self, limit: int = 50) -> str:
        return build_yaml_suggestions_markdown_from_module(self, limit=limit)

    def patch_note_properties(
        self,
        path: str,
        properties: dict[str, Any],
        dry_run: bool = True,
        allow_overwrite: bool = False,
        namespace: str = "linza",
    ) -> dict[str, Any]:
        return patch_note_properties_from_module(
            self,
            path=path,
            properties=properties,
            dry_run=dry_run,
            allow_overwrite=allow_overwrite,
            namespace=namespace,
        )

    def _yaml_tag_vocabulary(self) -> dict[str, dict[str, Any]]:
        return yaml_tag_vocabulary_from_module(self)

    def suggest_tag_candidates(
        self,
        path: str,
        max_candidates: int = 20,
        include_new: bool = True,
    ) -> dict[str, Any]:
        return suggest_tag_candidates_from_module(
            self,
            path=path,
            max_candidates=max_candidates,
            include_new=include_new,
        )

    def audit_tag_vocabulary(self) -> dict[str, Any]:
        return audit_tag_vocabulary_from_module(self)

    def build_tag_vocabulary_markdown(self) -> str:
        return build_tag_vocabulary_markdown_from_module(self)

    async def build_review_apply_queue(
        self,
        max_notes: int = 120,
        max_domains: int = 8,
        limit: int = 40,
        redact: bool = False,
        include_memory: bool = False,
        analysis_stage: str = "all",
    ) -> dict[str, Any]:
        return await build_review_apply_queue_from_module(
            self,
            max_notes=max_notes,
            max_domains=max_domains,
            limit=limit,
            redact=redact,
            include_memory=include_memory,
            analysis_stage=analysis_stage,
        )

    def approve_draft_item(
        self,
        item_type: str,
        dry_run: bool = True,
        allow_overwrite: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return approve_draft_item_from_module(
            self,
            item_type=item_type,
            dry_run=dry_run,
            allow_overwrite=allow_overwrite,
            **kwargs,
        )

    async def approve_review_queue_items(
        self,
        item_ids: list[str],
        max_notes: int = 120,
        max_domains: int = 8,
        limit: int = 40,
        dry_run: bool = True,
        allow_overwrite: bool = False,
        include_memory: bool = False,
    ) -> dict[str, Any]:
        return await approve_review_queue_items_from_module(
            self,
            item_ids=item_ids,
            max_notes=max_notes,
            max_domains=max_domains,
            limit=limit,
            dry_run=dry_run,
            allow_overwrite=allow_overwrite,
            include_memory=include_memory,
        )

    async def apply_learned_review_queue(
        self,
        mode: str = "review",
        max_notes: int = 120,
        max_domains: int = 8,
        limit: int = 40,
        dry_run: bool = True,
        allow_overwrite: bool = False,
        include_memory: bool = False,
    ) -> dict[str, Any]:
        return await apply_learned_review_queue_from_module(
            self,
            mode=mode,
            max_notes=max_notes,
            max_domains=max_domains,
            limit=limit,
            dry_run=dry_run,
            allow_overwrite=allow_overwrite,
            include_memory=include_memory,
        )

    async def guide_next_steps(
        self,
        max_notes: int = 120,
        max_domains: int = 8,
        limit: int = 40,
        include_memory: bool = False,
        include_tool_guide: bool = False,
        language: str = "auto",
    ) -> dict[str, Any]:
        return await guide_next_steps_from_module(
            self,
            max_notes=max_notes,
            max_domains=max_domains,
            limit=limit,
            include_memory=include_memory,
            include_tool_guide=include_tool_guide,
            language=language,
        )

    async def agent_workspace(
        self,
        action: str,
        artifacts: list[dict[str, Any]] | None = None,
        source_kind: str = "",
        batch_id: str = "",
        privacy: str = "private",
        kind: str = "all",
        item_ids: list[str] | None = None,
        dry_run: bool = True,
        query: str = "",
        trace: dict[str, Any] | None = None,
        trace_id: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await agent_workspace_from_module(
            self,
            action=action,
            artifacts=artifacts,
            source_kind=source_kind,
            batch_id=batch_id,
            privacy=privacy,
            kind=kind,
            item_ids=item_ids,
            dry_run=dry_run,
            query=query,
            trace=trace,
            trace_id=trace_id,
            limit=limit,
            **kwargs,
        )

def extract_events(text: str, chunk_id: str = "", heading: str = "") -> list[dict[str, Any]]:
    core = object.__new__(LinzaCore)
    record = {
        "path": "",
        "title": "",
        "role": "note",
        "chunks": [{"chunk_id": chunk_id, "heading": heading, "text": text}],
    }
    draft = LinzaCore._build_event_flow_draft(core, [record], {})
    return list(draft.get("events", []))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def content_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
