import re
from typing import Any, Optional

from .utils import clean_markdown, extract_title


CHUNK_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
CODE_FENCE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
TABLE_RE = re.compile(r"^(\|.+\|\s*$\n)(\|[:\-|]+\|\s*$\n)?(\|.+\|\s*$\n)+", re.MULTILINE)
QUOTE_RE = re.compile(r"^>+\s+(.*)$", re.MULTILINE)
QUESTION_RE = re.compile(r"\?\s*$", re.MULTILINE)


def _detect_chunk_type(text: str, heading: str) -> str:
    if CODE_FENCE_RE.search(text):
        return "code"
    if TABLE_RE.search(text):
        return "table"
    if QUOTE_RE.search(text):
        return "quote"
    if any(line.strip().startswith(("- ", "* ", "1. ")) for line in text.split("\n")[:3]):
        return "list"
    if QUESTION_RE.search(text):
        return "question"
    return "prose"


def chunk_markdown(text: str, max_chars: int = 1200) -> list[dict[str, Any]]:
    """Heading-aware semantic chunking. Returns list of chunk dicts."""
    body = clean_markdown(text)
    if not body.strip():
        return []

    headings = list(CHUNK_HEADING_RE.finditer(body))
    chunks = []

    if not headings:
        chunks.append({
            "text": body.strip(),
            "heading": extract_title(text),
            "level": 0,
            "type": "prose",
            "start": 0,
        })
    else:
        for i, m in enumerate(headings):
            level = len(m.group(1))
            heading_text = m.group(2).strip()
            start = m.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
            section_body = body[start:end].strip()
            if section_body:
                chunks.append({
                    "text": section_body,
                    "heading": heading_text,
                    "level": level,
                    "type": _detect_chunk_type(section_body, heading_text),
                    "start": start,
                })

    # Merge small chunks into larger ones
    merged = []
    for chunk in chunks:
        if merged and len(chunk["text"]) < max_chars * 0.3 and len(merged[-1]["text"]) < max_chars:
            merged[-1]["text"] += "\n" + chunk["text"]
            merged[-1]["type"] = "mixed" if merged[-1]["type"] != chunk["type"] else merged[-1]["type"]
        else:
            merged.append(chunk)

    # Split oversized chunks
    final = []
    for chunk in merged:
        if len(chunk["text"]) > max_chars:
            for i in range(0, len(chunk["text"]), max_chars):
                piece = chunk["text"][i:i + max_chars]
                final.append({**chunk, "text": piece, "sub_index": i // max_chars})
        else:
            final.append(chunk)

    for i, chunk in enumerate(final):
        chunk.setdefault("sub_index", 0)
        chunk["chunk_index"] = i
        chunk["char_count"] = len(chunk["text"])

    return final


def split_text_chunks(text: str, max_chars: int = 1200) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            paragraph_break = text.rfind("\n\n", start, end)
            line_break = text.rfind("\n", start, end)
            if paragraph_break > start + 200:
                end = paragraph_break
            elif line_break > start + 200:
                end = line_break

        raw = text[start:end]
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        chunk_start = start + leading
        chunk_end = start + trailing
        chunk_text = text[chunk_start:chunk_end]
        if chunk_text:
            chunks.append({
                "chunk_id": f"chunk-{len(chunks):04d}",
                "start": chunk_start,
                "end": chunk_end,
                "text": chunk_text,
            })

        start = end
        while start < length and text[start].isspace():
            start += 1

    return chunks


def semantic_chunk_kind(text: str, heading: Optional[str]) -> str:
    stripped = text.strip()
    if "```" in stripped:
        return "code"
    if re.search(r"(?m)^\s*\|.+\|\s*$", stripped):
        return "table"
    if re.search(r"(?m)^\s{0,3}>\s+", stripped):
        return "quote"
    if re.search(r"(?m)^\s{0,3}[-*+]\s+", stripped) or re.search(r"(?m)^\s{0,3}\d+\.\s+", stripped):
        return "list"
    if re.search(r"\b(arxiv|doi|https?://|РёСЃС‚РѕС‡РЅРёРє|СЂРµС„РµСЂРµРЅСЃ)\b", stripped, re.IGNORECASE):
        return "source"
    if "?" in stripped or re.search(r"\b(question|РІРѕРїСЂРѕСЃ|РїРѕС‡РµРјСѓ|РєР°Рє)\b", stripped, re.IGNORECASE):
        return "question"
    if heading:
        return "section"
    return "paragraph"


def split_semantic_chunks(text: str, max_chars: int = 1200) -> list[dict[str, Any]]:
    """Split Markdown into reviewable meaning chunks, preserving headings and offsets."""
    chunks: list[dict[str, Any]] = []
    headings = list(re.finditer(r"(?m)^\s{0,3}(#{1,6})\s+(.+?)\s*$", text))
    ranges: list[tuple[int, int, Optional[str]]] = []

    if headings:
        for idx, match in enumerate(headings):
            start = match.start()
            end = headings[idx + 1].start() if idx + 1 < len(headings) else len(text)
            ranges.append((start, end, match.group(2).strip()))
        if headings[0].start() > 0:
            ranges.insert(0, (0, headings[0].start(), None))
    else:
        ranges.append((0, len(text), None))

    for start, end, heading in ranges:
        section = text[start:end]
        if not section.strip():
            continue
        parts = split_text_chunks(section, max_chars=max_chars)
        for part in parts:
            chunk_text = part["text"]
            chunk_start = start + part["start"]
            chunk_end = start + part["end"]
            chunks.append({
                "chunk_id": f"sem-{len(chunks):04d}",
                "start": chunk_start,
                "end": chunk_end,
                "kind": semantic_chunk_kind(chunk_text, heading),
                "heading": heading,
                "text": chunk_text,
            })

    return chunks


def strip_generated_service_sections(text: str) -> str:
    # Defensive cleanup for old generated service markers from imported vaults.
    return re.sub(
        r"(?ms)^\s{0,3}#{1,6}\s+(?:Связи\s+для\s+графа|РЎРІСЏР·Рё\s+РґР»СЏ\s+РіСЂР°С„Р°)\s*$.*?(?=^\s{0,3}#{1,6}\s+|\Z)",
        "",
        text,
    )


_semantic_chunk_kind = semantic_chunk_kind


__all__ = [
    "chunk_markdown",
    "semantic_chunk_kind",
    "split_semantic_chunks",
    "split_text_chunks",
    "strip_generated_service_sections",
]
