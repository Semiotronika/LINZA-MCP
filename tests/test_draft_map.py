from tests.test_support import *


class DraftMapTests(OperatorTestCase):

    def test_draft_vault_map_proposes_domains_and_hierarchy_without_writing(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Products").mkdir()
            (vault / "Research").mkdir()
            (vault / "Products" / "Context Server.md").write_text(
                "# Context Server\n\n"
                "Agent context server for Markdown graphs, semantic links, retrieval, and MCP tools.\n\n"
                "## Retrieval\n\n"
                "The server builds context packs and explains relationships between notes.\n",
                encoding="utf-8",
            )
            linza_path = vault / "Products" / "LINZA.md"
            original_linza = (
                "# LINZA\n\n"
                "Zero friction vault onboarding for Markdown notes, automatic domains, review queues, and thresholds.\n\n"
                "## Review queue\n\n"
                "The system shows a draft map before writing anything.\n"
            )
            linza_path.write_text(original_linza, encoding="utf-8")
            (vault / "Research" / "Embedding Geometry.md").write_text(
                "# Embedding Geometry\n\n"
                "Cosine similarity, anisotropy, hubness, and calibrated thresholds for retrieval quality.\n",
                encoding="utf-8",
            )
            (vault / "Research" / "Graph RAG.md").write_text(
                "# Graph RAG\n\n"
                "Knowledge graphs, retrieval paths, citations, and source-aware context reconstruction.\n",
                encoding="utf-8",
            )
            (vault / "Daily Log.md").write_text(
                "# Daily Log\n\n"
                "Today we discussed launch tasks and wrote a short working note.\n",
                encoding="utf-8",
            )

            result = asyncio.run(core.draft_vault_map(max_notes=20, max_domains=4))

            self.assertEqual(result["tool"], "draft_vault_map")
            self.assertTrue(result["read_only"])
            self.assertEqual(result["summary"]["notes"], 5)
            self.assertGreater(result["summary"]["semantic_chunks"], 5)
            self.assertGreaterEqual(result["summary"]["candidate_domains"], 2)
            self.assertTrue(result["candidate_domains"])
            domain_members = [
                set(note["path"] for note in domain["representative_notes"])
                for domain in result["candidate_domains"]
            ]
            self.assertTrue(any({"Products/Context Server.md", "Products/LINZA.md"}.issubset(members) for members in domain_members))
            self.assertTrue(result["hierarchy_draft"])
            contract = result["onboarding_contract"]
            self.assertFalse(contract["root"]["expose_l0"])
            self.assertEqual(contract["root"]["policy"], "implicit_vault_root")
            self.assertEqual(contract["entity_roles"]["policy"], "compat_alias_for_material_types")
            self.assertEqual(contract["material_types"]["policy"], "discover_from_vault_then_review")
            self.assertEqual(contract["material_types"]["baseline_types"], [])
            self.assertTrue(all(item.startswith("type-") for item in contract["material_types"]["suggested_types"]))
            self.assertIn("event_flow", contract["visible_axes"])
            self.assertIn("L0-L5", contract["hidden_engine_mechanics"])
            self.assertIn("LINZA never writes", " ".join(result["policy"]))
            self.assertEqual(original_linza, linza_path.read_text(encoding="utf-8"))
        finally:
            storage.close()
            tmp.cleanup()

    def test_draft_vault_map_uses_embedding_second_pass_to_merge_overlapping_domains(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Products").mkdir()
            (vault / "Labs").mkdir()
            (vault / "Products" / "LINZA Onboarding.md").write_text(
                "# LINZA Onboarding\n\n"
                "Vault onboarding, markdown notes, automatic domains, review queue, semantic map, thresholds.\n",
                encoding="utf-8",
            )
            (vault / "Labs" / "Semantic Vault Map.md").write_text(
                "# Semantic Vault Map\n\n"
                "Markdown vault onboarding with semantic map, automatic domains, review queue, and threshold calibration.\n",
                encoding="utf-8",
            )
            (vault / "Products" / "LINZA Review Queue.md").write_text(
                "# LINZA Review Queue\n\n"
                "Review queue for automatic domain drafts, markdown vault structure, and safe approval workflow.\n",
                encoding="utf-8",
            )
            (vault / "Physics.md").write_text(
                "# Physics\n\n"
                "Cosmology, gravity, thermodynamics, equations, observations, and physical models.\n",
                encoding="utf-8",
            )

            result = asyncio.run(core.draft_vault_map(max_notes=20, max_domains=6))

            second_pass = result["embedding_second_pass"]
            self.assertEqual(second_pass["status"], "ok")
            self.assertGreaterEqual(second_pass["embedded_notes"], 4)
            self.assertGreaterEqual(second_pass["merged_domains"], 1)
            self.assertTrue(any(domain.get("merged_from") for domain in result["candidate_domains"]))
            all_domain_paths = [
                {note["path"] for note in domain["representative_notes"]}
                for domain in result["candidate_domains"]
            ]
            self.assertTrue(any({"Products/LINZA Onboarding.md", "Labs/Semantic Vault Map.md"}.issubset(paths) for paths in all_domain_paths))
        finally:
            storage.close()
            tmp.cleanup()

    def test_draft_vault_map_returns_roles_lenses_and_event_flow(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            (vault / "Work").mkdir()
            (vault / "Product" / "Decision Log.md").write_text(
                "# Decision Log\n\n"
                "Fact: first-run onboarding threshold is too high for a raw vault.\n"
                "Decision: build LINZA as a separate zero-friction MCP server.\n"
                "Action: added draft_vault_map and review-first onboarding.\n"
                "Result: the system now proposes domains before writing metadata.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "Agent Lenses.md").write_text(
                "# Agent Lenses\n\n"
                "Specification: LINZA should support find, research, write, act, verify, organize, and event flow lenses.\n"
                "Hypothesis: causal memory helps agents understand why a product changed.\n",
                encoding="utf-8",
            )
            (vault / "Work" / "Next Tasks.md").write_text(
                "# Next Tasks\n\n"
                "- [ ] Improve human domain names.\n"
                "- [ ] Review proposed roles before writing YAML.\n",
                encoding="utf-8",
            )

            result = asyncio.run(core.draft_vault_map(max_notes=20, max_domains=5))

            self.assertIn("role_draft", result)
            roles_by_path = {item["path"]: item["role"] for item in result["role_draft"]["notes"]}
            self.assertTrue(roles_by_path["Product/Decision Log.md"].startswith("type-"))
            self.assertTrue(roles_by_path["Product/Agent Lenses.md"].startswith("type-"))
            self.assertTrue(roles_by_path["Work/Next Tasks.md"].startswith("type-"))
            self.assertEqual(result["role_draft"]["policy"], "discover_from_vault_then_review")
            self.assertTrue(result["role_draft"]["material_type_candidates"])
            self.assertTrue(all(item["id"].startswith("type-") for item in result["role_draft"]["material_type_candidates"]))

            self.assertIn("lens_suggestions", result)
            lens_ids = {item["id"] for item in result["lens_suggestions"]}
            self.assertTrue({"find", "research", "write", "act", "verify", "organize", "event_flow"}.issubset(lens_ids))

            self.assertIn("event_flow_draft", result)
            event_types = {item["type"] for item in result["event_flow_draft"]["events"]}
            self.assertTrue({"fact", "decision", "action", "result", "hypothesis"}.issubset(event_types))
            self.assertTrue(result["event_flow_draft"]["causal_candidates"])
            self.assertEqual(result["event_flow_draft"]["policy"], "evidence_first")
            self.assertTrue(result["event_flow_draft"]["requires_review"])
        finally:
            storage.close()
            tmp.cleanup()

    def test_draft_vault_map_exposes_stage_views_and_pattern_insights(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            (vault / "Research").mkdir()
            (vault / "Product" / "Onboarding Problems.md").write_text(
                "# Onboarding Problems\n\n"
                "Problem: onboarding is confusing for new workspaces.\n"
                "Term: memory means accepted context for future agents.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "Review Problems.md").write_text(
                "# Review Problems\n\n"
                "Problem: review cards lack evidence, so humans do not trust them.\n"
                "Term: memory means long-lived operational guidance.\n",
                encoding="utf-8",
            )
            (vault / "Research" / "Embedding Notes.md").write_text(
                "# Embedding Notes\n\n"
                "Research note about retrieval, chunks, semantic search, and ranking.\n",
                encoding="utf-8",
            )
            (vault / "Research" / "Chunk Notes.md").write_text(
                "# Chunk Notes\n\n"
                "Research note about chunks, context windows, semantic search, and ranking.\n",
                encoding="utf-8",
            )

            domain_stage = asyncio.run(core.draft_vault_map(
                max_notes=20,
                max_domains=4,
                analysis_stage="domains",
            ))
            pattern_stage = asyncio.run(core.draft_vault_map(
                max_notes=20,
                max_domains=4,
                analysis_stage="patterns",
            ))

            self.assertEqual(domain_stage["analysis_stage"]["requested"], "domains")
            self.assertEqual(domain_stage["stage_view"]["id"], "domains")
            self.assertTrue(domain_stage["stage_view"]["items"])
            self.assertIn("candidate_domains", domain_stage["stage_view"]["sections"])

            pattern_types = {item["type"] for item in pattern_stage["pattern_draft"]["cards"]}
            self.assertIn("repeated_problem", pattern_types)
            self.assertIn("terminology_drift", pattern_types)
            self.assertIn("gap", pattern_types)
            for card in pattern_stage["pattern_draft"]["cards"]:
                self.assertTrue(card["evidence"])
                self.assertTrue(card["why"])
                self.assertEqual(card["write_policy"], "review_only_sidecar_or_context")
            self.assertEqual(pattern_stage["stage_view"]["id"], "patterns")
            self.assertEqual(pattern_stage["stage_view"]["items"], pattern_stage["pattern_draft"]["cards"][:5])
        finally:
            storage.close()
            tmp.cleanup()

    def test_material_types_are_discovered_without_builtin_ontology(self):
        from linza_mcp.roles import guess_note_role, role_review_metadata

        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Research").mkdir()
            (vault / "Research" / "Embedding Experiment.md").write_text(
                "# Embedding Experiment\n\n"
                "Benchmark setup: compare raw scoring with centered scoring.\n"
                "Result: centered scoring improves broad search diagnostics.\n",
                encoding="utf-8",
            )
            (vault / "Research" / "Search Specification.md").write_text(
                "# Search Specification\n\n"
                "Specification: broad search uses centered scoring by default.\n",
                encoding="utf-8",
            )

            result = asyncio.run(core.draft_vault_map(max_notes=20, max_domains=4))
            roles_by_path = {item["path"]: item["role"] for item in result["role_draft"]["notes"]}

            self.assertTrue(roles_by_path["Research/Embedding Experiment.md"].startswith("type-"))
            self.assertTrue(roles_by_path["Research/Search Specification.md"].startswith("type-"))
            material_types = result["onboarding_contract"]["material_types"]
            self.assertEqual(material_types["baseline_types"], [])
            self.assertEqual(material_types["optional_types"], [])
            self.assertNotIn("experiment", material_types["suggested_types"])
            self.assertTrue(all(item.startswith("type-") for item in material_types["suggested_types"]))

            ru_role = guess_note_role(
                "\u044d\u043a\u0441\u043f\u0435\u0440\u0438\u043c\u0435\u043d\u0442: \u0447\u0430\u043d\u043a\u0438",
                "\u0412\u044b\u0432\u043e\u0434\u044b: \u044d\u0442\u043e \u0441\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u0435 "
                "\u0434\u0432\u0443\u0445 \u043f\u043e\u0434\u0445\u043e\u0434\u043e\u0432.",
                "",
                {},
            )
            self.assertEqual(ru_role["role"], "untyped")
            self.assertEqual(ru_role["reason"], "clean_slate_no_role_guess")

            research_role = guess_note_role(
                "Embedding research study",
                "Research notes about anisotropy and semantic search.",
                "",
                {},
            )
            self.assertEqual(research_role["role"], "untyped")

            accepted_role = guess_note_role(
                "Anything",
                "Body",
                "",
                {"role": "lab-log"},
            )
            self.assertEqual(accepted_role["role"], "lab-log")
            self.assertEqual(accepted_role["reason"], "accepted_yaml")

            role_meta = role_review_metadata("type-001")
            self.assertEqual(role_meta["kind"], "material_type")
            self.assertEqual(role_meta["yaml_value"], "type-001")
            self.assertEqual(role_meta["storage_key"], "role")
            self.assertNotIn("label_en", role_meta)
            self.assertIn("\u0430\u0432\u0442\u043e\u043c\u0430\u0442", role_meta["definition"].lower())

            log_role = guess_note_role(
                "Лог Opus 3.1.0",
                "Проверка и тестирование проходили в ходе сессии.\nИтог: записали результат.",
                "",
                {},
            )
            self.assertEqual(log_role["role"], "untyped")
            self.assertEqual(log_role["reason"], "clean_slate_no_role_guess")
        finally:
            storage.close()
            tmp.cleanup()

    def test_draft_vault_map_returns_memory_draft_and_memory_lens(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            (vault / "Product" / "Session Log.md").write_text(
                "# Session Log\n\n"
                "Fact: agents lose useful context when session notes stay raw.\n"
                "Decision: add a reviewed memory consolidation queue.\n"
                "Action: keep memory candidates in sidecar storage before any note edits.\n"
                "Result: future sessions can retrieve accepted context without reading everything.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "Memory Rule.md").write_text(
                "# Memory Rule\n\n"
                "Rule: never write generated traces into source notes without human review.\n"
                "Lesson: durable memory should preserve evidence, source, and review state.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "Next Tasks.md").write_text(
                "# Next Tasks\n\n"
                "- [ ] Review memory candidates after every substantial session.\n",
                encoding="utf-8",
            )

            result = asyncio.run(core.draft_vault_map(max_notes=20, max_domains=4))

            lens_ids = {item["id"] for item in result["lens_suggestions"]}
            self.assertIn("memory", lens_ids)
            self.assertIn("memory_draft", result)
            memory = result["memory_draft"]
            self.assertEqual(memory["policy"], "consolidation_queue_review_first")
            self.assertTrue(memory["requires_review"])
            self.assertGreaterEqual(memory["summary"]["candidates"], 3)
            memory_types = {item["memory_type"] for item in memory["consolidation_candidates"]}
            self.assertTrue({"episodic", "procedural", "prospective"}.issubset(memory_types))
            self.assertTrue(all(item["target_store"] == ".linza" for item in memory["consolidation_candidates"]))
            self.assertTrue(any("prediction_error" in item.get("signals", []) for item in memory["consolidation_candidates"]))
        finally:
            storage.close()
            tmp.cleanup()

    def test_memory_draft_adds_recall_context_staleness_conflicts_and_evolution(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            (vault / "Product" / "2026-01-01 Memory Decision.md").write_text(
                "# Memory Decision\n\n"
                "Decision: agents may write accepted memory directly into notes.\n"
                "Result: the early workflow was fast but risky.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "2026-03-01 Memory Update.md").write_text(
                "# Memory Update\n\n"
                "Decision: agents must not write generated memory into source notes.\n"
                "Lesson: memory cards need evidence and human review before storage.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "Next Actions.md").write_text(
                "# Next Actions\n\n"
                "- [ ] Review accepted memory after large imports.\n",
                encoding="utf-8",
            )

            result = asyncio.run(core.draft_vault_map(
                max_notes=20,
                max_domains=4,
                analysis_stage="memory",
            ))
            memory = result["memory_draft"]
            candidates = memory["consolidation_candidates"]

            self.assertEqual(result["stage_view"]["id"], "memory")
            self.assertEqual(result["stage_view"]["items"], candidates[:5])
            self.assertTrue(candidates)
            for candidate in candidates:
                self.assertTrue(candidate["recall_context"])
                self.assertIn(candidate["staleness_risk"], {"low", "medium", "high"})
                self.assertTrue(candidate["review_after"])
                self.assertTrue(candidate["review_questions"])
                self.assertIn("When should future agents recall this?", candidate["review_questions"])

            self.assertTrue(any(item.get("conflict_candidates") for item in candidates))
            self.assertTrue(any(
                item.get("evolution", {}).get("related_sources")
                for item in candidates
            ))
        finally:
            storage.close()
            tmp.cleanup()

    def test_memory_draft_summary_matches_returned_limit(self):
        tmp, vault, storage, core = self.make_core()
        try:
            records = [
                {
                    "path": "A.md",
                    "title": "A",
                    "role": "decision",
                    "domain_ids": [],
                    "chunks": [{"text": "Decision: keep memory reviewed.\n"}],
                },
                {
                    "path": "B.md",
                    "title": "B",
                    "role": "decision",
                    "domain_ids": [],
                    "chunks": [{"text": "Decision: keep memory in sidecar storage.\n"}],
                },
            ]
            event_flow = {
                "events": [
                    {"path": "A.md", "type": "decision", "evidence": "Decision: keep memory reviewed.", "role": "decision"},
                    {"path": "B.md", "type": "decision", "evidence": "Decision: keep memory in sidecar storage.", "role": "decision"},
                    {"path": "B.md", "type": "result", "evidence": "Result: agents can reuse accepted memory.", "role": "decision"},
                ]
            }

            memory = core._build_memory_draft(records, event_flow, [], limit=2)

            self.assertEqual(len(memory["consolidation_candidates"]), 2)
            self.assertEqual(memory["summary"]["candidates"], 2)
        finally:
            storage.close()
            tmp.cleanup()

    def test_draft_vault_map_adds_human_domain_name_candidates(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Products").mkdir()
            (vault / "Products" / "LINZA Onboarding.md").write_text(
                "# LINZA Onboarding\n\n"
                "LINZA helps agents inspect a raw Markdown vault and propose safe onboarding domains.\n",
                encoding="utf-8",
            )
            (vault / "Products" / "LINZA Review Queue.md").write_text(
                "# LINZA Review Queue\n\n"
                "LINZA shows review queues before metadata writes and keeps the first contact safe.\n",
                encoding="utf-8",
            )
            (vault / "Products" / "Vault Setup.md").write_text(
                "# Vault Setup\n\n"
                "The onboarding map calibrates thresholds and groups raw notes before any YAML change.\n",
                encoding="utf-8",
            )

            result = asyncio.run(core.draft_vault_map(max_notes=20, max_domains=4))

            domain = next(
                item for item in result["candidate_domains"]
                if any(note["path"] == "Products/LINZA Onboarding.md" for note in item["representative_notes"])
            )
            self.assertIn("display_name", domain)
            self.assertIn("name_candidates", domain)
            self.assertTrue(domain["name_candidates"])
            self.assertEqual(domain["name"], domain["display_name"])
            self.assertNotIn("Products:", domain["display_name"])
            self.assertIn("LINZA", domain["display_name"])
            self.assertTrue(any("title" in candidate["reason"] for candidate in domain["name_candidates"]))
        finally:
            storage.close()
            tmp.cleanup()

    def test_event_flow_links_causal_candidates_across_notes_in_same_domain(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            (vault / "Product" / "2026-05-01 Problem.md").write_text(
                "# 2026-05-01 Problem\n\n"
                "Fact: LINZA onboarding is confusing for a raw vault.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "2026-05-02 Decision.md").write_text(
                "# 2026-05-02 Decision\n\n"
                "Decision: use a draft vault map with human review before YAML changes.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "2026-05-03 Action.md").write_text(
                "# 2026-05-03 Action\n\n"
                "Action: added role drafts, agent lenses, and event flow to draft_vault_map.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "2026-05-04 Result.md").write_text(
                "# 2026-05-04 Result\n\n"
                "Result: agents can now see facts, decisions, actions, and outcomes as a cautious history.\n",
                encoding="utf-8",
            )

            result = asyncio.run(core.draft_vault_map(max_notes=20, max_domains=4))

            flow = result["event_flow_draft"]
            cross_note = [item for item in flow["causal_candidates"] if item.get("scope") == "cross_note"]
            self.assertTrue(cross_note)
            self.assertTrue(any(item["relation"] == "basis_for" for item in cross_note))
            self.assertTrue(any(item["relation"] == "led_to_action" for item in cross_note))
            self.assertTrue(any(item["relation"] == "led_to_result" for item in cross_note))
            self.assertTrue(all(item.get("shared_domain_ids") for item in cross_note))
            self.assertGreaterEqual(flow["summary"]["cross_note_candidates"], 3)
        finally:
            storage.close()
            tmp.cleanup()

    def test_domain_display_names_are_deduplicated_from_candidates(self):
        domains = [
            {
                "id": "domain-001",
                "name": "Recursive self-organization",
                "display_name": "Recursive self-organization",
                "name_candidates": [
                    {"label": "Recursive self-organization", "reason": "title phrase"},
                    {"label": "Recursive agents", "reason": "companion term"},
                ],
                "folders": [("Agents", 2)],
            },
            {
                "id": "domain-002",
                "name": "Recursive self-organization",
                "display_name": "Recursive self-organization",
                "name_candidates": [
                    {"label": "Recursive self-organization", "reason": "title phrase"},
                    {"label": "Recursive thermodynamics", "reason": "companion term"},
                ],
                "folders": [("Physics", 2)],
            },
        ]

        LinzaCore._dedupe_draft_domain_names(domains)

        names = [domain["display_name"] for domain in domains]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(domains[0]["display_name"], "Recursive self-organization")
        self.assertEqual(domains[1]["display_name"], "Recursive self-organization (Physics)")
        self.assertEqual(domains[1]["name"], "Recursive self-organization (Physics)")

    def test_domain_terms_use_capped_smooth_idf(self):
        records = [
            {"tokens": {"commonterm", "specificterm"}},
            {"tokens": {"commonterm", "specificterm"}},
            {"tokens": {"commonterm", "specificterm"}},
            {"tokens": {"commonterm", "localterm"}},
        ]
        global_doc_counts = Counter({
            "commonterm": 90,
            "specificterm": 18,
            "localterm": 1,
        })

        terms = LinzaCore._domain_terms(records, global_doc_counts, total_docs=100)
        direct_terms = domain_terms(records, global_doc_counts, total_docs=100)

        self.assertLess(terms.index("specificterm"), terms.index("commonterm"))
        self.assertLess(terms.index("commonterm"), terms.index("localterm"))
        self.assertEqual(terms, direct_terms)

    def test_record_similarity_can_use_idf_weighted_overlap(self):
        global_doc_counts = Counter({
            "commonterm": 90,
            "specificterm": 12,
            "othertopic": 12,
        })
        left = {"tokens": {"commonterm", "specificterm"}, "folder": "", "tags": [], "role": "note"}
        strong = {"tokens": {"commonterm", "specificterm"}, "folder": "", "tags": [], "role": "note"}
        weak = {"tokens": {"commonterm", "othertopic"}, "folder": "", "tags": [], "role": "note"}

        strong_score = LinzaCore._record_similarity(left, strong, global_doc_counts, total_docs=100)
        weak_score = LinzaCore._record_similarity(left, weak, global_doc_counts, total_docs=100)

        self.assertGreater(strong_score, weak_score)
        self.assertEqual(strong_score, record_similarity(left, strong, global_doc_counts, total_docs=100))
