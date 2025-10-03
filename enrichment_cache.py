"""
Enrichment Cache System - Production-Ready AI Title Classification
Implements ChatGPT's best practices for Railway deployment

Features:
- Postgres metadata storage with advisory locks (multi-instance safe)
- Railway volume storage for Parquet files
- Automatic fallback to file-based metadata if Postgres unavailable
- Background async enrichment
"""

import hashlib
import struct
import os
import time
import json
import random
import pandas as pd
from pathlib import Path
import threading
from typing import Optional, Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

# Import Postgres backend (with graceful fallback)
try:
    from postgres_cache import PostgresEnrichmentCache, sha256_file, atomic_write_parquet
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    print("[CACHE] Postgres module not available, using file-based cache only")

# ============================================================================
# UTILITY FUNCTIONS (ChatGPT's recommendations)
# ============================================================================

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


# ============================================================================
# ENRICHMENT CACHE MANAGER
# ============================================================================

class EnrichmentCacheManager:
    """
    Manages AI-enriched dataset cache with:
    - Postgres metadata storage (Railway Postgres - multi-instance safe)
    - File-based Parquet cache (Railway volume - survives deployments)
    - Advisory locks (prevents duplicate enrichment across instances)
    - Model/prompt versioning
    - Automatic invalidation on CSV changes
    - Background async enrichment
    - Graceful fallback to file-only mode if Postgres unavailable
    """

    def __init__(self,
                 csv_path: str,
                 cache_dir: str = "/app/data",
                 model_version: str = "gpt-5-mini",
                 prompt_version: str = "v1",
                 database_url: Optional[str] = None):

        self.csv_path = csv_path
        self.cache_dir = cache_dir
        self.model_version = model_version
        self.prompt_version = prompt_version

        # Ensure cache directory exists
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        # Compute dataset key (includes CSV hash + model + prompt version)
        self.csv_hash = sha256_file(csv_path)
        dataset_key_str = f"{self.csv_hash}_{model_version}_{prompt_version}"
        self.dataset_key = hashlib.sha256(dataset_key_str.encode()).hexdigest()[:16]

        # Cache paths
        self.cache_file = os.path.join(cache_dir, f"enriched_{self.dataset_key}.parquet")
        self.metadata_file = os.path.join(cache_dir, f"metadata_{self.dataset_key}.json")

        # Postgres backend (optional, graceful fallback)
        self.pg_cache = None
        if POSTGRES_AVAILABLE and database_url:
            self.pg_cache = PostgresEnrichmentCache(database_url)
            print(f"[CACHE] Postgres mode enabled (DB + volume hybrid)")
        else:
            print(f"[CACHE] File-only mode (no Postgres)")

        # State
        self.enriched_df: Optional[pd.DataFrame] = None
        self.is_building = False
        self.build_thread: Optional[threading.Thread] = None


    def get_cached_data(self) -> Optional[pd.DataFrame]:
        """Load cached enriched data if valid (checks Postgres metadata if available)"""

        # MODE 1: Postgres + Volume (production Railway)
        if self.pg_cache and self.pg_cache.db_available:
            record = self.pg_cache.get_cache_record(
                self.csv_hash,
                self.model_version,
                self.prompt_version
            )

            if record and record['status'] == 'ready' and record['enriched_file_path']:
                if os.path.exists(record['enriched_file_path']):
                    try:
                        print(f"[CACHE] Loading from volume (Postgres-verified): {record['enriched_file_path']}")
                        df = pd.read_parquet(record['enriched_file_path'])
                        print(f"[CACHE] Loaded {len(df)} enriched studies")
                        return df
                    except Exception as e:
                        print(f"[CACHE] Error loading Parquet: {e}")

        # MODE 2: File-only fallback (local dev or Postgres unavailable)
        if not os.path.exists(self.cache_file) or not os.path.exists(self.metadata_file):
            return None

        try:
            # Load file-based metadata
            with open(self.metadata_file, 'r') as f:
                metadata = json.load(f)

            # Validate metadata
            if (metadata.get('dataset_key') == self.dataset_key and
                metadata.get('status') == 'ready'):

                print(f"[CACHE] Loading enriched data (file-based): {self.cache_file}")
                df = pd.read_parquet(self.cache_file)
                print(f"[CACHE] Loaded {len(df)} enriched studies")
                return df

        except Exception as e:
            print(f"[CACHE] Error loading file cache: {e}")

        return None


    def save_metadata(self, status: str, message: str = "", enriched_file_path: str = None):
        """Save cache metadata to both Postgres (if available) and file"""

        # Save to Postgres (production)
        if self.pg_cache and self.pg_cache.db_available:
            self.pg_cache.upsert_cache_record(
                csv_hash=self.csv_hash,
                model_version=self.model_version,
                prompt_version=self.prompt_version,
                status=status,
                enriched_file_path=enriched_file_path or self.cache_file,
                message=message
            )

        # Also save to file (dev mode + backup)
        metadata = {
            'dataset_key': self.dataset_key,
            'csv_hash': self.csv_hash,
            'model_version': self.model_version,
            'prompt_version': self.prompt_version,
            'status': status,
            'message': message,
            'enriched_file_path': enriched_file_path or self.cache_file,
            'updated_at': time.time()
        }

        with open(self.metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)


    def build_cache_async(self, df: pd.DataFrame, ta_filters: list):
        """Start background enrichment process (with Postgres advisory lock if available)"""
        if self.is_building:
            print("[CACHE] Build already in progress, skipping...")
            return

        # Try to acquire advisory lock (prevents duplicate builds across instances)
        if self.pg_cache and self.pg_cache.db_available:
            lock_acquired = self.pg_cache.try_acquire_lock(self.dataset_key)
            if not lock_acquired:
                print("[CACHE] Another instance is building, will wait for result...")
                self.is_building = False
                return
        else:
            lock_acquired = False  # File-only mode, no lock needed

        self.is_building = True
        self.save_metadata('building', 'Enriching titles with AI...', self.cache_file)

        def background_enrich():
            try:
                print(f"[CACHE] Starting enrichment: {len(df)} studies")
                enriched = enrich_titles_batch(df, self.model_version)

                # Save atomically to volume
                atomic_write_parquet(enriched, self.cache_file)
                self.save_metadata('ready', f'Enriched {len(enriched)} studies', self.cache_file)

                # Update in-memory cache
                self.enriched_df = enriched
                self.is_building = False

                print(f"[CACHE] ✓ Enrichment complete: {self.cache_file}")

            except Exception as e:
                print(f"[CACHE] ✗ Enrichment failed: {e}")
                self.save_metadata('failed', str(e), self.cache_file)
                self.is_building = False

            finally:
                # Release advisory lock
                if lock_acquired and self.pg_cache:
                    self.pg_cache.release_lock(self.dataset_key)
                    print("[CACHE] Advisory lock released")

        self.build_thread = threading.Thread(target=background_enrich, daemon=True)
        self.build_thread.start()


    def get_or_build(self, df: pd.DataFrame, ta_filters: list) -> Optional[pd.DataFrame]:
        """
        Get cached data or trigger background build (Postgres-aware)

        Flow:
        1. Check cache (Postgres metadata + volume file)
        2. If missing, check if another instance is building (Postgres status)
        3. If no one building, try to acquire lock and start build
        4. Return None if building (caller uses fallback)
        """
        # Try to load from cache
        cached = self.get_cached_data()
        if cached is not None:
            self.enriched_df = cached
            return cached

        # Check if another instance is building (Postgres-aware)
        if self.pg_cache and self.pg_cache.db_available:
            record = self.pg_cache.get_cache_record(
                self.csv_hash,
                self.model_version,
                self.prompt_version
            )

            if record and record['status'] == 'building':
                print("[CACHE] Another instance is building, waiting...")
                # Could optionally wait here, but better to return None and serve fallback
                return None

        # Check if local build in progress
        if self.is_building:
            print("[CACHE] Enrichment in progress (local), returning None (use fallback)")
            return None

        # Start background build (will acquire advisory lock if Postgres available)
        print("[CACHE] No valid cache found, starting enrichment...")
        self.build_cache_async(df, ta_filters)

        return None  # Caller should use fallback until ready


# ============================================================================
# AI ENRICHMENT FUNCTIONS
# ============================================================================

def enrich_single_title(title: str, model: str = "gpt-5-mini", max_retries: int = 3) -> Dict[str, Any]:
    """
    Extract metadata from single title using ultra-lean prompt
    Returns: {line_of_therapy, phase, disease_state, biomarkers, novelty, is_emerging}
    Includes retry logic with exponential backoff for rate limits
    """
    client = OpenAI()

    prompt = f"""Extract from this oncology abstract title. Return JSON only (no prose):
Title: "{title}"

{{
  "line_of_therapy": "1L|2L|3L|Maintenance|Adjuvant|Neoadjuvant|Perioperative|Unknown",
  "phase": "FIH|Phase 1|Phase 2|Phase 3|Phase 1/2|Phase 2/3|Basket|Umbrella|Unknown",
  "disease_state": ["Metastatic", "MIBC", "NMIBC", "Locally Advanced", "Recurrent", ...],
  "biomarkers": ["FGFR3", "PD-L1", "HER2", "Nectin-4", "TROP-2", ...],
  "novelty": ["Novel", "First-in-Human", "First Results", "Resistance", "Biosimilar", ...],
  "is_emerging": true|false
}}"""

    for attempt in range(max_retries):
        try:
            # Use responses.create API for gpt-5-mini (same as chat/playbook system)
            response = client.responses.create(
                model=model,
                input=[{"role": "user", "content": prompt}],
                reasoning={"effort": "minimal"},  # Fastest reasoning for simple extraction
                text={"verbosity": "low"},  # Concise JSON output
                max_output_tokens=120
            )

            content = response.output_text

            # Validate we got actual content
            if not content or content.strip() == "":
                raise ValueError("Empty response from API")

            result = json.loads(content)
            return result

        except json.JSONDecodeError as e:
            # JSON parsing error - retry with backoff
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"[ENRICH] Invalid JSON response, retrying in {wait_time:.1f}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
            else:
                print(f"[ENRICH] JSON parsing failed after {max_retries} retries: {e}")

        except Exception as e:
            error_str = str(e)

            # Check if rate limit error
            if "rate_limit" in error_str.lower() or "429" in error_str:
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"[ENRICH] Rate limit hit, retrying in {wait_time:.1f}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[ENRICH] Rate limit exceeded after {max_retries} retries: {e}")
            else:
                # Non-rate-limit error, retry anyway
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"[ENRICH] Error (will retry): {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[ENRICH] Error processing title after {max_retries} retries: {e}")

            # Return fallback after all retries exhausted
            break

    return {
        "line_of_therapy": "Unknown",
        "phase": "Unknown",
        "disease_state": [],
        "biomarkers": [],
        "novelty": [],
        "is_emerging": False
    }


def enrich_titles_batch(df: pd.DataFrame, model: str = "gpt-5-mini", max_workers: int = 4) -> pd.DataFrame:
    """
    Enrich all titles with AI classification using concurrent workers
    Reduced to 4 workers to stay under OpenAI rate limit (500 RPM for gpt-5-mini)
    With improved retry logic (3 retries per study with exponential backoff)
    Expected: ~3-5 minutes for 4,686 titles with 4 workers
    """
    print(f"[ENRICH] Processing {len(df)} titles with {max_workers} workers (rate-limit optimized)...")

    enriched_data = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(enrich_single_title, row['Title'], model): idx
            for idx, row in df.iterrows()
        }

        # Collect results with progress
        completed = 0
        for future in futures:
            idx = futures[future]
            try:
                ai_result = future.result(timeout=30)
                row_data = df.loc[idx].to_dict()
                row_data.update(ai_result)
                enriched_data.append(row_data)

                completed += 1
                if completed % 50 == 0:
                    print(f"[ENRICH] Progress: {completed}/{len(df)} ({completed*100//len(df)}%)")

            except Exception as e:
                print(f"[ENRICH] Error on row {idx}: {e}")
                # Fallback: keep original row without enrichment
                row_data = df.loc[idx].to_dict()
                row_data.update({
                    "line_of_therapy": "Unknown",
                    "phase": "Unknown",
                    "disease_state": [],
                    "biomarkers": [],
                    "novelty": [],
                    "is_emerging": False
                })
                enriched_data.append(row_data)

    enriched_df = pd.DataFrame(enriched_data)
    print(f"[ENRICH] ✓ Complete: {len(enriched_df)} titles enriched")

    return enriched_df
