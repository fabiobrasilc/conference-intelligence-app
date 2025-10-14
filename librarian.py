"""
Production Librarian - gpt-4o-mini with NDJSON + Pattern Hints
===============================================================

Optimizations:
- gpt-4o-mini (fast, reliable, cost-efficient)
- NDJSON output (one JSON per line) - truncation-proof
- Pattern hints (trial IDs, biomarkers, drugs)
- Async parallel batching (4 concurrent)
- Auto-retry for missing IDs
- Deterministic alias backstop (regex sweep)
- Filter non-study rows

Usage:
    python librarian.py --ta "Bladder Cancer"
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
# HELPERS
# ============================================================================

def is_valid_study(title: str, row_id: str) -> bool:
    """
    Filter out obvious non-study rows.
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

    # Process everything else (including empty IDs, discussants, LBAs, etc.)
    # AI will extract what it can, or return minimal data for non-studies
    return True


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

    # MET-specific detection: distinguish MET alterations from metastasis
    # Only tag as MET biomarker if it appears with alteration/mutation/exon context
    met_biomarker_patterns = [
        r'\bmet\s+alteration',
        r'\bmet\s+mutation',
        r'\bmet\s+amplification',
        r'\bmet\s+exon',
        r'\bmetex14',
        r'\bmet\s+ex14',
        r'\bmet\s+ex\s*14',
        r'\bc-met\b',
        r'\bhgf/met\b'
    ]

    if any(re.search(pattern, title_lower) for pattern in met_biomarker_patterns):
        if 'MET' not in record['biomarkers']:
            record['biomarkers'].append('MET')

    return record


# ============================================================================
# ASYNC EXTRACTION WITH NDJSON
# ============================================================================

async def librarian_extract_batch_async(
    studies: List[Dict],
    batch_num: int,
    total_batches: int,
    max_tokens: Optional[int] = None
) -> List[Dict]:
    """
    Extract structured JSON using gpt-4o-mini with NDJSON format.
    Includes pattern hints for better extraction.
    """

    # Dynamic token sizing
    if max_tokens is None:
        per_item = 65
        max_tokens = min(300 + per_item * len(studies), 3000)

    # Build compact prompt with abstracts
    studies_text = "\n".join([
        f"[{s['row_id']}]\nTitle: {s['title']}\nAbstract: {s['abstract'][:500] if s['abstract'] else 'Not available'}\n"
        for s in studies
    ])

    # NDJSON prompt with pattern hints
    user_prompt = f"""Extract structured data from {len(studies)} studies (titles + abstracts when available).

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

**CRITICAL - MET BIOMARKER EXTRACTION (HIGHEST PRIORITY)**:
YOU MUST extract MET as a biomarker when ANY of these appear in title/abstract:
- "MET exon 14" / "METex14" / "METex 14" / "MET ex14" → Extract "MET" in biomarkers array
- "MET amplification" / "MET amp" / "METamp" → Extract "MET" in biomarkers array
- "MET overexpression" / "MET protein" / "c-MET" → Extract "MET" in biomarkers array
- "MET alteration" / "MET mutation" / "HGF/MET" → Extract "MET" in biomarkers array

DO NOT extract "MET" when these appear (these are NOT biomarkers):
- "metastatic" / "metastasis" / "mNSCLC" / "metastases" → These describe disease stage, NOT MET biomarker

**CRITICAL - MET DRUG EXTRACTION (HIGHEST PRIORITY)**:
ALWAYS extract these MET-targeting drugs when mentioned:
- tepotinib, Tepmetko, capmatinib, Tabrecta, savolitinib, crizotinib
- telisotuzumab vedotin, Teliso-V, amivantamab, osimertinib + savolitinib, osimertinib + capmatinib

**CRITICAL - Regimen vs Drugs**:
- "regimen": The PRIMARY treatment being studied (how you'd describe it clinically)
  - For combinations: "osimertinib + savolitinib", "nivolumab + gemcitabine/cisplatin"
  - For monotherapy: "tepotinib", "capmatinib", "erdafitinib"
  - For sequence studies: "platinum chemotherapy → avelumab maintenance"
- "drugs": Individual drug components (array for deduplication/normalization later)

**Pattern Hints**:
- Trial IDs: Look like "EV-302", "POTOMAC", "SunRISe-4", "KEYNOTE-A39", "SAVANNAH"
- Biomarkers: Gene/protein tokens like "FGFR3", "PD-L1", "TROP2", "HER2", "MET"
  - CRITICAL for MET: "MET alteration", "MET exon", "MET amplification", "MET mutation", "METex14" = biomarker (extract as "MET")
  - "metastatic", "metastasis", "mNSCLC" = population descriptor (NOT a biomarker)
- Drugs: Brand/generic/codes like "enfortumab vedotin", "Padcev", "LY3866288", "nivolumab"
  - MET-targeting drugs: "tepotinib", "Tepmetko", "capmatinib", "Tabrecta", "savolitinib", "crizotinib", "telisotuzumab vedotin", "Teliso-V", "amivantamab"
- Combinations: Look for "+", "with", "plus", "combined with" patterns (e.g., "osimertinib + savolitinib")

Extract ONLY what's explicit in title and abstract. Use abstract content for richer extraction. Output exactly {len(studies)} lines.

**Studies**:
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
    batch_size: int = 20
) -> List[Dict]:
    """Run batches with auto-retry + deterministic backstop."""

    total_batches = (len(studies) + batch_size - 1) // batch_size

    print(f"[LIBRARIAN] Running {total_batches} batches (size={batch_size}, max 4 concurrent)...")

    # Initial batch run
    tasks = []
    batch_map = {}

    for i in range(0, len(studies), batch_size):
        batch = studies[i:i+batch_size]
        batch_idx = len(tasks)
        batch_map[batch_idx] = batch
        tasks.append(librarian_extract_batch_async(batch, batch_idx+1, total_batches))

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

        # Get abstract if available
        abstract = str(row.get('Abstract', '')).strip()
        if abstract == 'nan' or abstract == 'None':
            abstract = ''

        # Handle potentially missing Identifier
        try:
            row_id = str(row['Identifier']).strip()
            if not row_id or row_id == 'nan' or row_id == 'None':
                row_id = f"ROW_{idx}"
        except:
            row_id = f"ROW_{idx}"

        if is_valid_study(title, row_id):
            studies.append({'row_id': row_id, 'title': title, 'abstract': abstract})
            study_map[row_id] = title
        else:
            skipped += 1

    print(f"[LIBRARIAN] Valid studies: {len(studies)} (skipped {skipped} non-study rows)")

    # Run extraction
    import time
    start_time = time.time()

    extracted = asyncio.run(run_batches_with_retries(studies, study_map, aliases, batch_size))

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
