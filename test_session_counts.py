#!/usr/bin/env python3
"""
Check actual session counts in ESMO dataset
"""
import pandas as pd

# Load the dataset
print("Loading ESMO 2025 dataset...")
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv', encoding='latin-1')
print(f"Dataset loaded: {len(df)} total rows")

# Check Session column values
print(f"\n=== SESSION COLUMN ANALYSIS ===")
print(f"Column name: 'Session'")
print(f"Unique session values and counts:")

session_counts = df['Session'].value_counts()
print(session_counts)

# Check specifically for "Proffered Paper"
print(f"\n=== PROFFERED PAPER ANALYSIS ===")
proffered_exact = df[df['Session'] == 'Proffered Paper']
print(f"Exact match 'Proffered Paper': {len(proffered_exact)}")

proffered_contains = df[df['Session'].str.contains('Proffered', case=False, na=False)]
print(f"Contains 'Proffered': {len(proffered_contains)}")

# Show sample proffered entries
print(f"\nSample 'Proffered' entries:")
for session_type in session_counts.index:
    if 'proffered' in session_type.lower():
        print(f"  '{session_type}': {session_counts[session_type]} entries")

# Check if there are multiple session-like columns
print(f"\n=== ALL COLUMNS ===")
print(f"All columns: {list(df.columns)}")

# Check Theme column too (in case session info is there)
if 'Theme' in df.columns:
    print(f"\n=== THEME COLUMN ANALYSIS ===")
    theme_counts = df['Theme'].value_counts()
    print("Top 10 Theme values:")
    for theme, count in theme_counts.head(10).items():
        print(f"  '{theme}': {count}")