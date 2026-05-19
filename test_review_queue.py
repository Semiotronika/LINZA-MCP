from test_support import *


class ReviewQueueTests(OperatorTestCase):

    def test_approve_draft_role_dry_run_then_writes_only_linza_yaml(self):
        tmp, vault, storage, core = self.make_core()
        try:
            note = vault / "Decision.md"
            original = "# Decision\n\nDecision: build LINZA as a safe onboarding server.\n"
            note.write_text(original, encoding="utf-8")

            preview = core.approve_draft_item(
                item_type="role",
                path="Decision.md",
                role="decision",
            )

            self.assertEqual(preview["status"], "preview")
            self.assertTrue(preview["dry_run"])
            self.assertTrue(preview["body_preserved"])
            self.assertEqual(note.read_text(encoding="utf-8"), original)
            self.assertTrue(any(change["property"] == "role" for change in preview["changes"]))

            result = core.approve_draft_item(
                item_type="role",
                path="Decision.md",
                role="decision",
                dry_run=False,
            )

            self.assertEqual(result["status"], "written")
            metadata, body = strip_frontmatter(note.read_text(encoding="utf-8"))
            self.assertEqual(get_linza_metadata(metadata)["role"], "decision")
            self.assertEqual(body, original)
        finally:
            storage.close()
            tmp.cleanup()

    def test_approve_draft_role_preserves_body_newlines_exactly(self):
        tmp, vault, storage, core = self.make_core()
        try:
            note = vault / "LF Only.md"
            original = "# LF Only\n\nDecision: preserve the note body exactly.\n"
            with note.open("w", encoding="utf-8", newline="") as handle:
                handle.write(original)

            result = core.approve_draft_item(
                item_type="role",
                path="LF Only.md",
                role="decision",
                dry_run=False,
            )

            self.assertEqual(result["status"], "written")
            with note.open("r", encoding="utf-8", newline="") as handle:
                raw_after = handle.read()
            metadata, body = strip_frontmatter(raw_after)
            self.assertEqual(get_linza_metadata(metadata)["role"], "decision")
            self.assertEqual(body, original)
            self.assertNotIn("\r\n", body)
        finally:
            storage.close()
            tmp.cleanup()

    def test_approve_draft_role_preserves_leading_blank_body_line(self):
        tmp, vault, storage, core = self.make_core()
        try:
            note = vault / "Leading Blank.md"
            original = "\r\n# Leading Blank\r\n\r\nDecision: keep the leading blank line.\r\n"
            with note.open("w", encoding="utf-8", newline="") as handle:
                handle.write(original)

            result = core.approve_draft_item(
                item_type="role",
                path="Leading Blank.md",
                role="decision",
                dry_run=False,
            )

            self.assertEqual(result["status"], "written")
            with note.open("r", encoding="utf-8", newline="") as handle:
                raw_after = handle.read()
            metadata, body = strip_frontmatter(raw_after)
            self.assertEqual(get_linza_metadata(metadata)["role"], "decision")
            self.assertEqual(body, original)
        finally:
            storage.close()
            tmp.cleanup()

    def test_patch_note_properties_writes_readable_linza_yaml(self):
        tmp, vault, storage, core = self.make_core()
        try:
            note = vault / "Readable.md"
            original = "# Readable\n\nBody.\n"
            note.write_text(original, encoding="utf-8")

            result = core.patch_note_properties(
                "Readable.md",
                {
                    "domains": ["Alpha", "Beta"],
                    "state": "mapped",
                    "role_confidence": "high",
                    "role": "note",
                },
                dry_run=False,
                allow_overwrite=True,
            )

            self.assertEqual(result["status"], "written")
            raw_after = note.read_text(encoding="utf-8")
            self.assertTrue(raw_after.startswith(
                "---\n"
                "role: note\n"
                "confidence: high\n"
                "domains:\n"
                "  - Alpha\n"
                "  - Beta\n"
                "---\n"
            ))
            self.assertNotIn("\nlinza:", raw_after)
            self.assertNotIn("linza_", raw_after)
            self.assertNotIn("schema:", raw_after)
            self.assertNotIn("state:", raw_after)
            self.assertNotIn("\ndomains: [", raw_after)
            metadata, body = strip_frontmatter(raw_after)
            self.assertEqual(get_linza_metadata(metadata)["domains"], ["Alpha", "Beta"])
            self.assertEqual(get_linza_metadata(metadata)["confidence"], "high")
            self.assertEqual(body, original)
        finally:
            storage.close()
            tmp.cleanup()

    def test_approve_draft_domain_appends_domain_to_multiple_notes(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Alpha.md").write_text(
                "---\nlinza:\n  schema: 1\n  domains:\n  - Existing\n---\n# Alpha\n\nBody.\n",
                encoding="utf-8",
            )
            (vault / "Beta.md").write_text("# Beta\n\nBody.\n", encoding="utf-8")

            result = core.approve_draft_item(
                item_type="domain",
                domain_name="LINZA Onboarding",
                paths=["Alpha.md", "Beta.md"],
                dry_run=False,
            )

            self.assertEqual(result["status"], "written")
            self.assertEqual(len(result["file_results"]), 2)
            alpha_meta, alpha_body = strip_frontmatter((vault / "Alpha.md").read_text(encoding="utf-8"))
            beta_meta, beta_body = strip_frontmatter((vault / "Beta.md").read_text(encoding="utf-8"))
            self.assertEqual(get_linza_metadata(alpha_meta)["domains"], ["Existing", "LINZA Onboarding"])
            self.assertEqual(get_linza_metadata(beta_meta)["domains"], ["LINZA Onboarding"])
            self.assertEqual(alpha_body, "# Alpha\n\nBody.\n")
            self.assertEqual(beta_body, "# Beta\n\nBody.\n")
        finally:
            storage.close()
            tmp.cleanup()

    def test_approve_draft_causal_link_records_approval_without_touching_notes(self):
        tmp, vault, storage, core = self.make_core()
        try:
            source = vault / "Problem.md"
            target = vault / "Decision.md"
            source.write_text("# Problem\n\nFact: onboarding is confusing.\n", encoding="utf-8")
            target.write_text("# Decision\n\nDecision: add review before writes.\n", encoding="utf-8")
            before_source = source.read_text(encoding="utf-8")
            before_target = target.read_text(encoding="utf-8")

            preview = core.approve_draft_item(
                item_type="causal_link",
                source_path="Problem.md",
                target_path="Decision.md",
                relation="basis_for",
                evidence="Fact appears before decision in the same draft domain.",
            )

            self.assertEqual(preview["status"], "preview")
            self.assertEqual(storage.list_approved_items("causal_link"), [])

            result = core.approve_draft_item(
                item_type="causal_link",
                source_path="Problem.md",
                target_path="Decision.md",
                relation="basis_for",
                evidence="Fact appears before decision in the same draft domain.",
                dry_run=False,
            )

            self.assertEqual(result["status"], "recorded")
            approved = storage.list_approved_items("causal_link")
            self.assertEqual(len(approved), 1)
            self.assertEqual(approved[0]["payload"]["relation"], "basis_for")
            self.assertEqual(source.read_text(encoding="utf-8"), before_source)
            self.assertEqual(target.read_text(encoding="utf-8"), before_target)
        finally:
            storage.close()
            tmp.cleanup()

    def test_approve_draft_memory_item_records_sidecar_only(self):
        tmp, vault, storage, core = self.make_core()
        try:
            note = vault / "Session Log.md"
            note.write_text(
                "# Session Log\n\n"
                "Decision: preserve durable memory only after review.\n",
                encoding="utf-8",
            )
            before = note.read_text(encoding="utf-8")

            preview = core.approve_draft_item(
                item_type="memory_item",
                source_path="Session Log.md",
                memory_type="episodic",
                summary="Decision to preserve durable memory only after review.",
                evidence="Decision: preserve durable memory only after review.",
                signals=["decision", "review"],
            )

            self.assertEqual(preview["status"], "preview")
            self.assertEqual(storage.list_approved_items("memory_item"), [])
            self.assertEqual(note.read_text(encoding="utf-8"), before)

            result = core.approve_draft_item(
                item_type="memory_item",
                source_path="Session Log.md",
                memory_type="episodic",
                summary="Decision to preserve durable memory only after review.",
                evidence="Decision: preserve durable memory only after review.",
                signals=["decision", "review"],
                dry_run=False,
            )

            self.assertEqual(result["status"], "recorded")
            approved = storage.list_approved_items("memory_item")
            self.assertEqual(len(approved), 1)
            self.assertEqual(approved[0]["payload"]["memory_type"], "episodic")
            self.assertEqual(approved[0]["payload"]["source_path"], "Session Log.md")
            self.assertEqual(note.read_text(encoding="utf-8"), before)
        finally:
            storage.close()
            tmp.cleanup()

    def test_approve_draft_hierarchy_link_records_sidecar_only(self):
        tmp, vault, storage, core = self.make_core()
        try:
            parent = vault / "Product Overview.md"
            child = vault / "Product Decision.md"
            parent.write_text("# Product Overview\n\nProject overview and semantic map.\n", encoding="utf-8")
            child.write_text("# Product Decision\n\nDecision: keep hierarchy links reviewed.\n", encoding="utf-8")
            before_parent = parent.read_text(encoding="utf-8")
            before_child = child.read_text(encoding="utf-8")

            preview = core.approve_draft_item(
                item_type="hierarchy_link",
                parent_path="Product Overview.md",
                child_paths=["Product Decision.md"],
                domain_name="Product",
                evidence="Product overview groups the decision note.",
            )

            self.assertEqual(preview["status"], "preview")
            self.assertEqual(storage.list_approved_items("hierarchy_link"), [])
            self.assertEqual(parent.read_text(encoding="utf-8"), before_parent)
            self.assertEqual(child.read_text(encoding="utf-8"), before_child)

            result = core.approve_draft_item(
                item_type="hierarchy_link",
                parent_path="Product Overview.md",
                child_paths=["Product Decision.md"],
                domain_name="Product",
                evidence="Product overview groups the decision note.",
                dry_run=False,
            )

            self.assertEqual(result["status"], "recorded")
            approved = storage.list_approved_items("hierarchy_link")
            self.assertEqual(len(approved), 1)
            self.assertEqual(approved[0]["payload"]["parent_path"], "Product Overview.md")
            self.assertEqual(approved[0]["payload"]["child_paths"], ["Product Decision.md"])
            self.assertEqual(parent.read_text(encoding="utf-8"), before_parent)
            self.assertEqual(child.read_text(encoding="utf-8"), before_child)
        finally:
            storage.close()
            tmp.cleanup()

    def test_build_review_apply_queue_contains_safe_approval_payloads(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            (vault / "Product" / "2026-05-01 Problem.md").write_text(
                "# 2026-05-01 Problem\n\n"
                "Fact: onboarding is confusing for a raw vault.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "2026-05-02 Decision.md").write_text(
                "# 2026-05-02 Decision\n\n"
                "Decision: add draft domains and human review before YAML changes.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "2026-05-03 Action.md").write_text(
                "# 2026-05-03 Action\n\n"
                "Action: added approve_draft_item as a dry-run first workflow.\n",
                encoding="utf-8",
            )

            result = asyncio.run(core.build_review_apply_queue(max_notes=20, max_domains=4, limit=20))

            self.assertEqual(result["tool"], "build_review_apply_queue")
            self.assertTrue(result["read_only"])
            self.assertTrue(result["items"])
            self.assertIn("markdown", result)
            self.assertIn("approve_draft_item", result["markdown"])
            self.assertTrue(all(item["approval"]["tool"] == "approve_draft_item" for item in result["items"]))
            self.assertTrue(all(item["approval"]["arguments"]["dry_run"] is True for item in result["items"]))
            self.assertTrue(all(item.get("human", {}).get("question") for item in result["items"]))
            item_types = {item["approval"]["arguments"]["item_type"] for item in result["items"]}
            self.assertIn("material_type", item_types)
            self.assertIn("domain", item_types)
            self.assertIn("causal_link", item_types)
            self.assertIn("hierarchy_link", item_types)
            type_item = next(item for item in result["items"] if item["kind"] == "material_type")
            self.assertEqual(type_item["approval"]["arguments"]["item_type"], "material_type")
            self.assertIn("type_id", type_item["approval"]["arguments"])
            self.assertNotIn("type_name", type_item["approval"]["arguments"])
            self.assertIn("Как назвать", type_item["human"]["question"])
            self.assertNotIn("role", item_types)
            for note_path in vault.glob("Product/*.md"):
                metadata, _ = strip_frontmatter(note_path.read_text(encoding="utf-8"))
                self.assertNotIn("linza", metadata)
            self.assertEqual(storage.list_approved_items(), [])
        finally:
            storage.close()
            tmp.cleanup()

    def test_review_queue_can_focus_stage_and_explain_evidence_trace(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            (vault / "Product" / "Domain A.md").write_text(
                "# Domain A\n\n"
                "Decision: build review cards with visible evidence.\n"
                "Action: add structured signals to every proposal.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "Domain B.md").write_text(
                "# Domain B\n\n"
                "Decision: keep writes gated by exact review IDs.\n"
                "Result: source notes stay protected.\n",
                encoding="utf-8",
            )
            (vault / "Other.md").write_text(
                "# Other\n\n"
                "Physics observations and unrelated measurements.\n",
                encoding="utf-8",
            )

            domain_queue = asyncio.run(core.build_review_apply_queue(
                max_notes=20,
                max_domains=4,
                limit=10,
                analysis_stage="domains",
            ))
            event_queue = asyncio.run(core.build_review_apply_queue(
                max_notes=20,
                max_domains=4,
                limit=10,
                analysis_stage="event_flow",
            ))
            guide = asyncio.run(core.guide_next_steps(max_notes=20, max_domains=4, limit=5))

            self.assertTrue(domain_queue["items"])
            self.assertEqual({item["kind"] for item in domain_queue["items"]}, {"domain"})
            self.assertTrue(domain_queue["items"][0]["evidence_trace"])
            self.assertTrue(all("label" in entry and "value" in entry for entry in domain_queue["items"][0]["evidence_trace"]))
            self.assertEqual(event_queue["analysis_stage"]["requested"], "event_flow")
            self.assertTrue(all(item["kind"] == "causal_link" for item in event_queue["items"]))
            self.assertEqual(guide["review_window"]["stage"], guide["stage"]["id"])
            self.assertLessEqual(len(guide["recommended_cards"]), 5)
            for card in guide["recommended_cards"]:
                self.assertIn(card["kind"], set(guide["stage"].get("kinds", [guide["stage"]["kind"]])))
        finally:
            storage.close()
            tmp.cleanup()

    def test_material_type_review_names_cluster_before_yaml_roles(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Sessions").mkdir()
            (vault / "Sessions" / "Run One.md").write_text(
                "# Run One\n\n- step one\n- step two\n- result\n",
                encoding="utf-8",
            )
            (vault / "Sessions" / "Run Two.md").write_text(
                "# Run Two\n\n- step one\n- step two\n- result\n",
                encoding="utf-8",
            )
            (vault / "Reference.md").write_text(
                "# Reference\n\nLonger paragraph with context and several [[Run One]] links.\n",
                encoding="utf-8",
            )

            queue = asyncio.run(core.build_review_apply_queue(max_notes=20, max_domains=4, limit=30))
            type_item = next(item for item in queue["items"] if item["kind"] == "material_type")
            type_id = type_item["approval"]["arguments"]["type_id"]
            self.assertTrue(type_id.startswith("type-"))

            blocked = core.approve_draft_item(
                item_type="material_type",
                type_id=type_id,
                paths=type_item["approval"]["arguments"]["paths"],
                dry_run=False,
            )
            self.assertEqual(blocked["status"], "blocked_missing_type_name")

            named = core.approve_draft_item(
                item_type="material_type",
                type_id=type_id,
                type_name="логи",
                paths=type_item["approval"]["arguments"]["paths"],
                evidence=type_item.get("evidence", ""),
                dry_run=False,
            )
            self.assertEqual(named["status"], "recorded")
            self.assertEqual(storage.list_approved_items("material_type")[0]["payload"]["type_name"], "логи")

            next_queue = asyncio.run(core.build_review_apply_queue(max_notes=20, max_domains=4, limit=30))
            role_items = [
                item for item in next_queue["items"]
                if item["kind"] == "role" and item["approval"]["arguments"].get("role") == "логи"
            ]
            self.assertTrue(role_items)
            self.assertFalse(any(
                item["kind"] == "role" and str(item["approval"]["arguments"].get("role", "")).startswith("type-")
                for item in next_queue["items"]
            ))

            applied = core.approve_draft_item(
                item_type="role",
                path=role_items[0]["approval"]["arguments"]["path"],
                role=role_items[0]["approval"]["arguments"]["role"],
                dry_run=False,
            )
            self.assertEqual(applied["status"], "written")
            written = vault / role_items[0]["approval"]["arguments"]["path"]
            metadata, body = strip_frontmatter(written.read_text(encoding="utf-8"))
            self.assertEqual(get_linza_metadata(metadata)["role"], "логи")
            self.assertNotIn("type-", get_linza_metadata(metadata)["role"])
            self.assertTrue(body.strip())
        finally:
            storage.close()
            tmp.cleanup()

    def test_learned_review_queue_modes_use_accepted_examples(self):
        from linza_mcp.review_queue import learning_examples_from_storage, select_learned_queue_items

        tmp, vault, storage, core = self.make_core()
        try:
            storage.record_approved_item("role", {"path": "Old Concept.md", "role": "concept"})
            storage.record_approved_item("domain", {"domain_name": "Product"})
            storage.record_approved_item("hierarchy_link", {
                "parent_path": "Product Overview.md",
                "child_paths": ["Product Decision.md"],
                "domain_name": "Product",
            })
            queue_items = [
                {
                    "id": "rq-role-1",
                    "kind": "role",
                    "priority": "high",
                    "approval": {"arguments": {"item_type": "role", "role": "concept"}},
                },
                {
                    "id": "rq-domain-1",
                    "kind": "domain",
                    "priority": "high",
                    "approval": {"arguments": {"item_type": "domain", "domain_name": "Product"}},
                },
                {
                    "id": "rq-hierarchy-1",
                    "kind": "hierarchy_link",
                    "priority": "medium",
                    "approval": {"arguments": {"item_type": "hierarchy_link", "domain_name": "Product"}},
                },
                {
                    "id": "rq-causal-1",
                    "kind": "causal_link",
                    "priority": "medium",
                    "approval": {"arguments": {"item_type": "causal_link", "relation": "basis_for"}},
                },
            ]

            examples = learning_examples_from_storage(storage)
            self.assertEqual(select_learned_queue_items(queue_items, examples, mode="review"), [])
            assisted = select_learned_queue_items(queue_items, examples, mode="assisted")
            self.assertEqual(assisted, ["rq-role-1", "rq-domain-1", "rq-hierarchy-1"])
            storage.record_approved_item("causal_link", {"relation": "basis_for"})
            autopilot_examples = learning_examples_from_storage(storage)
            autopilot = select_learned_queue_items(queue_items, autopilot_examples, mode="autopilot")
            self.assertIn("rq-causal-1", autopilot)
        finally:
            storage.close()
            tmp.cleanup()

    def test_learning_examples_expose_rules_for_supervised_growth(self):
        from linza_mcp.review_queue import (
            learning_examples_from_storage,
            select_learned_queue_items,
            select_learned_queue_matches,
        )

        tmp, vault, storage, core = self.make_core()
        try:
            storage.record_approved_item("domain", {"domain_name": "Product"})
            storage.record_approved_item("hierarchy_link", {
                "parent_path": "Product/Overview.md",
                "child_paths": ["Product/Decision.md"],
                "domain_name": "Product",
                "relation": "parent_of",
            })
            storage.record_approved_item("causal_link", {
                "source_path": "Product/Problem.md",
                "target_path": "Product/Decision.md",
                "relation": "basis_for",
            })
            queue_items = [
                {
                    "id": "rq-causal-1",
                    "kind": "causal_link",
                    "priority": "medium",
                    "approval": {"arguments": {"item_type": "causal_link", "relation": "basis_for"}},
                },
                {
                    "id": "rq-causal-2",
                    "kind": "causal_link",
                    "priority": "medium",
                    "approval": {"arguments": {"item_type": "causal_link", "relation": "contradicts"}},
                },
            ]

            examples = learning_examples_from_storage(storage)
            self.assertEqual(examples["rules"]["domain_names"], ["Product"])
            self.assertEqual(examples["rules"]["hierarchy_relations"], ["parent_of"])
            self.assertEqual(examples["rules"]["causal_relations"], ["basis_for"])
            self.assertIn("Product", examples["rules"]["path_prefixes"])

            matches = select_learned_queue_matches(queue_items, examples, mode="assisted")
            self.assertEqual(matches["rq-causal-1"], ["accepted_causal_relation:basis_for"])
            self.assertNotIn("rq-causal-2", matches)
            self.assertEqual(select_learned_queue_items(queue_items, examples, mode="assisted"), ["rq-causal-1"])
        finally:
            storage.close()
            tmp.cleanup()

    def test_apply_learned_review_queue_dry_run_selects_only_after_examples(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            (vault / "Product" / "Product Overview.md").write_text(
                "# Product Overview\n\nProject overview for semantic graph and review queue.\n",
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

            no_examples = asyncio.run(core.apply_learned_review_queue(
                mode="assisted",
                max_notes=20,
                max_domains=4,
                limit=30,
            ))
            self.assertEqual(no_examples["selected_ids"], [])

            storage.record_approved_item("material_type", {"type_id": "type-001", "type_name": "логи"})
            storage.record_approved_item("role", {"path": "Seed.md", "role": "логи"})
            storage.record_approved_item("domain", {"domain_name": "Product"})
            storage.record_approved_item("hierarchy_link", {
                "parent_path": "Seed Parent.md",
                "child_paths": ["Seed Child.md"],
                "domain_name": "Product",
            })

            learned = asyncio.run(core.apply_learned_review_queue(
                mode="assisted",
                max_notes=20,
                max_domains=4,
                limit=30,
            ))
            self.assertEqual(learned["status"], "preview")
            self.assertTrue(learned["selected_ids"])
            self.assertTrue(learned["dry_run"])
            self.assertEqual(storage.list_approved_items("role")[0]["payload"]["role"], "логи")
            self.assertNotIn("apply_result", no_examples)
        finally:
            storage.close()
            tmp.cleanup()

    def test_build_review_apply_queue_keeps_memory_opt_in(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            (vault / "Product" / "Session Log.md").write_text(
                "# Session Log\n\n"
                "Decision: add a reviewed memory consolidation queue.\n"
                "Result: future agents can recover accepted context.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "Memory Rule.md").write_text(
                "# Memory Rule\n\n"
                "Rule: never write generated traces into source notes without human review.\n",
                encoding="utf-8",
            )

            default_queue = asyncio.run(core.build_review_apply_queue(max_notes=20, max_domains=4, limit=20))
            memory_queue = asyncio.run(core.build_review_apply_queue(
                max_notes=20,
                max_domains=4,
                limit=20,
                include_memory=True,
            ))

            self.assertNotIn("memory_item", {item["kind"] for item in default_queue["items"]})
            self.assertIn("memory_item", {item["kind"] for item in memory_queue["items"]})
            self.assertFalse(default_queue["summary"]["include_memory"])
            self.assertTrue(memory_queue["summary"]["include_memory"])
        finally:
            storage.close()
            tmp.cleanup()

    def test_memory_review_cards_carry_memory_2_context_to_approval_payload(self):
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

            queue = asyncio.run(core.build_review_apply_queue(
                max_notes=20,
                max_domains=4,
                limit=20,
                include_memory=True,
                analysis_stage="memory",
            ))
            memory_item = next(item for item in queue["items"] if item["kind"] == "memory_item")
            args = memory_item["approval"]["arguments"]

            self.assertEqual(queue["analysis_stage"]["requested"], "memory")
            self.assertTrue(args["recall_context"])
            self.assertTrue(args["review_after"])
            self.assertIn(args["staleness_risk"], {"low", "medium", "high"})
            self.assertIn("conflict_candidates", args)
            self.assertIn("evolution", args)
            trace_labels = {entry["label"] for entry in memory_item["evidence_trace"]}
            self.assertTrue({
                "recall_context",
                "staleness_risk",
                "review_after",
            }.issubset(trace_labels))

            approve_args = dict(args)
            approve_args["dry_run"] = False
            recorded = core.approve_draft_item(**approve_args)
            self.assertEqual(recorded["status"], "recorded")
            approved = storage.list_approved_items("memory_item")
            self.assertEqual(len(approved), 1)
            payload = approved[0]["payload"]
            self.assertEqual(payload["recall_context"], args["recall_context"])
            self.assertEqual(payload["review_after"], args["review_after"])
            self.assertEqual(payload["staleness_risk"], args["staleness_risk"])
            self.assertIn("evolution", payload)
        finally:
            storage.close()
            tmp.cleanup()

    def test_build_review_apply_queue_skips_roles_already_in_linza_yaml(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Existing Concept.md").write_text(
                "---\nlinza:\n  role: concept\n---\n# Existing Concept\n\nConcept note already accepted.\n",
                encoding="utf-8",
            )
            (vault / "New Decision.md").write_text(
                "# New Decision\n\nDecision: review this role candidate.\n",
                encoding="utf-8",
            )
            initial_queue = asyncio.run(core.build_review_apply_queue(max_notes=20, max_domains=4, limit=20))
            type_item = next(
                item for item in initial_queue.get("items", [])
                if item.get("kind") == "material_type"
                and "New Decision.md" in item.get("approval", {}).get("arguments", {}).get("paths", [])
            )
            storage.record_approved_item(
                "material_type",
                {"type_id": type_item["approval"]["arguments"]["type_id"], "type_name": "решение"},
            )

            queue = asyncio.run(core.build_review_apply_queue(max_notes=20, max_domains=4, limit=20))
            role_paths = {
                item.get("approval", {}).get("arguments", {}).get("path")
                for item in queue.get("items", [])
                if item.get("kind") == "role"
            }

            self.assertNotIn("Existing Concept.md", role_paths)
            self.assertIn("New Decision.md", role_paths)
        finally:
            storage.close()
            tmp.cleanup()

    def test_build_review_apply_queue_redacted_hides_paths_evidence_and_payloads(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Private").mkdir()
            secret = "SECRET_TOKEN_ABC"
            (vault / "Private" / "Secret Project.md").write_text(
                f"# Secret Project\n\nDecision: keep {secret} out of public reports.\n",
                encoding="utf-8",
            )
            (vault / "Private" / "Secret Followup.md").write_text(
                f"# Secret Followup\n\nAction: review {secret} only locally.\n",
                encoding="utf-8",
            )

            result = asyncio.run(core.build_review_apply_queue(
                max_notes=20,
                max_domains=4,
                limit=10,
                redact=True,
            ))

            dump = json.dumps(result, ensure_ascii=False)
            self.assertTrue(result["redacted"])
            self.assertNotIn("Secret Project", dump)
            self.assertNotIn("Secret Followup", dump)
            self.assertNotIn(secret, dump)
            self.assertNotIn('"approval":', dump)
            self.assertNotIn("approve_draft_item", dump)
            self.assertTrue(all(item["payload_redacted"] for item in result["items"]))
            self.assertTrue(all("note_count" in item for item in result["items"]))
        finally:
            storage.close()
            tmp.cleanup()

    def test_review_apply_queue_ids_are_stable_from_approval_payloads(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            (vault / "Product" / "2026-05-01 Problem.md").write_text(
                "# 2026-05-01 Problem\n\nFact: onboarding is confusing for a raw vault.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "2026-05-02 Decision.md").write_text(
                "# 2026-05-02 Decision\n\nDecision: add draft domains and human review before YAML changes.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "2026-05-03 Action.md").write_text(
                "# 2026-05-03 Action\n\nAction: added approve_draft_item as a dry-run first workflow.\n",
                encoding="utf-8",
            )

            first = asyncio.run(core.build_review_apply_queue(max_notes=20, max_domains=4, limit=20))
            second = asyncio.run(core.build_review_apply_queue(max_notes=20, max_domains=4, limit=20))

            by_payload_first = {
                json.dumps(item["approval"]["arguments"], sort_keys=True): item["id"]
                for item in first["items"]
            }
            by_payload_second = {
                json.dumps(item["approval"]["arguments"], sort_keys=True): item["id"]
                for item in second["items"]
            }

            self.assertEqual(by_payload_first, by_payload_second)
            self.assertTrue(all(item["id"].startswith("rq-") for item in first["items"]))
            self.assertFalse(any(item["id"].startswith("RQ-00") for item in first["items"]))
        finally:
            storage.close()
            tmp.cleanup()

    def test_approve_review_queue_items_previews_then_applies_selected_ids(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            decision = vault / "Product" / "2026-05-02 Decision.md"
            decision.write_text(
                "# 2026-05-02 Decision\n\nDecision: add draft domains and human review before YAML changes.\n",
                encoding="utf-8",
            )
            (vault / "Product" / "2026-05-03 Action.md").write_text(
                "# 2026-05-03 Action\n\nAction: added approve_draft_item as a dry-run first workflow.\n",
                encoding="utf-8",
            )

            queue = asyncio.run(core.build_review_apply_queue(max_notes=20, max_domains=4, limit=20))
            type_item = next(item for item in queue["items"] if item["kind"] == "material_type")
            named = core.approve_draft_item(
                item_type="material_type",
                type_id=type_item["approval"]["arguments"]["type_id"],
                type_name="решения",
                paths=type_item["approval"]["arguments"]["paths"],
                evidence=type_item.get("evidence", ""),
                dry_run=False,
            )
            self.assertEqual(named["status"], "recorded")

            queue = asyncio.run(core.build_review_apply_queue(max_notes=20, max_domains=4, limit=20))
            role_item = next(item for item in queue["items"] if item["kind"] == "role")

            preview = asyncio.run(core.approve_review_queue_items(
                item_ids=[role_item["id"], role_item["id"]],
                max_notes=20,
                max_domains=4,
                limit=20,
            ))

            self.assertEqual(preview["tool"], "approve_review_queue_items")
            self.assertTrue(preview["dry_run"])
            self.assertEqual(preview["summary"]["requested"], 1)
            self.assertEqual(preview["summary"]["matched"], 1)
            self.assertEqual(preview["results"][0]["approval_result"]["status"], "preview")
            self.assertIn("human", preview["results"][0])
            self.assertIn("question", preview["results"][0]["human"])
            metadata, _ = strip_frontmatter(decision.read_text(encoding="utf-8"))
            self.assertNotIn("linza", metadata)

            applied = asyncio.run(core.approve_review_queue_items(
                item_ids=[role_item["id"]],
                max_notes=20,
                max_domains=4,
                limit=20,
                dry_run=False,
            ))

            self.assertEqual(applied["status"], "applied")
            self.assertEqual(applied["summary"]["matched"], 1)
            self.assertIn("human", applied["results"][0])
            self.assertIn("Product/2026-05-02 Decision.md", applied["written_paths"])
            metadata, body = strip_frontmatter(decision.read_text(encoding="utf-8"))
            self.assertEqual(
                get_linza_metadata(metadata)["role"],
                role_item["approval"]["arguments"]["role"],
            )
            self.assertEqual(get_linza_metadata(metadata)["role"], "решения")
            self.assertEqual(body, "# 2026-05-02 Decision\n\nDecision: add draft domains and human review before YAML changes.\n")
        finally:
            storage.close()
            tmp.cleanup()

    def test_build_review_apply_queue_keeps_causal_links_under_limit(self):
        tmp, vault, storage, core = self.make_core()
        try:
            (vault / "Product").mkdir()
            notes = {
                "2026-05-01 Problem.md": "Fact: onboarding is confusing for a raw vault.\n",
                "2026-05-02 Decision.md": "Decision: add a review queue before any YAML changes.\n",
                "2026-05-03 Action.md": "Action: implemented dry-run approval primitives.\n",
                "Project Alpha.md": "Project: LINZA onboarding.\n",
                "Project Beta.md": "Project: LINZA review flow.\n",
                "Project Gamma.md": "Project: LINZA context packs.\n",
                "Project Delta.md": "Project: LINZA safe writes.\n",
                "Project Epsilon.md": "Project: LINZA vault discovery.\n",
            }
            for filename, body in notes.items():
                (vault / "Product" / filename).write_text(
                    f"# {Path(filename).stem}\n\n{body}",
                    encoding="utf-8",
                )

            result = asyncio.run(core.build_review_apply_queue(max_notes=20, max_domains=4, limit=5))

            item_types = [item["approval"]["arguments"]["item_type"] for item in result["items"]]
            self.assertLessEqual(len(result["items"]), 5)
            self.assertIn("causal_link", item_types)
        finally:
            storage.close()
            tmp.cleanup()
