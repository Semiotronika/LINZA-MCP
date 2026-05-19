"""LINZA MCP entry point."""

import anyio

from linza_mcp import (  # noqa: F401
    FRONTMATTER_RE,
    IGNORED_DIRS,
    LINZA_EVENT_PATTERNS,
    LINZA_SCHEMA_VERSION,
    WIKILINK_RE,
    LinzaCore,
    LinzaStorage,
    MeanCenteredEmbeddings,
    Storage,
    __version__,
    agent_workspace,
    chunk_markdown,
    content_hash,
    cosine_similarity,
    extract_events,
    extract_tag_details,
    extract_tags,
    extract_wikilinks,
    format_yaml_block,
    guess_note_role,
    is_legacy_graph_metadata,
    material_type_vocabulary,
    normalize_tag,
    parse_frontmatter,
    patch_frontmatter,
    strip_frontmatter,
)
from linza_mcp.embed import (  # noqa: F401
    EmbeddingProvider,
    LMStudioProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    get_embedding_provider,
)
from linza_mcp.server import LinzaMCPServer, load_config_from_env, main  # noqa: F401


if __name__ == "__main__":
    anyio.run(main)
