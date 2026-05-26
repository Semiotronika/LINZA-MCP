import asyncio
import importlib.util
import json
import math
import re
import shutil
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

from linza_mcp import LinzaCore, Storage, strip_frontmatter
from linza_mcp.domains import domain_terms, record_similarity
from linza_mcp.utils import get_linza_metadata


class StableTestEmbeddingProvider:
    """Deterministic local embedding fake used by tests instead of external services."""

    def __init__(self, dim: int = 64, model: str = "test-embedding"):
        self.dim = int(dim)
        self.model = model
        self.api_url = "test://local"
        self.api_key = None

    async def embed(self, texts):
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9]{3,}", text.lower())
        for token in tokens:
            idx = sum(ord(char) for char in token) % self.dim
            vector[idx] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector




class OperatorTestCase(unittest.TestCase):
    def make_core(self):
        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        db_path = vault / ".linza" / "linza.db"
        storage = Storage(db_path)
        core = LinzaCore(vault, storage, StableTestEmbeddingProvider())
        return tmp, vault, storage, core
