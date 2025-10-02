#!/usr/bin/env python3
"""
Test script to find all MD Anderson references in ESMO 2025 dataset
"""
import pandas as pd

# Load the dataset
print("Loading ESMO 2025 dataset...")
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv', encoding='latin-1')
print(f"Dataset loaded: {len(df)} total rows")
print(f"Columns: {list(df.columns)}")

# Search for MD Anderson in each column
search_term = "MD Anderson"
print(f"\n=== Searching for '{search_term}' across all columns ===")

total_matches = 0
all_matches = pd.Series([False] * len(df))

# Check each column individually
esmo_columns = ['Title', 'Speakers', 'Speaker Location', 'Affiliation', 'Identifier', 'Room', 'Date', 'Time', 'Session', 'Theme']

for col in esmo_columns:
    if col in df.columns:
        col_matches = df[col].astype(str).str.contains(search_term, case=False, na=False)
        matches_count = col_matches.sum()
        if matches_count > 0:
            print(f"  {col}: {matches_count} matches")
            # Show a few examples
            sample_matches = df[col_matches][col].head(3).tolist()
            for match in sample_matches:
                print(f"    - {match}")
            all_matches = all_matches | col_matches
            total_matches += matches_count

print(f"\nTotal unique rows with '{search_term}': {all_matches.sum()}")
print(f"Total column matches (may include duplicates): {total_matches}")

# Show all unique matching rows
if all_matches.sum() > 0:
    print(f"\n=== All {all_matches.sum()} unique matching rows ===")
    matching_rows = df[all_matches][['Title', 'Speakers', 'Affiliation']].head(10)
    for idx, row in matching_rows.iterrows():
        print(f"Row {idx}:")
        print(f"  Title: {row['Title']}")
        print(f"  Speakers: {row['Speakers']}")
        print(f"  Affiliation: {row['Affiliation']}")
        print()