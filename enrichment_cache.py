"""
Enrichment Cache System - Production-Ready AI Title Classification
Implements ChatGPT's best practices for Railway deployment
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
import asyncio
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

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
    - File-based cache (Railway volume compatible)
    - Model/prompt versioning
    - Automatic invalidation on CSV changes
    - Background async enrichment
    """

    def __init__(self,
                 csv_path: str,
                 cache_dir: str = "/app/data",
                 model_version: str = "gpt-5-mini",
                 prompt_version: str = "v1"):

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

        # State
        self.enriched_df: Optional[pd.DataFrame] = None
        self.is_building = False
        self.build_thread: Optional[threading.Thread] = None


    def get_cached_data(self) -> Optional[pd.DataFrame]:
        """Load cached enriched data if valid"""
        if not os.path.exists(self.cache_file) or not os.path.exists(self.metadata_file):
            return None

        try:
            # Load metadata
            with open(self.metadata_file, 'r') as f:
                metadata = json.load(f)

            # Validate metadata
            if (metadata.get('dataset_key') == self.dataset_key and
                metadata.get('status') == 'ready'):

                print(f"[CACHE] Loading enriched data: {self.cache_file}")
                df = pd.read_parquet(self.cache_file)
                print(f"[CACHE] Loaded {len(df)} enriched studies")
                return df

        except Exception as e:
            print(f"[CACHE] Error loading cache: {e}")

        return None


    def save_metadata(self, status: str, message: str = ""):
        """Save cache metadata"""
        metadata = {
            'dataset_key': self.dataset_key,
            'csv_hash': self.csv_hash,
            'model_version': self.model_version,
            'prompt_version': self.prompt_version,
            'status': status,
            'message': message,
            'updated_at': time.time()
        }

        with open(self.metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)


    def build_cache_async(self, df: pd.DataFrame, ta_filters: list):
        """Start background enrichment process"""
        if self.is_building:
            print("[CACHE] Build already in progress, skipping...")
            return

        self.is_building = True
        self.save_metadata('building', 'Enriching titles with AI...')

        def background_enrich():
            try:
                print(f"[CACHE] Starting enrichment: {len(df)} studies")
                enriched = enrich_titles_batch(df, self.model_version)

                # Save atomically
                atomic_write_parquet(enriched, self.cache_file)
                self.save_metadata('ready', f'Enriched {len(enriched)} studies')

                # Update in-memory cache
                self.enriched_df = enriched
                self.is_building = False

                print(f"[CACHE] ✓ Enrichment complete: {self.cache_file}")

            except Exception as e:
                print(f"[CACHE] ✗ Enrichment failed: {e}")
                self.save_metadata('failed', str(e))
                self.is_building = False

        self.build_thread = threading.Thread(target=background_enrich, daemon=True)
        self.build_thread.start()


    def get_or_build(self, df: pd.DataFrame, ta_filters: list) -> Optional[pd.DataFrame]:
        """Get cached data or trigger background build"""
        # Try to load from cache
        cached = self.get_cached_data()
        if cached is not None:
            self.enriched_df = cached
            return cached

        # Check if build in progress
        if self.is_building:
            print("[CACHE] Enrichment in progress, returning None (use fallback)")
            return None

        # Start background build
        print("[CACHE] No valid cache found, starting enrichment...")
        self.build_cache_async(df, ta_filters)

        return None  # Caller should use fallback until ready


# ============================================================================
# AI ENRICHMENT FUNCTIONS
# ============================================================================

def enrich_single_title(title: str, model: str = "gpt-5-mini") -> Dict[str, Any]:
    """
    Extract metadata from single title using ultra-lean prompt
    Returns: {line_of_therapy, phase, disease_state, biomarkers, novelty, is_emerging}
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

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        return result

    except Exception as e:
        print(f"[ENRICH] Error processing title: {e}")
        return {
            "line_of_therapy": "Unknown",
            "phase": "Unknown",
            "disease_state": [],
            "biomarkers": [],
            "novelty": [],
            "is_emerging": False
        }


def enrich_titles_batch(df: pd.DataFrame, model: str = "gpt-5-mini", max_workers: int = 16) -> pd.DataFrame:
    """
    Enrich all titles with AI classification using concurrent workers
    Expected: ~60-90s for 1,000 titles with 16 workers
    """
    print(f"[ENRICH] Processing {len(df)} titles with {max_workers} workers...")

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
