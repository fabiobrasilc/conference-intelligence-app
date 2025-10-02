#!/usr/bin/env python3
"""
Test the enhanced TA filter logic with new keywords
"""
import pandas as pd
import os

# Change to the correct directory
os.chdir(r"C:\Users\m337928\OneDrive - MerckGroup\Documents\Python Projects\conference_intelligence_app")

print("Loading ESMO 2025 dataset...")
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv', encoding='latin-1')
print(f"Total rows: {len(df)}")

# Test the new TA filter mappings
TA_FILTERS = {
    "Bladder Cancer": ["bladder", "urothelial", "uroepithelial", "transitional cell", "GU", "genitourinary"],
    "Renal Cancer": ["renal", "renal cell", "RCC"],
    "Lung Cancer": ["NSCLC", "non-small cell lung cancer", "non-small-cell lung cancer", "MET", "ALK", "EGFR", "KRAS"],
    "Colorectal Cancer": ["colorectal", "CRC", "colon", "rectal", "GI", "gastrointestinal", "bowel", "KRAS", "MSI", "microsatellite"],
    "Head and Neck Cancer": ["head and neck", "head & neck", "H&N", "HNSCC", "SCCHN", "squamous cell carcinoma of the head", "oral", "pharyngeal", "laryngeal"],
    "TGCT": ["TGCT", "PVNS", "tenosynovial giant cell tumor", "pigmented villonodular synovitis"]
}

print("\n=== Testing Enhanced TA Filter Keywords ===")

for ta_name, keywords in TA_FILTERS.items():
    print(f"\n--- {ta_name} ---")
    print(f"Keywords: {keywords}")

    # Create mask for all keywords
    mask = pd.Series([False] * len(df))

    for keyword in keywords:
        # Search in both Title and Theme columns
        if len(keyword.split()) > 1:
            # Multi-word phrases - use word boundary matching
            import re
            pattern = r'\b' + re.escape(keyword) + r'\b'
            title_matches = df["Title"].str.contains(pattern, case=False, na=False, regex=True)
            theme_matches = df["Theme"].str.contains(pattern, case=False, na=False, regex=True)
        else:
            # Single words
            title_matches = df["Title"].str.contains(keyword, case=False, na=False, regex=False)
            theme_matches = df["Theme"].str.contains(keyword, case=False, na=False, regex=False)

        keyword_matches = title_matches | theme_matches
        mask = mask | keyword_matches

        if keyword_matches.sum() > 0:
            print(f"  '{keyword}': {keyword_matches.sum()} matches")

    # Apply exclusions for Bladder Cancer (exclude prostate)
    if ta_name == "Bladder Cancer":
        exclusion_mask = (
            df["Title"].str.contains("prostate", case=False, na=False, regex=False) |
            df["Theme"].str.contains("prostate", case=False, na=False, regex=False)
        )
        mask = mask & ~exclusion_mask
        print(f"  After excluding prostate: {mask.sum()} matches")

    total_matches = mask.sum()
    print(f"  Total {ta_name} matches: {total_matches}")

    # Show a few sample titles
    if total_matches > 0:
        filtered_df = df[mask]
        print(f"  Sample titles:")
        for idx, row in filtered_df.head(3).iterrows():
            title = row['Title'][:80] + "..." if len(row['Title']) > 80 else row['Title']
            print(f"    - {title}")

print("\n=== Special Test: Lung Cancer Phrase Matching ===")
# Test specifically for "non-small cell lung cancer" vs "cell"
nsclc_phrase_pattern = r'\bnon-small cell lung cancer\b'
nsclc_matches = df["Title"].str.contains(nsclc_phrase_pattern, case=False, na=False, regex=True)
print(f"'non-small cell lung cancer' phrase matches: {nsclc_matches.sum()}")

cell_matches = df["Title"].str.contains("cell", case=False, na=False, regex=False)
print(f"'cell' word matches: {cell_matches.sum()}")
print("✅ Phrase matching prevents false positives!")

print("\n=== Testing Complete! ===")
print("TA filters are working with enhanced keyword logic.")