"""
Postgres-backed Enrichment Cache with Advisory Locks
Implements ChatGPT's best practices for Railway Postgres deployment
"""

import hashlib
import struct
import os
import time
import json
import pandas as pd
from pathlib import Path
import threading
from typing import Optional, Dict, Any
from datetime import datetime


def lock_key(s: str) -> int:
    """Generate stable 64-bit lock key from string (for Postgres advisory locks)"""
    h = hashlib.sha1(s.encode()).digest()
    return struct.unpack('>q', h[:8])[0]


def sha256_file(path: str) -> str:
    """Stream file to compute SHA256 hash (memory-efficient)"""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):  # 1MB chunks
            h.update(chunk)
    return h.hexdigest()


def atomic_write_parquet(df: pd.DataFrame, target_path: str):
    """Atomically write Parquet file (no partial reads)"""
    tmp_path = f"{target_path}.tmp"
    df.to_parquet(tmp_path, index=False)
    os.replace(tmp_path, target_path)  # Atomic on same filesystem


class PostgresEnrichmentCache:
    """
    Production-grade Postgres cache with:
    - Advisory locks (prevents duplicate enrichment across instances)
    - UPSERT-based metadata (crash-safe)
    - Atomic Parquet writes
    - Automatic fallback to file-based cache if DB unavailable
    """

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url
        self.db_available = False
        self.conn = None

        if database_url:
            try:
                import psycopg2
                self.conn = psycopg2.connect(database_url)
                self.conn.autocommit = True  # For advisory locks
                self.db_available = True
                self._ensure_schema()
                print("[POSTGRES] Connected to database for enrichment cache")
            except Exception as e:
                print(f"[POSTGRES] Could not connect, falling back to file-based cache: {e}")
                self.db_available = False


    def _ensure_schema(self):
        """Create enrichment_cache table if not exists"""
        if not self.db_available:
            return

        schema_sql = """
        CREATE TABLE IF NOT EXISTS enrichment_cache (
            id SERIAL PRIMARY KEY,
            csv_hash VARCHAR(64) NOT NULL,
            model_version VARCHAR(50) NOT NULL,
            prompt_version VARCHAR(50) NOT NULL,
            enriched_file_path VARCHAR(512),
            status VARCHAR(20) NOT NULL,
            message TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (csv_hash, model_version, prompt_version)
        );

        CREATE INDEX IF NOT EXISTS idx_enrichment_lookup
        ON enrichment_cache(csv_hash, model_version, prompt_version, status);
        """

        try:
            with self.conn.cursor() as cur:
                cur.execute(schema_sql)
            print("[POSTGRES] Enrichment cache schema ready")
        except Exception as e:
            print(f"[POSTGRES] Schema creation error: {e}")


    def try_acquire_lock(self, dataset_key: str) -> bool:
        """Try to acquire Postgres advisory lock (non-blocking)"""
        if not self.db_available:
            return True  # Fallback mode - always "acquire"

        key = lock_key(dataset_key)

        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(%s)", (key,))
                result = cur.fetchone()[0]
                return bool(result)
        except Exception as e:
            print(f"[POSTGRES] Lock acquisition error: {e}")
            return False


    def release_lock(self, dataset_key: str):
        """Release Postgres advisory lock"""
        if not self.db_available:
            return

        key = lock_key(dataset_key)

        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (key,))
        except Exception as e:
            print(f"[POSTGRES] Lock release error: {e}")


    def get_cache_record(self, csv_hash: str, model_version: str, prompt_version: str) -> Optional[Dict]:
        """Get cache metadata from Postgres"""
        if not self.db_available:
            return None

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT enriched_file_path, status, message, updated_at
                    FROM enrichment_cache
                    WHERE csv_hash = %s AND model_version = %s AND prompt_version = %s
                """, (csv_hash, model_version, prompt_version))

                row = cur.fetchone()
                if row:
                    return {
                        'enriched_file_path': row[0],
                        'status': row[1],
                        'message': row[2],
                        'updated_at': row[3]
                    }
        except Exception as e:
            print(f"[POSTGRES] Query error: {e}")

        return None


    def upsert_cache_record(self, csv_hash: str, model_version: str, prompt_version: str,
                           status: str, enriched_file_path: str = None, message: str = ""):
        """UPSERT cache record (idempotent, crash-safe)"""
        if not self.db_available:
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO enrichment_cache
                        (csv_hash, model_version, prompt_version, status, enriched_file_path, message, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (csv_hash, model_version, prompt_version)
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        enriched_file_path = EXCLUDED.enriched_file_path,
                        message = EXCLUDED.message,
                        updated_at = NOW()
                """, (csv_hash, model_version, prompt_version, status, enriched_file_path, message))
        except Exception as e:
            print(f"[POSTGRES] UPSERT error: {e}")


    def wait_for_build(self, csv_hash: str, model_version: str, prompt_version: str,
                      max_wait: int = 300, poll_interval: int = 5) -> Optional[str]:
        """
        Wait for another instance to finish building cache
        Returns: file_path if ready, None if timeout/failed
        """
        if not self.db_available:
            return None

        print(f"[POSTGRES] Waiting for enrichment build (max {max_wait}s)...")
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            record = self.get_cache_record(csv_hash, model_version, prompt_version)

            if record and record['status'] == 'ready':
                print(f"[POSTGRES] Build complete after {elapsed}s")
                return record['enriched_file_path']
            elif record and record['status'] == 'failed':
                print(f"[POSTGRES] Build failed: {record['message']}")
                return None

        print(f"[POSTGRES] Build timeout after {max_wait}s")
        return None


    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            print("[POSTGRES] Connection closed")
