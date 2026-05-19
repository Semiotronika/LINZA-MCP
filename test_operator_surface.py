from test_support import *


class OperatorSurfaceTests(OperatorTestCase):

    def test_storage_records_schema_version_for_migrations(self):
        from linza_mcp.storage import LINZA_SCHEMA_VERSION, SCHEMA_MIGRATIONS

        tmp = tempfile.TemporaryDirectory()
        db_path = Path(tmp.name) / ".linza" / "linza.db"
        storage = Storage(db_path)
        try:
            user_version = int(storage.conn.execute("PRAGMA user_version").fetchone()[0])
            rows = storage.conn.execute(
                "SELECT version, description FROM schema_migrations ORDER BY version"
            ).fetchall()
            self.assertEqual(user_version, LINZA_SCHEMA_VERSION)
            self.assertEqual(
                [(row["version"], row["description"]) for row in rows],
                list(SCHEMA_MIGRATIONS),
            )
        finally:
            storage.close()
            tmp.cleanup()

    def test_index_recomputes_when_embedding_signature_changes(self):
        class FixedEmbeddingProvider:
            def __init__(self, model: str, vector: list[float]):
                self.model = model
                self.vector = vector

            async def embed(self, texts: list[str]) -> list[list[float]]:
                return [list(self.vector) for _ in texts]

        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        (vault / "Alpha.md").write_text("alpha beta gamma", encoding="utf-8")
        storage = Storage(vault / ".linza" / "linza.db")
        try:
            first_core = LinzaCore(vault, storage, FixedEmbeddingProvider("tiny-a", [1.0, 0.0]))
            asyncio.run(first_core.index_vault())
            first = storage.get_file_metadata("Alpha.md")
            self.assertEqual(first["embedding_provider"], "FixedEmbeddingProvider")
            self.assertEqual(first["embedding_model"], "tiny-a")
            self.assertEqual(first["embedding_dim"], 2)
            self.assertEqual(first["embedding"], [1.0, 0.0])

            second_core = LinzaCore(vault, storage, FixedEmbeddingProvider("tiny-b", [0.0, 1.0, 0.0]))
            asyncio.run(second_core.index_vault(force=False))
            second = storage.get_file_metadata("Alpha.md")
            self.assertEqual(second["embedding_model"], "tiny-b")
            self.assertEqual(second["embedding_dim"], 3)
            self.assertEqual(second["embedding"], [0.0, 1.0, 0.0])

            search = asyncio.run(second_core.search("alpha", top_k=1))
            self.assertNotIn("error", search)
        finally:
            storage.close()
            tmp.cleanup()

    def test_direct_module_imports_preserve_core_contract(self):
        from linza_mcp.diagnostics import build_bases_plan_markdown as direct_bases_plan
        from linza_mcp.diagnostics import build_diagnostic_markdown as direct_diagnostic_report
        from linza_mcp.diagnostics import build_review_queue_markdown as direct_review_report
        from linza_mcp.diagnostics import build_semantic_links_markdown as direct_semantic_report
        from linza_mcp.diagnostics import build_yaml_suggestions_markdown as direct_yaml_report
        from linza_mcp.diagnostics import explain_relationship as direct_explain_relationship
        from linza_mcp.diagnostics import scan_vault as direct_scan_vault
        from linza_mcp.diagnostics import suggest_properties_for_note as direct_suggest_properties
        from linza_mcp.domains import dedupe_draft_domain_names as direct_dedupe_domains
        from linza_mcp.domains import domain_centroid as direct_domain_centroid
        from linza_mcp.domains import domain_name as direct_domain_name
        from linza_mcp.domains import domain_name_candidates as direct_domain_names
        from linza_mcp.domains import domain_terms as direct_domain_terms
        from linza_mcp.domains import draft_record_text as direct_draft_record_text
        from linza_mcp.domains import merge_draft_domains as direct_merge_domains
        from linza_mcp.domains import record_similarity as direct_record_similarity
        from linza_mcp.domains import refresh_draft_domain as direct_refresh_domain
        from linza_mcp.domains import vector_cosine as direct_vector_cosine
        from linza_mcp.draft_map import build_event_flow_draft as direct_event_flow_draft
        from linza_mcp.draft_map import build_lens_suggestions as direct_lens_suggestions
        from linza_mcp.draft_map import build_memory_draft as direct_memory_draft
        from linza_mcp.draft_map import build_role_draft as direct_role_draft
        from linza_mcp.draft_map import draft_vault_map as direct_draft_vault_map
        from linza_mcp.draft_map import group_records_by_role_or_folder as direct_record_groups
        from linza_mcp.draft_map import parent_score as direct_parent_score
        from linza_mcp.draft_map import percentile as direct_percentile
        from linza_mcp.draft_map import select_draft_notes as direct_select_notes
        from linza_mcp.chunker import split_semantic_chunks as direct_semantic_chunks
        from linza_mcp.core import LinzaCore as DirectCore
        from linza_mcp.embed import LMStudioProvider as DirectLMStudio
        from linza_mcp.embed import MeanCenteredEmbeddings as DirectCenterer
        from linza_mcp.graph import check_rule as direct_check_rule
        from linza_mcp.graph import explain_node as direct_explain_node
        from linza_mcp.graph import show_flow as direct_show_flow
        from linza_mcp.graph import who_depends as direct_who_depends
        from linza_mcp.indexing import build_context_pack_markdown as direct_context_pack
        from linza_mcp.indexing import calibrate_embeddings as direct_calibrate
        from linza_mcp.indexing import classify_relation_candidate as direct_classify_relation
        from linza_mcp.indexing import create_profile as direct_create_profile
        from linza_mcp.indexing import index_single_file as direct_index_single
        from linza_mcp.indexing import index_vault as direct_index_vault
        from linza_mcp.indexing import rebuild_bridges as direct_rebuild_bridges
        from linza_mcp.indexing import recenter_profiles as direct_recenter_profiles
        from linza_mcp.indexing import search as direct_search
        from linza_mcp.indexing import suggest_links as direct_suggest_links
        from linza_mcp.operator import guide_next_steps as direct_guide_next_steps
        from linza_mcp.properties import patch_note_properties as direct_patch_properties
        from linza_mcp.artifacts import ingest_artifacts as direct_ingest_artifacts
        from linza_mcp.calibr import record_trace as direct_record_trace
        from linza_mcp.review_queue import approve_draft_item as direct_approve_draft
        from linza_mcp.review_queue import build_review_apply_queue as direct_build_queue
        from linza_mcp.review_queue import approve_review_queue_items as direct_approve_queue
        from linza_mcp.review_queue import apply_learned_review_queue as direct_apply_learned_queue
        from linza_mcp.server import LinzaMCPServer as DirectMCPServer
        from linza_mcp.server import load_config_from_env as direct_load_config
        from linza_mcp.storage import Storage as DirectStorage
        from linza_mcp.tags import audit_tag_vocabulary as direct_audit_tags
        from linza_mcp.tags import build_tag_vocabulary_markdown as direct_tag_report
        from linza_mcp.tags import suggest_tag_candidates as direct_suggest_tags
        from linza_mcp.workflows import agent_workspace as direct_agent_workspace
        from linza_mcp.workflows import doctor as direct_doctor
        import server as root_server

        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        storage = DirectStorage(vault / ".linza" / "linza.db")
        core = DirectCore(vault, storage, StableTestEmbeddingProvider(dim=2))
        try:
            self.assertEqual(DirectLMStudio.__module__, "linza_mcp.embed")
            self.assertEqual(DirectStorage.__module__, "linza_mcp.storage")
            self.assertEqual(DirectMCPServer.__module__, "linza_mcp.server")
            self.assertEqual(direct_load_config.__module__, "linza_mcp.server")
            self.assertEqual(root_server.LinzaCore.__module__, "linza_mcp.compat")
            self.assertEqual(root_server.LinzaMCPServer.__module__, "linza_mcp.server")
            vectors = asyncio.run(StableTestEmbeddingProvider(dim=4).embed(["alpha beta", "beta gamma"]))
            self.assertEqual(len(vectors), 2)
            self.assertEqual(len(vectors[0]), 4)
            centerer = DirectCenterer()
            centered = centerer.fit_transform([[1.0, 0.0], [0.0, 1.0]])
            self.assertEqual(centered, [[0.5, -0.5], [-0.5, 0.5]])
            self.assertEqual(direct_approve_draft.__module__, "linza_mcp.review_queue")
            self.assertEqual(direct_build_queue.__module__, "linza_mcp.review_queue")
            self.assertEqual(direct_approve_queue.__module__, "linza_mcp.review_queue")
            self.assertEqual(direct_apply_learned_queue.__module__, "linza_mcp.review_queue")
            self.assertEqual(direct_explain_node.__module__, "linza_mcp.graph")
            self.assertEqual(direct_who_depends.__module__, "linza_mcp.graph")
            self.assertEqual(direct_show_flow.__module__, "linza_mcp.graph")
            self.assertEqual(direct_check_rule.__module__, "linza_mcp.graph")
            self.assertEqual(direct_index_vault.__module__, "linza_mcp.indexing")
            self.assertEqual(direct_index_single.__module__, "linza_mcp.indexing")
            self.assertEqual(direct_rebuild_bridges.__module__, "linza_mcp.indexing")
            self.assertEqual(direct_recenter_profiles.__module__, "linza_mcp.indexing")
            self.assertEqual(direct_calibrate.__module__, "linza_mcp.indexing")
            self.assertEqual(direct_classify_relation.__module__, "linza_mcp.indexing")
            self.assertEqual(direct_search.__module__, "linza_mcp.indexing")
            self.assertEqual(direct_suggest_links.__module__, "linza_mcp.indexing")
            self.assertEqual(direct_create_profile.__module__, "linza_mcp.indexing")
            self.assertEqual(direct_context_pack.__module__, "linza_mcp.indexing")
            self.assertEqual(direct_guide_next_steps.__module__, "linza_mcp.operator")
            self.assertEqual(direct_patch_properties.__module__, "linza_mcp.properties")
            self.assertEqual(direct_ingest_artifacts.__module__, "linza_mcp.artifacts")
            self.assertEqual(direct_record_trace.__module__, "linza_mcp.calibr")
            self.assertEqual(direct_agent_workspace.__module__, "linza_mcp.workflows")
            self.assertEqual(direct_doctor.__module__, "linza_mcp.workflows")
            self.assertEqual(direct_audit_tags.__module__, "linza_mcp.tags")
            self.assertEqual(direct_suggest_tags.__module__, "linza_mcp.tags")
            self.assertEqual(direct_tag_report.__module__, "linza_mcp.tags")
            self.assertEqual(direct_scan_vault.__module__, "linza_mcp.diagnostics")
            self.assertEqual(direct_suggest_properties.__module__, "linza_mcp.diagnostics")
            self.assertEqual(direct_yaml_report.__module__, "linza_mcp.diagnostics")
            self.assertEqual(direct_review_report.__module__, "linza_mcp.diagnostics")
            self.assertEqual(direct_diagnostic_report.__module__, "linza_mcp.diagnostics")
            self.assertEqual(direct_semantic_report.__module__, "linza_mcp.diagnostics")
            self.assertEqual(direct_explain_relationship.__module__, "linza_mcp.diagnostics")
            self.assertEqual(direct_bases_plan.__module__, "linza_mcp.diagnostics")
            self.assertEqual(direct_domain_terms.__module__, "linza_mcp.domains")
            self.assertEqual(direct_record_similarity.__module__, "linza_mcp.domains")
            self.assertEqual(direct_dedupe_domains.__module__, "linza_mcp.domains")
            self.assertEqual(direct_vector_cosine.__module__, "linza_mcp.domains")
            self.assertEqual(direct_draft_record_text.__module__, "linza_mcp.domains")
            self.assertEqual(direct_domain_centroid.__module__, "linza_mcp.domains")
            self.assertEqual(direct_refresh_domain.__module__, "linza_mcp.domains")
            self.assertEqual(direct_merge_domains.__module__, "linza_mcp.domains")
            self.assertEqual(direct_domain_name.__module__, "linza_mcp.domains")
            self.assertEqual(direct_domain_names.__module__, "linza_mcp.domains")
            self.assertEqual(direct_role_draft.__module__, "linza_mcp.draft_map")
            self.assertEqual(direct_event_flow_draft.__module__, "linza_mcp.draft_map")
            self.assertEqual(direct_memory_draft.__module__, "linza_mcp.draft_map")
            self.assertEqual(direct_lens_suggestions.__module__, "linza_mcp.draft_map")
            self.assertEqual(direct_draft_vault_map.__module__, "linza_mcp.draft_map")
            self.assertEqual(direct_semantic_chunks.__module__, "linza_mcp.chunker")
            self.assertEqual(direct_percentile.__module__, "linza_mcp.draft_map")
            self.assertEqual(direct_parent_score.__module__, "linza_mcp.draft_map")
            self.assertEqual(direct_select_notes.__module__, "linza_mcp.draft_map")
            self.assertEqual(direct_record_groups.__module__, "linza_mcp.draft_map")
            self.assertTrue(hasattr(core, "approve_review_queue_items"))
            self.assertTrue(hasattr(core, "explain_node"))
            (vault / "Alpha.md").write_text("alpha", encoding="utf-8")
            asyncio.run(core.index_vault(with_embeddings=True))
            self.assertEqual(storage.load_corpus_mean()[1], 1)
            approved_id = storage.add_approved_item("memory_item", {"summary": "ok"})
            self.assertEqual(storage.get_approved_item_by_id(approved_id)["payload"]["summary"], "ok")
            (vault / "Tagged.md").write_text(
                "---\ntags:\n  - retrieval-layer\n---\nBody #inline_tag retrieval layer.\n",
                encoding="utf-8",
            )
            audit = core.audit_tag_vocabulary()
            self.assertEqual(audit["tool"], "audit_tags")
            suggestions = core.suggest_tag_candidates("Tagged.md")
            self.assertTrue(suggestions["read_only"])
            self.assertIn("LINZA Tag Vocabulary Audit", core.build_tag_vocabulary_markdown())
        finally:
            storage.close()
            tmp.cleanup()

    def test_mcp_surface_registers_expected_tools(self):
        from mcp.types import ListToolsRequest
        from linza_mcp.operator import ADVANCED_MCP_TOOLS, DEFAULT_MCP_TOOLS, TOOL_AUDIENCE, TOOL_GUIDE
        from linza_mcp.server import LinzaMCPServer, REPORT_DEFAULTS

        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        server = LinzaMCPServer(vault, StableTestEmbeddingProvider(), {"default_profile": "general"})
        try:
            handler = server.server.request_handlers[ListToolsRequest]
            result = asyncio.run(handler(ListToolsRequest(method="tools/list")))
            tools = {tool.name: tool for tool in result.root.tools}

            self.assertEqual(set(tools), set(DEFAULT_MCP_TOOLS))
            self.assertEqual(len(DEFAULT_MCP_TOOLS), 15)
            self.assertEqual(set(DEFAULT_MCP_TOOLS) | set(ADVANCED_MCP_TOOLS), set(TOOL_GUIDE))
            self.assertTrue(set(DEFAULT_MCP_TOOLS).isdisjoint(set(ADVANCED_MCP_TOOLS)))
            self.assertEqual(set(TOOL_AUDIENCE), set(TOOL_GUIDE))
            self.assertEqual(TOOL_AUDIENCE["guide_next_steps"], "human_entry")
            self.assertEqual(TOOL_AUDIENCE["agent_workspace"], "agent_facade")
            self.assertIn("agent_workspace", tools)
            self.assertIn("build_review_apply_queue", tools)
            self.assertNotIn("create_profile", tools)
            self.assertNotIn("build_diagnostic_report", tools)
            self.assertEqual(
                tools["build_review_apply_queue"].inputSchema["properties"]["path"]["default"],
                REPORT_DEFAULTS["review_apply_queue"],
            )
            self.assertFalse(
                tools["guide_next_steps"].inputSchema["properties"]["include_tool_guide"]["default"],
            )
            self.assertIn("action", tools["agent_workspace"].inputSchema["required"])
            self.assertIn("ingest_artifacts", tools["agent_workspace"].inputSchema["properties"]["action"]["enum"])
            self.assertIn("map", tools["agent_workspace"].inputSchema["properties"]["action"]["enum"])
            self.assertIn("grow", tools["agent_workspace"].inputSchema["properties"]["action"]["enum"])
            self.assertIn("record_trace", tools["agent_workspace"].inputSchema["properties"]["action"]["enum"])
            self.assertIn("review_calibr", tools["agent_workspace"].inputSchema["properties"]["action"]["enum"])
            self.assertIn("doctor", tools["agent_workspace"].inputSchema["properties"]["action"]["enum"])
            self.assertEqual(tools["agent_workspace"].inputSchema["properties"]["max_notes"]["default"], 120)
            self.assertEqual(tools["agent_workspace"].inputSchema["properties"]["max_domains"]["default"], 8)
            self.assertEqual(tools["agent_workspace"].inputSchema["properties"]["mode"]["default"], "assisted")
            self.assertTrue(tools["agent_workspace"].inputSchema["properties"]["dry_run"]["default"])
            self.assertTrue(REPORT_DEFAULTS["review_apply_queue"].startswith(".linza/reports/"))

            advanced_server = LinzaMCPServer(
                vault / "advanced",
                StableTestEmbeddingProvider(),
                {"default_profile": "general", "tool_surface": "advanced"},
            )
            try:
                advanced_handler = advanced_server.server.request_handlers[ListToolsRequest]
                advanced_result = asyncio.run(advanced_handler(ListToolsRequest(method="tools/list")))
                advanced_tools = {tool.name: tool for tool in advanced_result.root.tools}
                self.assertEqual(set(advanced_tools), set(TOOL_GUIDE))
                self.assertEqual(
                    advanced_tools["patch_properties"].inputSchema["properties"]["namespace"]["default"],
                    "linza",
                )
                self.assertIn("create_profile", advanced_tools)
                self.assertIn("build_diagnostic_report", advanced_tools)
            finally:
                advanced_server.storage.close()
        finally:
            server.storage.close()
            tmp.cleanup()

    def test_cli_version_and_help_do_not_start_server(self):
        from contextlib import redirect_stdout
        from io import StringIO

        from linza_mcp.cli import main
        from linza_mcp.compat import __version__

        version_output = StringIO()
        with self.assertRaises(SystemExit) as version_exit:
            with redirect_stdout(version_output):
                main(["--version"])
        self.assertEqual(version_exit.exception.code, 0)
        self.assertIn(f"linza-mcp {__version__}", version_output.getvalue())

        help_output = StringIO()
        with self.assertRaises(SystemExit) as help_exit:
            with redirect_stdout(help_output):
                main(["--help"])
        self.assertEqual(help_exit.exception.code, 0)
        self.assertIn("Run the LINZA MCP stdio server.", help_output.getvalue())

    def test_publishable_agent_pack_docs_are_private_safe(self):
        from linza_mcp.artifacts import ALLOWED_ARTIFACT_SUFFIXES
        from linza_mcp.compat import __version__

        root = Path(__file__).parent
        required = [
            root / "README.md",
            root / "README_EN.md",
            root / "pyproject.toml",
            root / "MANIFEST.in",
            root / "LICENSE",
            root / "SECURITY.md",
            root / "CHANGELOG.md",
            root / "CONTRIBUTING.md",
            root / "server.json",
            root / "glama.json",
            root / "LINZA_TOOL_CATALOG.md",
            root / "LINZA_TOOL_GUIDE.md",
            root / "scripts" / "README.md",
            root / "agent-pack" / "README.md",
            root / "agent-pack" / "skills" / "linza-operator" / "SKILL.md",
            root / "agent-pack" / "skills" / "linza-operator" / "references" / "workflows.md",
            root / "agent-pack" / "skills" / "linza-operator" / "references" / "safety-policy.md",
            root / "agent-pack" / "skills" / "linza-operator" / "references" / "tool-audience.md",
        ]
        for path in required:
            self.assertTrue(path.exists(), str(path))

        skill = (root / "agent-pack" / "skills" / "linza-operator" / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\n"))
        self.assertIn("name: linza-operator", skill)
        self.assertIn("description:", skill)
        self.assertIn("references/workflows.md", skill)

        combined = "\n".join(path.read_text(encoding="utf-8") for path in required)
        forbidden = [
            "Masha",
            "Маша",
            "base — копия",
            "Новый лог",
            "C:\\Users\\",
            ".zeroclaw",
        ]
        for marker in forbidden:
            self.assertNotIn(marker, combined)

        self.assertIn("локальный review-gated sidecar", (root / "README.md").read_text(encoding="utf-8"))
        self.assertIn("Local MCP Server", (root / "README_EN.md").read_text(encoding="utf-8"))
        self.assertIn("mcp-name: io.github.semiotronika/linza-mcp", (root / "README.md").read_text(encoding="utf-8"))
        self.assertNotIn("NOUZ", (root / "README.md").read_text(encoding="utf-8"))
        self.assertNotIn("NOUZ", (root / "README_EN.md").read_text(encoding="utf-8"))
        self.assertNotIn("назначаются вручную", (root / "README.md").read_text(encoding="utf-8"))
        self.assertNotIn("coverage", (root / "README.md").read_text(encoding="utf-8"))
        self.assertIn("Obsidian или любой другой", (root / "README.md").read_text(encoding="utf-8"))
        self.assertIn("It does not change your data", (root / "README_EN.md").read_text(encoding="utf-8"))
        self.assertIn("First Output Example", (root / "README_EN.md").read_text(encoding="utf-8"))
        self.assertIn("prompt injection", (root / "README.md").read_text(encoding="utf-8"))
        self.assertIn("prompt-injection", (root / "README_EN.md").read_text(encoding="utf-8"))
        public_embedding_docs = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                root / "README.md",
                root / "README_EN.md",
                root / "server.json",
                root / "agent-pack" / "skills" / "linza-operator" / "SKILL.md",
            ]
        )
        removed_provider_name = "hash"
        self.assertNotIn(f"`{removed_provider_name}`", public_embedding_docs)
        self.assertNotIn(f"LINZA_EMBED_PROVIDER={removed_provider_name}", public_embedding_docs)
        for env_var in {"LINZA_EMBED_KEY", "LINZA_BRIDGE_THRESHOLD", "LINZA_DEFAULT_PROFILE"}:
            self.assertIn(env_var, (root / "README.md").read_text(encoding="utf-8"))
            self.assertIn(env_var, (root / "README_EN.md").read_text(encoding="utf-8"))
        import tomllib
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "linza-mcp")
        self.assertEqual(pyproject["project"]["version"], __version__)
        self.assertEqual(pyproject["project"]["readme"], "README_EN.md")
        self.assertEqual(pyproject["project"]["scripts"]["linza-mcp"], "linza_mcp.cli:main")
        self.assertIn("mcp >= 1.0.0", pyproject["project"]["dependencies"])
        self.assertIn("defusedxml >= 0.7", pyproject["project"]["dependencies"])

        manifest = (root / "MANIFEST.in").read_text(encoding="utf-8")
        self.assertIn("include CONTRIBUTING.md", manifest)
        self.assertIn("include LINZA_TOOL_GUIDE.md", manifest)

        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
        for ignored in [".env", ".env.*", ".venv/", "venv/"]:
            self.assertIn(ignored, gitignore)

        server_json = json.loads((root / "server.json").read_text(encoding="utf-8"))
        self.assertEqual(server_json["name"], "io.github.semiotronika/linza-mcp")
        self.assertEqual(server_json["version"], __version__)
        self.assertEqual(server_json["packages"][0]["registryType"], "pypi")
        self.assertEqual(server_json["packages"][0]["identifier"], "linza-mcp")
        self.assertEqual(server_json["packages"][0]["version"], __version__)
        self.assertEqual(server_json["packages"][0]["transport"]["type"], "stdio")
        env_names = {
            item["name"]
            for item in server_json["packages"][0]["environmentVariables"]
        }
        self.assertEqual(
            env_names,
            {
                "LINZA_VAULT",
                "LINZA_EMBED_PROVIDER",
                "LINZA_EMBED_URL",
                "LINZA_EMBED_MODEL",
                "LINZA_EMBED_KEY",
                "LINZA_BRIDGE_THRESHOLD",
                "LINZA_DEFAULT_PROFILE",
                "LINZA_TOOL_SURFACE",
            },
        )
        glama = json.loads((root / "glama.json").read_text(encoding="utf-8"))
        self.assertEqual(glama["$schema"], "https://glama.ai/mcp/schemas/server.json")
        self.assertIn("Semiotronika", glama["maintainers"])

        from linza_mcp.embed import LMStudioProvider, get_embedding_provider
        from linza_mcp.server import load_config_from_env
        self.assertEqual(load_config_from_env()["embed_provider"], "lmstudio")
        self.assertIsInstance(get_embedding_provider(""), LMStudioProvider)
        self.assertIsInstance(
            get_embedding_provider("lmstudio", "http://127.0.0.1:1234/v1"),
            LMStudioProvider,
        )
        production_embedding_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in [
                root / "linza_mcp" / "embed.py",
                root / "linza_mcp" / "server.py",
                root / "linza_mcp" / "__init__.py",
                root / "server.py",
            ]
        )
        legacy_provider_symbol = "Hashing" + "EmbeddingProvider"
        self.assertNotIn(legacy_provider_symbol, production_embedding_source)
        with self.assertRaisesRegex(ValueError, "lmstudio, openai, or ollama"):
            get_embedding_provider(removed_provider_name)

        self.assertIn("examples/sample-vault", combined)
        self.assertIn("TOOL_AUDIENCE", combined)
        self.assertIn("DEFAULT_MCP_TOOLS", combined)
        self.assertIn("LINZA_TOOL_SURFACE=advanced", combined)
        self.assertIn("browser/web-fetch", combined)
        self.assertIn("source_kind=\"web_article\"", combined)
        self.assertIn("Tool Catalog", combined)
        self.assertIn('agent_workspace(action="teach")', combined)
        self.assertIn("selected_rules", combined)
        self.assertIn("Error Handling", skill)
        self.assertIn("developer/CI-facing", (root / "scripts" / "README.md").read_text(encoding="utf-8"))
        self.assertIn("from linza_mcp import (", (root / "server.py").read_text(encoding="utf-8"))
        self.assertNotIn("from linza_mcp import *", (root / "server.py").read_text(encoding="utf-8"))
        self.assertNotIn('__import__("json")', (root / "linza_mcp" / "embed.py").read_text(encoding="utf-8"))
        self.assertNotIn("build_apply_queue", (root / "linza_mcp" / "server.py").read_text(encoding="utf-8"))
        public_scripts = {path.name for path in (root / "scripts").iterdir()}
        self.assertEqual(
            public_scripts,
            {"README.md", "linza_doctor.py", "smoke_mcp_tools.py", "smoke_copy_vault.py", "demo_core.ps1"},
        )
        script_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / "scripts").iterdir()
            if path.is_file()
        )
        self.assertNotIn(legacy_provider_symbol, script_text)
        self.assertIn("get_embedding_provider", script_text)
        for internal_script in {
            "complete_copy_onboarding.py",
            "live_copy_walkthrough.py",
            "clear_linza_yaml.py",
            "reformat_linza_yaml.py",
            "restore_frontmatter_from_backup.py",
            "clean_vault.ps1",
        }:
            self.assertNotIn(internal_script, public_scripts)
        from linza_mcp.operator import TOOL_GUIDE
        catalog = (root / "LINZA_TOOL_CATALOG.md").read_text(encoding="utf-8")
        guide = (root / "LINZA_TOOL_GUIDE.md").read_text(encoding="utf-8")
        for tool_name in TOOL_GUIDE:
            self.assertIn(f"`{tool_name}`", catalog)
        self.assertEqual(guide.count("5. Memory"), 1)
        self.assertIn("6. calibr lens", guide)
        self.assertNotIn(".log", ALLOWED_ARTIFACT_SUFFIXES)
        self.assertEqual({".md", ".txt", ".json", ".pdf", ".docx", ".xlsx"}, ALLOWED_ARTIFACT_SUFFIXES)

    def test_chunker_russian_hints_are_not_mojibake_dead_code(self):
        from linza_mcp.chunker import semantic_chunk_kind, strip_generated_service_sections

        self.assertEqual(semantic_chunk_kind("Источник: https://example.com", None), "source")
        self.assertEqual(semantic_chunk_kind("Почему это важно", None), "question")
        body = (
            "# Note\n\n"
            "Keep this.\n\n"
            "## Связи для графа\n\n"
            "Generated service block.\n\n"
            "## Next\n\n"
            "Keep that.\n"
        )

        cleaned = strip_generated_service_sections(body)
        self.assertIn("Keep this.", cleaned)
        self.assertIn("Keep that.", cleaned)
        self.assertNotIn("Generated service block.", cleaned)

    def test_artifact_file_extractors_support_office_documents(self):
        tmp, vault, storage, core = self.make_core()
        try:
            docs = vault / "incoming"
            docs.mkdir()
            docx_path = docs / "Decision Brief.docx"
            with zipfile.ZipFile(docx_path, "w") as archive:
                archive.writestr(
                    "word/document.xml",
                    (
                        '<?xml version="1.0" encoding="UTF-8"?>'
                        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                        "<w:body>"
                        "<w:p><w:r><w:t>Decision: imported documents stay behind review.</w:t></w:r></w:p>"
                        "<w:p><w:r><w:t>Result: agents can use document text without rewriting notes.</w:t></w:r></w:p>"
                        "</w:body></w:document>"
                    ),
                )

            xlsx_path = docs / "Review Metrics.xlsx"
            with zipfile.ZipFile(xlsx_path, "w") as archive:
                archive.writestr(
                    "xl/workbook.xml",
                    (
                        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                        '<sheets><sheet name="Metrics" sheetId="1" r:id="rId1"/></sheets></workbook>'
                    ),
                )
                archive.writestr(
                    "xl/_rels/workbook.xml.rels",
                    (
                        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
                        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
                        "</Relationships>"
                    ),
                )
                archive.writestr(
                    "xl/sharedStrings.xml",
                    (
                        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                        "<si><t>Metric</t></si><si><t>Reviewable cards</t></si><si><t>Status</t></si><si><t>Ready</t></si>"
                        "</sst>"
                    ),
                )
                archive.writestr(
                    "xl/worksheets/sheet1.xml",
                    (
                        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                        "<sheetData>"
                        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                        '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c></row>'
                        "</sheetData></worksheet>"
                    ),
                )

            ingest = asyncio.run(core.agent_workspace(
                action="ingest_artifacts",
                source_kind="document",
                batch_id="office-docs",
                artifacts=[
                    {"path": "incoming/Decision Brief.docx"},
                    {"path": "incoming/Review Metrics.xlsx"},
                ],
            ))

            self.assertEqual(ingest["summary"]["stored"], 2)
            contents = [
                storage.get_artifact(item["id"])["content"]
                for item in ingest["artifacts"]
            ]
            self.assertTrue(any("imported documents stay behind review" in content for content in contents))
            self.assertTrue(any("Reviewable cards" in content and "Ready" in content for content in contents))
            metadata = [
                storage.get_artifact(item["id"])["metadata"]
                for item in ingest["artifacts"]
            ]
            self.assertEqual({item["extractor"] for item in metadata}, {"docx-xml", "xlsx-xml"})
            self.assertTrue(all(item["source_sha256"] for item in metadata))

            if not importlib.util.find_spec("pypdf") and not importlib.util.find_spec("PyPDF2"):
                pdf_path = docs / "Report.pdf"
                pdf_path.write_bytes(b"%PDF-1.4\n% synthetic placeholder\n")
                with self.assertRaisesRegex(ValueError, "PDF extraction requires optional dependency"):
                    asyncio.run(core.agent_workspace(
                        action="ingest_artifacts",
                        source_kind="document",
                        artifacts=[{"path": "incoming/Report.pdf"}],
                    ))
        finally:
            storage.close()
            tmp.cleanup()

    def test_mcp_report_writes_use_sidecar_defaults_not_visible_notes(self):
        from linza_mcp.server import LinzaMCPServer, REPORT_DEFAULTS

        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        server = LinzaMCPServer(vault, StableTestEmbeddingProvider(), {"default_profile": "general"})
        try:
            diagnostic = asyncio.run(server._call_tool("build_diagnostic_report", {"write": True}))
            diagnostic_payload = json.loads(diagnostic.content[0].text)
            self.assertEqual(diagnostic_payload["status"], "written")
            self.assertEqual(diagnostic_payload["path"], REPORT_DEFAULTS["diagnostic"])
            self.assertTrue((vault / REPORT_DEFAULTS["diagnostic"]).exists())
            self.assertFalse((vault / "LINZA").exists())

            (vault / "Context.md").write_text("semantic search graph context", encoding="utf-8")
            asyncio.run(server.core.index_vault(force=True))
            context_pack = asyncio.run(server._call_tool("create_context_pack", {
                "title": "Visible clutter check",
                "query": "semantic search",
                "write": True,
            }))
            context_payload = json.loads(context_pack.content[0].text)
            self.assertEqual(context_payload["status"], "written")
            self.assertTrue(context_payload["path"].startswith(".linza/context-packs/"))
            self.assertTrue((vault / context_payload["path"]).exists())
            self.assertFalse((vault / "LINZA").exists())

            visible = vault / "Visible.md"
            visible.write_text("human note", encoding="utf-8")
            blocked_report = asyncio.run(server._call_tool("build_diagnostic_report", {
                "write": True,
                "path": "Visible.md",
            }))
            blocked_report_payload = json.loads(blocked_report.content[0].text)
            self.assertEqual(blocked_report_payload["status"], "blocked")
            self.assertEqual(visible.read_text(encoding="utf-8"), "human note")

            blocked_context_pack = asyncio.run(server._call_tool("create_context_pack", {
                "title": "Blocked context",
                "query": "semantic search",
                "write": True,
                "path": "Context.md",
            }))
            blocked_context_payload = json.loads(blocked_context_pack.content[0].text)
            self.assertEqual(blocked_context_payload["status"], "blocked")
            self.assertEqual((vault / "Context.md").read_text(encoding="utf-8"), "semantic search graph context")
        finally:
            server.storage.close()
            tmp.cleanup()

    def test_mcp_write_file_is_dry_run_and_blocks_existing_notes_by_default(self):
        from linza_mcp.server import LinzaMCPServer

        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        server = LinzaMCPServer(vault, StableTestEmbeddingProvider(), {"default_profile": "general"})
        try:
            existing = vault / "Existing.md"
            original = "# Existing\n\nOriginal body.\n"
            with existing.open("w", encoding="utf-8", newline="") as handle:
                handle.write(original)

            preview = asyncio.run(server._call_tool("write_file", {
                "path": "New.md",
                "content": "# New\n\nDraft body.\n",
            }))
            preview_payload = json.loads(preview.content[0].text)
            self.assertEqual(preview_payload["status"], "preview")
            self.assertFalse((vault / "New.md").exists())

            blocked = asyncio.run(server._call_tool("write_file", {
                "path": "Existing.md",
                "content": "# Existing\n\nChanged body.\n",
                "dry_run": False,
            }))
            blocked_payload = json.loads(blocked.content[0].text)
            self.assertEqual(blocked_payload["status"], "blocked")
            with existing.open("r", encoding="utf-8", newline="") as handle:
                self.assertEqual(handle.read(), original)

            written = asyncio.run(server._call_tool("write_file", {
                "path": "New.md",
                "content": "# New\n\nDraft body.\n",
                "dry_run": False,
            }))
            written_payload = json.loads(written.content[0].text)
            self.assertEqual(written_payload["status"], "written")
            with (vault / "New.md").open("r", encoding="utf-8", newline="") as handle:
                self.assertEqual(handle.read(), "# New\n\nDraft body.\n")
            self.assertIsNotNone(server.storage.get_file_metadata("New.md"))
        finally:
            server.storage.close()
            tmp.cleanup()
