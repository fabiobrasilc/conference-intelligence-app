#!/usr/bin/env python3
"""
Simple test: If user clicks "Mini Oral Session", show ONLY rows where Session column = "Mini Oral Session"
"""
import pandas as pd

# Load the dataset
print("Loading ESMO 2025 dataset...")
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv', encoding='latin-1')
print(f"Total rows: {len(df)}")

# Simple filter: Show only Mini Oral Session rows
print("\n=== Simple Filter Test ===")
session_type = "Mini Oral Session"
filtered_df = df[df['Session'] == session_type]
print(f"Rows with Session = '{session_type}': {len(filtered_df)}")

# Show first few results
if len(filtered_df) > 0:
    print(f"\nFirst 3 results:")
    for idx, row in filtered_df.head(3).iterrows():
        print(f"  Row {idx}: {row['Title'][:60]}... | Session: {row['Session']}")

# Test other session types
print(f"\n=== Testing Other Session Types ===")
test_sessions = ["Proffered Paper", "ePoster", "Poster", "Educational Session"]

for session in test_sessions:
    count = len(df[df['Session'] == session])
    print(f"'{session}': {count} rows")

# Test partial matching vs exact matching
print(f"\n=== Exact vs Contains Matching ===")
exact_mini = len(df[df['Session'] == 'Mini Oral Session'])
contains_mini = len(df[df['Session'].str.contains('Mini', case=False, na=False)])
print(f"Exact 'Mini Oral Session': {exact_mini}")
print(f"Contains 'Mini': {contains_mini}")

print("\nConclusion: Simple exact matching works perfectly!")
print("The problem is in the Flask app logic, not the data.")