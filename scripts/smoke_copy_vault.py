"""Run a LINZA smoke test against a Markdown-only copy of a vault.

The script is intentionally private-output safe: it prints aggregate counts only,
not note titles, note text, or generated domain names.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parents[1]
sys.path.insert(0, str(REPO_ROOT))

from server import LinzaCore, LinzaStorage, get_embedding_provider, strip_frontmatter  # noqa: E402


class SmokeEmbeddingProvider:
    """Deterministic local embeddings for copy-only workflow smoke tests."""

    def __init__(self, model: str = "smoke-deterministic", dim: int = 64):
        self.model = model
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dim
            tokens = [token for token in text.lower().split() if token.strip()] or [text]
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8", errors="ignore")).digest()
                for index in range(0, min(16, len(digest)), 2):
                    bucket = digest[index] % self.dim
                    sign = 1.0 if digest[index + 1] % 2 else -1.0
                    vector[bucket] += sign
            vectors.append(vector)
        return vectors


def make_embedding_provider(
    embed_provider: str,
    embed_url: str,
    embed_key: str | None,
    embed_model: str | None,
):
    provider_name = str(embed_provider or "").strip().lower()
    if provider_name in {"smoke", "deterministic", "test"}:
        return SmokeEmbeddingProvider(model=embed_model or "smoke-deterministic")
    return get_embedding_provider(embed_provider, embed_url, embed_key, embed_model)


def hash_markdown_files(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in root.rglob("*.md"):
        if ".linza" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        hashes[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def body_map(root: Path) -> dict[str, str]:
    bodies: dict[str, str] = {}
    for path in root.rglob("*.md"):
        if ".linza" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        _, body = strip_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        bodies[rel] = body
    return bodies


def copy_markdown_vault(source: Path, workdir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    workdir.mkdir(parents=True, exist_ok=True)
    for suffix in range(100):
        name = f"linza-vault-copy-{timestamp}" if suffix == 0 else f"linza-vault-copy-{timestamp}-{suffix}"
        target = workdir / name
        try:
            target.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            continue
    else:
        raise FileExistsError(f"could not allocate unique temp vault under {workdir}")
    for source_file in source.rglob("*.md"):
        if ".linza" in source_file.parts:
            continue
        rel = source_file.relative_to(source)
        target_file = target / rel
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
    return target


def by_kind(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        kind = item.get("kind", "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def first_item_id(queue: dict[str, Any], item_type: str) -> str | None:
    for item in queue.get("items", []):
        arguments = item.get("approval", {}).get("arguments", {})
        if arguments.get("item_type") == item_type:
            return item.get("id")
    return None


def first_ids(items: list[dict[str, Any]], limit: int) -> list[str]:
    ids: list[str] = []
    for item in items:
        item_id = str(item.get("id") or "").strip()
        if item_id:
            ids.append(item_id)
        if len(ids) >= limit:
            break
    return ids


async def run_smoke(
    source_vault: Path,
    workdir: Path,
    max_notes: int,
    max_domains: int,
    limit: int,
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

    storage = LinzaStorage(copy_vault, copy_vault / ".linza" / "linza.db")
    provider = make_embedding_provider(embed_provider, embed_url, embed_key, embed_model)
    core = LinzaCore(copy_vault, storage, provider, {"default_profile": "general"})
    try:
        doctor_before = await core.agent_workspace(action="doctor")
        await core.index_vault(force=True)
        doctor_after = await core.agent_workspace(action="doctor")
        guide = await core.guide_next_steps(max_notes=max_notes, max_domains=max_domains, limit=limit)

        next_args = guide.get("next_step", {}).get("primary_arguments", {})
        review_kind = str(next_args.get("kind") or "all")
        review = await core.agent_workspace(
            action="review_next",
            kind=review_kind,
            max_notes=max_notes,
            max_domains=max_domains,
            limit=limit,
        )
        if not review.get("items") and review_kind != "all":
            review_kind = "all"
            review = await core.agent_workspace(
                action="review_next",
                kind=review_kind,
                max_notes=max_notes,
                max_domains=max_domains,
                limit=limit,
            )

        if not review.get("read_only"):
            raise AssertionError("agent_workspace review_next must be read-only")
        if review.get("review_surface") != "vault":
            raise AssertionError(f"expected vault review surface, got {review.get('review_surface')}")
        if not review.get("items"):
            raise AssertionError("agent_workspace review_next returned no vault review cards")
        if any(not str(item.get("id", "")).startswith("rq-") for item in review["items"]):
            raise AssertionError("vault review cards must use rq-* IDs")

        selected_ids = first_ids(review["items"], min(3, limit))
        preview = await core.agent_workspace(
            action="apply_review_items",
            item_ids=selected_ids,
            max_notes=max_notes,
            max_domains=max_domains,
            limit=limit,
            dry_run=True,
        )
        if preview.get("status") != "preview":
            raise AssertionError(f"dry-run approval did not preview: {preview.get('status')}")

        applied_result = await core.agent_workspace(
            action="apply_review_items",
            item_ids=selected_ids,
            max_notes=max_notes,
            max_domains=max_domains,
            limit=limit,
            dry_run=False,
        )
        if applied_result.get("status") != "applied":
            raise AssertionError(f"selected vault approval did not apply: {applied_result.get('status')}")

        workspace_map = await core.agent_workspace(action="map", max_notes=max_notes, max_domains=max_domains, limit=limit)
        teach = await core.agent_workspace(action="teach", max_notes=max_notes, max_domains=max_domains, limit=min(5, limit))
        grow = await core.agent_workspace(
            action="grow",
            mode="assisted",
            max_notes=max_notes,
            max_domains=max_domains,
            limit=limit,
            dry_run=True,
        )

        artifact_ingest = await core.agent_workspace(
            action="ingest_artifacts",
            source_kind="copy_smoke",
            batch_id="copy-smoke",
            artifacts=[{
                "title": "Copy smoke artifact",
                "source_kind": "copy_smoke",
                "content": (
                    "Decision: keep the public MCP surface small. "
                    "Action: route review and apply through agent_workspace. "
                    "Result: agents can use the workflow without raw low-level tools."
                ),
            }],
        )
        artifact_analysis = await core.agent_workspace(
            action="analyze_inbox",
            source_kind="copy_smoke",
            batch_id="copy-smoke",
            limit=limit,
        )
        artifact_review = await core.agent_workspace(
            action="review_next",
            source_kind="copy_smoke",
            batch_id="copy-smoke",
            limit=min(5, limit),
        )
        aw_ids = first_ids(artifact_review.get("items", []), 1)
        artifact_apply = {}
        if aw_ids:
            artifact_apply = await core.agent_workspace(
                action="apply_review_items",
                item_ids=aw_ids,
                source_kind="copy_smoke",
                batch_id="copy-smoke",
                dry_run=False,
            )

        trace_record = await core.agent_workspace(
            action="record_trace",
            trace={
                "task": "Copy smoke workflow",
                "expected": "Run public LINZA workflow actions on a copied vault only.",
                "result": "Vault review, artifact review, and growth preview completed.",
                "status": "done",
                "tool_calls": [
                    {"name": "agent_workspace.review_next", "status": "ok"},
                    {"name": "agent_workspace.apply_review_items", "arguments": {"dry_run": True}},
                    {"name": "agent_workspace.apply_review_items", "arguments": {"dry_run": False}},
                ],
                "changed_files": [],
                "tests": [{"name": "smoke_copy_vault", "status": "passed"}],
                "errors": [],
            },
        )
        trace_id = trace_record.get("trace", {}).get("id", "")
        calibr_review = await core.agent_workspace(action="review_calibr", trace_id=trace_id, limit=min(5, limit))

        applied_count = applied_result.get("summary", {}).get("applied", 0)
        status_counts = by_kind([
            {"kind": item.get("approval_result", {}).get("status", "unknown")}
            for item in applied_result.get("items", [])
        ])

        approved_total = len(storage.list_approved_items())
    finally:
        storage.close()

    source_hashes_after = hash_markdown_files(source_vault)
    if source_hashes_before != source_hashes_after:
        raise AssertionError("source vault changed during copy smoke")

    copy_bodies_after = body_map(copy_vault)
    body_changes = [
        rel for rel, before in copy_bodies_before.items()
        if copy_bodies_after.get(rel) != before
    ]
    if body_changes:
        raise AssertionError(f"copy note bodies changed: {len(body_changes)}")

    return {
        "status": "ok",
        "source_markdown_files": len(source_hashes_before),
        "copy_markdown_files": len(copy_bodies_before),
        "copy_vault": str(copy_vault.relative_to(WORKSPACE_ROOT)),
        "doctor": {
            "before": doctor_before.get("status"),
            "after": doctor_after.get("status"),
            "indexed_files": doctor_after.get("counts", {}).get("indexed_files", 0),
        },
        "guide": {
            "stage": guide.get("stage", {}).get("id"),
            "primary_tool": guide.get("next_step", {}).get("primary_tool"),
            "primary_action": guide.get("next_step", {}).get("primary_arguments", {}).get("action"),
            "approval_action": guide.get("next_step", {}).get("approval_arguments", {}).get("action"),
        },
        "vault_review": {
            "kind": review_kind,
            "items": len(review["items"]),
            "by_kind": by_kind(review["items"]),
            "selected_ids": len(selected_ids),
            "dry_run_status": preview.get("status"),
            "apply_status": applied_result.get("status"),
        },
        "workspace_map": {
            "status": workspace_map.get("status"),
            "domains": len(workspace_map.get("workspace_map", {}).get("domains", [])),
            "pending_review": workspace_map.get("workspace_map", {}).get("pending_review", {}),
        },
        "supervised_growth": {
            "teach_status": teach.get("status"),
            "teach_cards": len(teach.get("teaching", {}).get("cards", [])),
            "grow_status": grow.get("status"),
            "grow_dry_run": grow.get("dry_run"),
            "selected_ids": len(grow.get("growth", {}).get("selected_ids", [])),
        },
        "artifact_flow": {
            "stored": artifact_ingest.get("summary", {}).get("stored", 0),
            "reviewable_events": artifact_analysis.get("summary", {}).get("reviewable_events", 0),
            "review_items": len(artifact_review.get("items", [])),
            "applied_aw_items": artifact_apply.get("summary", {}).get("applied", 0) if artifact_apply else 0,
        },
        "calibr": {
            "trace_recorded": bool(trace_id),
            "review_items": len(calibr_review.get("items", [])),
        },
        "selected_approval_statuses": status_counts,
        "selected_approvals_written_or_recorded": applied_count,
        "approved_records": approved_total,
        "source_changed": False,
        "copy_note_body_changes": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test LINZA on a Markdown-only copy of a vault.")
    parser.add_argument("--source-vault", type=Path, default=WORKSPACE_ROOT / "Obsidian" / "base")
    parser.add_argument("--workdir", type=Path, default=REPO_ROOT / ".test-tmp")
    parser.add_argument("--max-notes", type=int, default=120)
    parser.add_argument("--max-domains", type=int, default=8)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--embed-provider", default=os.environ.get("LINZA_EMBED_PROVIDER", "smoke"))
    parser.add_argument("--embed-model", default=os.environ.get("LINZA_EMBED_MODEL"))
    parser.add_argument("--embed-url", default=os.environ.get("LINZA_EMBED_URL", "http://127.0.0.1:1234/v1"))
    parser.add_argument("--embed-key", default=os.environ.get("LINZA_EMBED_KEY"))
    args = parser.parse_args()

    summary = asyncio.run(run_smoke(
        args.source_vault,
        args.workdir,
        args.max_notes,
        args.max_domains,
        args.limit,
        args.embed_provider,
        args.embed_model,
        args.embed_url,
        args.embed_key,
    ))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
