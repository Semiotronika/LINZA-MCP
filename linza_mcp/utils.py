import re
from pathlib import Path
from typing import Any


WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]#|]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
TAG_RE = re.compile(r"(?<!\w)#([\w/_-]+)")
HEX_COLOR_TAG_RE = re.compile(r"^[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?$")
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n)?", re.DOTALL)
TAG_SPLIT_RE = re.compile(r"[,\s]+")

COMMON_TAG_HINTS = {
    "note", "notes", "draft", "log", "project", "research", "idea", "article",
    "заметка", "заметки", "черновик", "лог", "проект", "исследование",
    "исследования", "идея", "статья", "данные", "анализ", "метод", "ии",
}
TECHNICAL_TAG_NOISE = {
    "http", "https", "www", "com", "org", "json", "yaml", "true", "false", "none",
    "null", "todo", "fixme", "pytest", "server", "python", "return", "class", "def",
    "import", "from", "path", "file", "files", "error", "test", "tests",
}
DOMAIN_NOISE_TERMS = {
    "graph", "links", "link", "node", "nodes", "edge", "edges", "start", "target",
    "связи", "связь", "графа", "граф", "узел", "узлы", "через", "того", "какой",
    "которые", "которая", "который", "будет", "можно", "нужно", "если",
}
DOMAIN_GENERIC_FOLDERS = {
    "area", "areas", "folder", "folders", "product", "products", "project", "projects",
    "research", "notes", "work", "base", "vault", "inbox", "archive", "drafts",
    "область", "области", "папка", "папки", "продукт", "продукты", "проект",
    "проекты", "исследование", "исследования", "заметки", "работа", "база",
    "архив", "черновики",
}
DOMAIN_TITLE_NOISE = DOMAIN_NOISE_TERMS | DOMAIN_GENERIC_FOLDERS | COMMON_TAG_HINTS | TECHNICAL_TAG_NOISE
STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "about",
    "как", "что", "для", "это", "или", "при", "над", "под", "про", "без",
    "через", "после", "тоже", "если", "мой", "моя", "мои", "его", "её",
}
IGNORED_DIRS = {".git", ".obsidian", ".smart-env", ".linza", "LINZA", "node_modules", "__pycache__"}
LINZA_YAML_KEY_ORDER = ("role", "confidence", "domains")
LINZA_VISIBLE_KEYS = {"role", "confidence", "domains"}
LINZA_LEGACY_FLAT_PREFIX = "linza_"
LINZA_LEGACY_VISIBLE_KEYS = {"role_confidence"}

LINZA_EVENT_PATTERNS: list[tuple[str, str, str]] = [
    ("decision", r"^\s*(decision|решение|решили|выбрали|принято)\s*[:—-]|\b(decided|решили|выбрали|принято решение)\b", "decision language"),
    ("action", r"^\s*(action|done|сделано|действие)\s*[:—-]|\b(added|renamed|implemented|launched|запустили|добавил[иа]?|переименовал[иа]?|сделал[иа]?)\b", "action language"),
    ("result", r"^\s*(result|outcome|итог|результат|следствие)\s*[:—-]|\b(therefore|so now|привело|получилось|теперь|в итоге|поэтому)\b", "result language"),
    ("hypothesis", r"^\s*(hypothesis|assumption|гипотеза|предположение)\s*[:—-]|\b(может быть|похоже|вероятно|assume|hypothesis)\b", "hypothesis language"),
    ("fact", r"^\s*(fact|observation|факт|наблюдение|проверка)\s*[:—-]|\b(found|showed|показал[ао]?|обнаружил[иа]?|проверено)\b", "fact language"),
]

LINZA_EVENT_PATTERNS_RU_EXTRA: list[tuple[str, str, str]] = [
    ("action", r"\b(сделав|сделанный|сделавший|выполнив|выполнен|реализовав|реализован)\b", "russian participle action"),
    ("decision", r"\b(назначено|утверждено|одобрено|запланировано|постановили|постановлено)\b", "russian decision"),
    ("result", r"\b(приведший|приведённый|обусловивший|вызванный|повлёкший)\b", "russian participle result"),
    ("fact", r"\b(выявлено|установлено|зафиксировано|измерено|рассчитано|проведено)\b", "russian fact"),
]


def now_ts() -> float:
    import time
    return time.time()


CYR_RE = re.compile(r"[\u0410-\u044f\u0401\u0451]")

def tokenize(value: str) -> set[str]:
    text = value.lower().replace("\u0451", "\u0435")
    tokens = re.findall("[A-Za-z\u0410-\u044f\u0401\u04510-9]{3,}", text)
    return {t for t in tokens if t not in STOPWORDS}


def normalize_note_name(value: str) -> str:
    value = Path(value).stem if value.endswith(".md") else value
    value = value.lower().replace("\u0451", "\u0435")
    value = re.sub(r"[\u005f\u2013\u2014\-]+", " ", value)
    value = re.sub(r"[^\w ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def safe_vault_path(vault_path: Path, value: str) -> tuple[str, Path]:
    rel = str(value or "").replace("\\", "/").strip("/")
    path = Path(rel)
    if not rel or path.is_absolute() or path.drive or ".." in path.parts:
        raise ValueError("Path must be vault-relative and stay inside the vault")
    return rel, Path(vault_path) / rel


def clean_markdown(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_~]{1,3}", "", text)
    text = re.sub(r"^[\s>|:-]+", "", text, flags=re.MULTILINE)
    return text.strip()


def extract_title(text: str) -> str:
    if m := re.search(r"^#{1,6}\s+(.+)$", text, re.MULTILINE):
        return m.group(1).strip()
    return ""


def extract_tags_from_text(text: str) -> set[str]:
    tags = set()
    for m in TAG_RE.finditer(text):
        tag = m.group(1).strip().lower()
        if len(tag) > 20 or len(tag) < 2:
            continue
        if HEX_COLOR_TAG_RE.match(tag):
            continue
        if tag in COMMON_TAG_HINTS | TECHNICAL_TAG_NOISE:
            continue
        tags.add(tag)
    return tags


def extract_wikilinks(content: str) -> list[str]:
    return [normalize_note_name(m.group(1)) for m in WIKILINK_RE.finditer(content)]


def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    result = {}
    for line in m.group(1).split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip().strip("\"'")
            if val and not val.startswith("["):
                result[key] = val
    return result


def strip_frontmatter(content: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(content)
    if not match:
        return {}, content
    raw = match.group(1)
    body = content[match.end():]
    metadata = {}
    try:
        import yaml
        parsed = yaml.safe_load(raw) or {}
        if isinstance(parsed, dict):
            metadata = parsed
    except Exception:
        metadata = {}
    return metadata, body


def normalize_tag(value: str) -> Optional[str]:
    tag = str(value).strip().strip("#").strip()
    if not tag:
        return None
    tag = tag.replace("\\", "/").strip("/")
    tag = tag.lower().replace("ё", "е")
    tag = tag.replace("–", "-").replace("—", "-")
    tag = re.sub(r"[\s_]+", "-", tag)
    tag = re.sub(r"-{2,}", "-", tag)
    tag = tag.strip("-/")
    if not tag or HEX_COLOR_TAG_RE.fullmatch(tag):
        return None
    return tag


def _raw_frontmatter_tags(metadata: dict) -> list[str]:
    fm_tags = metadata.get("tags", [])
    if isinstance(fm_tags, str):
        return [t.strip("# ") for t in TAG_SPLIT_RE.split(fm_tags) if t.strip("# ")]
    if isinstance(fm_tags, list):
        return [str(t).strip("# ") for t in fm_tags if str(t).strip("# ")]
    return []


def extract_tag_details(content: str, metadata: dict) -> dict:
    _, body = strip_frontmatter(content)
    details = {"yaml": [], "inline": [], "ignored_inline": []}
    for raw in _raw_frontmatter_tags(metadata):
        normalized = normalize_tag(raw)
        if normalized:
            details["yaml"].append({"raw": raw, "normalized": normalized})
    for raw in TAG_RE.findall(body):
        normalized = normalize_tag(raw)
        if normalized:
            details["inline"].append({"raw": raw, "normalized": normalized})
        else:
            details["ignored_inline"].append({"raw": raw, "reason": "not_a_tag"})
    return details


def extract_tags(content: str, metadata: dict) -> list[str]:
    details = extract_tag_details(content, metadata)
    tags = {item["normalized"] for item in details["yaml"] + details["inline"]}
    return sorted(tags)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def content_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def should_ignore_path(path: Path, vault: Path) -> bool:
    try:
        parts = path.relative_to(vault).parts
    except ValueError:
        parts = path.parts
    return any(part in IGNORED_DIRS or part.startswith(".") for part in parts)


def is_legacy_graph_metadata(metadata: dict) -> bool:
    return any(key in metadata for key in ("sign", "level", "parents_meta", "artifact_sign"))


def normalize_linza_key(key: str) -> str:
    target_key = str(key)
    if target_key.startswith(LINZA_LEGACY_FLAT_PREFIX):
        target_key = target_key[len(LINZA_LEGACY_FLAT_PREFIX):]
    if target_key == "type":
        return "role"
    if target_key == "role_confidence":
        return "confidence"
    if target_key == "status":
        return "state"
    return target_key


def linza_flat_key(key: str) -> str:
    return normalize_linza_key(key)


def _ordered_linza_block(block: dict) -> dict:
    ordered = {}
    for key in LINZA_YAML_KEY_ORDER:
        if key in block:
            ordered[key] = block[key]
    for key, value in block.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def get_linza_metadata(metadata: dict) -> dict:
    if not isinstance(metadata, dict):
        return {}
    block: dict[str, Any] = {}
    nested = metadata.get("linza")
    if isinstance(nested, dict):
        for key, value in nested.items():
            block[normalize_linza_key(str(key))] = value
    for key, value in metadata.items():
        if not isinstance(key, str):
            continue
        if key.startswith(LINZA_LEGACY_FLAT_PREFIX):
            block[normalize_linza_key(key)] = value
            continue
        normalized_key = normalize_linza_key(key)
        if normalized_key in LINZA_VISIBLE_KEYS:
            block[normalized_key] = value
    return _ordered_linza_block(block)


def get_linza_property(metadata: dict, key: str, default: Any = None) -> Any:
    return get_linza_metadata(metadata).get(normalize_linza_key(key), default)


def set_linza_metadata(metadata: dict, block: dict) -> dict:
    normalized = dict(metadata)
    normalized.pop("linza", None)
    for key in list(normalized):
        if not isinstance(key, str):
            continue
        if key.startswith(LINZA_LEGACY_FLAT_PREFIX) or key in LINZA_LEGACY_VISIBLE_KEYS:
            normalized.pop(key, None)
    for key, value in _ordered_linza_block(block).items():
        target_key = normalize_linza_key(key)
        if target_key not in LINZA_VISIBLE_KEYS:
            continue
        normalized[linza_flat_key(target_key)] = value
    return normalized


def _normalize_yaml_metadata(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    linza_block = get_linza_metadata(data)
    if linza_block:
        return set_linza_metadata(data, linza_block)
    return dict(data)


def _dump_readable_yaml(data: dict) -> str:
    import yaml

    class ReadableSafeDumper(yaml.SafeDumper):
        def increase_indent(self, flow=False, indentless=False):
            return super().increase_indent(flow, False)

    return yaml.dump(
        _normalize_yaml_metadata(data),
        Dumper=ReadableSafeDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()


def format_yaml_block(data: dict) -> str:
    return _dump_readable_yaml(data)


def patch_frontmatter(
    content: str, patch: dict,
    allow_overwrite: bool = False, namespace: str = "linza",
) -> tuple[str, list[dict], list[dict]]:
    existing_frontmatter = FRONTMATTER_RE.match(content)
    metadata, body = strip_frontmatter(content)
    if existing_frontmatter and existing_frontmatter.group(1).strip() and not metadata:
        return content, [], [{"property": "*", "reason": "yaml_parse_failed"}]

    protected = {"sign", "level", "parents", "parents_meta", "artifact_sign"}
    if is_legacy_graph_metadata(metadata):
        protected.update({"type", "status", "tags"})
    changes = []
    skipped = []
    linza_block = get_linza_metadata(metadata) if namespace == "linza" else {}
    if namespace == "linza" and "linza" in metadata and not isinstance(metadata.get("linza"), dict):
        return content, [], [{"property": "linza", "reason": "linza_block_not_mapping"}]

    for key, value in patch.items():
        if namespace == "linza":
            target_key = normalize_linza_key(str(key))
            if target_key not in LINZA_VISIBLE_KEYS:
                skipped.append({"property": target_key, "reason": "not_visible_yaml_property"})
                continue
            if target_key in linza_block and not allow_overwrite:
                skipped.append({"property": linza_flat_key(target_key), "reason": "already_exists"})
                continue
            old = linza_block.get(target_key)
            linza_block[target_key] = value
            changes.append({"property": linza_flat_key(target_key), "old": old, "new": value})
            continue
        elif namespace in {"plain", ""}:
            target_key = str(key)
        else:
            target_key = f"{namespace}_{key}"
        if target_key in protected or (namespace == "plain" and key in protected):
            skipped.append({"property": key, "reason": "protected_graph_field"})
            continue
        if target_key in metadata and not allow_overwrite:
            skipped.append({"property": target_key, "reason": "already_exists"})
            continue
        old = metadata.get(target_key)
        metadata[target_key] = value
        changes.append({"property": target_key, "old": old, "new": value})

    if namespace == "linza" and changes:
        metadata = set_linza_metadata(metadata, linza_block)

    if not changes:
        return content, changes, skipped

    yaml_text = format_yaml_block(metadata)
    if existing_frontmatter:
        new_content = f"---\n{yaml_text}\n---\n{body}"
    else:
        new_content = f"---\n{yaml_text}\n---\n{content}"
    return new_content, changes, skipped
