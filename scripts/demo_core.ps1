# Demo: LINZA core tools on a raw vault
param(
    [Parameter(Mandatory=$true)]
    [string]$VaultPath
)

$vault = Resolve-Path $VaultPath
$scriptDir = Split-Path -Parent $PSCommandPath
$linzaDir = Resolve-Path (Join-Path $scriptDir "..")

Set-Location $linzaDir

Write-Host "=== LINZA Demo ===" -ForegroundColor Cyan
Write-Host "Vault: $vault"
Write-Host ""

# Run Python demo
python -c @"
import sys, json
sys.path.insert(0, r'$linzaDir')

from linza_mcp import LinzaCore, Storage, HashingEmbeddingProvider

vault = r'$vault'
db_path = f'{vault}/.linza/linza.db'
storage = Storage(db_path)
core = LinzaCore(vault, storage, HashingEmbeddingProvider(dim=512))

# 1. scan_vault
print('=== SCAN ===')
scan = core.scan_vault()
print(f'Total notes: {scan["total_notes"]}')
print(f'Folders: {len(scan["folder_counts"])}')
print(f'Folders list:')
for folder, count in scan['folder_counts'][:10]:
    print(f'  {folder or "(root)"} -> {count} notes')
print(f'Tags found: {len(scan["tag_counts"])}')
print(f'Unresolved links: {len(scan["unresolved_links"])}')
for ul in scan['unresolved_links'][:5]:
    print(f'  [[{ul["link"]}]] x{ul["count"]}')

# 2. draft_vault_map
print()
print('=== DRAFT VAULT MAP ===')
import asyncio
draft = asyncio.run(core.draft_vault_map(max_notes=30, max_domains=6))
print(f'Status: {draft["status"]}')
print(f'Sample: {draft["summary"]["notes"]} notes')
print(f'Domains found: {draft["summary"].get("candidate_domains")}')
print(f'Events found: {draft["summary"].get("event_flow_items")}')
print(f'Roles assigned: {draft["summary"].get("role_drafts")}')
print()
print('--- Candidate Domains ---')
for d in draft['candidate_domains']:
    terms = ', '.join(d.get('representative_terms', d.get('top_terms', []))[:5])
    paths = [n.get('path','') for n in d.get('representative_notes', [])[:3]]
    print(f'  {d.get("display_name", d.get("name","?"))}: {terms}')
    print(f'    notes: {paths}')
print()
print('--- Role Sample ---')
for n in draft['role_draft']['notes'][:8]:
    print(f'  {n["path"]} -> {n["role"]} (confidence: {n["confidence"]})')
print()
print('--- Event Types ---')
for t, c in draft['event_flow_draft']['event_counts'][:6]:
    print(f'  {t}: {c}')
print()
print('--- Lens Suggestions ---')
for lens in draft.get('lens_suggestions', [])[:5]:
    print(f'  {lens["id"]}: {lens["label"]}')

# 3. build_review_apply_queue
print()
print('=== REVIEW QUEUE ===')
queue = asyncio.run(core.build_review_apply_queue(max_notes=30, max_domains=6, limit=10))
print(f'Queue items: {queue["summary"]["items"]}')
for item in queue['items'][:5]:
    print(f'  [{item["id"]}] {item["kind"]}: {item["title"]} (priority: {item["priority"]})')

storage.close()
"@
