#!/usr/bin/env python3
"""
Simple debug script to check date and session filtering
"""
import pandas as pd

# Load a small sample of the data
print("Loading ESMO 2025 data (first 1000 rows)...")
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv', encoding='latin-1', nrows=1000)
print(f"Sample dataset: {len(df)} rows")

# Check Date column format
print("\n=== DATE COLUMN ANALYSIS ===")
print("Sample Date values:")
print(df['Date'].head(10).tolist())
print(f"Unique Date values: {df['Date'].unique()}")

# Check Session column for proffered
print("\n=== SESSION COLUMN ANALYSIS ===")
proffered_sessions = df[df['Session'].astype(str).str.contains('proffered', case=False, na=False)]
print(f"Sessions containing 'proffered': {len(proffered_sessions)}")

exact_proffered = df[df['Session'].astype(str).str.contains('Proffered Paper', case=False, na=False)]
print(f"Sessions exactly 'Proffered Paper': {len(exact_proffered)}")

# Show sample session values
print("\nSample Session values:")
print(df['Session'].value_counts().head(10))

# Check comprehensive search
print("\n=== COMPREHENSIVE SEARCH COMPARISON ===")
search_mask = pd.Series([False] * len(df))
for col in ['Title', 'Speakers', 'Session', 'Theme']:
    if col in df.columns:
        col_mask = df[col].astype(str).str.contains('proffered', case=False, na=False)
        search_mask = search_mask | col_mask
        print(f"{col} contains 'proffered': {col_mask.sum()}")

print(f"Total 'proffered' matches across all columns: {search_mask.sum()}")