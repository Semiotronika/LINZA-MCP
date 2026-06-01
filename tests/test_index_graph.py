from tests.test_support import *


class IndexGraphTests(OperatorTestCase):

    def test_chunk_markdown_is_stable_heading_aware_and_hashes_offsets(self):
        from linza_mcp.chunker import CHUNKER_VERSION, chunk_markdown

        text = "# Root\n\nAlpha paragraph.\n\n## Details\n\nBeta paragraph with enough words for a second block.\n"

        chunks = chunk_markdown(text, source_id="note.md", max_chars=45, overlap_chars=8)
        chunks_again = chunk_markdown(text, source_id="note.md", max_chars=45, overlap_chars=8)

        self.assertEqual(chunks, chunks_again)
        self.assertEqual([chunk["index"] for chunk in chunks], list(range(len(chunks))))
        self.assertEqual(chunks[0]["source_id"], "note.md")
        self.assertTrue(chunks[0]["chunk_id"].startswith("chunk:"))
        self.assertEqual(chunks[0]["id"], chunks[0]["chunk_id"])
        self.assertEqual(chunks[0]["chunker_version"], CHUNKER_VERSION)
        self.assertEqual(chunks[0]["heading"], "Root")
        self.assertEqual(chunks[-1]["heading"], "Details")
        self.assertTrue(all(chunk["start_char"] < chunk["end_char"] for chunk in chunks))
        self.assertTrue(all(chunk["char_count"] <= 45 + 8 for chunk in chunks))
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        self.assertTrue(all(chunk["text"] == normalized[chunk["start_char"]:chunk["end_char"]] for chunk in chunks))
        self.assertTrue(all(chunk["start"] == chunk["start_char"] for chunk in chunks))
        self.assertTrue(all(chunk["end"] == chunk["end_char"] for chunk in chunks))
        self.assertTrue(all(chunk["body_start_char"] >= chunk["start_char"] for chunk in chunks))
        self.assertTrue(all(chunk["body_end_char"] == chunk["end_char"] for chunk in chunks))
        self.assertTrue(all(chunk["body_hash"] for chunk in chunks))
        self.assertTrue(all(chunk["text_hash"] for chunk in chunks))

    def test_index_vault_stores_note_chunk_embeddings(self):
        class TinyProvider:
            model = "tiny"

            async def embed(self, texts):
                vectors = []
                for text in texts:
                    lower = text.lower()
                    if "alpha" in lower:
                        vectors.append([1.0, 0.0])
                    elif "beta" in lower:
                        vectors.append([0.0, 1.0])
                    else:
                        vectors.append([0.5, 0.5])
                return vectors

        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        storage = Storage(vault / ".linza" / "linza.db")
        core = LinzaCore(vault, storage, TinyProvider())
        try:
            (vault / "Alpha.md").write_text(
                "# Alpha\n\nAlpha paragraph for chunk search.\n\n## Beta\n\nBeta paragraph for bridge evidence.\n",
                encoding="utf-8",
            )

            asyncio.run(core.index_vault(force=True))

            chunks = storage.list_chunk_embeddings("Alpha.md")
            self.assertGreaterEqual(len(chunks), 2)
            self.assertEqual(storage.get_chunk_embedding_count(), len(chunks))
            self.assertTrue(all(chunk["path"] == "Alpha.md" for chunk in chunks))
            self.assertTrue(all(chunk["chunk_id"].startswith("chunk:") for chunk in chunks))
            self.assertTrue(all(chunk["chunker_version"] >= 1 for chunk in chunks))
            self.assertTrue(all(chunk["body_hash"] for chunk in chunks))
            self.assertTrue(all(chunk["text_hash"] for chunk in chunks))
            self.assertEqual(chunks[0]["embedding_provider"], "TinyProvider")
            self.assertEqual(chunks[0]["embedding_model"], "tiny")
            self.assertEqual(chunks[0]["embedding_dim"], 2)
            self.assertEqual(chunks[0]["embedding"], [1.0, 0.0])
        finally:
            storage.close()
            tmp.cleanup()

    def test_search_chunk_embeddings_uses_centered_scoring_for_large_global_sets(self):
        from linza_mcp.chunker import CHUNKER_VERSION
        from linza_mcp.indexing import search_chunk_embeddings

        class QueryProvider:
            async def embed(self, texts):
                if texts != ["needle"]:
                    raise AssertionError(texts)
                return [[1.0, 0.0]]

        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        storage = Storage(vault / ".linza" / "linza.db")
        core = LinzaCore(vault, storage, QueryProvider())
        try:
            for index in range(50):
                path = f"note-{index}.md"
                vector = [1.0, 0.0] if index == 0 else [0.0, 1.0]
                storage.replace_chunk_embeddings(
                    path,
                    [{
                        "chunk_id": f"chunk:{index}",
                        "id": f"chunk:{index}",
                        "chunker_version": CHUNKER_VERSION,
                        "index": 0,
                        "start_char": 0,
                        "end_char": 10,
                        "body_start_char": 0,
                        "body_end_char": 10,
                        "heading": "",
                        "kind": "paragraph",
                        "body_hash": f"body-{index}",
                        "text_hash": f"text-{index}",
                        "text": "needle" if index == 0 else "background",
                    }],
                    [vector],
                    embedding_provider="QueryProvider",
                    embedding_model="test",
                    embedding_dim=2,
                    file_hash=f"hash-{index}",
                )

            result = asyncio.run(search_chunk_embeddings(core, "needle", top_k=1))

            self.assertEqual(result["score_mode_requested"], "auto")
            self.assertEqual(result["score_mode"], "centered")
            self.assertEqual(result["candidate_count"], 50)
            self.assertEqual(result["matches"][0]["chunk_id"], "chunk:0")
            self.assertEqual(result["matches"][0]["score"], result["matches"][0]["score_centered"])
            self.assertEqual(result["matches"][0]["score_raw"], 1.0)

            scoped = asyncio.run(search_chunk_embeddings(core, "needle", top_k=1, path="note-0.md"))
            self.assertEqual(scoped["score_mode"], "raw")
            self.assertIsNone(scoped["matches"][0]["score_centered"])

            forced = asyncio.run(search_chunk_embeddings(
                core,
                "needle",
                top_k=1,
                path="note-0.md",
                score_mode="centered",
            ))
            self.assertEqual(forced["score_mode"], "raw")
            self.assertIsNone(forced["matches"][0]["score_centered"])
            self.assertEqual(forced["candidate_count"], 1)
        finally:
            storage.close()
            tmp.cleanup()

    def test_rebuild_bridges_uses_centered_chunk_evidence_when_available(self):
        from linza_mcp.chunker import CHUNKER_VERSION
        from linza_mcp.indexing import rebuild_bridges

        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        storage = Storage(vault / ".linza" / "linza.db")
        core = LinzaCore(vault, storage, StableTestEmbeddingProvider(dim=3))
        try:
            storage.upsert_file(
                "Alpha.md",
                "# Alpha\n\nShared needle topic.\n",
                1.0,
                [1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                "hash-alpha",
                embedding_provider="StableTestEmbeddingProvider",
                embedding_model="test-embedding",
                embedding_dim=3,
            )
            storage.upsert_file(
                "Beta.md",
                "# Beta\n\nShared needle topic.\n",
                1.0,
                [1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                "hash-beta",
                embedding_provider="StableTestEmbeddingProvider",
                embedding_model="test-embedding",
                embedding_dim=3,
            )

            for path, prefix in (("Alpha.md", "source"), ("Beta.md", "target")):
                chunks = []
                vectors = []
                for index in range(25):
                    is_needle = index == 0
                    chunks.append({
                        "chunk_id": f"chunk:{prefix}-{index}",
                        "id": f"chunk:{prefix}-{index}",
                        "chunker_version": CHUNKER_VERSION,
                        "index": index,
                        "start_char": index * 10,
                        "end_char": index * 10 + 8,
                        "body_start_char": index * 10,
                        "body_end_char": index * 10 + 8,
                        "heading": "Shared",
                        "kind": "section",
                        "body_hash": f"body-{prefix}-{index}",
                        "text_hash": f"text-{prefix}-{index}",
                        "text": "shared needle topic" if is_needle else "background topic",
                    })
                    if is_needle:
                        vectors.append([1.0, 0.0, 0.0])
                    elif prefix == "source":
                        vectors.append([0.0, 1.0, 0.0])
                    else:
                        vectors.append([0.0, 0.0, 1.0])
                storage.replace_chunk_embeddings(
                    path,
                    chunks,
                    vectors,
                    embedding_provider="StableTestEmbeddingProvider",
                    embedding_model="test-embedding",
                    embedding_dim=3,
                    file_hash=f"hash-{prefix}",
                )

            asyncio.run(rebuild_bridges(core, threshold=0.1))

            bridges = storage.get_all_bridges()
            self.assertEqual(len(bridges), 1)
            bridge = bridges[0]
            self.assertGreater(bridge["note_score"], 0.9)
            self.assertEqual(bridge["chunk_score_mode"], "centered")
            self.assertEqual(bridge["chunk_score"], bridge["chunk_score_centered"])
            self.assertEqual(bridge["evidence"]["source"]["chunk_id"], "chunk:source-0")
            self.assertEqual(bridge["evidence"]["target"]["chunk_id"], "chunk:target-0")
            self.assertIn("shared needle topic", bridge["evidence"]["source"]["snippet"])
        finally:
            storage.close()
            tmp.cleanup()

    def test_guide_next_steps_routes_domain_seed_to_role_review(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            (vault / "Product" / "Product Overview.md").write_text(
                "# Product Overview\n\nProject overview for a semantic graph and review queue.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "Product Concept.md").write_text(
                "# Product Concept\n\nConcept note about automatic domains and reviewed hierarchy.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "Product Decision.md").write_text(
                "# Product Decision\n\nDecision: apply confident examples only after review.\n",
                encoding="utf-8",
            )
            storage.record_approved_item("domain", {"domain_name": "Product"})

            guide = asyncio.run(core.guide_next_steps(
                max_notes=20,
                max_domains=4,
                limit=20,
                include_tool_guide=True,
            ))

            self.assertEqual(guide["tool"], "guide_next_steps")
            self.assertTrue(guide["read_only"])
            self.assertEqual(guide["stage"]["id"], "review_roles")
            self.assertEqual(guide["next_step"]["primary_tool"], "agent_workspace")
            self.assertEqual(guide["next_step"]["primary_arguments"]["action"], "review_next")
            self.assertEqual(guide["next_step"]["approval_tool"], "agent_workspace")
            self.assertEqual(guide["next_step"]["approval_arguments"]["action"], "apply_review_items")
            self.assertEqual(guide["user_view"]["mode"], "human_onboarding")
            self.assertIn("technical", guide["user_view"])
            self.assertEqual(guide["user_view"]["route"][1]["status"], "current")
            self.assertIn("\u0444\u043e\u0440\u043c\u0430\u0442", guide["user_view"]["route"][1]["title"].lower())
            user_dump = json.dumps(
                {key: value for key, value in guide["user_view"].items() if key != "technical"},
                ensure_ascii=False,
            )
            self.assertNotIn("build_review_apply_queue", user_dump)
            self.assertNotIn("label_en", user_dump)
            self.assertIn("\u0444\u043e\u0440\u043c\u0430\u0442", user_dump.lower())
            self.assertGreaterEqual(guide["pending"]["material_type"], 1)
            self.assertEqual(guide["approved"]["domain"], 1)
            self.assertIn("roles", guide["stage_sequence"][1]["id"])
            self.assertIn("label_human", guide["stage_sequence"][1])
            self.assertTrue(guide["recommended_cards"])
            self.assertTrue(all(card.get("kind") == "material_type" for card in guide["recommended_cards"]))
            self.assertTrue(all(card.get("human", {}).get("question") for card in guide["recommended_cards"]))
            self.assertIn("build_review_apply_queue", guide["tool_guide"])
            self.assertEqual(guide["tool_guide"]["approve_review_queue_items"]["default_mode"], "dry_run")
            self.assertIn("write_scope", guide["tool_guide"]["approve_review_queue_items"])
        finally:
            storage.close()
            tmp.cleanup()

    def test_index_recenters_profiles_created_before_corpus_mean(self):
        class TinyProvider:
            async def embed(self, texts):
                vectors = []
                for text in texts:
                    lower = text.lower()
                    if "general" in lower:
                        vectors.append([2.0, 2.0])
                    elif "alpha" in lower:
                        vectors.append([1.0, 0.0])
                    elif "beta" in lower:
                        vectors.append([0.0, 1.0])
                    else:
                        vectors.append([0.5, 0.5])
                return vectors

        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        storage = Storage(vault / ".linza" / "linza.db")
        core = LinzaCore(vault, storage, TinyProvider())
        try:
            asyncio.run(core.create_profile("general", "general knowledge"))
            before = storage.get_profile("general")
            self.assertEqual(before["raw_embedding"], before["centered_embedding"])

            (vault / "Alpha.md").write_text("alpha", encoding="utf-8")
            (vault / "Beta.md").write_text("beta", encoding="utf-8")
            asyncio.run(core.index_vault(force=True))

            after = storage.get_profile("general")
            self.assertEqual(after["raw_embedding"], [2.0, 2.0])
            self.assertEqual(after["centered_embedding"], [1.5, 1.5])
        finally:
            storage.close()
            tmp.cleanup()

    def test_embedding_signature_mismatch_blocks_search_and_bridges(self):
        from linza_mcp.indexing import embedding_index_status

        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Old.md").write_text("Old indexed note.\n", encoding="utf-8")
            storage.upsert_file(
                "Old.md",
                "Old indexed note.\n",
                0,
                [1.0, 0.0],
                [1.0, 0.0],
                "old-hash",
                embedding_provider="OldProvider",
                embedding_model="old-model",
                embedding_dim=2,
            )

            status = embedding_index_status(core)
            self.assertEqual(status["status"], "needs_reindex")
            self.assertEqual(status["mismatch_count"], 1)

            asyncio.run(core.rebuild_bridges())
            self.assertEqual(storage.get_all_bridges(), [])

            search = asyncio.run(core.search("old note"))
            self.assertEqual(search["error"], "embedding_signature_mismatch")

            with self.assertRaises(RuntimeError):
                asyncio.run(core.index_single_file("Old.md", "Updated old note."))
        finally:
            storage.close()
            tmp.cleanup()

    def test_search_blocks_stale_source_index(self):
        import os
        import time

        tmp, vault, storage, core = self.make_core()
        try:
            note = vault / "Project.md"
            note.write_text("Decision: index the first version.\n", encoding="utf-8")
            asyncio.run(core.index_vault(force=True))

            note.write_text(
                "Decision: index the first version.\nAction: changed after indexing.\n",
                encoding="utf-8",
            )
            changed_time = time.time() + 5
            os.utime(note, (changed_time, changed_time))

            result = asyncio.run(core.search("changed after indexing", top_k=3))

            self.assertEqual(result["error"], "source_index_stale")
            self.assertEqual(result["sync"]["status"], "stale")
            self.assertEqual(result["sync"]["changed_count"], 1)
        finally:
            storage.close()
            tmp.cleanup()

    def test_bridge_pair_guard_skips_large_pairwise_rebuild(self):
        tmp, vault, storage, core = self.make_core()
        try:
            core.config["max_bridge_pairs"] = 1
            for name in ["Alpha.md", "Beta.md", "Gamma.md"]:
                (vault / name).write_text(
                    "Shared semantic bridge material for the same product workflow.\n",
                    encoding="utf-8",
                )

            asyncio.run(core.index_vault(force=True))

            self.assertEqual(storage.get_file_count(), 3)
            self.assertEqual(storage.get_all_bridges(), [])
        finally:
            storage.close()
            tmp.cleanup()

    def test_russian_tokenize_and_lexical_score_work(self):
        from linza_mcp.indexing import lexical_score
        from linza_mcp.utils import tokenize

        query = "\u0430\u043d\u0438\u0437\u043e\u0442\u0440\u043e\u043f\u0438\u044f \u044d\u043c\u0431\u0435\u0434\u0434\u0438\u043d\u0433\u043e\u0432 \u0441\u0435\u043c\u0430\u043d\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043f\u043e\u0438\u0441\u043a"
        content = "Mean-centered embeddings: \u0430\u043d\u0438\u0437\u043e\u0442\u0440\u043e\u043f\u0438\u044f \u044d\u043c\u0431\u0435\u0434\u0434\u0438\u043d\u0433\u043e\u0432 \u0438 \u0441\u0435\u043c\u0430\u043d\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043f\u043e\u0438\u0441\u043a."
        tokens = tokenize(query)
        self.assertIn("\u0430\u043d\u0438\u0437\u043e\u0442\u0440\u043e\u043f\u0438\u044f", tokens)
        self.assertIn("\u044d\u043c\u0431\u0435\u0434\u0434\u0438\u043d\u0433\u043e\u0432", tokens)
        score, overlap = lexical_score(query, content)
        self.assertGreater(score, 0.0)
        self.assertGreaterEqual(overlap, 1)

    def test_search_does_not_hide_exact_lexical_match_behind_semantic_noise(self):
        class NoisyProvider:
            async def embed(self, texts):
                vectors = []
                for text in texts:
                    lower = text.lower()
                    if "\u0430\u043d\u0438\u0437\u043e\u0442\u0440\u043e\u043f\u0438\u044f" in lower:
                        vectors.append([0.0, 1.0])
                    elif "unrelated" in lower:
                        vectors.append([1.0, 0.0])
                    else:
                        vectors.append([1.0, 0.0])
                return vectors

        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        storage = Storage(vault / ".linza" / "linza.db")
        core = LinzaCore(vault, storage, NoisyProvider())
        try:
            exact = vault / "Exact.md"
            exact.write_text(
                "\u0410\u043d\u0438\u0437\u043e\u0442\u0440\u043e\u043f\u0438\u044f \u044d\u043c\u0431\u0435\u0434\u0434\u0438\u043d\u0433\u043e\u0432 \u0438 \u0441\u0435\u043c\u0430\u043d\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043f\u043e\u0438\u0441\u043a.",
                encoding="utf-8",
            )
            (vault / "Distractor.md").write_text(
                "unrelated generic systems note",
                encoding="utf-8",
            )

            asyncio.run(core.index_vault(force=True))
            result = asyncio.run(core.search(
                "\u0430\u043d\u0438\u0437\u043e\u0442\u0440\u043e\u043f\u0438\u044f \u044d\u043c\u0431\u0435\u0434\u0434\u0438\u043d\u0433\u043e\u0432 \u0441\u0435\u043c\u0430\u043d\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u0439 \u043f\u043e\u0438\u0441\u043a",
                top_k=2,
            ))

            self.assertEqual(result["results"][0]["path"], "Exact.md")
            self.assertGreater(result["results"][0]["lexical_score"], 0.0)
        finally:
            storage.close()
            tmp.cleanup()

    def test_diagnostics_property_reports_are_read_only(self):
        tmp, vault, storage, core = self.make_core()
        try:
            project = vault / "Project Plan.md"
            project.write_text(
                "# Project Plan\n\n"
                "Project plan with TODO section.\n\n"
                "TODO\n- Review the next milestone.\n\n"
                "It references [[Missing Node]] so the review report has a concrete candidate.\n",
                encoding="utf-8",
            )
            original = project.read_text(encoding="utf-8")

            suggestion = core.suggest_properties_for_note("Project Plan.md")
            self.assertEqual(suggestion["path"], "Project Plan.md")
            self.assertEqual(suggestion["role"], "untyped")
            self.assertEqual(suggestion["yaml_preview"], "")
            self.assertTrue(suggestion["write_policy"].startswith("read-only"))

            yaml_report = core.build_yaml_suggestions_markdown(limit=10)
            self.assertIn("# LINZA YAML Suggestions", yaml_report)
            self.assertNotIn("```yaml", yaml_report)

            review_report = core.build_review_queue_markdown(limit=10)
            self.assertIn("# LINZA Review Queue", review_report)
            self.assertIn("fix_link", review_report)
            self.assertEqual(project.read_text(encoding="utf-8"), original)
        finally:
            storage.close()
            tmp.cleanup()

    def test_explain_node_resolves_title_and_reports_graph_context(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Alpha.md").write_text(
                "---\ntags:\n  - project\nlinza:\n  role: project\n---\n"
                "# Alpha\n\nAlpha links to [[Beta]] and [[Missing Node]].\n",
                encoding="utf-8",
            )
            (vault / "Beta.md").write_text(
                "# Beta\n\nBeta links back to [[Alpha]].\n",
                encoding="utf-8",
            )
            storage.update_bridges([
                {"source": "Alpha.md", "target": "Beta.md", "score": 0.82, "type": "semantic"}
            ])

            result = core.explain_node("Alpha")

            self.assertEqual(result["tool"], "explain_node")
            self.assertTrue(result["read_only"])
            self.assertEqual(result["path"], "Alpha.md")
            self.assertEqual(result["linza"], {"role": "project"})
            self.assertEqual(result["explicit_graph"]["incoming"], ["Beta.md"])
            self.assertEqual(result["explicit_graph"]["outgoing"], ["Beta.md"])
            self.assertEqual(
                result["explicit_graph"]["broken_outgoing_links"],
                [{"source": "Alpha.md", "target": "missing node"}],
            )
            self.assertEqual(result["semantic_bridges"][0]["target"], "Beta.md")
        finally:
            storage.close()
            tmp.cleanup()

    def test_who_depends_layers_backlinks_and_marks_semantic_neighbors(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Alpha.md").write_text("Alpha body.\n", encoding="utf-8")
            (vault / "Beta.md").write_text("Beta depends on [[Alpha]].\n", encoding="utf-8")
            (vault / "Gamma.md").write_text("Gamma depends on [[Beta]].\n", encoding="utf-8")
            storage.update_bridges([
                {"source": "Alpha.md", "target": "Gamma.md", "score": 0.71, "type": "semantic"}
            ])

            result = core.who_depends("Alpha.md", depth=3)

            self.assertEqual(result["explicit_dependents"], ["Beta.md"])
            self.assertEqual(result["this_depends_on"], [])
            self.assertEqual(result["dependent_layers"], [
                {"depth": 1, "nodes": ["Beta.md"]},
                {"depth": 2, "nodes": ["Gamma.md"]},
            ])
            self.assertEqual(result["semantic_neighbors"], ["Gamma.md"])
        finally:
            storage.close()
            tmp.cleanup()

    def test_show_flow_finds_node_to_node_route(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Alpha.md").write_text("Alpha links to [[Beta]].\n", encoding="utf-8")
            (vault / "Beta.md").write_text("Beta links to [[Gamma]].\n", encoding="utf-8")
            (vault / "Gamma.md").write_text("Gamma body.\n", encoding="utf-8")

            result = asyncio.run(core.show_flow(source="Alpha.md", target="Gamma.md", max_depth=3))

            self.assertEqual(result["mode"], "node_to_node")
            self.assertTrue(result["found"])
            self.assertEqual([item["path"] for item in result["route"]], ["Alpha.md", "Beta.md", "Gamma.md"])
            self.assertEqual([item["edge"] for item in result["route"]], ["start", "wikilink_out", "wikilink_out"])
        finally:
            storage.close()
            tmp.cleanup()

    def test_show_flow_uses_approved_sidecar_edges_with_confidence_labels(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Alpha.md").write_text("Alpha source.\n", encoding="utf-8")
            (vault / "Gamma.md").write_text("Gamma target.\n", encoding="utf-8")
            storage.record_approved_item("causal_link", {
                "source_path": "Alpha.md",
                "target_path": "Gamma.md",
                "relation": "led_to",
                "evidence": "Alpha led to Gamma after human review.",
            })

            result = asyncio.run(core.show_flow(source="Alpha.md", target="Gamma.md", max_depth=2))

            self.assertTrue(result["found"])
            self.assertEqual([item["path"] for item in result["route"]], ["Alpha.md", "Gamma.md"])
            self.assertEqual(result["route"][1]["edge"], "approved_causal")
            self.assertEqual(result["route"][1]["confidence"], "APPROVED")
            self.assertEqual(result["route"][1]["relation"], "led_to")
        finally:
            storage.close()
            tmp.cleanup()

    def test_check_rule_filters_rule_output_to_one_note(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Alpha.md").write_text("Alpha links to [[Missing Node]].\n", encoding="utf-8")
            (vault / "Beta.md").write_text("Beta is isolated.\n", encoding="utf-8")

            result = core.check_rule("broken_links", path="Alpha")

            self.assertEqual(result["tool"], "check_rule")
            self.assertEqual(result["path"], "Alpha.md")
            self.assertEqual(result["status"], "warning")
            self.assertEqual(result["issue_count"], 1)
            self.assertEqual(
                result["results"],
                {"broken_links": [{"source": "Alpha.md", "target": "missing node"}]},
            )
        finally:
            storage.close()
            tmp.cleanup()

    def test_index_single_file_replaces_existing_vector_in_corpus_mean(self):
        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        storage = Storage(vault / ".linza" / "linza.db")
        core = LinzaCore(vault, storage, StableTestEmbeddingProvider(dim=2))
        try:
            (vault / "Alpha.md").write_text("alpha v1", encoding="utf-8")
            (vault / "Beta.md").write_text("beta", encoding="utf-8")

            asyncio.run(core.index_vault(with_embeddings=True))
            mean, count = storage.load_corpus_mean()
            self.assertEqual(count, 2)

            (vault / "Alpha.md").write_text("alpha v2", encoding="utf-8")
            asyncio.run(core.index_vault(with_embeddings=True))

            mean, count = storage.load_corpus_mean()
            self.assertEqual(count, 2)
        finally:
            storage.close()
            tmp.cleanup()

    def test_index_single_file_recomputes_corpus_mean_after_delete(self):
        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        storage = Storage(vault / ".linza" / "linza.db")
        core = LinzaCore(vault, storage, StableTestEmbeddingProvider(dim=2))
        try:
            (vault / "Alpha.md").write_text("alpha", encoding="utf-8")
            (vault / "Beta.md").write_text("beta", encoding="utf-8")
            asyncio.run(core.index_vault(with_embeddings=True))

            (vault / "Beta.md").unlink()
            # Re-index (delete handled by re-scanning vault)
            asyncio.run(core.index_vault(with_embeddings=True))

            mean, count = storage.load_corpus_mean()
            self.assertEqual(count, 1)
        finally:
            storage.close()
            tmp.cleanup()

    def test_indexing_module_powers_profile_search_links_and_context_pack(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Orbit Research.md").write_text(
                "# Orbit Research\n\n"
                "Orbit telescope physics mission data orbit telescope calibration.\n",
                encoding="utf-8",
            )
            (vault / "Kitchen Notes.md").write_text(
                "# Kitchen Notes\n\n"
                "Bread recipe flour oven sourdough kitchen schedule.\n",
                encoding="utf-8",
            )
            (vault / "Orbit Followup.md").write_text(
                "# Orbit Followup\n\n"
                "Telescope orbit mission analysis and physics followup notes.\n",
                encoding="utf-8",
            )

            asyncio.run(core.index_vault(with_embeddings=True))
            calibration = core.calibrate_embeddings()
            self.assertEqual(calibration["status"], "ok")

            created = asyncio.run(core.create_profile(
                "space",
                "orbit telescope physics mission",
                "Space research focus",
            ))
            self.assertEqual(created["status"], "created")

            result = asyncio.run(core.search(
                "orbit telescope physics",
                profile_name="space",
                top_k=2,
                explain=True,
            ))

            self.assertEqual(result["retrieval"], "mean-centered embeddings + lexical overlap")
            self.assertEqual(result["profile"], "space")
            result_paths = [item["path"] for item in result["results"]]
            self.assertIn("Orbit Research.md", result_paths)
            self.assertIn("Orbit Followup.md", result_paths)
            self.assertGreater(storage.get_profile("space")["usage_count"], 0)
            self.assertIn("Profile: 'space'", result["explanation"])

            links = asyncio.run(core.suggest_links("Orbit Research.md", top_k=2))
            self.assertTrue(any(item["path"] == "Orbit Followup.md" for item in links))
            relation = core.classify_relation_candidate("Orbit Research.md", "Orbit Followup.md", 0.7)
            self.assertIn("relation", relation)

            markdown = core.build_context_pack_markdown(
                "Space Pack",
                "orbit telescope physics",
                [item["path"] for item in result["results"]],
            )
            self.assertIn("# Context Pack: Space Pack", markdown)
            self.assertIn("[[Orbit Research]]", markdown)
        finally:
            storage.close()
            tmp.cleanup()
