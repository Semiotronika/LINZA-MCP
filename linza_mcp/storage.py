"""SQLite storage for LINZA."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


LINZA_SCHEMA_VERSION = 2

SCHEMA_MIGRATIONS = (
    (1, "Initial LINZA sidecar schema"),
    (2, "Track embedding provider metadata for reindex safety"),
)


def now_ts() -> float:
    return time.time()


class Storage:
    """LINZA sidecar storage.

    Accepts both `Storage(db_path)` and `LinzaStorage(vault_path, db_path)` so
    older local scripts keep working after the modular split.
    """

    def __init__(self, vault_or_db_path: str | Path, db_path: str | Path | None = None):
        if db_path is None:
            resolved_db = Path(vault_or_db_path)
            self.vault_path = (
                resolved_db.parent.parent
                if resolved_db.parent.name == ".linza"
                else resolved_db.parent
            )
            self.db_path = resolved_db
        else:
            self.vault_path = Path(vault_or_db_path)
            self.db_path = Path(db_path)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                content TEXT,
                mtime REAL,
                embedding BLOB,
                centered_embedding BLOB,
                embedding_provider TEXT,
                embedding_model TEXT,
                embedding_dim INTEGER,
                hash TEXT,
                indexed_at REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                name TEXT PRIMARY KEY,
                keywords TEXT,
                raw_embedding BLOB,
                centered_embedding BLOB,
                description TEXT,
                parent_profile TEXT,
                usage_count INTEGER DEFAULT 0,
                created_at REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS active_profile (
                key TEXT PRIMARY KEY,
                name TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bridges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                target TEXT,
                score REAL,
                type TEXT,
                created_at REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT,
                profile TEXT,
                results TEXT,
                user_feedback INTEGER,
                timestamp REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS corpus_meta (
                key TEXT PRIMARY KEY,
                mean_embedding BLOB,
                file_count INTEGER,
                updated_at REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS approved_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                source_kind TEXT NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                source_uri TEXT,
                metadata TEXT,
                privacy TEXT,
                batch_id TEXT,
                created_at REAL,
                imported_at REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS artifact_chunks (
                id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                start INTEGER,
                end INTEGER,
                kind TEXT,
                heading TEXT,
                text TEXT NOT NULL,
                created_at REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_traces (
                id TEXT PRIMARY KEY,
                task TEXT,
                expected TEXT,
                result TEXT,
                status TEXT,
                tool_calls TEXT,
                changed_files TEXT,
                tests TEXT,
                errors TEXT,
                context_tokens INTEGER,
                metadata TEXT,
                created_at REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS calibr_metrics (
                id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                metric_index INTEGER NOT NULL,
                metric_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                summary TEXT NOT NULL,
                evidence TEXT,
                payload TEXT NOT NULL,
                created_at REAL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at REAL NOT NULL
            )
        """)
        self._run_schema_migrations()
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.commit()

    def _run_schema_migrations(self) -> None:
        current = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        if current > LINZA_SCHEMA_VERSION:
            raise RuntimeError(
                f"LINZA database schema {current} is newer than this server supports "
                f"({LINZA_SCHEMA_VERSION})"
            )
        for version, description in SCHEMA_MIGRATIONS:
            if version <= current:
                continue
            if version == 2:
                self._ensure_file_embedding_metadata_columns()
            self.conn.execute(
                """
                INSERT OR IGNORE INTO schema_migrations (version, description, applied_at)
                VALUES (?, ?, ?)
                """,
                (version, description, now_ts()),
            )
            self.conn.execute(f"PRAGMA user_version = {int(version)}")

    def _ensure_file_embedding_metadata_columns(self) -> None:
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(files)")}
        additions = {
            "embedding_provider": "TEXT",
            "embedding_model": "TEXT",
            "embedding_dim": "INTEGER",
        }
        for name, column_type in additions.items():
            if name not in existing:
                self.conn.execute(f"ALTER TABLE files ADD COLUMN {name} {column_type}")

    def close(self):
        self.conn.close()

    # --- File operations ---

    def get_file_metadata(self, path: str) -> Optional[Dict]:
        cur = self.conn.execute(
            """
            SELECT path, content, embedding, centered_embedding, embedding_provider,
                   embedding_model, embedding_dim, hash, indexed_at
            FROM files WHERE path = ?
            """,
            (path,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "path": row["path"],
            "content": row["content"],
            "embedding": json.loads(row["embedding"]) if row["embedding"] else None,
            "centered_embedding": json.loads(row["centered_embedding"]) if row["centered_embedding"] else None,
            "embedding_provider": row["embedding_provider"],
            "embedding_model": row["embedding_model"],
            "embedding_dim": row["embedding_dim"],
            "hash": row["hash"],
            "indexed_at": row["indexed_at"],
        }

    def upsert_file(
        self,
        path: str,
        content: str,
        mtime: float,
        raw_embedding: List[float],
        centered_embedding: List[float],
        file_hash: str,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
        embedding_dim: int | None = None,
    ):
        stored_dim = int(embedding_dim) if embedding_dim is not None else len(raw_embedding or [])
        self.conn.execute("""
            REPLACE INTO files
            (path, content, mtime, embedding, centered_embedding, embedding_provider,
             embedding_model, embedding_dim, hash, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            path,
            content,
            mtime,
            json.dumps(raw_embedding),
            json.dumps(centered_embedding),
            embedding_provider,
            embedding_model,
            stored_dim,
            file_hash,
            now_ts(),
        ))
        self.conn.commit()

    def delete_file(self, path: str):
        self.conn.execute("DELETE FROM files WHERE path = ?", (path,))
        self.conn.commit()

    def list_files(self) -> List[str]:
        cur = self.conn.execute("SELECT path FROM files")
        return [row["path"] for row in cur]

    def get_all_embeddings(self, use_centered: bool = True) -> List[Tuple[str, List[float]]]:
        if use_centered:
            cur = self.conn.execute(
                "SELECT path, centered_embedding AS vector FROM files WHERE centered_embedding IS NOT NULL"
            )
        else:
            cur = self.conn.execute(
                "SELECT path, embedding AS vector FROM files WHERE embedding IS NOT NULL"
            )
        return [(row["path"], json.loads(row["vector"])) for row in cur]

    def get_all_file_records(self) -> List[Dict[str, Any]]:
        cur = self.conn.execute("""
            SELECT path, content, mtime, embedding, centered_embedding,
                   embedding_provider, embedding_model, embedding_dim,
                   hash, indexed_at
            FROM files ORDER BY path
        """)
        return [
            {
                "path": row["path"],
                "content": row["content"] or "",
                "mtime": row["mtime"],
                "embedding": json.loads(row["embedding"]) if row["embedding"] else None,
                "centered_embedding": json.loads(row["centered_embedding"]) if row["centered_embedding"] else None,
                "embedding_provider": row["embedding_provider"],
                "embedding_model": row["embedding_model"],
                "embedding_dim": row["embedding_dim"],
                "hash": row["hash"],
                "indexed_at": row["indexed_at"],
            }
            for row in cur
        ]

    def get_file_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) as c FROM files")
        return cur.fetchone()["c"]

    # --- Corpus mean ---

    def save_corpus_mean(self, mean: List[float], count: int):
        self.conn.execute("""
            REPLACE INTO corpus_meta (key, mean_embedding, file_count, updated_at)
            VALUES ('mean', ?, ?, ?)
        """, (json.dumps(mean), count, now_ts()))
        self.conn.commit()

    def clear_corpus_mean(self):
        self.conn.execute("DELETE FROM corpus_meta WHERE key = 'mean'")
        self.conn.commit()

    def load_corpus_mean(self) -> Optional[Tuple[List[float], int]]:
        cur = self.conn.execute("SELECT mean_embedding, file_count FROM corpus_meta WHERE key = 'mean'")
        row = cur.fetchone()
        if row and row["mean_embedding"]:
            return json.loads(row["mean_embedding"]), row["file_count"]
        return None

    # --- Profile operations ---

    def get_profile(self, name: str) -> Optional[Dict]:
        cur = self.conn.execute("""
            SELECT name, keywords, raw_embedding, centered_embedding, description,
                   parent_profile, usage_count
            FROM profiles WHERE name = ?
        """, (name,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "name": row["name"],
            "keywords": row["keywords"],
            "raw_embedding": json.loads(row["raw_embedding"]) if row["raw_embedding"] else None,
            "centered_embedding": json.loads(row["centered_embedding"]) if row["centered_embedding"] else None,
            "description": row["description"],
            "parent_profile": row["parent_profile"],
            "usage_count": row["usage_count"],
        }

    def set_profile(
        self,
        name: str,
        keywords: str,
        raw_embedding: List[float],
        centered_embedding: List[float],
        description: str = "",
        parent_profile: Optional[str] = None,
    ):
        existing = self.get_profile(name)
        usage_count = existing["usage_count"] if existing else 0
        self.conn.execute("""
            REPLACE INTO profiles
            (name, keywords, raw_embedding, centered_embedding, description, parent_profile, usage_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            keywords,
            json.dumps(raw_embedding),
            json.dumps(centered_embedding),
            description,
            parent_profile,
            usage_count,
            now_ts(),
        ))
        self.conn.commit()

    def increment_profile_usage(self, name: str):
        self.conn.execute("UPDATE profiles SET usage_count = usage_count + 1 WHERE name = ?", (name,))
        self.conn.commit()

    def list_profiles(self) -> List[Dict]:
        cur = self.conn.execute("""
            SELECT name, keywords, description, parent_profile, usage_count
            FROM profiles ORDER BY usage_count DESC
        """)
        return [
            {
                "name": row["name"],
                "keywords": row["keywords"],
                "description": row["description"],
                "parent_profile": row["parent_profile"],
                "usage_count": row["usage_count"],
            }
            for row in cur
        ]

    def get_all_profile_records(self) -> List[Dict]:
        cur = self.conn.execute("""
            SELECT name, keywords, raw_embedding, centered_embedding, description,
                   parent_profile, usage_count
            FROM profiles ORDER BY name
        """)
        return [
            {
                "name": row["name"],
                "keywords": row["keywords"],
                "raw_embedding": json.loads(row["raw_embedding"]) if row["raw_embedding"] else None,
                "centered_embedding": json.loads(row["centered_embedding"]) if row["centered_embedding"] else None,
                "description": row["description"],
                "parent_profile": row["parent_profile"],
                "usage_count": row["usage_count"],
            }
            for row in cur
        ]

    def update_profile_centered_embedding(self, name: str, centered_embedding: List[float]) -> None:
        self.conn.execute(
            "UPDATE profiles SET centered_embedding = ? WHERE name = ?",
            (json.dumps(centered_embedding), name),
        )
        self.conn.commit()

    def set_active_profile(self, name: str):
        self.conn.execute("REPLACE INTO active_profile (key, name) VALUES ('active', ?)", (name,))
        self.conn.commit()

    def get_active_profile(self) -> Optional[str]:
        cur = self.conn.execute("SELECT name FROM active_profile WHERE key = 'active'")
        row = cur.fetchone()
        return row["name"] if row else None

    # --- Bridges ---

    def update_bridges(self, bridges: List[Dict]):
        self.conn.execute("DELETE FROM bridges")
        timestamp = now_ts()
        for bridge in bridges:
            self.conn.execute("""
                INSERT INTO bridges (source, target, score, type, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                bridge["source"],
                bridge["target"],
                bridge["score"],
                bridge["type"],
                timestamp,
            ))
        self.conn.commit()

    def get_bridges_for_file(self, path: str) -> List[Dict]:
        cur = self.conn.execute("""
            SELECT source, target, score, type FROM bridges
            WHERE source = ? OR target = ?
        """, (path, path))
        return [
            {
                "source": row["source"],
                "target": row["target"],
                "score": row["score"],
                "type": row["type"],
            }
            for row in cur
        ]

    def get_all_bridges(self) -> List[Dict]:
        cur = self.conn.execute("SELECT source, target, score, type FROM bridges")
        return [
            {
                "source": row["source"],
                "target": row["target"],
                "score": row["score"],
                "type": row["type"],
            }
            for row in cur
        ]

    # --- Search history ---

    def log_search(self, query: str, profile: Optional[str], results: List[Dict], feedback: int = 0):
        self.conn.execute("""
            INSERT INTO search_history (query, profile, results, user_feedback, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (query, profile, json.dumps(results), feedback, now_ts()))
        self.conn.commit()

    def get_profile_search_stats(self, profile: str, limit: int = 100) -> List[Dict]:
        cur = self.conn.execute("""
            SELECT query, user_feedback, timestamp FROM search_history
            WHERE profile = ? ORDER BY timestamp DESC LIMIT ?
        """, (profile, limit))
        return [
            {"query": row["query"], "feedback": row["user_feedback"], "timestamp": row["timestamp"]}
            for row in cur
        ]

    def get_search_history(self, limit: int = 50) -> List[Dict]:
        cur = self.conn.execute("""
            SELECT query, profile, results, user_feedback, timestamp
            FROM search_history ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cur]

    # --- Human approvals ---

    def record_approved_item(
        self,
        item_type: str,
        payload: Dict[str, Any],
        status: str = "accepted",
    ) -> int:
        cur = self.conn.execute("""
            INSERT INTO approved_items (item_type, payload, status, created_at)
            VALUES (?, ?, ?, ?)
        """, (item_type, json.dumps(payload, ensure_ascii=False), status, now_ts()))
        self.conn.commit()
        return int(cur.lastrowid)

    def add_approved_item(self, item_type: str, payload: Dict[str, Any]) -> int:
        return self.record_approved_item(item_type, payload, status="approved")

    def list_approved_items(self, item_type: Optional[str] = None, limit: int = 100) -> list[Dict[str, Any]]:
        if item_type:
            cur = self.conn.execute("""
                SELECT id, item_type, payload, status, created_at
                FROM approved_items
                WHERE item_type = ?
                ORDER BY id DESC
                LIMIT ?
            """, (item_type, limit))
        else:
            cur = self.conn.execute("""
                SELECT id, item_type, payload, status, created_at
                FROM approved_items
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
        return [
            {
                "id": row["id"],
                "item_type": row["item_type"],
                "payload": json.loads(row["payload"]),
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in cur
        ]

    def get_approved_item_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) as c FROM approved_items")
        return int(cur.fetchone()["c"])

    def get_approved_item_by_id(self, item_id: int) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute("""
            SELECT id, item_type, payload, status, created_at
            FROM approved_items WHERE id = ?
        """, (item_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "item_type": row["item_type"],
            "payload": json.loads(row["payload"]),
            "status": row["status"],
            "created_at": row["created_at"],
        }

    # --- Agent workspace artifacts ---

    def record_artifact(
        self,
        artifact_id: str,
        source_kind: str,
        title: str,
        content: str,
        content_hash: str,
        source_uri: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        privacy: str = "private",
        batch_id: str = "",
    ) -> Dict[str, Any]:
        existing = self.get_artifact(artifact_id)
        if existing:
            return {**existing, "status": "duplicate"}
        timestamp = now_ts()
        self.conn.execute("""
            INSERT INTO artifacts
            (id, source_kind, title, content, content_hash, source_uri, metadata, privacy, batch_id, created_at, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            artifact_id,
            source_kind,
            title,
            content,
            content_hash,
            source_uri,
            json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            privacy,
            batch_id,
            timestamp,
            timestamp,
        ))
        self.conn.commit()
        return self.get_artifact(artifact_id) | {"status": "stored"}

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute("""
            SELECT id, source_kind, title, content, content_hash, source_uri,
                   metadata, privacy, batch_id, created_at, imported_at
            FROM artifacts WHERE id = ?
        """, (artifact_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "source_kind": row["source_kind"],
            "title": row["title"] or "",
            "content": row["content"] or "",
            "content_hash": row["content_hash"],
            "source_uri": row["source_uri"] or "",
            "metadata": json.loads(row["metadata"] or "{}"),
            "privacy": row["privacy"] or "private",
            "batch_id": row["batch_id"] or "",
            "created_at": row["created_at"],
            "imported_at": row["imported_at"],
        }

    def list_artifacts(
        self,
        source_kind: Optional[str] = None,
        batch_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if source_kind:
            clauses.append("source_kind = ?")
            params.append(source_kind)
        if batch_id:
            clauses.append("batch_id = ?")
            params.append(batch_id)
        query = """
            SELECT id, source_kind, title, content, content_hash, source_uri,
                   metadata, privacy, batch_id, created_at, imported_at
            FROM artifacts
        """
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += """
            ORDER BY imported_at DESC, id DESC
            LIMIT ?
        """
        params.append(max(1, int(limit)))
        cur = self.conn.execute(query, tuple(params))
        rows = []
        for row in cur:
            rows.append({
                "id": row["id"],
                "source_kind": row["source_kind"],
                "title": row["title"] or "",
                "content": row["content"] or "",
                "content_hash": row["content_hash"],
                "source_uri": row["source_uri"] or "",
                "metadata": json.loads(row["metadata"] or "{}"),
                "privacy": row["privacy"] or "private",
                "batch_id": row["batch_id"] or "",
                "created_at": row["created_at"],
                "imported_at": row["imported_at"],
            })
        return rows

    def get_artifact_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) as c FROM artifacts")
        return int(cur.fetchone()["c"])

    def get_artifact_chunk_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) as c FROM artifact_chunks")
        return int(cur.fetchone()["c"])

    def replace_artifact_chunks(self, artifact_id: str, chunks: list[Dict[str, Any]]) -> None:
        self.conn.execute("DELETE FROM artifact_chunks WHERE artifact_id = ?", (artifact_id,))
        timestamp = now_ts()
        for index, chunk in enumerate(chunks):
            chunk_id = str(chunk.get("chunk_id") or f"chunk-{index:04d}")
            stored_id = f"{artifact_id}-{chunk_id}"
            self.conn.execute("""
                INSERT INTO artifact_chunks
                (id, artifact_id, chunk_index, start, end, kind, heading, text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                stored_id,
                artifact_id,
                index,
                chunk.get("start"),
                chunk.get("end"),
                chunk.get("kind") or chunk.get("type") or "text",
                chunk.get("heading") or "",
                chunk.get("text") or "",
                timestamp,
            ))
        self.conn.commit()

    def list_artifact_chunks(self, artifact_id: Optional[str] = None, limit: int = 1000) -> list[Dict[str, Any]]:
        if artifact_id:
            cur = self.conn.execute("""
                SELECT id, artifact_id, chunk_index, start, end, kind, heading, text, created_at
                FROM artifact_chunks
                WHERE artifact_id = ?
                ORDER BY chunk_index ASC
                LIMIT ?
            """, (artifact_id, max(1, int(limit))))
        else:
            cur = self.conn.execute("""
                SELECT id, artifact_id, chunk_index, start, end, kind, heading, text, created_at
                FROM artifact_chunks
                ORDER BY created_at DESC, artifact_id, chunk_index
                LIMIT ?
            """, (max(1, int(limit)),))
        return [
            {
                "id": row["id"],
                "artifact_id": row["artifact_id"],
                "chunk_index": row["chunk_index"],
                "start": row["start"],
                "end": row["end"],
                "kind": row["kind"],
                "heading": row["heading"] or "",
                "text": row["text"] or "",
                "created_at": row["created_at"],
            }
            for row in cur
        ]

    def search_artifact_chunks(self, query_tokens: set[str], limit: int = 10) -> list[Dict[str, Any]]:
        cur = self.conn.execute("""
            SELECT c.id, c.artifact_id, c.chunk_index, c.start, c.end, c.kind,
                   c.heading, c.text, a.title, a.source_kind, a.privacy, a.batch_id
            FROM artifact_chunks c
            JOIN artifacts a ON a.id = c.artifact_id
            ORDER BY c.created_at DESC, c.artifact_id, c.chunk_index
        """)
        scored: list[tuple[float, Dict[str, Any]]] = []
        for row in cur:
            text = row["text"] or ""
            haystack = f"{row['title'] or ''} {row['source_kind'] or ''} {row['heading'] or ''} {text}".lower()
            score = 0.0
            if query_tokens:
                score = sum(1.0 for token in query_tokens if token in haystack)
                if score <= 0:
                    continue
            scored.append((
                score,
                {
                    "chunk_id": row["id"],
                    "artifact_id": row["artifact_id"],
                    "chunk_index": row["chunk_index"],
                    "start": row["start"],
                    "end": row["end"],
                    "kind": row["kind"],
                    "heading": row["heading"] or "",
                    "text": text,
                    "title": row["title"] or "",
                    "source_kind": row["source_kind"],
                    "privacy": row["privacy"] or "private",
                    "batch_id": row["batch_id"] or "",
                    "score": round(score, 3),
                },
            ))
        scored.sort(key=lambda item: (-item[0], item[1]["artifact_id"], item[1]["chunk_index"]))
        return [item for _score, item in scored[: max(1, int(limit))]]

    def record_audit_event(self, event_type: str, payload: Dict[str, Any]) -> int:
        cur = self.conn.execute("""
            INSERT INTO audit_events (event_type, payload, created_at)
            VALUES (?, ?, ?)
        """, (event_type, json.dumps(payload, ensure_ascii=False, sort_keys=True), now_ts()))
        self.conn.commit()
        return int(cur.lastrowid)

    def list_audit_events(self, event_type: Optional[str] = None, limit: int = 100) -> list[Dict[str, Any]]:
        if event_type:
            cur = self.conn.execute("""
                SELECT id, event_type, payload, created_at
                FROM audit_events
                WHERE event_type = ?
                ORDER BY id DESC
                LIMIT ?
            """, (event_type, max(1, int(limit))))
        else:
            cur = self.conn.execute("""
                SELECT id, event_type, payload, created_at
                FROM audit_events
                ORDER BY id DESC
                LIMIT ?
            """, (max(1, int(limit)),))
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload"]),
                "created_at": row["created_at"],
            }
            for row in cur
        ]

    def get_audit_event_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) as c FROM audit_events")
        return int(cur.fetchone()["c"])

    # --- calibr agent traces ---

    def record_agent_trace(
        self,
        trace_id: str,
        task: str,
        expected: str = "",
        result: str = "",
        status: str = "",
        tool_calls: Optional[list[Dict[str, Any]]] = None,
        changed_files: Optional[list[str]] = None,
        tests: Optional[list[Dict[str, Any]]] = None,
        errors: Optional[list[str]] = None,
        context_tokens: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        existing = self.get_agent_trace(trace_id)
        if existing:
            return {**existing, "status": "duplicate"}
        timestamp = now_ts()
        self.conn.execute("""
            INSERT INTO agent_traces
            (id, task, expected, result, status, tool_calls, changed_files, tests,
             errors, context_tokens, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trace_id,
            task,
            expected,
            result,
            status,
            json.dumps(tool_calls or [], ensure_ascii=False, sort_keys=True),
            json.dumps(changed_files or [], ensure_ascii=False, sort_keys=True),
            json.dumps(tests or [], ensure_ascii=False, sort_keys=True),
            json.dumps(errors or [], ensure_ascii=False, sort_keys=True),
            int(context_tokens or 0),
            json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            timestamp,
        ))
        self.conn.commit()
        return self.get_agent_trace(trace_id) | {"status": "stored"}

    def get_agent_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute("""
            SELECT id, task, expected, result, status, tool_calls, changed_files,
                   tests, errors, context_tokens, metadata, created_at
            FROM agent_traces WHERE id = ?
        """, (trace_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "task": row["task"] or "",
            "expected": row["expected"] or "",
            "result": row["result"] or "",
            "status": row["status"] or "",
            "tool_calls": json.loads(row["tool_calls"] or "[]"),
            "changed_files": json.loads(row["changed_files"] or "[]"),
            "tests": json.loads(row["tests"] or "[]"),
            "errors": json.loads(row["errors"] or "[]"),
            "context_tokens": int(row["context_tokens"] or 0),
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
        }

    def list_agent_traces(self, limit: int = 100) -> list[Dict[str, Any]]:
        cur = self.conn.execute("""
            SELECT id, task, expected, result, status, tool_calls, changed_files,
                   tests, errors, context_tokens, metadata, created_at
            FROM agent_traces
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        """, (max(1, int(limit)),))
        return [
            {
                "id": row["id"],
                "task": row["task"] or "",
                "expected": row["expected"] or "",
                "result": row["result"] or "",
                "status": row["status"] or "",
                "tool_calls": json.loads(row["tool_calls"] or "[]"),
                "changed_files": json.loads(row["changed_files"] or "[]"),
                "tests": json.loads(row["tests"] or "[]"),
                "errors": json.loads(row["errors"] or "[]"),
                "context_tokens": int(row["context_tokens"] or 0),
                "metadata": json.loads(row["metadata"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in cur
        ]

    def get_agent_trace_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) as c FROM agent_traces")
        return int(cur.fetchone()["c"])

    def replace_calibr_metrics(self, trace_id: str, metrics: list[Dict[str, Any]]) -> None:
        self.conn.execute("DELETE FROM calibr_metrics WHERE trace_id = ?", (trace_id,))
        timestamp = now_ts()
        for index, metric in enumerate(metrics):
            self.conn.execute("""
                INSERT INTO calibr_metrics
                (id, trace_id, metric_index, metric_type, severity, summary,
                 evidence, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(metric["id"]),
                trace_id,
                index,
                str(metric.get("metric_type") or "observation"),
                str(metric.get("severity") or "medium"),
                str(metric.get("summary") or ""),
                str(metric.get("evidence") or ""),
                json.dumps(metric.get("payload") or {}, ensure_ascii=False, sort_keys=True),
                timestamp,
            ))
        self.conn.commit()

    def list_calibr_metrics(
        self,
        trace_id: Optional[str] = None,
        metric_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if trace_id:
            clauses.append("trace_id = ?")
            params.append(trace_id)
        if metric_type:
            clauses.append("metric_type = ?")
            params.append(metric_type)
        query = """
            SELECT id, trace_id, metric_index, metric_type, severity, summary,
                   evidence, payload, created_at
            FROM calibr_metrics
        """
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += """
            ORDER BY created_at DESC, trace_id DESC, metric_index ASC
            LIMIT ?
        """
        params.append(max(1, int(limit)))
        cur = self.conn.execute(query, tuple(params))
        return [
            {
                "id": row["id"],
                "trace_id": row["trace_id"],
                "metric_index": row["metric_index"],
                "metric_type": row["metric_type"],
                "severity": row["severity"],
                "summary": row["summary"],
                "evidence": row["evidence"] or "",
                "payload": json.loads(row["payload"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in cur
        ]

    def get_calibr_metric_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) as c FROM calibr_metrics")
        return int(cur.fetchone()["c"])


LinzaStorage = Storage

__all__ = ["Storage", "LinzaStorage", "LINZA_SCHEMA_VERSION", "SCHEMA_MIGRATIONS"]
