import tempfile
import unittest
from pathlib import Path

from linza_mcp import (
    LinzaCore,
    LinzaStorage,
    extract_tag_details,
    extract_tags,
    normalize_tag,
)
from tests.test_support import StableTestEmbeddingProvider


class TagVocabularyTests(unittest.TestCase):
    def test_extract_tags_normalizes_yaml_and_ignores_inline_colors(self):
        content = """---
tags:
  - Research
  - гранты
---
# Heading
<span style="color:#FF00A1">pink</span>
#inline_tag #local/
"""
        metadata = {"tags": ["Research", "гранты"]}

        self.assertEqual(normalize_tag(" Research "), "research")
        self.assertEqual(normalize_tag("local/"), "local")
        self.assertIsNone(normalize_tag("FF00A1"))
        self.assertEqual(extract_tags(content, metadata), ["inline-tag", "local", "research", "гранты"])

        details = extract_tag_details(content, metadata)
        self.assertIn({"raw": "FF00A1", "reason": "not_a_tag"}, details["ignored_inline"])

    def test_audit_tag_vocabulary_reports_aliases_and_false_inline_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "A.md").write_text(
                "---\ntags:\n  - грант\n  - Research\n---\nBody #FFFFFF\n",
                encoding="utf-8",
            )
            (vault / "B.md").write_text(
                "---\ntags:\n  - гранты\n  - research\n---\nBody #context_tag\n",
                encoding="utf-8",
            )

            storage = LinzaStorage(vault, vault / ".linza" / "linza.db")
            try:
                core = LinzaCore(storage, StableTestEmbeddingProvider(), {})
                audit = core.audit_tag_vocabulary()
            finally:
                storage.close()

        self.assertEqual(audit["summary"]["notes_scanned"], 2)
        self.assertEqual(audit["summary"]["ignored_inline_tags"], 1)
        self.assertIn(("FFFFFF", 1), audit["ignored_inline_tags"])
        aliases = {(item["left"], item["right"]) for item in audit["alias_candidates"]}
        self.assertIn(("грант", "гранты"), aliases)
        variants = {item["canonical"]: item for item in audit["variant_groups"]}
        self.assertIn("research", variants)

    def test_suggest_tag_candidates_uses_chunks_without_writing_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "Source.md").write_text(
                "---\ntags:\n  - retrieval-layer\n---\nSource note\n",
                encoding="utf-8",
            )
            target = vault / "Log.md"
            original = (
                "---\ntype: artifact\n---\n"
                "# Session log\n\n"
                "We debugged the retrieval layer and chunk search contract.\n\n"
                "The retrieval layer must stay reviewable before any tag is accepted.\n"
            )
            target.write_text(original, encoding="utf-8")

            storage = LinzaStorage(vault, vault / ".linza" / "linza.db")
            try:
                core = LinzaCore(storage, StableTestEmbeddingProvider(), {})
                result = core.suggest_tag_candidates("Log.md")
            finally:
                storage.close()

            self.assertTrue(result["read_only"])
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            candidates = {item["tag"]: item for item in result["candidate_tags"]}
            self.assertIn("retrieval-layer", candidates)
            self.assertEqual(candidates["retrieval-layer"]["source"], "vocabulary_hit")
            self.assertEqual(candidates["retrieval-layer"]["status"], "candidate")
            self.assertTrue(candidates["retrieval-layer"]["evidence"])
            self.assertIn("chunk_id", candidates["retrieval-layer"]["evidence"][0])

    def test_suggest_tag_candidates_separates_existing_yaml_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            (vault / "Tagged.md").write_text(
                "---\ntags:\n  - Clean_Tag\n---\nBody with #inline_tag and repeated ontology ontology.\n",
                encoding="utf-8",
            )

            storage = LinzaStorage(vault, vault / ".linza" / "linza.db")
            try:
                core = LinzaCore(storage, StableTestEmbeddingProvider(), {})
                result = core.suggest_tag_candidates("Tagged.md")
            finally:
                storage.close()

        existing = {item["tag"] for item in result["existing_tags"]}
        candidates = {item["tag"]: item for item in result["candidate_tags"]}
        self.assertEqual(existing, {"clean-tag"})
        self.assertNotIn("clean-tag", candidates)
        self.assertIn("inline-tag", candidates)
        self.assertEqual(candidates["inline-tag"]["source"], "inline")


if __name__ == "__main__":
    unittest.main()
