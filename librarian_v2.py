"""
Librarian V2 - TA-Aware with Landscape Context
===============================================

NEW IN V2:
- TA-specific filtering (e.g., exclude SCLC from Lung Cancer)
- Load TA-specific landscape JSON files (nsclc-json.json, bladder-json.json, etc.)
- Inject EMD asset context into prompts
- TA-aware examples and pattern hints

Optimizations (from V1):
- gpt-4o-mini (fast, reliable, cost-efficient)
- NDJSON output (one JSON per line) - truncation-proof
- Pattern hints (trial IDs, biomarkers, drugs)
- Async parallel batching (4 concurrent)
- Auto-retry for missing IDs
- Deterministic alias backstop (regex sweep)
- Filter non-study rows

Usage:
    python librarian_v2.py --ta "Bladder Cancer"
    python librarian_v2.py --ta "Lung Cancer"  # Auto-filters SCLC
"""

import json
import sys
import asyncio
import re
from pathlib import Path
from typing import List, Dict, Optional, Set
import argparse
import pandas as pd
from openai import AsyncOpenAI

# Import from app.py
from app import df_global, get_filtered_dataframe_multi

# Initialize async OpenAI client
aclient = AsyncOpenAI(timeout=180)

# Semaphore for concurrent batch control
SEM = asyncio.Semaphore(4)


# ============================================================================
# TA-SPECIFIC CONFIGURATION (V2)
# ============================================================================

TA_LIBRARIAN_CONFIG = {
    "Lung Cancer": {
        "exclude_if_title_contains": [
            "small cell lung", "small-cell lung", "SCLC",
            "limited stage", "extensive stage", "small cell carcinoma"
        ],
        "focus": "non-small cell lung cancer (NSCLC) only, with emphasis on MET-altered NSCLC (METex14 skipping mutations, MET amplification)",
        "emd_asset": "Tepotinib (Tepmetko)",
        "emd_indication": "Metastatic NSCLC with MET exon 14 skipping mutations (FDA traditional approval Feb 15, 2024; NCCN-preferred)",
        "landscape_file": "nsclc-json.json",
        "example_regimens": [
            "tepotinib monotherapy",
            "capmatinib monotherapy",
            "telisotuzumab vedotin",
            "osimertinib + savolitinib",
            "amivantamab + lazertinib"
        ]
    },
    "Bladder Cancer": {
        "exclude_if_title_contains": [],
        "focus": "urothelial carcinoma (all stages)",
        "emd_asset": "Avelumab (Bavencio)",
        "emd_indication": "1L maintenance after platinum chemotherapy",
        "landscape_file": "bladder-json.json",
        "example_regimens": [
            "enfortumab vedotin + pembrolizumab",
            "avelumab maintenance",
            "platinum chemotherapy → avelumab maintenance"
        ]
    },
    "Renal Cancer": {
        "exclude_if_title_contains": [],
        "focus": "renal cell carcinoma (RCC)",
        "emd_asset": "None (no EMD asset)",
        "emd_indication": "N/A",
        "landscape_file": None,
        "example_regimens": [
            "cabozantinib + nivolumab",
            "lenvatinib + pembrolizumab"
        ]
    },
    "Colorectal Cancer": {
        "exclude_if_title_contains": [],
        "focus": "colorectal cancer (CRC)",
        "emd_asset": "Cetuximab (Erbitux)",
        "emd_indication": "KRAS wild-type metastatic CRC",
        "landscape_file": "erbi-crc-json.json",
        "example_regimens": [
            "cetuximab + chemotherapy",
            "bevacizumab + FOLFOX"
        ]
    },
    "Head and Neck Cancer": {
        "exclude_if_title_contains": [],
        "focus": "head and neck squamous cell carcinoma (HNSCC)",
        "emd_asset": "Cetuximab (Erbitux)",
        "emd_indication": "Recurrent/metastatic HNSCC",
        "landscape_file": "erbi-HN-json.json",
        "example_regimens": [
            "cetuximab + platinum/5-FU",
            "pembrolizumab monotherapy"
        ]
    },
    "TGCT": {
        "exclude_if_title_contains": ["testicular", "germ cell tumor"],  # Avoid confusion with testicular GCT
        "focus": "tenosynovial giant cell tumor",
        "emd_asset": "Pimicotinib",
        "emd_indication": "Tenosynovial giant cell tumor (EMD Serono/Merck KGaA acquired worldwide commercialization rights from Abbisko; pivotal trial: MANEUVER)",
        "landscape_file": None,
        "example_regimens": [
            "pimicotinib",
            "vimseltinib",
            "pexidartinib"
        ]
    }
}


# ============================================================================
# HELPERS
# ============================================================================

def is_valid_study(title: str, row_id: str, ta: str = None) -> bool:
    """
    Filter out obvious non-study rows.
    V2: Added TA-specific exclusions (e.g., filter SCLC for Lung Cancer).

    Let AI handle borderline cases - better to over-include than miss real studies.
    """
    title_lower = title.lower().strip()

    # Only skip OBVIOUS non-studies
    skip_phrases = [
        "q&a session", "q&a and discussion",
        "meet the expert",
        "break",
        "opening remarks",
        "closing remarks"
    ]

    for phrase in skip_phrases:
        if phrase in title_lower:
            return False

    # V2: TA-specific exclusions
    if ta and ta in TA_LIBRARIAN_CONFIG:
        ta_config = TA_LIBRARIAN_CONFIG[ta]
        exclude_phrases = ta_config.get("exclude_if_title_contains", [])

        for phrase in exclude_phrases:
            if phrase.lower() in title_lower:
                return False  # Skip this study (e.g., SCLC for Lung Cancer)

    # Process everything else (including empty IDs, discussants, LBAs, etc.)
    # AI will extract what it can, or return minimal data for non-studies
    return True


def load_landscape_context(ta: str) -> Dict:
    """
    V2: Load TA-specific competitive landscape JSON file.
    Returns competitor drugs and biomarkers for prompt context.
    """
    if ta not in TA_LIBRARIAN_CONFIG:
        return {}

    ta_config = TA_LIBRARIAN_CONFIG[ta]
    landscape_file = ta_config.get("landscape_file")

    if not landscape_file:
        return {}

    try:
        filepath = Path(__file__).parent / landscape_file
        with open(filepath, 'r', encoding='utf-8') as f:
            landscape_data = json.load(f)

        # Extract relevant info for prompt
        context = {
            "emd_asset": ta_config.get("emd_asset", ""),
            "emd_indication": ta_config.get("emd_indication", ""),
            "focus": ta_config.get("focus", ""),
            "competitors": [],
            "biomarkers": []
        }

        # Extract competitor drug names
        if "direct_competitors" in landscape_data:
            context["competitors"] = [
                comp.get("drug", "") for comp in landscape_data["direct_competitors"]
            ][:5]  # Top 5 competitors

        # Extract biomarker names
        if "key_biomarkers" in landscape_data:
            context["biomarkers"] = [
                bio.get("biomarker", "") for bio in landscape_data["key_biomarkers"]
            ][:5]  # Top 5 biomarkers

        return context

    except Exception as e:
        print(f"[WARN] Could not load landscape file {landscape_file}: {e}")
        return {}


def load_aliases(ta: str) -> Dict:
    """Load entity aliases for deterministic backstop."""
    try:
        alias_file = Path(__file__).parent / "bladder-aliases.json"
        with open(alias_file, 'r') as f:
            return json.load(f)
    except:
        return {"drug_aliases": {}, "biomarker_aliases": {}}


def deterministic_alias_sweep(record: Dict, title: str, aliases: Dict) -> Dict:
    """
    Deterministic backstop: regex sweep for missed entities using aliases.
    Runs AFTER AI extraction to catch short tokens, novel codes.
    """
    title_lower = title.lower()

    # Sweep drugs
    if not record.get('drugs'):
        record['drugs'] = []

    for canonical, variants in aliases.get('drug_aliases', {}).items():
        for variant in variants:
            if re.search(r'\b' + re.escape(variant.lower()) + r'\b', title_lower):
                if canonical not in record['drugs']:
                    record['drugs'].append(canonical)

    # Sweep biomarkers
    if not record.get('biomarkers'):
        record['biomarkers'] = []

    for canonical, variants in aliases.get('biomarker_aliases', {}).items():
        for variant in variants:
            if re.search(r'\b' + re.escape(variant.lower()) + r'\b', title_lower):
                if canonical not in record['biomarkers']:
                    record['biomarkers'].append(canonical)

    return record


# ============================================================================
# ASYNC EXTRACTION WITH NDJSON
# ============================================================================

async def librarian_extract_batch_async(
    studies: List[Dict],
    batch_num: int,
    total_batches: int,
    ta: str = None,
    max_tokens: Optional[int] = None
) -> List[Dict]:
    """
    V2: Extract structured JSON using gpt-4o-mini with NDJSON format + TA-specific context.
    Includes pattern hints for better extraction.
    """

    # Dynamic token sizing
    if max_tokens is None:
        per_item = 65
        max_tokens = min(300 + per_item * len(studies), 3000)

    # V2: Load TA-specific landscape context
    landscape_context = load_landscape_context(ta) if ta else {}
    ta_config = TA_LIBRARIAN_CONFIG.get(ta, {}) if ta else {}

    # Build TA-specific context string
    ta_context_str = ""
    if landscape_context:
        ta_context_str = f"""
**THERAPEUTIC AREA CONTEXT ({ta})**:
- Focus: {landscape_context.get('focus', 'all studies')}
- EMD Serono Asset: {landscape_context.get('emd_asset', 'N/A')}
- Top Competitors: {', '.join(landscape_context.get('competitors', [])[:3])}
- Key Biomarkers: {', '.join(landscape_context.get('biomarkers', [])[:3])}

"""

    # Build example regimens from TA config
    example_regimens = ta_config.get("example_regimens", [
        "enfortumab vedotin + pembrolizumab",
        "avelumab maintenance",
        "platinum chemotherapy → avelumab maintenance"
    ])

    # Build compact prompt
    studies_text = "\n".join([
        f"[{s['row_id']}] {s['title'][:180]}"
        for s in studies
    ])

    # NDJSON prompt with pattern hints
    user_prompt = f"""Extract structured data from {len(studies)} {ta if ta else 'oncology'} study titles.
{ta_context_str}

**Output Format**: One JSON object per line (NDJSON). Do NOT wrap in array. Omit empty/null fields.

**Schema per line**:
{{
  "row_id": <string>,
  "regimen": <string describing the treatment approach>,
  "drugs": [<array of individual drug names>],
  "biomarkers": [<array of biomarkers>],
  "modality": [from: ["ADC","IO","TKI","Chemotherapy","Intravesical","Radiotherapy","Vaccine","Perioperative","Maintenance","Neoadjuvant","Adjuvant","Bispecific","CAR-T"]],
  "population": <"NMIBC"|"MIBC"|"mUC"|"UTUC"|"Other">,
  "line": <"1L"|"2L"|"3L"|"Maintenance"|"Perioperative"|"Neoadjuvant"|"Adjuvant">,
  "phase": <"Phase 1"|"Phase 2"|"Phase 3"|"Approved"|"Not specified">,
  "trial_id": <string>
}}

**CRITICAL - Regimen vs Drugs**:
- "regimen": The PRIMARY treatment being studied (how you'd describe it clinically)
  - Examples from {ta if ta else 'oncology'}: {', '.join(f'"{r}"' for r in example_regimens)}
- "drugs": Individual drug components (array for deduplication/normalization later)

**Pattern Hints**:
- Trial IDs: Look like "EV-302", "POTOMAC", "SunRISe-4", "KEYNOTE-A39"
- Biomarkers: Gene/protein tokens like "FGFR3", "PD-L1", "TROP2", "HER2"
- Drugs: Brand/generic/codes like "enfortumab vedotin", "Padcev", "LY3866288", "nivolumab"
- Combinations: Look for "+", "with", "plus", "combined with" patterns

Extract ONLY what's explicit in title. Output exactly {len(studies)} lines.

**Titles**:
{studies_text}"""

    try:
        async with SEM:
            response = await aclient.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a data extractor. Output ONLY NDJSON. No prose."},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=max_tokens
            )

        response_text = response.choices[0].message.content or ""

        if not response_text.strip():
            print(f"[BATCH {batch_num}/{total_batches}] Empty response - retrying with +500 tokens")
            await asyncio.sleep(0.6)  # Backoff
            return await librarian_extract_batch_async(
                studies, batch_num, total_batches, max_tokens=max_tokens + 500
            )

        # Parse NDJSON
        extracted = []
        for line in response_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("row_id"):
                    extracted.append(obj)
            except json.JSONDecodeError:
                continue

        if len(extracted) < len(studies):
            print(f"[BATCH {batch_num}/{total_batches}] Partial: {len(extracted)}/{len(studies)} records")

        return extracted

    except Exception as e:
        print(f"[BATCH {batch_num}/{total_batches}] ERROR: {e}")
        return []


async def librarian_extract_batch_async_retry(
    studies: List[Dict],
    sub_batch_size: int = 10
) -> List[Dict]:
    """Retry missing IDs in smaller batches."""
    all_extracted = []

    num_sub_batches = (len(studies) + sub_batch_size - 1) // sub_batch_size

    for i in range(0, len(studies), sub_batch_size):
        sub_batch = studies[i:i+sub_batch_size]
        sub_num = (i // sub_batch_size) + 1

        per_item = 70
        max_tokens = min(300 + per_item * len(sub_batch), 1500)

        extracted = await librarian_extract_batch_async(
            sub_batch, sub_num, num_sub_batches, max_tokens
        )

        all_extracted.extend(extracted)

    return all_extracted


async def run_batches_with_retries(
    studies: List[Dict],
    study_map: Dict[str, str],  # row_id -> title
    aliases: Dict,
    ta: str,  # V2: Added TA parameter
    batch_size: int = 20
) -> List[Dict]:
    """V2: Run batches with auto-retry + deterministic backstop + TA context."""

    total_batches = (len(studies) + batch_size - 1) // batch_size

    print(f"[LIBRARIAN] Running {total_batches} batches (size={batch_size}, max 4 concurrent)...")

    # Initial batch run
    tasks = []
    batch_map = {}

    for i in range(0, len(studies), batch_size):
        batch = studies[i:i+batch_size]
        batch_idx = len(tasks)
        batch_map[batch_idx] = batch
        tasks.append(librarian_extract_batch_async(batch, batch_idx+1, total_batches, ta))  # V2: Pass ta

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect results
    all_extracted = {}
    missing_studies = []

    for batch_idx, result in enumerate(results):
        batch = batch_map[batch_idx]

        if isinstance(result, Exception):
            print(f"[BATCH {batch_idx+1}] EXCEPTION: {result}")
            got = []
        else:
            got = result

        got_map = {r.get("row_id"): r for r in got if r.get("row_id")}
        want_ids = {s["row_id"] for s in batch}
        missing_ids = want_ids - set(got_map.keys())

        all_extracted.update(got_map)

        if missing_ids:
            missing_studies.extend([s for s in batch if s["row_id"] in missing_ids])
            print(f"[BATCH {batch_idx+1}] Missing {len(missing_ids)}/{len(batch)} IDs - will retry")
        else:
            print(f"[BATCH {batch_idx+1}] SUCCESS: {len(got)}/{len(batch)} records")

    print(f"[LIBRARIAN] Initial pass: {len(all_extracted)}/{len(studies)} extracted")

    # Retry missing
    if missing_studies:
        print(f"[LIBRARIAN] Retrying {len(missing_studies)} missing studies...")

        retry_results = await librarian_extract_batch_async_retry(missing_studies, sub_batch_size=10)

        for record in retry_results:
            if record.get("row_id"):
                all_extracted[record["row_id"]] = record

        print(f"[LIBRARIAN] After retry: {len(all_extracted)}/{len(studies)} extracted")

    # Deterministic alias backstop
    print(f"[LIBRARIAN] Running deterministic alias sweep...")
    for row_id, record in all_extracted.items():
        title = study_map.get(row_id, "")
        all_extracted[row_id] = deterministic_alias_sweep(record, title, aliases)

    return list(all_extracted.values())


# ============================================================================
# MAIN
# ============================================================================

def librarian_process_all(
    ta: str,
    limit: Optional[int] = None,
    batch_size: int = 20
) -> List[Dict]:
    """Process all studies."""

    print(f"\n{'='*80}")
    print(f"LIBRARIAN: {ta}")
    print(f"{'='*80}\n")

    # Load aliases
    aliases = load_aliases(ta)

    # Filter to TA
    filtered_df = get_filtered_dataframe_multi(
        drug_filters=[], ta_filters=[ta], session_filters=[], date_filters=[]
    )

    print(f"[LIBRARIAN] Filtered to {len(filtered_df)} {ta} studies")

    if limit:
        filtered_df = filtered_df.head(limit)
        print(f"[LIBRARIAN] Limited to {len(filtered_df)} studies")

    # Filter non-studies
    studies = []
    study_map = {}
    skipped = 0

    for idx, row in filtered_df.iterrows():
        title = str(row['Title'])

        # Handle potentially missing Identifier
        try:
            row_id = str(row['Identifier']).strip()
            if not row_id or row_id == 'nan' or row_id == 'None':
                row_id = f"ROW_{idx}"
        except:
            row_id = f"ROW_{idx}"

        if is_valid_study(title, row_id, ta):  # V2: Pass ta for TA-specific filtering
            studies.append({'row_id': row_id, 'title': title})
            study_map[row_id] = title
        else:
            skipped += 1

    print(f"[LIBRARIAN] Valid studies: {len(studies)} (skipped {skipped} non-study rows)")

    # Run extraction
    import time
    start_time = time.time()

    extracted = asyncio.run(run_batches_with_retries(studies, study_map, aliases, ta, batch_size))  # V2: Pass ta

    elapsed = time.time() - start_time

    print(f"\n[LIBRARIAN] COMPLETE: {len(extracted)}/{len(studies)} studies")
    print(f"[LIBRARIAN] Time: {elapsed:.1f}s ({len(extracted)/elapsed if elapsed > 0 else 0:.1f} studies/sec)")

    return extracted


def main():
    parser = argparse.ArgumentParser(description='Production Librarian')
    parser.add_argument('--ta', type=str, default="Bladder Cancer")
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--batch-size', type=int, default=20)
    parser.add_argument('--output', type=str, default=None)

    args = parser.parse_args()

    extracted = librarian_process_all(args.ta, args.limit, args.batch_size)

    # Sample
    print(f"\n{'='*80}")
    print(f"SAMPLE (first 3)")
    print(f"{'='*80}\n")

    for record in extracted[:3]:
        print(json.dumps(record, indent=2))
        print()

    # Save
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(extracted, f, indent=2, ensure_ascii=False)
        print(f"\n[SAVED] {len(extracted)} records -> {output_path}")

    # Stats
    print(f"\n{'='*80}")
    print(f"STATS")
    print(f"{'='*80}\n")

    drug_count = sum(1 for r in extracted if r.get('drugs'))
    biomarker_count = sum(1 for r in extracted if r.get('biomarkers'))
    trial_count = sum(1 for r in extracted if r.get('trial_id'))

    print(f"Records with drugs: {drug_count}/{len(extracted)}")
    print(f"Records with biomarkers: {biomarker_count}/{len(extracted)}")
    print(f"Records with trial_id: {trial_count}/{len(extracted)}")

    all_drugs = set()
    all_biomarkers = set()

    for r in extracted:
        all_drugs.update(r.get('drugs', []))
        all_biomarkers.update(r.get('biomarkers', []))

    print(f"\nUnique drugs: {len(all_drugs)}")
    print(f"Unique biomarkers: {len(all_biomarkers)}")


if __name__ == "__main__":
    main()
