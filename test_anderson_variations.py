#!/usr/bin/env python3
"""
Test script to find all Anderson references (with and without MD) in ESMO 2025 dataset
"""
import pandas as pd

# Load the dataset
print("Loading ESMO 2025 dataset...")
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv', encoding='latin-1')
print(f"Dataset loaded: {len(df)} total rows")

# Search for different Anderson variations
anderson_variations = [
    "MD Anderson",
    "Anderson Cancer",
    "Anderson Center",
    "University of Texas Anderson",
    "UT Anderson",
    " Anderson "  # Anderson with spaces (not at start/end)
]

print(f"\n=== Searching for Anderson variations across all columns ===")

esmo_columns = ['Title', 'Speakers', 'Speaker Location', 'Affiliation', 'Identifier', 'Room', 'Date', 'Time', 'Session', 'Theme']

for search_term in anderson_variations:
    print(f"\n--- Searching for '{search_term}' ---")
    total_found = False

    for col in esmo_columns:
        if col in df.columns:
            col_matches = df[col].astype(str).str.contains(search_term, case=False, na=False)
            matches_count = col_matches.sum()
            if matches_count > 0:
                print(f"  {col}: {matches_count} matches")
                # Show examples
                sample_matches = df[col_matches][col].head(2).tolist()
                for match in sample_matches:
                    print(f"    - {match}")
                total_found = True

    if not total_found:
        print(f"  No matches found for '{search_term}'")

# Also check for any degree suffixes that might indicate cleaning
print(f"\n=== Checking for degree cleaning patterns ===")
degree_patterns = [
    ", MD",
    ", M.D.",
    ", PhD",
    ", M.D,",
    "MD,",
    "M.D.,"
]

for pattern in degree_patterns:
    total_with_pattern = 0
    for col in ['Speakers', 'Affiliation']:
        if col in df.columns:
            matches = df[col].astype(str).str.contains(pattern, case=False, na=False).sum()
            if matches > 0:
                print(f"  {col} contains '{pattern}': {matches} matches")
                total_with_pattern += matches

    if total_with_pattern == 0:
        print(f"  No '{pattern}' found in dataset")