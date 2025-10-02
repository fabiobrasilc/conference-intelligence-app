#!/usr/bin/env python3
"""
Test why Veronika Muller appears in bladder cancer filter
"""
import pandas as pd
from pathlib import Path

# Load data
CSV_FILE = Path(__file__).parent / "ESMO_2025_FINAL_20250929.csv"
df = pd.read_csv(CSV_FILE, encoding="latin-1").fillna("")

# Search for Veronika Muller
author_name = "Veronika Muller"
matches = df[df['Speakers'].str.contains(author_name, case=False, na=False)]

print(f"Studies with '{author_name}':")
print(f"Total count: {len(matches)}")
print()

for idx, row in matches.iterrows():
    print(f"{idx+1}. [{row['Session']}] {row['Title']}")
    print(f"   Theme: {row['Theme']}")
    print(f"   Does Title contain 'bladder'? {('bladder' in row['Title'].lower())}")
    print(f"   Does Theme contain 'bladder'? {('bladder' in row['Theme'].lower())}")
    print(f"   Does Title contain 'GU'? {('GU' in row['Title'])}")
    print(f"   Does Theme contain 'GU'? {('GU' in row['Theme'])}")
    print()

# Now test the bladder filter logic
print("=" * 80)
print("TESTING BLADDER FILTER LOGIC")
print("=" * 80)

bladder_keywords = ["bladder", "urothelial", "uroepithelial", "transitional cell", "GU", "genitourinary"]
exclusions = ["prostate"]

# Apply bladder filter
bladder_mask = pd.Series([False] * len(df))
for keyword in bladder_keywords:
    title_mask = df["Title"].str.contains(keyword, case=False, na=False)
    theme_mask = df["Theme"].str.contains(keyword, case=False, na=False)
    keyword_mask = title_mask | theme_mask

    if keyword_mask.any():
        print(f"Keyword '{keyword}': {keyword_mask.sum()} matches")
        # Check if Veronika Muller matches this keyword
        muller_matches_keyword = matches[keyword_mask[matches.index]].any()
        if len(matches[keyword_mask[matches.index]]) > 0:
            print(f"  -> Veronika Muller matches '{keyword}'!")
            for _, row in matches[keyword_mask[matches.index]].iterrows():
                print(f"     Title: {row['Title'][:80]}")
                print(f"     Theme: {row['Theme']}")

    bladder_mask = bladder_mask | keyword_mask

# Exclude prostate
for exclusion in exclusions:
    prostate_mask = df["Title"].str.contains(exclusion, case=False, na=False) | df["Theme"].str.contains(exclusion, case=False, na=False)
    bladder_mask = bladder_mask & ~prostate_mask

filtered_df = df[bladder_mask]
print(f"\nTotal bladder cancer sessions: {len(filtered_df)}")

# Check if Veronika Muller is in the filtered results
muller_in_bladder = filtered_df[filtered_df['Speakers'].str.contains(author_name, case=False, na=False)]
print(f"Veronika Muller in bladder filter: {len(muller_in_bladder)} studies")