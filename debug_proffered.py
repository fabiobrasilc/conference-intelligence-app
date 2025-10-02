#!/usr/bin/env python3
"""
Debug script to analyze "proffered" search vs filter discrepancies
"""
import pandas as pd

# Load the data
print("Loading ESMO 2025 data...")
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv', encoding='latin-1')
print(f"Total dataset: {len(df)} rows")
print(f"Columns: {list(df.columns)}")

# Check Session column values for "proffered"
print("\n=== SESSION COLUMN ANALYSIS ===")
session_with_proffered = df[df['Session'].astype(str).str.contains('proffered', case=False, na=False, regex=False)]
print(f"Session column contains 'proffered': {len(session_with_proffered)} matches")

# Check unique Session values that contain "proffered"
proffered_sessions = df['Session'].astype(str).str.lower().unique()
proffered_sessions = [s for s in proffered_sessions if 'proffered' in s]
print(f"Unique Session values with 'proffered': {proffered_sessions}")

# Test comprehensive search across ALL columns
print("\n=== COMPREHENSIVE SEARCH TEST ===")
search_columns = ['Title', 'Speakers', 'Speaker Location', 'Affiliation', 'Room', 'Session', 'Theme', 'Identifier']

total_matches = pd.Series([False] * len(df))
for col in search_columns:
    if col in df.columns:
        col_mask = df[col].astype(str).str.contains('proffered', case=False, na=False, regex=False)
        total_matches = total_matches | col_mask
        print(f"{col}: {col_mask.sum()} matches")

print(f"Total comprehensive search matches: {total_matches.sum()}")

# Show a few examples of what we found
print("\n=== SAMPLE MATCHES ===")
sample_matches = df[total_matches].head(10)
for idx, row in sample_matches.iterrows():
    print(f"Row {idx}: {row['Title'][:100]}... | Session: {row['Session']}")

# Check for exact "Proffered Paper" matches
print("\n=== EXACT 'PROFFERED PAPER' MATCHES ===")
exact_matches = df[df['Session'].astype(str).str.contains('Proffered Paper', case=False, na=False, regex=False)]
print(f"Exact 'Proffered Paper' matches: {len(exact_matches)}")

# Show all unique Session values to see what we're working with
print("\n=== ALL UNIQUE SESSION VALUES ===")
unique_sessions = df['Session'].value_counts()
print(f"Total unique session types: {len(unique_sessions)}")
print("Top 15 session types:")
print(unique_sessions.head(15))