"""
Tagger - Entity Normalization & Aggregation
============================================

Takes Librarian output (structured JSON per study) and:
1. Normalizes drug/biomarker names using alias dictionaries
2. Counts occurrences across all studies
3. Identifies competitor drugs vs emerging threats
4. Generates summary statistics for Journalist

Usage:
    from tagger import tag_and_aggregate
    tagged_data = tag_and_aggregate(librarian_output, aliases)
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set, Optional
from collections import Counter


def normalize_regimen(regimen: str) -> Optional[str]:
    """
    Normalize regimen strings for consistent counting.

    Args:
        regimen: Raw regimen string from Librarian

    Returns:
        Normalized regimen or None if it should be filtered out
    """
    if not regimen or not regimen.strip():
        return None

    normalized = regimen.strip()

    # Filter out junk/generic regimens
    junk_patterns = [
        r'^N/A$',
        r'^Not specified$',
        r'^Optim(is|iz)ing',
        r'^Systemic Therapy$',
        r'^Treatment$',
        r'^Therapy$',
        r'^Study$',
        r'^Trial$',
        r'^Discussion$',
        r'^Educational',
    ]

    for pattern in junk_patterns:
        if re.match(pattern, normalized, re.IGNORECASE):
            return None

    # Standardize "and" to "+"
    normalized = re.sub(r'\s+and\s+', ' + ', normalized, flags=re.IGNORECASE)

    # Standardize spacing around + and →
    normalized = re.sub(r'\s*\+\s*', ' + ', normalized)
    normalized = re.sub(r'\s*→\s*', ' → ', normalized)

    # Lowercase drug names for consistency but preserve capitalization of abbreviations
    # This is tricky - for now just standardize spacing
    normalized = ' '.join(normalized.split())

    return normalized


def normalize_entity(entity: str, alias_dict: Dict[str, List[str]]) -> str:
    """
    Normalize an entity name using alias dictionary.

    Args:
        entity: Raw entity name from AI extraction
        alias_dict: {canonical_name: [alias1, alias2, ...]}

    Returns:
        Canonical name if found, otherwise original entity (lowercased)
    """
    entity_lower = entity.lower().strip()

    # Check if it matches any canonical name or alias
    for canonical, aliases in alias_dict.items():
        if entity_lower == canonical.lower():
            return canonical
        if entity_lower in [a.lower() for a in aliases]:
            return canonical

    # Return original if no match found
    return entity


def tag_and_aggregate(
    librarian_records: List[Dict],
    aliases: Dict
) -> Dict:
    """
    Normalize entities and aggregate statistics.

    Args:
        librarian_records: List of extracted study records from Librarian
        aliases: Alias dictionaries loaded from bladder-aliases.json

    Returns:
        Dict with:
        - tagged_records: Normalized version of input records
        - drug_counts: {drug: count}
        - biomarker_counts: {biomarker: count}
        - competitor_drugs: Set of known competitors found
        - emerging_drugs: Set of novel/emerging drugs found
        - stats: Summary statistics
    """

    drug_alias_dict = aliases.get("drug_aliases", {})
    biomarker_alias_dict = aliases.get("biomarker_aliases", {})
    known_competitors = set(aliases.get("known_competitors", []))

    # Counters
    regimen_counter = Counter()  # Count by REGIMEN (treatment approach)
    drug_counter = Counter()      # Count individual drugs (for reference)
    biomarker_counter = Counter()
    competitor_regimens = set()
    emerging_regimens = set()

    # Tag each record
    tagged_records = []

    for record in librarian_records:
        tagged_record = record.copy()

        # Normalize regimen (primary treatment approach)
        raw_regimen = record.get("regimen", "")
        normalized_regimen = normalize_regimen(raw_regimen) if raw_regimen else None

        if normalized_regimen:
            # Count by normalized regimen (this is what we show to AI)
            regimen_counter[normalized_regimen] += 1
            tagged_record["regimen_normalized"] = normalized_regimen

            # Classify regimen as competitor or emerging based on drugs
            raw_drugs = record.get("drugs", [])
            has_competitor = any(
                normalize_entity(d, drug_alias_dict).lower() in [c.lower() for c in known_competitors]
                for d in raw_drugs if d
            )
            if has_competitor:
                competitor_regimens.add(normalized_regimen)
            else:
                emerging_regimens.add(normalized_regimen)

        # Normalize drugs (keep for reference, but don't use for main counting)
        raw_drugs = record.get("drugs", [])
        normalized_drugs = []
        for drug in raw_drugs:
            if drug:  # Skip empty strings
                normalized = normalize_entity(drug, drug_alias_dict)
                normalized_drugs.append(normalized)
                drug_counter[normalized] += 1  # Keep for reference

        tagged_record["drugs_normalized"] = normalized_drugs

        # Normalize biomarkers
        raw_biomarkers = record.get("biomarkers", [])
        normalized_biomarkers = []
        for biomarker in raw_biomarkers:
            if biomarker:  # Skip empty strings
                normalized = normalize_entity(biomarker, biomarker_alias_dict)
                normalized_biomarkers.append(normalized)
                biomarker_counter[normalized] += 1

        tagged_record["biomarkers_normalized"] = normalized_biomarkers

        tagged_records.append(tagged_record)

    # Generate summary statistics
    stats = {
        "total_studies": len(librarian_records),
        "studies_with_regimen": sum(1 for r in librarian_records if r.get("regimen")),
        "studies_with_drugs": sum(1 for r in librarian_records if r.get("drugs")),
        "studies_with_biomarkers": sum(1 for r in librarian_records if r.get("biomarkers")),
        "unique_regimens": len(regimen_counter),
        "unique_drugs": len(drug_counter),
        "unique_biomarkers": len(biomarker_counter),
        "competitor_regimens_found": len(competitor_regimens),
        "emerging_regimens_found": len(emerging_regimens)
    }

    return {
        "tagged_records": tagged_records,
        "regimen_counts": dict(regimen_counter.most_common()),  # PRIMARY: count by regimen
        "drug_counts": dict(drug_counter.most_common()),        # REFERENCE: individual drugs
        "biomarker_counts": dict(biomarker_counter.most_common()),
        "competitor_regimens": sorted(list(competitor_regimens)),
        "emerging_regimens": sorted(list(emerging_regimens)),
        "stats": stats
    }


def main():
    """CLI for testing Tagger"""
    import argparse

    parser = argparse.ArgumentParser(description="Tag and aggregate Librarian output")
    parser.add_argument("--input", required=True, help="Librarian JSON output file")
    parser.add_argument("--aliases", default="bladder-aliases.json", help="Alias dictionary")
    parser.add_argument("--output", help="Output file for tagged data (optional)")
    args = parser.parse_args()

    # Load inputs
    with open(args.input, 'r', encoding='utf-8') as f:
        librarian_records = json.load(f)

    with open(args.aliases, 'r', encoding='utf-8') as f:
        aliases = json.load(f)

    print(f"[TAGGER] Loaded {len(librarian_records)} records from {args.input}")

    # Run tagging
    result = tag_and_aggregate(librarian_records, aliases)

    # Print summary
    print("\n" + "="*80)
    print("TAGGER SUMMARY")
    print("="*80)
    print(f"Total studies: {result['stats']['total_studies']}")
    print(f"Studies with drugs: {result['stats']['studies_with_drugs']}")
    print(f"Studies with biomarkers: {result['stats']['studies_with_biomarkers']}")
    print(f"Unique drugs: {result['stats']['unique_drugs']}")
    print(f"Unique biomarkers: {result['stats']['unique_biomarkers']}")
    print(f"Competitor drugs found: {result['stats']['competitor_drugs_found']}")
    print(f"Emerging drugs found: {result['stats']['emerging_drugs_found']}")

    print("\n" + "="*80)
    print("TOP 10 DRUGS")
    print("="*80)
    for drug, count in list(result['drug_counts'].items())[:10]:
        tag = "COMPETITOR" if drug in result['competitor_drugs'] else "EMERGING"
        print(f"{drug:30} {count:3} studies [{tag}]")

    print("\n" + "="*80)
    print("TOP 10 BIOMARKERS")
    print("="*80)
    for biomarker, count in list(result['biomarker_counts'].items())[:10]:
        print(f"{biomarker:30} {count:3} studies")

    # Save output if requested
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n[SAVED] Tagged data -> {args.output}")


if __name__ == "__main__":
    main()
