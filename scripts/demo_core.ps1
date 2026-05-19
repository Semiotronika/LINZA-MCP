# Demo: LINZA core read/review flow on a local vault.
param(
    [Parameter(Mandatory=$true)]
    [string]$VaultPath,

    [string]$EmbedProvider = $(if ($env:LINZA_EMBED_PROVIDER) { $env:LINZA_EMBED_PROVIDER } else { "lmstudio" }),
    [string]$EmbedUrl = $(if ($env:LINZA_EMBED_URL) { $env:LINZA_EMBED_URL } else { "http://127.0.0.1:1234/v1" }),
    [string]$EmbedModel = $env:LINZA_EMBED_MODEL,
    [string]$EmbedKey = $env:LINZA_EMBED_KEY
)

$vault = Resolve-Path -LiteralPath $VaultPath
$scriptDir = Split-Path -Parent $PSCommandPath
$linzaDir = Resolve-Path -LiteralPath (Join-Path $scriptDir "..")

Set-Location -LiteralPath $linzaDir

Write-Host "=== LINZA Demo ===" -ForegroundColor Cyan
Write-Host "Vault: $vault"
Write-Host "Embedding provider: $EmbedProvider"
Write-Host "Embedding endpoint: $EmbedUrl"
Write-Host ""

python -c @"
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, r'$linzaDir')

from linza_mcp import LinzaCore, LinzaStorage
from linza_mcp.embed import get_embedding_provider

vault = Path(r'$vault')
storage = LinzaStorage(vault, vault / '.linza' / 'linza.db')
provider = get_embedding_provider(
    r'$EmbedProvider',
    r'$EmbedUrl',
    r'$EmbedKey',
    r'$EmbedModel',
)
core = LinzaCore(storage, provider, {})

async def main():
    try:
        doctor = await core.agent_workspace(action='doctor')
        print('=== DOCTOR ===')
        print(f"Status: {doctor.get('status')}")
        print(f"Indexed files: {doctor.get('counts', {}).get('indexed_files')}")
        print(f"Artifacts: {doctor.get('counts', {}).get('artifacts')}")
        print()

        print('=== INDEX ===')
        await core.index_vault(force=False)
        print(f"Files: {storage.get_file_count()}")
        print(f"Semantic bridges: {len(storage.get_all_bridges())}")
        print()

        print('=== MAP ===')
        workspace_map = await core.agent_workspace(action='map', limit=8)
        human_view = workspace_map.get('human_view', {})
        print(human_view.get('summary') or workspace_map.get('status'))
        for action in human_view.get('next_actions', [])[:5]:
            print(f"- {action}")
        print()

        print('=== REVIEW QUEUE ===')
        queue = await core.build_review_apply_queue(max_notes=40, max_domains=6, limit=8)
        print(f"Queue items: {queue.get('summary', {}).get('items')}")
        for item in queue.get('items', [])[:5]:
            print(f"- [{item.get('id')}] {item.get('kind')}: {item.get('title')}")
    finally:
        storage.close()

asyncio.run(main())
"@
