"""Run a LINZA smoke test against a Markdown-only copy of a vault.

The script is intentionally private-output safe: it prints aggregate counts only,
not note titles, note text, or generated domain names.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from server import HashingEmbeddingProvider, LinzaCore, LinzaStorage, strip_frontmatter  # noqa: E402


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


async def run_smoke(source_vault: Path, workdir: Path, max_notes: int, max_domains: int, limit: int) -> dict[str, Any]:
    source_vault = source_vault.resolve()
    workdir = workdir.resolve()
    if not source_vault.exists():
        raise FileNotFoundError(f"source vault not found: {source_vault}")

    source_hashes_before = hash_markdown_files(source_vault)
    copy_vault = copy_markdown_vault(source_vault, workdir)
    copy_bodies_before = body_map(copy_vault)

    storage = LinzaStorage(copy_vault, copy_vault / ".linza" / "linza.db")
    core = LinzaCore(storage, HashingEmbeddingProvider(), {})
    applied: list[str] = []
    try:
        draft = await core.draft_vault_map(max_notes=max_notes, max_domains=max_domains)
        queue = await core.build_review_apply_queue(max_notes=max_notes, max_domains=max_domains, limit=limit)

        if not draft.get("read_only"):
            raise AssertionError("draft_vault_map must be read-only")
        if not queue.get("read_only"):
            raise AssertionError("build_review_apply_queue must be read-only")
        if not queue.get("items"):
            raise AssertionError("review/apply queue is empty")
        if any(not item.get("approval", {}).get("arguments", {}).get("dry_run") for item in queue["items"]):
            raise AssertionError("all queue approval payloads must keep dry_run=true")

        report_rel = Path("LINZA") / "06 Review Apply Queue.md"
        report_path = copy_vault / report_rel
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(queue["markdown"])

        selected_ids: list[str] = []
        for item_type in ("role", "domain", "hierarchy_link", "causal_link"):
            item_id = first_item_id(queue, item_type)
            if not item_id:
                continue
            selected_ids.append(item_id)
            applied.append(item_type)

        result = await core.approve_review_queue_items(
            selected_ids,
            max_notes=max_notes,
            max_domains=max_domains,
            limit=limit,
            dry_run=False,
        )
        if result.get("error") or result.get("missing_ids"):
            raise AssertionError(f"selected approval failed: {result}")
        if result.get("status") != "applied":
            raise AssertionError(f"selected approval did not apply: {result}")
        matched_count = result.get("summary", {}).get("matched", 0)
        if matched_count != len(selected_ids):
            raise AssertionError(f"selected approval matched only {matched_count}/{len(selected_ids)} items")
        applied_count = result.get("summary", {}).get("applied", 0)
        status_counts = by_kind([
            {"kind": item.get("approval_result", {}).get("status", "unknown")}
            for item in result.get("results", [])
        ])

        approved_total = len(storage.list_approved_items())
    finally:
        storage.close()

    source_hashes_after = hash_markdown_files(source_vault)
    if source_hashes_before != source_hashes_after:
        raise AssertionError("source vault changed during copy smoke")

    copy_bodies_after = body_map(copy_vault)
    report_rel = Path("LINZA") / "06 Review Apply Queue.md"
    body_changes = [
        rel for rel, before in copy_bodies_before.items()
        if rel != report_rel.as_posix() and copy_bodies_after.get(rel) != before
    ]
    if body_changes:
        raise AssertionError(f"copy note bodies changed: {len(body_changes)}")

    return {
        "status": "ok",
        "source_markdown_files": len(source_hashes_before),
        "copy_markdown_files": len(copy_bodies_before),
        "copy_vault": str(copy_vault.relative_to(WORKSPACE_ROOT)),
        "draft_summary": {
            key: draft["summary"].get(key)
            for key in (
                "notes",
                "vault_notes_seen",
                "semantic_chunks",
                "candidate_domains",
                "hierarchy_candidates",
                "role_drafts",
                "event_flow_items",
                "review_items",
            )
        },
        "queue_summary": {
            "items": len(queue["items"]),
            "by_kind": by_kind(queue["items"]),
        },
        "applied_on_copy": applied,
        "selected_approval_statuses": status_counts,
        "selected_approvals_written_or_recorded": applied_count,
        "approved_records": approved_total,
        "report_written": report_rel.as_posix(),
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
    args = parser.parse_args()

    summary = asyncio.run(run_smoke(args.source_vault, args.workdir, args.max_notes, args.max_domains, args.limit))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
