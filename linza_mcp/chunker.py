import hashlib
import re
from dataclasses import dataclass
from typing import Any, Optional


SOURCE_HINT_TERMS = (
    "arxiv",
    "doi",
    "http://",
    "https://",
    "\u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a",
    "\u0440\u0435\u0444\u0435\u0440\u0435\u043d\u0441",
)
QUESTION_HINT_TERMS = (
    "question",
    "\u0432\u043e\u043f\u0440\u043e\u0441",
    "\u043f\u043e\u0447\u0435\u043c\u0443",
    "\u043a\u0430\u043a",
)
GENERATED_SERVICE_HEADINGS = (
    "\u0421\u0432\u044f\u0437\u0438 \u0434\u043b\u044f \u0433\u0440\u0430\u0444\u0430",
)


HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
CHUNKER_VERSION = 1
CHUNK_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
CODE_FENCE_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
TABLE_RE = re.compile(r"^(\|.+\|\s*$\n)(\|[:\-|]+\|\s*$\n)?(\|.+\|\s*$\n)+", re.MULTILINE)
QUOTE_RE = re.compile(r"^>+\s+(.*)$", re.MULTILINE)
QUESTION_RE = re.compile(r"\?\s*$", re.MULTILINE)


@dataclass(frozen=True)
class _Block:
    start: int
    end: int
    text: str
    heading: str


def contains_word_hint(text: str, hints: tuple[str, ...]) -> bool:
    lowered = text.lower()
    for hint in hints:
        if "://" in hint:
            if hint in lowered:
                return True
            continue
        if re.search(rf"(?<!\w){re.escape(hint)}(?!\w)", lowered, re.IGNORECASE):
            return True
    return False


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


def chunk_markdown(
    text: str,
    max_chars: int = 1200,
    *,
    source_id: str = "",
    overlap_chars: int = 120,
) -> list[dict[str, Any]]:
    """Split Markdown into stable, embedding-ready semantic chunks."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.strip():
        return []

    max_chars = max(1, int(max_chars))
    overlap_chars = max(0, min(int(overlap_chars), max_chars // 2))
    base_chunks = _make_base_chunks(normalized, max_chars=max_chars)

    chunks: list[dict[str, Any]] = []
    body_hash_counts: dict[str, int] = {}
    for index, block in enumerate(base_chunks):
        prefix_start = max(0, block.start - overlap_chars) if index else block.start
        overlap = block.start - prefix_start
        chunk_text = normalized[prefix_start:block.end]
        body_text = normalized[block.start:block.end]
        body_hash = hashlib.sha1(body_text.encode("utf-8")).hexdigest()[:12]
        text_hash = hashlib.sha1(chunk_text.encode("utf-8")).hexdigest()[:12]
        occurrence = body_hash_counts.get(body_hash, 0)
        body_hash_counts[body_hash] = occurrence + 1
        digest = hashlib.sha1(
            f"{CHUNKER_VERSION}\0{source_id}\0{body_hash}\0{occurrence}".encode("utf-8")
        ).hexdigest()[:12]
        chunk_id = f"chunk:{digest}"
        kind = semantic_chunk_kind(body_text, block.heading)
        chunks.append(
            {
                "id": chunk_id,
                "chunk_id": chunk_id,
                "chunker_version": CHUNKER_VERSION,
                "source_id": source_id,
                "index": index,
                "chunk_index": index,
                "start": prefix_start,
                "end": block.end,
                "start_char": prefix_start,
                "end_char": block.end,
                "body_start_char": block.start,
                "body_end_char": block.end,
                "overlap_chars": overlap,
                "char_count": len(chunk_text),
                "heading": block.heading,
                "kind": kind,
                "type": kind,
                "body_hash": body_hash,
                "text_hash": text_hash,
                "text": chunk_text,
            }
        )

    return chunks


def _make_base_chunks(text: str, *, max_chars: int) -> list[_Block]:
    chunks: list[_Block] = []
    current_text = ""
    current_start = 0
    current_end = 0
    current_heading = ""

    for block in _markdown_blocks(text):
        if current_text and block.heading and block.heading != current_heading:
            chunks.append(_Block(current_start, current_end, current_text, current_heading))
            current_text = ""

        if len(block.text) > max_chars:
            if current_text:
                chunks.append(_Block(current_start, current_end, current_text, current_heading))
                current_text = ""
            chunks.extend(_split_large_block(block, max_chars=max_chars))
            continue

        if current_text and len(current_text) + len(block.text) > max_chars:
            chunks.append(_Block(current_start, current_end, current_text, current_heading))
            current_text = ""

        if not current_text:
            current_start = block.start
            current_heading = block.heading
        current_text += block.text
        current_end = block.end
        if block.heading:
            current_heading = block.heading

    if current_text:
        chunks.append(_Block(current_start, current_end, current_text, current_heading))
    return chunks


def _markdown_blocks(text: str) -> list[_Block]:
    blocks: list[_Block] = []
    current: list[str] = []
    current_start = 0
    pos = 0
    active_heading = ""
    block_heading = ""
    fence_char = ""
    fence_len = 0

    def flush(end: int) -> None:
        nonlocal current, current_start, block_heading
        if not current:
            return
        block_text = "".join(current)
        if block_text.strip():
            blocks.append(_Block(current_start, end, block_text, block_heading))
        current = []
        block_heading = active_heading

    for line in text.splitlines(keepends=True):
        stripped_line = line.rstrip("\n")
        fence_match = FENCE_RE.match(stripped_line)
        in_fence = bool(fence_char)
        heading_match = None if in_fence or fence_match else HEADING_RE.match(stripped_line)
        is_blank = not line.strip()

        if heading_match:
            flush(pos)
            active_heading = heading_match.group(2).strip()
            block_heading = active_heading
            current_start = pos
            current = [line]
        elif is_blank:
            if current:
                current.append(line)
                pos += len(line)
                flush(pos)
                continue
        else:
            if not current:
                current_start = pos
                block_heading = active_heading
            current.append(line)

        pos += len(line)
        if fence_match:
            marker = fence_match.group(1)
            marker_char = marker[0]
            if not fence_char:
                fence_char = marker_char
                fence_len = len(marker)
            elif marker_char == fence_char and len(marker) >= fence_len:
                fence_char = ""
                fence_len = 0

    flush(pos)
    return blocks


def _split_large_block(block: _Block, *, max_chars: int) -> list[_Block]:
    pieces: list[_Block] = []
    cursor = block.start
    text_cursor = 0
    while text_cursor < len(block.text):
        slice_text = block.text[text_cursor : text_cursor + max_chars]
        start = cursor
        end = cursor + len(slice_text)
        pieces.append(_Block(start, end, slice_text, block.heading))
        cursor = end
        text_cursor += len(slice_text)
    return pieces


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
    if contains_word_hint(stripped, SOURCE_HINT_TERMS):
        return "source"
    if "?" in stripped or contains_word_hint(stripped, QUESTION_HINT_TERMS):
        return "question"
    if heading:
        return "section"
    return "paragraph"


def split_semantic_chunks(
    text: str,
    max_chars: int = 1200,
    *,
    source_id: str = "",
    overlap_chars: int = 0,
) -> list[dict[str, Any]]:
    """Split Markdown into reviewable meaning chunks, preserving headings and offsets."""
    return chunk_markdown(
        text,
        max_chars=max_chars,
        source_id=source_id,
        overlap_chars=overlap_chars,
    )


def strip_generated_service_sections(text: str) -> str:
    # Defensive cleanup for old generated service markers from imported vaults.
    heading_pattern = "|".join(re.escape(title) for title in GENERATED_SERVICE_HEADINGS)
    return re.sub(
        rf"(?ms)^\s{{0,3}}#{{1,6}}\s+(?:{heading_pattern})\s*$.*?(?=^\s{{0,3}}#{{1,6}}\s+|\Z)",
        "",
        text,
    )


_semantic_chunk_kind = semantic_chunk_kind


__all__ = [
    "CHUNKER_VERSION",
    "chunk_markdown",
    "semantic_chunk_kind",
    "split_semantic_chunks",
    "split_text_chunks",
    "strip_generated_service_sections",
]
