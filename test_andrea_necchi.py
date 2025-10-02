#!/usr/bin/env python3
"""
Quick test script to check Andrea Necchi's study count
"""
import pandas as pd
from pathlib import Path

# Load data
CSV_FILE = Path(__file__).parent / "ESMO_2025_FINAL_20250929.csv"
df = pd.read_csv(CSV_FILE, encoding="latin-1").fillna("")

print(f"Total sessions in dataset: {len(df)}")
print(f"Columns: {list(df.columns)}")
print()

# Search for Andrea Necchi
author_name = "Andrea Necchi"
matches = df[df['Speakers'].str.contains(author_name, case=False, na=False)]

print(f"Studies with '{author_name}':")
print(f"Total count: {len(matches)}")
print()

for idx, row in matches.iterrows():
    print(f"{idx+1}. [{row['Session']}] {row['Title'][:80]}...")
    print(f"   ID: {row['Identifier']}, Theme: {row['Theme']}")
    print()

# Now test with bladder cancer filter
print("=" * 80)
print("BLADDER CANCER FILTER TEST")
print("=" * 80)

bladder_keywords = ["bladder", "urothelial", "uroepithelial", "transitional cell", "GU", "genitourinary"]
exclusions = ["prostate"]

# Apply bladder filter
bladder_mask = pd.Series([False] * len(df))
for keyword in bladder_keywords:
    title_mask = df["Title"].str.contains(keyword, case=False, na=False)
    theme_mask = df["Theme"].str.contains(keyword, case=False, na=False)
    bladder_mask = bladder_mask | title_mask | theme_mask

# Exclude prostate
for exclusion in exclusions:
    prostate_mask = df["Title"].str.contains(exclusion, case=False, na=False) | df["Theme"].str.contains(exclusion, case=False, na=False)
    bladder_mask = bladder_mask & ~prostate_mask

filtered_df = df[bladder_mask]
print(f"Total bladder cancer sessions: {len(filtered_df)}")
print()

# Now find Andrea Necchi in filtered data
necchi_filtered = filtered_df[filtered_df['Speakers'].str.contains(author_name, case=False, na=False)]
print(f"Andrea Necchi studies in bladder cancer filter: {len(necchi_filtered)}")
print()

for idx, row in necchi_filtered.iterrows():
    print(f"{idx+1}. [{row['Session']}] {row['Title'][:80]}...")
    print(f"   ID: {row['Identifier']}")
    print()

# Check deduplication
print("=" * 80)
print("DEDUPLICATION TEST")
print("=" * 80)

# Try deduplicating by "Abstract #" column (if exists)
if "Abstract #" in filtered_df.columns:
    print("Using 'Abstract #' for deduplication")
    dedup_df = filtered_df.drop_duplicates(subset=["Abstract #"])
else:
    print("No 'Abstract #' column - trying 'Identifier'")
    dedup_df = filtered_df.drop_duplicates(subset=["Identifier"])

print(f"Before dedup: {len(necchi_filtered)} Andrea Necchi studies")

necchi_dedup = dedup_df[dedup_df['Speakers'].str.contains(author_name, case=False, na=False)]
print(f"After dedup: {len(necchi_dedup)} Andrea Necchi studies")
print()

# Check which ones have empty IDs
empty_id_count = (necchi_filtered['Identifier'] == '').sum()
print(f"Studies with empty Identifier: {empty_id_count}")