import asyncio
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

from linza_mcp import LinzaCore, Storage, HashingEmbeddingProvider, strip_frontmatter
from linza_mcp.domains import domain_terms, record_similarity
from linza_mcp.utils import get_linza_metadata


class StaticEmbeddingProvider:
    """Simple test embedding provider with fixed vectors."""
    def __init__(self, vectors):
        self.vectors = vectors

    def embed(self, text):
        key = text[:20].replace("\n", " ")
        return self.vectors.get(key, self.vectors.get(list(self.vectors.keys())[0], [0.5, 0.5]))




class OperatorTestCase(unittest.TestCase):
    def make_core(self):
        tmp = tempfile.TemporaryDirectory()
        vault = Path(tmp.name)
        db_path = vault / ".linza" / "linza.db"
        storage = Storage(db_path)
        core = LinzaCore(vault, storage, HashingEmbeddingProvider())
        return tmp, vault, storage, core
