#!/usr/bin/env python3
"""
Debug date formats in ESMO dataset
"""
import pandas as pd

print("Loading ESMO 2025 dataset...")
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv', encoding='latin-1')
print(f"Total rows: {len(df)}")

print("\n=== Date Column Analysis ===")
print(f"Date column type: {df['Date'].dtype}")
print(f"Non-null dates: {df['Date'].notna().sum()}")

print("\n=== Unique Date Values (first 20) ===")
unique_dates = df['Date'].dropna().unique()
print(f"Total unique dates: {len(unique_dates)}")
for i, date in enumerate(unique_dates[:20]):
    count = (df['Date'] == date).sum()
    print(f"{i+1:2d}. '{date}' - {count} sessions")

print("\n=== Date Format Samples ===")
sample_dates = df['Date'].dropna().head(10)
for i, date in enumerate(sample_dates):
    print(f"Row {i+1}: '{date}'")

# Check for 2024 vs 2025
dates_2024 = df['Date'].astype(str).str.contains('2024', na=False).sum()
dates_2025 = df['Date'].astype(str).str.contains('2025', na=False).sum()
print(f"\nDates containing '2024': {dates_2024}")
print(f"Dates containing '2025': {dates_2025}")

print("\n=== Current Filter Configuration Issue ===")
filter_dates = ["10/17/2025", "10/18/2025", "10/19/2025", "10/20/2025", "10/21/2025"]
for filter_date in filter_dates:
    matches = df['Date'].astype(str).str.contains(filter_date, case=False, na=False).sum()
    print(f"Filter '{filter_date}' matches: {matches}")