#!/usr/bin/env python3
"""
Test why 'medley' search is not working with Bladder Cancer filter
"""

import sys
import pandas as pd
import re

# Load the data
import os
os.chdir(r'c:\Users\m337928\OneDrive - MerckGroup\Documents\Python Projects\conference_intelligence_app')
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv')
print(f"Total dataset: {len(df)} rows")

# Apply Bladder Cancer filter (simulating the backend logic)
bladder_keywords = ["bladder", "urothelial", "uroepithelial", "transitional cell", "genitourinary", "GU"]
exclude_keywords = ["prostate", "penile", "renal cell", "kidney"]

# Create theme mask
theme_matches = df['Theme'].str.contains('|'.join(bladder_keywords), case=False, na=False)

# Exclusion logic
exclude_mask = pd.Series([False] * len(df))
for exclude_term in exclude_keywords:
    exclude_mask |= df['Theme'].str.contains(exclude_term, case=False, na=False)

# Special rule: if Theme contains "renal", only match if Title also has bladder keywords
renal_in_theme = df['Theme'].str.contains('renal', case=False, na=False)
title_has_bladder = df['Title'].str.contains('|'.join(bladder_keywords), case=False, na=False)
exclude_mask = exclude_mask & ~(renal_in_theme & title_has_bladder)

bladder_df = df[theme_matches & ~exclude_mask].copy()
print(f"Bladder Cancer filtered: {len(bladder_df)} rows")

# Check for "medley" in filtered dataset
medley_in_filtered = bladder_df['Title'].str.contains('medley', case=False, na=False)
print(f"\n'Medley' in Title column: {medley_in_filtered.sum()} results")

if medley_in_filtered.sum() > 0:
    medley_rows = bladder_df[medley_in_filtered]
    for idx, row in medley_rows.iterrows():
        print(f"\nFound medley study:")
        print(f"  Title: {row['Title']}")
        print(f"  Theme: {row['Theme']}")
        print(f"  Identifier: {row.get('Identifier', 'N/A')}")

# Now simulate the search function logic
print(f"\n=== Simulating execute_simple_search() ===")
keyword = "medley"
search_columns = ['Title', 'Speakers', 'Speaker Location', 'Affiliation', 'Identifier', 'Room', 'Date', 'Time', 'Session', 'Theme']

# Check which columns exist
actual_columns = [col for col in search_columns if col in bladder_df.columns]
print(f"Searching in columns: {actual_columns}")

# FIX: Initialize mask with same index as bladder_df
mask = pd.Series([False] * len(bladder_df), index=bladder_df.index)
print(f"Initial mask index: {mask.index[:5].tolist()}")
print(f"Initial mask length: {len(mask)}")
print(f"Bladder_df index: {bladder_df.index[:5].tolist()}")
print(f"Bladder_df length: {len(bladder_df)}")

for col in actual_columns:
    try:
        col_mask = bladder_df[col].astype(str).str.contains(keyword, case=False, na=False, regex=False)
        matches = col_mask.sum()
        if matches > 0:
            print(f"  {col}: {matches} matches")
            print(f"    col_mask index: {col_mask.index[:5].tolist()}")
            print(f"    col_mask length: {len(col_mask)}")
            print(f"    Matching indices: {col_mask[col_mask].index.tolist()}")
        mask = mask | col_mask
        print(f"    Mask sum after {col}: {mask.sum()}")
    except Exception as e:
        print(f"  {col}: ERROR - {e}")

print(f"\nTotal matches: {mask.sum()}")
print(f"Expected: 1, Got: {mask.sum()}")

if mask.sum() == 0:
    print("\nBUG CONFIRMED: Search function returns 0 results when it should return 1")
else:
    print("\nSearch function working correctly!")
