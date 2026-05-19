"""Embedding providers and mean-centering for LINZA."""

from __future__ import annotations

import hashlib
import json
from typing import List, Optional

import numpy as np

from .storage import Storage


class EmbeddingProvider:
    def __init__(self, api_url: str = "", api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class OpenAICompatibleProvider(EmbeddingProvider):
    async def embed(self, texts: List[str]) -> List[List[float]]:
        import aiohttp

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "input": texts,
            "model": self.model or "text-embedding-ada-002",
        }
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{self.api_url}/embeddings", json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = (await response.text())[:500]
                    raise RuntimeError(f"Embedding API error: {error_text}")
                data = await response.json()
                embeddings = sorted(data["data"], key=lambda item: item["index"])
                return [item["embedding"] for item in embeddings]


class OllamaProvider(EmbeddingProvider):
    async def embed(self, texts: List[str]) -> List[List[float]]:
        import aiohttp

        headers = {"Content-Type": "application/json"}
        embeddings: list[list[float]] = []
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for text in texts:
                payload = {"model": self.model or "nomic-embed-text", "prompt": text}
                async with session.post(f"{self.api_url}/api/embeddings", json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = (await response.text())[:500]
                        raise RuntimeError(f"Ollama error: {error_text}")
                    data = await response.json()
                    embeddings.append(data["embedding"])
        return embeddings


class HashingEmbeddingProvider(EmbeddingProvider):
    """Offline lexical embedding fallback for diagnostics when no model is running."""

    def __init__(
        self,
        dim: int = 512,
        api_url: str = "",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        super().__init__(api_url, api_key, model)
        self.dim = int(model or dim)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        vectors = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=float)
            tokens = self._tokenize(text)
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:4], "big") % self.dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vec[idx] += sign
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec.tolist())
        return vectors

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        import re

        stopwords = {
            "the", "and", "for", "with", "from", "this", "that", "into", "about",
            "как", "что", "для", "это", "или", "при", "над", "под", "про", "без",
            "через", "после", "тоже", "если", "мой", "моя", "мои", "его", "её",
        }
        tokens = re.findall(r"[A-Za-zА-Яа-яёЁ0-9]{3,}", text.lower().replace("ё", "е"))
        return {token for token in tokens if token not in stopwords}


class MeanCenteredEmbeddings:
    """Handles corpus-wide mean subtraction for anisotropy correction."""

    def __init__(self, provider: EmbeddingProvider | None = None):
        self.provider = provider
        self.corpus_mean: Optional[np.ndarray] = None
        self.is_fitted = False

    def fit(self, embeddings: List[List[float]]) -> None:
        if not embeddings:
            return
        arr = np.array(embeddings)
        self.corpus_mean = np.mean(arr, axis=0)
        self.is_fitted = True

    def transform(self, embeddings: List[List[float]]) -> List[List[float]]:
        if not self.is_fitted or self.corpus_mean is None:
            return embeddings
        arr = np.array(embeddings)
        if arr.ndim != 2 or arr.shape[1] != self.corpus_mean.shape[0]:
            return embeddings
        return (arr - self.corpus_mean).tolist()

    def fit_transform(self, embeddings: List[List[float]]) -> List[List[float]]:
        self.fit(embeddings)
        return self.transform(embeddings)

    def compute_corpus_mean(self, storage: Storage) -> tuple[List[float], int]:
        records = [
            record
            for record in storage.get_all_file_records()
            if record.get("embedding") is not None
        ]
        if not records:
            storage.clear_corpus_mean()
            self.corpus_mean = None
            self.is_fitted = False
            return [], 0
        embeddings = [record["embedding"] for record in records]
        self.fit(embeddings)
        if self.corpus_mean is None:
            return [], 0
        mean = self.corpus_mean.tolist()
        storage.save_corpus_mean(mean, len(embeddings))
        return mean, len(embeddings)

    def calibrate_embeddings(self, storage: Storage, force: bool = False) -> dict:
        if force or not storage.load_corpus_mean():
            mean_vec, count = self.compute_corpus_mean(storage)
        else:
            mean_vec, count = storage.load_corpus_mean()
            self.corpus_mean = np.array(mean_vec)
            self.is_fitted = bool(mean_vec)
        if not mean_vec:
            return {"status": "empty_corpus", "mean": None, "centroid_norm": None}

        updated = 0
        mean_arr = np.array(mean_vec)
        for record in storage.get_all_file_records():
            raw = record.get("embedding")
            if not raw:
                continue
            centered = (np.array(raw) - mean_arr).tolist()
            storage.conn.execute(
                "UPDATE files SET centered_embedding = ? WHERE path = ?",
                (json.dumps(centered), record["path"]),
            )
            updated += 1
        storage.conn.commit()
        return {
            "status": "calibrated",
            "file_count": count,
            "updated_embeddings": updated,
            "centroid_norm": round(float(np.linalg.norm(mean_arr)), 4),
        }


def get_embedding_provider(
    provider: str,
    api_url: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> EmbeddingProvider:
    provider_name = (provider or "hash").lower()
    if provider_name in {"hash", "hashing", "offline", "local"}:
        return HashingEmbeddingProvider(api_url=api_url, api_key=api_key, model=model)
    if provider_name == "ollama":
        return OllamaProvider(api_url, api_key, model)
    return OpenAICompatibleProvider(api_url, api_key, model)


__all__ = [
    "EmbeddingProvider",
    "HashingEmbeddingProvider",
    "MeanCenteredEmbeddings",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "get_embedding_provider",
]
