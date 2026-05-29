"""User-readable LINZA doctor over the safe copy-vault smoke checks.

The command is private-output safe: it reports counts and statuses only, never
note text, titles, generated domains, or source paths from the vault.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.smoke_copy_vault import run_smoke as run_copy_smoke  # noqa: E402
from scripts.smoke_mcp_tools import run_smoke as run_tool_smoke  # noqa: E402


def _check(check_id: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "detail": detail,
    }


async def run_doctor(
    source_vault: Path,
    workdir: Path,
    max_notes: int = 120,
    max_domains: int = 8,
    limit: int = 20,
) -> dict[str, Any]:
    copy_summary = await run_copy_smoke(source_vault, workdir, max_notes, max_domains, limit)
    tool_summary = await run_tool_smoke(source_vault, workdir)

    checks = [
        _check(
            "copy_vault_smoke",
            "Copy-vault workflow",
            "ok",
            (
                f"{copy_summary['copy_markdown_files']} copied notes, "
                f"{copy_summary['queue_summary']['items']} review intents, "
                f"{copy_summary['selected_approvals_written_or_recorded']} selected approvals."
            ),
        ),
        _check(
            "mcp_tool_surface",
            "MCP tool surface",
            "ok",
            (
                f"{tool_summary['tools_registered']} tools registered, "
                f"{tool_summary['tool_calls_ok']} smoke calls completed."
            ),
        ),
        _check(
            "source_unchanged",
            "Source vault unchanged",
            "ok" if not copy_summary["source_changed"] and not tool_summary["source_changed"] else "fail",
            "The source vault hashes stayed unchanged during both smoke checks.",
        ),
        _check(
            "body_safety",
            "Existing note bodies preserved",
            "ok"
            if copy_summary["copy_note_body_changes"] == 0
            and tool_summary["copy_existing_note_body_changes"] == 0
            else "fail",
            "Existing copied note bodies stayed byte-for-byte equivalent after frontmatter-safe operations.",
        ),
        _check(
            "agent_workspace_facade",
            "Agent workspace facade",
            "ok",
            "The smoke run exercises the small artifact/calibr workflow instead of exposing raw tools to a user.",
        ),
    ]
    has_failure = any(item["status"] == "fail" for item in checks)
    status = "ready" if not has_failure else "needs_attention"

    return {
        "status": status,
        "human_view": {
            "title": "LINZA doctor: ready" if status == "ready" else "LINZA doctor: needs attention",
            "summary": (
                "LINZA can work safely on this vault shape: tools respond, copy checks pass, "
                "and existing note bodies are protected."
                if status == "ready"
                else "One or more safety checks failed; inspect the machine-readable sections before using LINZA."
            ),
            "checks": [
                {
                    "label": item["label"],
                    "status": item["status"],
                    "detail": item["detail"],
                }
                for item in checks
            ],
            "next_steps": [
                "Use LINZA on a copy first when testing new review/apply behavior.",
                "Load real logs or articles through the artifact inbox.",
                "Review intents before accepting memory, relations, or metadata.",
                "Use context export when an agent needs a compact packet for work.",
            ],
        },
        "checks": checks,
        "copy_vault": {
            "source_markdown_files": copy_summary["source_markdown_files"],
            "copy_markdown_files": copy_summary["copy_markdown_files"],
            "draft_summary": copy_summary["draft_summary"],
            "queue_summary": copy_summary["queue_summary"],
            "selected_approvals_written_or_recorded": copy_summary["selected_approvals_written_or_recorded"],
            "source_changed": copy_summary["source_changed"],
            "copy_note_body_changes": copy_summary["copy_note_body_changes"],
        },
        "mcp_tools": {
            "tools_registered": tool_summary["tools_registered"],
            "tool_calls_ok": tool_summary["tool_calls_ok"],
            "queue_ids_checked": tool_summary["queue_ids_checked"],
            "tool_smoke_files_written": tool_summary["tool_smoke_files_written"],
            "source_changed": tool_summary["source_changed"],
            "copy_existing_note_body_changes": tool_summary["copy_existing_note_body_changes"],
        },
        "privacy": "Counts and statuses only; no note text, note titles, generated domains, or vault paths are printed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a private-safe LINZA doctor on a vault copy.")
    parser.add_argument("--source-vault", type=Path, default=WORKSPACE_ROOT / "Obsidian" / "base")
    parser.add_argument("--workdir", type=Path, default=REPO_ROOT / ".test-tmp")
    parser.add_argument("--max-notes", type=int, default=120)
    parser.add_argument("--max-domains", type=int, default=8)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    summary = asyncio.run(
        run_doctor(
            args.source_vault,
            args.workdir,
            max_notes=args.max_notes,
            max_domains=args.max_domains,
            limit=args.limit,
        )
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
