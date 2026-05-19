"""Smoke every LINZA MCP tool on a temporary Markdown-only vault copy.

The output is private-safe by design: it reports tool names, statuses, shapes,
and counts, but never prints note text, note titles, search results, or paths
from the user's vault.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from mcp.types import ListToolsRequest  # noqa: E402

from linza_mcp.embed import get_embedding_provider  # noqa: E402
from linza_mcp.server import LinzaMCPServer  # noqa: E402
from scripts.smoke_copy_vault import body_map, copy_markdown_vault, hash_markdown_files  # noqa: E402


EXPECTED_TOOLS = [
    "index_all",
    "index_file",
    "search",
    "suggest_links",
    "create_profile",
    "list_profiles",
    "switch_profile",
    "get_profile",
    "read_file",
    "write_file",
    "get_bridges",
    "get_stats",
    "calibrate_embeddings",
    "scan_vault",
    "draft_vault_map",
    "audit_tags",
    "suggest_tag_candidates",
    "suggest_properties",
    "patch_properties",
    "approve_draft_item",
    "approve_review_queue_items",
    "apply_learned_review_queue",
    "guide_next_steps",
    "agent_workspace",
    "list_approved_items",
    "build_bases_plan",
    "build_yaml_suggestions",
    "build_tag_vocabulary_report",
    "build_review_queue",
    "build_review_apply_queue",
    "build_diagnostic_report",
    "build_semantic_links",
    "explain_relationship",
    "explain_node",
    "who_depends",
    "show_flow",
    "check_rule",
    "create_context_pack",
]


def safe_note_paths(vault: Path) -> list[str]:
    paths: list[str] = []
    ignored = {".linza", "LINZA"}
    for path in sorted(vault.rglob("*.md")):
        rel_parts = path.relative_to(vault).parts
        if any(part in ignored or part.startswith(".") for part in rel_parts):
            continue
        paths.append(path.relative_to(vault).as_posix())
    return paths


def result_text(result: Any) -> str:
    chunks = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text is not None:
            chunks.append(text)
    return "\n".join(chunks)


def parse_result(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def payload_shape(parsed: Any, text: str) -> dict[str, Any]:
    if isinstance(parsed, dict):
        return {
            "shape": "json_object",
            "status": parsed.get("status", "ok"),
            "keys": sorted(str(key) for key in parsed.keys())[:16],
        }
    if isinstance(parsed, list):
        return {"shape": "json_list", "items": len(parsed)}
    return {
        "shape": "text",
        "chars": len(text),
        "lines": text.count("\n") + (1 if text else 0),
    }


async def call_tool(
    server: LinzaMCPServer,
    records: list[dict[str, Any]],
    name: str,
    arguments: dict[str, Any] | None = None,
) -> tuple[Any, str]:
    result = await server._call_tool(name, arguments or {})
    text = result_text(result)
    parsed = parse_result(text)
    record = {"tool": name, **payload_shape(parsed, text)}
    if getattr(result, "is_error", False):
        record["status"] = "error"
        records.append(record)
        raise AssertionError(f"{name} returned an MCP error")
    records.append(record)
    return parsed, text


async def registered_tools(server: LinzaMCPServer) -> list[str]:
    handler = server.server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))
    return sorted(tool.name for tool in result.root.tools)


async def run_smoke(
    source_vault: Path,
    workdir: Path,
    embed_provider: str,
    embed_model: str | None,
    embed_url: str,
    embed_key: str | None,
) -> dict[str, Any]:
    source_vault = source_vault.resolve()
    workdir = workdir.resolve()
    if not source_vault.exists():
        raise FileNotFoundError(f"source vault not found: {source_vault}")

    source_hashes_before = hash_markdown_files(source_vault)
    copy_vault = copy_markdown_vault(source_vault, workdir)
    copy_bodies_before = body_map(copy_vault)

    server = LinzaMCPServer(
        copy_vault,
        get_embedding_provider(embed_provider, embed_url, embed_key, embed_model),
        {"default_profile": "general", "bridge_threshold": 0.55, "tool_surface": "advanced"},
    )
    records: list[dict[str, Any]] = []

    try:
        tools = await registered_tools(server)
        expected = sorted(EXPECTED_TOOLS)
        if tools != expected:
            raise AssertionError(
                f"registered tool set changed: missing={sorted(set(expected) - set(tools))}, "
                f"extra={sorted(set(tools) - set(expected))}"
            )
        records.append({"tool": "tools/list", "shape": "tool_names", "items": len(tools), "status": "ok"})

        notes = safe_note_paths(copy_vault)
        if len(notes) < 2:
            raise AssertionError("need at least two non-LINZA Markdown notes for MCP smoke")
        first_note, second_note = notes[0], notes[1]

        await call_tool(server, records, "index_all", {"force": True})
        await call_tool(server, records, "index_file", {
            "path": "LINZA/tool-smoke/virtual-indexed.md",
            "content": "# Tool smoke\n\nSynthetic indexing content for LINZA MCP smoke.",
        })
        await call_tool(server, records, "create_profile", {
            "name": "smoke",
            "keywords": "semantic search graph context review",
            "description": "Temporary smoke profile",
        })
        await call_tool(server, records, "list_profiles")
        await call_tool(server, records, "switch_profile", {"name": "smoke"})
        await call_tool(server, records, "get_profile", {"name": "smoke"})
        await call_tool(server, records, "search", {
            "query": "semantic search graph context",
            "top_k": 3,
            "explain": True,
        })
        await call_tool(server, records, "suggest_links", {"path": first_note, "top_k": 3})
        await call_tool(server, records, "read_file", {"path": first_note})
        await call_tool(server, records, "write_file", {
            "path": "LINZA/tool-smoke/new-note.md",
            "content": "# LINZA tool smoke\n\nTemporary note created only inside the smoke copy.",
            "dry_run": False,
        })
        await call_tool(server, records, "get_bridges", {"path": first_note})
        await call_tool(server, records, "get_stats")
        await call_tool(server, records, "calibrate_embeddings")
        await call_tool(server, records, "scan_vault")
        await call_tool(server, records, "draft_vault_map", {
            "max_notes": 80,
            "max_domains": 6,
            "max_chunks_per_note": 8,
        })
        await call_tool(server, records, "audit_tags")
        await call_tool(server, records, "suggest_tag_candidates", {
            "path": first_note,
            "max_candidates": 10,
            "include_new": True,
        })
        await call_tool(server, records, "suggest_properties", {"path": first_note})
        await call_tool(server, records, "patch_properties", {
            "path": first_note,
            "properties": {"tool_smoke": True},
            "dry_run": True,
        })
        await call_tool(server, records, "approve_draft_item", {
            "item_type": "causal_link",
            "source_path": first_note,
            "target_path": second_note,
            "relation": "related",
            "evidence": "Smoke-only sidecar approval.",
            "dry_run": False,
        })

        queue_payload, _ = await call_tool(server, records, "build_review_apply_queue", {
            "max_notes": 80,
            "max_domains": 6,
            "limit": 12,
            "redact": True,
            "write": True,
            "path": "LINZA/tool-smoke/review-apply-queue.md",
        })
        queue_ids = [
            item.get("id")
            for item in (queue_payload or {}).get("items", [])
            if item.get("id")
        ][:3]
        if not queue_ids:
            raise AssertionError("build_review_apply_queue returned no stable IDs")

        await call_tool(server, records, "approve_review_queue_items", {
            "item_ids": queue_ids,
            "max_notes": 80,
            "max_domains": 6,
            "limit": 12,
            "dry_run": True,
        })
        await call_tool(server, records, "apply_learned_review_queue", {
            "mode": "review",
            "max_notes": 80,
            "max_domains": 6,
            "limit": 12,
            "dry_run": True,
        })
        await call_tool(server, records, "guide_next_steps", {
            "max_notes": 80,
            "max_domains": 6,
            "limit": 12,
            "include_tool_guide": False,
        })
        await call_tool(server, records, "agent_workspace", {
            "action": "ingest_artifacts",
            "artifacts": [{
                "source_kind": "agent_log",
                "title": "Tool smoke artifact",
                "content": "Decision: keep agent workspace behind one facade. Action: smoke the artifact inbox.",
            }],
        })
        await call_tool(server, records, "agent_workspace", {
            "action": "record_trace",
            "trace": {
                "task": "Smoke calibr trace",
                "expected": "Record a private sidecar trace without changing source notes.",
                "result": "Trace recorded during MCP smoke.",
                "status": "done",
                "tool_calls": [{"name": "agent_workspace", "arguments": {"action": "record_trace"}}],
                "changed_files": [],
                "tests": [{"name": "smoke", "status": "passed"}],
                "errors": [],
            },
        })
        await call_tool(server, records, "agent_workspace", {"action": "doctor"})
        await call_tool(server, records, "list_approved_items", {"limit": 10})
        await call_tool(server, records, "build_bases_plan", {
            "write": True,
            "path": "LINZA/tool-smoke/bases-plan.md",
        })
        await call_tool(server, records, "build_yaml_suggestions", {
            "write": True,
            "path": "LINZA/tool-smoke/yaml-suggestions.md",
            "limit": 20,
        })
        await call_tool(server, records, "build_tag_vocabulary_report", {
            "write": True,
            "path": "LINZA/tool-smoke/tag-vocabulary.md",
        })
        await call_tool(server, records, "build_review_queue", {
            "write": True,
            "path": "LINZA/tool-smoke/review-queue.md",
            "limit": 20,
        })
        await call_tool(server, records, "build_diagnostic_report", {
            "write": True,
            "path": "LINZA/tool-smoke/diagnostic.md",
        })
        await call_tool(server, records, "build_semantic_links", {
            "write": True,
            "path": "LINZA/tool-smoke/semantic-links.md",
            "limit": 20,
        })
        await call_tool(server, records, "explain_relationship", {
            "source": first_note,
            "target": second_note,
        })
        await call_tool(server, records, "explain_node", {"path": first_note})
        await call_tool(server, records, "who_depends", {"path": first_note, "depth": 1})
        await call_tool(server, records, "show_flow", {
            "query": "semantic graph context",
            "top_k": 4,
            "max_depth": 3,
        })
        await call_tool(server, records, "check_rule", {"rule": "all"})
        await call_tool(server, records, "create_context_pack", {
            "title": "LINZA tool smoke",
            "query": "semantic graph context",
            "top_k": 4,
            "write": True,
            "path": "LINZA/tool-smoke/context-pack.md",
        })
    finally:
        server.storage.close()

    source_hashes_after = hash_markdown_files(source_vault)
    if source_hashes_before != source_hashes_after:
        raise AssertionError("source vault changed during MCP tool smoke")

    copy_bodies_after = body_map(copy_vault)
    body_changes = [
        rel for rel, before in copy_bodies_before.items()
        if copy_bodies_after.get(rel) != before
    ]
    if body_changes:
        raise AssertionError(f"existing copy note bodies changed: {len(body_changes)}")

    tool_smoke_files = [
        path
        for path in (copy_vault / "LINZA" / "tool-smoke").glob("*.md")
        if path.is_file()
    ]

    return {
        "status": "ok",
        "source_markdown_files": len(source_hashes_before),
        "copy_markdown_files": len(copy_bodies_before),
        "copy_vault": str(copy_vault.relative_to(WORKSPACE_ROOT)),
        "tools_registered": len(EXPECTED_TOOLS),
        "tool_calls_ok": len(records),
        "tool_records": records,
        "queue_ids_checked": len(queue_ids),
        "tool_smoke_files_written": len(tool_smoke_files),
        "source_changed": False,
        "copy_existing_note_body_changes": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test every LINZA MCP tool.")
    parser.add_argument("--source-vault", type=Path, default=WORKSPACE_ROOT / "Obsidian" / "base")
    parser.add_argument("--workdir", type=Path, default=REPO_ROOT / ".test-tmp")
    parser.add_argument("--embed-provider", default=os.environ.get("LINZA_EMBED_PROVIDER", "lmstudio"))
    parser.add_argument("--embed-model", default=os.environ.get("LINZA_EMBED_MODEL"))
    parser.add_argument("--embed-url", default=os.environ.get("LINZA_EMBED_URL", "http://127.0.0.1:1234/v1"))
    parser.add_argument("--embed-key", default=os.environ.get("LINZA_EMBED_KEY"))
    args = parser.parse_args()

    summary = asyncio.run(run_smoke(
        args.source_vault,
        args.workdir,
        args.embed_provider,
        args.embed_model,
        args.embed_url,
        args.embed_key,
    ))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
