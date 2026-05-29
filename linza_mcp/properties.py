"""Safe note property patching for LINZA."""

from __future__ import annotations

from typing import Any, Dict

from .utils import is_legacy_graph_metadata, patch_frontmatter, safe_vault_path, strip_frontmatter


def _read_text_exact(path) -> str:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return handle.read()


def _write_text_exact(path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)


def patch_note_properties(
    core,
    path: str,
    properties: Dict[str, Any],
    dry_run: bool = True,
    allow_overwrite: bool = False,
    namespace: str = "linza",
) -> Dict[str, Any]:
    try:
        rel, full = safe_vault_path(core.storage.vault_path, path)
    except ValueError as exc:
        return {"error": str(exc), "path": path}
    if not full.exists() or not full.is_file():
        return {"error": "file not found", "path": path}

    original = _read_text_exact(full)
    metadata, original_body = strip_frontmatter(original)
    updated, changes, skipped = patch_frontmatter(
        original,
        properties,
        allow_overwrite=allow_overwrite,
        namespace=namespace,
    )
    result = {
        "path": rel,
        "dry_run": dry_run,
        "changes": changes,
        "skipped": skipped,
        "body_preserved": True,
        "namespace": namespace,
        "yaml_style": "user-facing flat properties",
        "legacy_graph_metadata_detected": is_legacy_graph_metadata(metadata),
        "protected_fields": ["sign", "level", "parents", "parents_meta", "artifact_sign"],
    }
    if is_legacy_graph_metadata(metadata):
        result["protected_fields"].extend(["type", "status", "tags"])
    _, updated_body = strip_frontmatter(updated)
    if updated_body != original_body:
        result["status"] = "blocked"
        result["body_preserved"] = False
        result["error"] = "body changed while patching properties"
        return result
    if dry_run or not changes:
        result["status"] = "preview"
        return result

    _write_text_exact(full, updated)
    result["status"] = "written"
    return result


__all__ = ["patch_note_properties"]
