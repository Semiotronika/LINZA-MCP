"""MCP server surface for LINZA."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict

import anyio
from mcp.server import Server
import mcp.server.stdio
from mcp.server.models import InitializationOptions
from mcp.types import CallToolResult, TextContent, Tool

from .compat import __version__, LinzaCore
from .embed import (
    EmbeddingProvider,
    LMStudioProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    get_embedding_provider,
)
from .operator import DEFAULT_MCP_TOOLS
from .storage import LinzaStorage


REPORT_DEFAULTS = {
    "diagnostic": ".linza/reports/00 Vault Diagnostic.md",
    "review_queue": ".linza/reports/01 Review Queue.md",
    "bases_plan": ".linza/reports/02 Bases Plan.md",
    "semantic_links": ".linza/reports/03 Semantic Links.md",
    "yaml_suggestions": ".linza/reports/04 YAML Suggestions.md",
    "tag_vocabulary": ".linza/reports/05 Tag Vocabulary Audit.md",
    "review_apply_queue": ".linza/reports/06 Review Apply Queue.md",
}


def _json_result(payload: Any) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))])


def _text_result(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)])


def _error_result(text: str) -> CallToolResult:
    return CallToolResult(is_error=True, content=[TextContent(type="text", text=text)])


def _vault_path(vault: Path, value: str) -> tuple[str, Path]:
    rel = str(value or "").replace("\\", "/").strip("/")
    path = Path(rel)
    if not rel or path.is_absolute() or path.drive or ".." in path.parts:
        raise ValueError("Path must be vault-relative and stay inside the vault")
    return rel, vault / rel


def _is_under_rel_prefix(rel: str, prefix: str) -> bool:
    normalized = rel.replace("\\", "/").strip("/")
    normalized_prefix = prefix.replace("\\", "/").strip("/")
    return normalized == normalized_prefix or normalized.startswith(f"{normalized_prefix}/")


def _generated_output_target(
    vault: Path,
    value: str,
    default_path: str,
    required_prefix: str,
    label: str,
) -> tuple[str, Path | None, dict[str, Any] | None]:
    rel, full_path = _vault_path(vault, value or default_path)
    if not _is_under_rel_prefix(rel, required_prefix):
        return rel, None, {
            "status": "blocked",
            "path": rel,
            "reason": f"{label} writes are restricted to {required_prefix}",
            "dry_run": True,
        }
    return rel, full_path, None


def _optional_vault_rel(vault: Path, value: Any) -> str:
    if not str(value or "").strip():
        return ""
    return _vault_path(vault, str(value))[0]


def _vault_rel_list(vault: Path, values: Any) -> list[str]:
    raw_values = [values] if isinstance(values, str) else (values or [])
    return [
        _optional_vault_rel(vault, value)
        for value in raw_values
        if str(value or "").strip()
    ]


def _write_text_exact(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)


def _tool(
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> Tool:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
    }
    if required:
        schema["required"] = required
    return Tool(name=name, description=description, inputSchema=schema)


class LinzaMCPServer:
    def __init__(self, vault_path: Path, embed_provider: EmbeddingProvider, config: Dict[str, Any]):
        self.vault_path = Path(vault_path)
        self.embed_provider = embed_provider
        self.config = config
        db_path = self.vault_path / ".linza" / "linza.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage = LinzaStorage(self.vault_path, db_path)
        self.core = LinzaCore(self.vault_path, self.storage, embed_provider, config)
        self.server = Server("linza-mcp")
        self._register_tools()

    def _register_tools(self) -> None:
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            tools = [
                _tool("index_all", "Full reindex of the vault.", {"force": {"type": "boolean"}}),
                _tool("index_file", "Incremental index of one file.", {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                }, ["path"]),
                _tool("search", "Semantic search across notes.", {
                    "query": {"type": "string"},
                    "profile": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                    "explain": {"type": "boolean", "default": False},
                }, ["query"]),
                _tool("suggest_links", "Suggest semantically similar notes for a file.", {
                    "path": {"type": "string"},
                    "profile": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                }, ["path"]),
                _tool("create_profile", "Create a profile/perspective from keywords.", {
                    "name": {"type": "string"},
                    "keywords": {"type": "string"},
                    "description": {"type": "string"},
                    "parent_profile": {"type": "string"},
                }, ["name", "keywords"]),
                _tool("list_profiles", "List profiles."),
                _tool("switch_profile", "Set active default profile.", {"name": {"type": "string"}}, ["name"]),
                _tool("get_profile", "Get profile details.", {"name": {"type": "string"}}, ["name"]),
                _tool("read_file", "Read a note.", {"path": {"type": "string"}}, ["path"]),
                _tool("write_file", "Create or explicitly overwrite a Markdown note. Dry-run by default.", {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "dry_run": {"type": "boolean", "default": True},
                    "allow_overwrite": {"type": "boolean", "default": False},
                }, ["path", "content"]),
                _tool("get_bridges", "Get semantic bridges for a note.", {"path": {"type": "string"}}, ["path"]),
                _tool("get_stats", "Get LINZA sidecar stats."),
                _tool("calibrate_embeddings", "Report embedding calibration and anisotropy diagnostics."),
                _tool("scan_vault", "Read-only vault diagnostic."),
                _tool("draft_vault_map", "Read-only first-pass LINZA map for a raw vault.", {
                    "max_notes": {"type": "integer", "default": 120},
                    "max_domains": {"type": "integer", "default": 8},
                    "max_chunks_per_note": {"type": "integer", "default": 12},
                    "use_embedding_second_pass": {"type": "boolean", "default": True},
                    "analysis_stage": {"type": "string", "default": "all"},
                }),
                _tool("audit_tags", "Read-only tag vocabulary audit."),
                _tool("suggest_tag_candidates", "Read-only tag candidates for one note.", {
                    "path": {"type": "string"},
                    "max_candidates": {"type": "integer", "default": 20},
                    "include_new": {"type": "boolean", "default": True},
                }, ["path"]),
                _tool("suggest_properties", "Suggest compact human-facing YAML for one note.", {"path": {"type": "string"}}, ["path"]),
                _tool("patch_properties", "Safely patch compact YAML/frontmatter for one note. Dry-run by default.", {
                    "path": {"type": "string"},
                    "properties": {"type": "object"},
                    "dry_run": {"type": "boolean", "default": True},
                    "allow_overwrite": {"type": "boolean", "default": False},
                    "namespace": {"type": "string", "default": "linza"},
                }, ["path", "properties"]),
                _tool("approve_draft_item", "Approve/apply one LINZA draft item. Dry-run by default.", {
                    "item_type": {"type": "string"},
                    "dry_run": {"type": "boolean", "default": True},
                    "allow_overwrite": {"type": "boolean", "default": False},
                    "path": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "parent_path": {"type": "string"},
                    "child_paths": {"type": "array", "items": {"type": "string"}},
                    "role": {"type": "string"},
                    "type_id": {"type": "string"},
                    "type_name": {"type": "string"},
                    "domain_name": {"type": "string"},
                    "source_path": {"type": "string"},
                    "target_path": {"type": "string"},
                    "relation": {"type": "string"},
                    "memory_type": {"type": "string"},
                    "summary": {"type": "string"},
                    "signals": {"type": "array", "items": {"type": "string"}},
                    "recall_context": {"type": "array", "items": {"type": "string"}},
                    "review_after": {"type": "string"},
                    "staleness_risk": {"type": "string"},
                    "conflict_candidates": {"type": "array", "items": {"type": "object"}},
                    "evolution": {"type": "object"},
                    "review_questions": {"type": "array", "items": {"type": "string"}},
                    "evidence": {"type": "string"},
                }, ["item_type"]),
                _tool("approve_review_queue_items", "Preview or apply selected stable IDs from build_review_apply_queue.", {
                    "item_ids": {"type": "array", "items": {"type": "string"}},
                    "max_notes": {"type": "integer", "default": 120},
                    "max_domains": {"type": "integer", "default": 8},
                    "limit": {"type": "integer", "default": 40},
                    "dry_run": {"type": "boolean", "default": True},
                    "allow_overwrite": {"type": "boolean", "default": False},
                    "include_memory": {"type": "boolean", "default": False},
                }, ["item_ids"]),
                _tool("apply_learned_review_queue", "Preview/apply review queue items selected from accepted examples.", {
                    "mode": {"type": "string", "default": "review"},
                    "max_notes": {"type": "integer", "default": 120},
                    "max_domains": {"type": "integer", "default": 8},
                    "limit": {"type": "integer", "default": 40},
                    "dry_run": {"type": "boolean", "default": True},
                    "allow_overwrite": {"type": "boolean", "default": False},
                    "include_memory": {"type": "boolean", "default": False},
                }),
                _tool("guide_next_steps", "Explain the current LINZA onboarding stage and safe next actions.", {
                    "max_notes": {"type": "integer", "default": 120},
                    "max_domains": {"type": "integer", "default": 8},
                    "limit": {"type": "integer", "default": 40},
                    "include_memory": {"type": "boolean", "default": False},
                    "include_tool_guide": {"type": "boolean", "default": False},
                }),
                _tool("agent_workspace", "One facade for workspace maps, teaching, supervised growth, artifact inbox, analysis, review, graph connect, and context export.", {
                    "action": {
                        "type": "string",
                        "enum": [
                            "ingest_artifacts",
                            "analyze_inbox",
                            "review_next",
                            "apply_review_items",
                            "teach",
                            "grow",
                            "connect",
                            "map",
                            "search_memory",
                            "export_context",
                            "record_trace",
                            "analyze_trace",
                            "review_calibr",
                            "doctor",
                        ],
                    },
                    "artifacts": {"type": "array", "items": {"type": "object"}},
                    "trace": {"type": "object"},
                    "trace_id": {"type": "string"},
                    "source_kind": {"type": "string"},
                    "batch_id": {"type": "string"},
                    "privacy": {"type": "string", "default": "private"},
                    "kind": {"type": "string", "default": "all"},
                    "mode": {"type": "string", "default": "assisted"},
                    "item_ids": {"type": "array", "items": {"type": "string"}},
                    "dry_run": {"type": "boolean", "default": True},
                    "allow_overwrite": {"type": "boolean", "default": False},
                    "include_memory": {"type": "boolean", "default": False},
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "max_depth": {"type": "integer", "default": 4},
                    "max_notes": {"type": "integer", "default": 120},
                    "max_domains": {"type": "integer", "default": 8},
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                }, ["action"]),
                _tool("list_approved_items", "List reviewed sidecar approvals.", {
                    "item_type": {"type": "string"},
                    "limit": {"type": "integer", "default": 100},
                }),
                _tool("build_bases_plan", "Build an Obsidian Bases plan report.", _report_schema(REPORT_DEFAULTS["bases_plan"])),
                _tool("build_yaml_suggestions", "Build a LINZA YAML suggestions report.", _report_schema(REPORT_DEFAULTS["yaml_suggestions"], {"limit": {"type": "integer", "default": 50}})),
                _tool("build_tag_vocabulary_report", "Build a tag vocabulary report.", _report_schema(REPORT_DEFAULTS["tag_vocabulary"])),
                _tool("build_review_queue", "Build a human-readable review queue.", _report_schema(REPORT_DEFAULTS["review_queue"], {"limit": {"type": "integer", "default": 30}})),
                _tool("build_review_apply_queue", "Build a review/apply queue with dry-run approval payloads.", _report_schema(REPORT_DEFAULTS["review_apply_queue"], {
                    "max_notes": {"type": "integer", "default": 120},
                    "max_domains": {"type": "integer", "default": 8},
                    "limit": {"type": "integer", "default": 40},
                    "include_memory": {"type": "boolean", "default": False},
                    "analysis_stage": {"type": "string", "default": "all"},
                    "redact": {"type": "boolean", "default": False},
                })),
                _tool("build_diagnostic_report", "Build a vault diagnostic report.", _report_schema(REPORT_DEFAULTS["diagnostic"])),
                _tool("build_semantic_links", "Build semantic link candidates report.", _report_schema(REPORT_DEFAULTS["semantic_links"], {"limit": {"type": "integer", "default": 50}})),
                _tool("explain_relationship", "Explain a possible relationship between two notes.", {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                }, ["source", "target"]),
                _tool("explain_node", "Explain one node's graph and semantic context.", {"path": {"type": "string"}}, ["path"]),
                _tool("who_depends", "Show backlinks/dependents for a note.", {
                    "path": {"type": "string"},
                    "depth": {"type": "integer", "default": 1},
                }, ["path"]),
                _tool("show_flow", "Show a node-to-node or query flow.", {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "query": {"type": "string"},
                    "profile": {"type": "string"},
                    "top_k": {"type": "integer", "default": 8},
                    "max_depth": {"type": "integer", "default": 4},
                }),
                _tool("check_rule", "Run read-only graph/rule checks.", {
                    "rule": {"type": "string", "default": "all"},
                    "path": {"type": "string"},
                }),
                _tool("create_context_pack", "Build an AI-ready context pack from semantic search.", {
                    "title": {"type": "string"},
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 8},
                    "write": {"type": "boolean", "default": False},
                    "path": {"type": "string"},
                }, ["title", "query"]),
            ]
            return self._listed_tools(tools)

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            arguments = arguments or {}
            try:
                return await self._call_tool(name, arguments)
            except Exception as exc:
                logging.exception("Tool %s failed", name)
                return _error_result(str(exc))

    def _listed_tools(self, tools: list[Tool]) -> list[Tool]:
        surface = str(
            self.config.get("tool_surface")
            or os.environ.get("LINZA_TOOL_SURFACE")
            or "default"
        ).strip().lower()
        if surface in {"advanced", "all", "full", "legacy"}:
            return tools
        default_names = set(DEFAULT_MCP_TOOLS)
        return [tool for tool in tools if tool.name in default_names]

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        if name == "index_all":
            await self.core.index_vault(force=bool(arguments.get("force", False)))
            return _json_result({
                "status": "complete",
                "files_indexed": self.storage.get_file_count(),
                "bridges": len(self.storage.get_all_bridges()),
            })
        if name == "index_file":
            path, _ = _vault_path(self.vault_path, arguments["path"])
            await self.core.index_single_file(path, arguments.get("content"))
            return _json_result({"status": "indexed", "path": path})
        if name == "search":
            return _json_result(await self.core.search(
                arguments["query"],
                profile_name=arguments.get("profile") or self.storage.get_active_profile(),
                top_k=int(arguments.get("top_k", 5)),
                explain=bool(arguments.get("explain", False)),
            ))
        if name == "suggest_links":
            path, _ = _vault_path(self.vault_path, arguments["path"])
            return _json_result(await self.core.suggest_links(
                path,
                profile_name=arguments.get("profile") or self.storage.get_active_profile(),
                top_k=int(arguments.get("top_k", 5)),
            ))
        if name == "create_profile":
            return _json_result(await self.core.create_profile(
                arguments["name"],
                arguments["keywords"],
                description=arguments.get("description", ""),
                parent_profile=arguments.get("parent_profile"),
            ))
        if name == "list_profiles":
            return _json_result(self.storage.list_profiles())
        if name == "switch_profile":
            profile_name = arguments["name"]
            if self.storage.get_profile(profile_name) is None:
                return _error_result(f"Profile '{profile_name}' not found.")
            self.storage.set_active_profile(profile_name)
            return _text_result(f"Active profile set to '{profile_name}'.")
        if name == "get_profile":
            profile = self.storage.get_profile(arguments["name"])
            if not profile:
                return _error_result(f"Profile '{arguments['name']}' not found.")
            chain = [profile["name"]]
            current = profile
            while current.get("parent_profile"):
                parent = self.storage.get_profile(current["parent_profile"])
                if not parent:
                    break
                chain.append(parent["name"])
                current = parent
            profile["inheritance_chain"] = chain
            return _json_result(profile)
        if name == "read_file":
            _, full_path = _vault_path(self.vault_path, arguments["path"])
            if not full_path.exists() or not full_path.is_file():
                return _error_result("File not found.")
            return _text_result(full_path.read_text(encoding="utf-8"))
        if name == "write_file":
            rel, full_path = _vault_path(self.vault_path, arguments["path"])
            content = arguments["content"]
            if not rel.endswith(".md"):
                return _json_result({
                    "status": "blocked",
                    "path": rel,
                    "reason": "write_file only writes Markdown notes",
                    "dry_run": True,
                })
            dry_run = bool(arguments.get("dry_run", True))
            allow_overwrite = bool(arguments.get("allow_overwrite", False))
            exists = full_path.exists()
            if exists and not allow_overwrite:
                return _json_result({
                    "status": "blocked",
                    "path": rel,
                    "reason": "file exists; pass allow_overwrite=true to replace content",
                    "dry_run": dry_run,
                })
            preview = {
                "status": "preview" if dry_run else "written",
                "path": rel,
                "dry_run": dry_run,
                "will_overwrite": exists,
                "reindexed": not dry_run,
            }
            if dry_run:
                return _json_result(preview)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            _write_text_exact(full_path, content)
            await self.core.index_single_file(rel, content)
            return _json_result(preview)
        if name == "get_bridges":
            path, _ = _vault_path(self.vault_path, arguments["path"])
            return _json_result(self.storage.get_bridges_for_file(path))
        if name == "get_stats":
            return _json_result({
                "files": self.storage.get_file_count(),
                "profiles": len(self.storage.list_profiles()),
                "bridges": len(self.storage.get_all_bridges()),
                "active_profile": self.storage.get_active_profile(),
            })
        if name == "calibrate_embeddings":
            return _json_result(self.core.calibrate_embeddings())
        if name == "scan_vault":
            return _json_result(self.core.scan_vault())
        if name == "draft_vault_map":
            return _json_result(await self.core.draft_vault_map(
                max_notes=int(arguments.get("max_notes", 120)),
                max_domains=int(arguments.get("max_domains", 8)),
                max_chunks_per_note=int(arguments.get("max_chunks_per_note", 12)),
                use_embedding_second_pass=bool(arguments.get("use_embedding_second_pass", True)),
                analysis_stage=arguments.get("analysis_stage", "all"),
            ))
        if name == "audit_tags":
            return _json_result(self.core.audit_tag_vocabulary())
        if name == "suggest_tag_candidates":
            path, _ = _vault_path(self.vault_path, arguments["path"])
            return _json_result(self.core.suggest_tag_candidates(
                path,
                max_candidates=int(arguments.get("max_candidates", 20)),
                include_new=bool(arguments.get("include_new", True)),
            ))
        if name == "suggest_properties":
            path, _ = _vault_path(self.vault_path, arguments["path"])
            return _json_result(self.core.suggest_properties_for_note(path))
        if name == "patch_properties":
            path, _ = _vault_path(self.vault_path, arguments["path"])
            result = self.core.patch_note_properties(
                path,
                arguments.get("properties", {}),
                dry_run=bool(arguments.get("dry_run", True)),
                allow_overwrite=bool(arguments.get("allow_overwrite", False)),
                namespace=arguments.get("namespace", "linza"),
            )
            if result.get("status") == "written":
                await self.core.index_single_file(path)
            return _json_result(result)
        if name == "approve_draft_item":
            result = self.core.approve_draft_item(
                item_type=arguments.get("item_type", ""),
                dry_run=bool(arguments.get("dry_run", True)),
                allow_overwrite=bool(arguments.get("allow_overwrite", False)),
                path=_optional_vault_rel(self.vault_path, arguments.get("path", "")),
                paths=_vault_rel_list(self.vault_path, arguments.get("paths", [])),
                parent_path=_optional_vault_rel(self.vault_path, arguments.get("parent_path", "")),
                child_paths=_vault_rel_list(self.vault_path, arguments.get("child_paths", [])),
                role=arguments.get("role", ""),
                type_id=arguments.get("type_id", ""),
                type_name=arguments.get("type_name", ""),
                domain_name=arguments.get("domain_name", ""),
                source_path=_optional_vault_rel(self.vault_path, arguments.get("source_path", "")),
                target_path=_optional_vault_rel(self.vault_path, arguments.get("target_path", "")),
                relation=arguments.get("relation", ""),
                memory_type=arguments.get("memory_type", ""),
                summary=arguments.get("summary", ""),
                signals=arguments.get("signals", []),
                recall_context=arguments.get("recall_context", []),
                review_after=arguments.get("review_after", ""),
                staleness_risk=arguments.get("staleness_risk", ""),
                conflict_candidates=arguments.get("conflict_candidates", []),
                evolution=arguments.get("evolution", {}),
                review_questions=arguments.get("review_questions", []),
                evidence=arguments.get("evidence", ""),
            )
            if result.get("status") == "written":
                for path in result.get("written_paths") or result.get("applied_to", []):
                    if path:
                        await self.core.index_single_file(path)
            return _json_result(result)
        if name == "approve_review_queue_items":
            result = await self.core.approve_review_queue_items(
                item_ids=arguments.get("item_ids", []),
                max_notes=int(arguments.get("max_notes", 120)),
                max_domains=int(arguments.get("max_domains", 8)),
                limit=int(arguments.get("limit", 40)),
                dry_run=bool(arguments.get("dry_run", True)),
                allow_overwrite=bool(arguments.get("allow_overwrite", False)),
                include_memory=bool(arguments.get("include_memory", False)),
            )
            for path in result.get("written_paths", []):
                if path:
                    await self.core.index_single_file(path)
            return _json_result(result)
        if name == "apply_learned_review_queue":
            result = await self.core.apply_learned_review_queue(
                mode=arguments.get("mode", "review"),
                max_notes=int(arguments.get("max_notes", 120)),
                max_domains=int(arguments.get("max_domains", 8)),
                limit=int(arguments.get("limit", 40)),
                dry_run=bool(arguments.get("dry_run", True)),
                allow_overwrite=bool(arguments.get("allow_overwrite", False)),
                include_memory=bool(arguments.get("include_memory", False)),
            )
            for path in result.get("written_paths", []):
                if path:
                    await self.core.index_single_file(path)
            return _json_result(result)
        if name == "guide_next_steps":
            return _json_result(await self.core.guide_next_steps(
                max_notes=int(arguments.get("max_notes", 120)),
                max_domains=int(arguments.get("max_domains", 8)),
                limit=int(arguments.get("limit", 40)),
                include_memory=bool(arguments.get("include_memory", False)),
                include_tool_guide=bool(arguments.get("include_tool_guide", False)),
            ))
        if name == "agent_workspace":
            return _json_result(await self.core.agent_workspace(
                action=arguments.get("action", ""),
                artifacts=arguments.get("artifacts", []),
                source_kind=arguments.get("source_kind", ""),
                batch_id=arguments.get("batch_id", ""),
                privacy=arguments.get("privacy", "private"),
                kind=arguments.get("kind", "all"),
                mode=arguments.get("mode", "assisted"),
                item_ids=arguments.get("item_ids", []),
                dry_run=bool(arguments.get("dry_run", True)),
                allow_overwrite=bool(arguments.get("allow_overwrite", False)),
                include_memory=bool(arguments.get("include_memory", False)),
                source=arguments.get("source", ""),
                target=arguments.get("target", ""),
                max_depth=int(arguments.get("max_depth", 4)),
                max_notes=int(arguments.get("max_notes", 120)),
                max_domains=int(arguments.get("max_domains", 8)),
                query=arguments.get("query", ""),
                trace=arguments.get("trace", {}),
                trace_id=arguments.get("trace_id", ""),
                limit=int(arguments.get("limit", 20)),
            ))
        if name == "list_approved_items":
            return _json_result(self.storage.list_approved_items(
                arguments.get("item_type"),
                limit=int(arguments.get("limit", 100)),
            ))
        if name == "build_bases_plan":
            return self._report_result(arguments, self.core.build_bases_plan_markdown(), REPORT_DEFAULTS["bases_plan"])
        if name == "build_yaml_suggestions":
            markdown = self.core.build_yaml_suggestions_markdown(limit=int(arguments.get("limit", 50)))
            return self._report_result(arguments, markdown, REPORT_DEFAULTS["yaml_suggestions"])
        if name == "build_tag_vocabulary_report":
            return self._report_result(arguments, self.core.build_tag_vocabulary_markdown(), REPORT_DEFAULTS["tag_vocabulary"])
        if name == "build_review_queue":
            markdown = self.core.build_review_queue_markdown(limit=int(arguments.get("limit", 30)))
            return self._report_result(arguments, markdown, REPORT_DEFAULTS["review_queue"])
        if name == "build_review_apply_queue":
            result = await self.core.build_review_apply_queue(
                max_notes=int(arguments.get("max_notes", 120)),
                max_domains=int(arguments.get("max_domains", 8)),
                limit=int(arguments.get("limit", 40)),
                include_memory=bool(arguments.get("include_memory", False)),
                analysis_stage=arguments.get("analysis_stage", "all"),
                redact=bool(arguments.get("redact", False)),
            )
            if arguments.get("write", False):
                rel, full_path, blocked = _generated_output_target(
                    self.vault_path,
                    arguments.get("path") or REPORT_DEFAULTS["review_apply_queue"],
                    REPORT_DEFAULTS["review_apply_queue"],
                    ".linza/reports",
                    "report",
                )
                if blocked:
                    return _json_result(blocked)
                assert full_path is not None
                full_path.parent.mkdir(parents=True, exist_ok=True)
                _write_text_exact(full_path, result["markdown"])
                result["report_written"] = rel
                result["note"] = "Created LINZA sidecar review/apply report. Existing user notes were not modified."
            return _json_result(result)
        if name == "build_diagnostic_report":
            return self._report_result(arguments, self.core.build_diagnostic_markdown(), REPORT_DEFAULTS["diagnostic"])
        if name == "build_semantic_links":
            markdown = self.core.build_semantic_links_markdown(limit=int(arguments.get("limit", 50)))
            return self._report_result(arguments, markdown, REPORT_DEFAULTS["semantic_links"])
        if name == "explain_relationship":
            return _json_result(self.core.explain_relationship(arguments["source"], arguments["target"]))
        if name == "explain_node":
            path, _ = _vault_path(self.vault_path, arguments["path"])
            return _json_result(self.core.explain_node(path))
        if name == "who_depends":
            path, _ = _vault_path(self.vault_path, arguments["path"])
            return _json_result(self.core.who_depends(path, depth=int(arguments.get("depth", 1))))
        if name == "show_flow":
            return _json_result(await self.core.show_flow(
                source=arguments.get("source"),
                target=arguments.get("target"),
                query=arguments.get("query"),
                profile_name=arguments.get("profile") or self.storage.get_active_profile(),
                top_k=int(arguments.get("top_k", 8)),
                max_depth=int(arguments.get("max_depth", 4)),
            ))
        if name == "check_rule":
            path = _optional_vault_rel(self.vault_path, arguments.get("path"))
            return _json_result(self.core.check_rule(rule=arguments.get("rule", "all"), path=path or None))
        if name == "create_context_pack":
            title = arguments["title"]
            query = arguments["query"]
            search = await self.core.search(query, top_k=int(arguments.get("top_k", 8)))
            paths = [item["path"] for item in search.get("results", [])]
            markdown = self.core.build_context_pack_markdown(title, query, paths)
            if arguments.get("write", False):
                safe_title = re.sub(r"[^A-Za-z\u0410-\u044f\u0401\u04510-9 _.-]+", "", title).strip() or "context-pack"
                rel, full_path, blocked = _generated_output_target(
                    self.vault_path,
                    arguments.get("path") or f".linza/context-packs/{safe_title}.md",
                    f".linza/context-packs/{safe_title}.md",
                    ".linza/context-packs",
                    "context pack",
                )
                if blocked:
                    return _json_result(blocked)
                assert full_path is not None
                full_path.parent.mkdir(parents=True, exist_ok=True)
                _write_text_exact(full_path, markdown)
                return _json_result({"status": "written", "path": rel, "notes": paths})
            return _text_result(markdown)
        return _error_result(f"Unknown tool: {name}")

    def _report_result(self, arguments: dict[str, Any], markdown: str, default_path: str) -> CallToolResult:
        if not arguments.get("write", False):
            return _text_result(markdown)
        rel, full_path, blocked = _generated_output_target(
            self.vault_path,
            arguments.get("path") or default_path,
            default_path,
            ".linza/reports",
            "report",
        )
        if blocked:
            return _json_result(blocked)
        assert full_path is not None
        full_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text_exact(full_path, markdown)
        return _json_result({
            "status": "written",
            "path": rel,
            "note": "Created LINZA sidecar report file. Existing user notes were not modified.",
        })

    async def run(self) -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(server_name="linza-mcp", server_version=__version__),
            )


def _report_schema(default_path: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    properties = {
        "write": {"type": "boolean", "default": False},
        "path": {"type": "string", "default": default_path},
    }
    if extra:
        properties.update(extra)
    return properties


def load_config_from_env() -> Dict[str, Any]:
    return {
        "vault_path": os.environ.get("LINZA_VAULT", os.path.abspath("./vault")),
        "embed_provider": os.environ.get("LINZA_EMBED_PROVIDER", "lmstudio"),
        "embed_api_url": os.environ.get("LINZA_EMBED_URL", "http://127.0.0.1:1234/v1"),
        "embed_api_key": os.environ.get("LINZA_EMBED_KEY"),
        "embed_model": os.environ.get("LINZA_EMBED_MODEL"),
        "bridge_threshold": float(os.environ.get("LINZA_BRIDGE_THRESHOLD", "0.55")),
        "default_profile": os.environ.get("LINZA_DEFAULT_PROFILE", "general"),
        "tool_surface": os.environ.get("LINZA_TOOL_SURFACE", "default"),
    }


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    config = load_config_from_env()
    vault_path = Path(config["vault_path"]).expanduser().resolve()
    vault_path.mkdir(parents=True, exist_ok=True)

    provider = get_embedding_provider(
        config["embed_provider"],
        config["embed_api_url"],
        config["embed_api_key"],
        config["embed_model"],
    )
    server = LinzaMCPServer(vault_path, provider, config)

    if not server.storage.list_profiles():
        general_keywords = "general notes ideas thoughts knowledge"
        raw, centered = await server.core._compute_embeddings([general_keywords])
        server.storage.set_profile(
            "general",
            general_keywords,
            raw[0],
            centered[0],
            "Default general-purpose profile",
        )
        server.storage.set_active_profile("general")
        logging.info("Created default 'general' profile")

    await server.run()


__all__ = [
    "EmbeddingProvider",
    "LMStudioProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "LinzaMCPServer",
    "get_embedding_provider",
    "load_config_from_env",
    "main",
]


if __name__ == "__main__":
    anyio.run(main)
