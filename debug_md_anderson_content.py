#!/usr/bin/env python3
"""
Check what's actually in the MD Anderson search results
"""
import pandas as pd

print("Loading ESMO dataset...")
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv', encoding='latin-1')

print("=== Searching for MD Anderson variations ===")

# Search variations of MD Anderson
search_terms = [
    "MD Anderson",
    "M.D. Anderson",
    "M D Anderson",
    "Anderson Cancer",
    "Texas MD",
    "Houston"  # MD Anderson is in Houston
]

all_text_columns = ['Title', 'Speakers', 'Speaker Location', 'Affiliation', 'Room', 'Date', 'Time', 'Session', 'Theme', 'Identifier']

for term in search_terms:
    print(f"\n--- Searching for '{term}' ---")

    # Create mask for all columns
    mask = pd.Series([False] * len(df))

    for col in all_text_columns:
        if col in df.columns:
            col_matches = df[col].astype(str).str.contains(term, case=False, na=False, regex=False)
            mask = mask | col_matches

    results = df[mask]
    print(f"Found {len(results)} results")

    if len(results) > 0:
        print("Sample matches:")
        for i, (idx, row) in enumerate(results.head(3).iterrows()):
            # Show which columns contain the term
            matching_cols = []
            for col in all_text_columns:
                if col in df.columns and term.lower() in str(row[col]).lower():
                    matching_cols.append(f"{col}: {str(row[col])[:80]}...")

            if matching_cols:
                print(f"  Result {i+1}:")
                for match in matching_cols[:2]:  # Show first 2 matching columns
                    print(f"    {match}")

# Special check: what does "MD Anderson" search actually find?
print("\n=== Exact check: What contains 'MD Anderson'? ===")
for col in ['Affiliation', 'Speakers', 'Speaker Location']:
    if col in df.columns:
        matches = df[df[col].astype(str).str.contains('MD Anderson', case=False, na=False)]
        print(f"\n{col} column with 'MD Anderson': {len(matches)} matches")
        if len(matches) > 0:
            for i, val in enumerate(matches[col].head(3)):
                print(f"  {i+1}. {val}")