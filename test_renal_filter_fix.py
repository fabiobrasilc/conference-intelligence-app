#!/usr/bin/env python3
"""Test renal filter fix - should exclude bladder-only studies from mixed themes"""

import pandas as pd
import os
import sys
import re

os.chdir(r'c:\Users\m337928\OneDrive - MerckGroup\Documents\Python Projects\conference_intelligence_app')
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv')

print('=== TESTING RENAL FILTER FIX ===\n')

# Apply NEW renal filter logic
keywords = ["renal", "renal cell"]
acronyms = ["RCC"]
bladder_keywords = ["bladder", "urothelial", "uroepithelial"]

# Build title-only match mask
title_has_renal = pd.Series([False] * len(df), index=df.index)
for keyword in keywords:
    title_has_renal = title_has_renal | df["Title"].str.contains(keyword, case=False, na=False, regex=False)
for acronym in acronyms:
    pattern = r'\b' + re.escape(acronym) + r'\b'
    title_has_renal = title_has_renal | df["Title"].str.contains(pattern, case=False, na=False, regex=True)

# Build theme-only match mask
theme_has_renal = pd.Series([False] * len(df), index=df.index)
for keyword in keywords:
    theme_has_renal = theme_has_renal | df["Theme"].str.contains(keyword, case=False, na=False, regex=False)
for acronym in acronyms:
    pattern = r'\b' + re.escape(acronym) + r'\b'
    theme_has_renal = theme_has_renal | df["Theme"].str.contains(pattern, case=False, na=False, regex=True)

# Check if theme contains bladder keywords
theme_has_bladder = pd.Series([False] * len(df), index=df.index)
for bladder_kw in bladder_keywords:
    theme_has_bladder = theme_has_bladder | df["Theme"].str.contains(bladder_kw, case=False, na=False, regex=False)

# Apply matching logic
new_mask = title_has_renal | (theme_has_renal & ~theme_has_bladder)
new_renal_studies = df[new_mask]

print(f'NEW renal filter results: {len(new_renal_studies)} studies')

# Check how many bladder studies are still in results
has_bladder = pd.Series([False] * len(new_renal_studies), index=new_renal_studies.index)
for kw in bladder_keywords:
    has_bladder = has_bladder | new_renal_studies['Title'].str.contains(kw, case=False, na=False)
    has_bladder = has_bladder | new_renal_studies['Theme'].str.contains(kw, case=False, na=False)

bladder_in_new_renal = new_renal_studies[has_bladder]

print(f'Bladder/urothelial studies in NEW results: {len(bladder_in_new_renal)} studies')
print()

# Show examples - these should ONLY be studies with renal in the title
if len(bladder_in_new_renal) > 0:
    print('Remaining bladder studies (should have renal in Title):')
    print('=' * 80)
    for idx, row in bladder_in_new_renal.head(5).iterrows():
        title = row['Title'][:70] + '...' if len(row['Title']) > 70 else row['Title']
        print(f'\nTitle: {title}')
        print(f'Theme: {row["Theme"]}')

        # Check if title has renal
        has_renal_in_title = any(kw in row['Title'].lower() for kw in ['renal', 'rcc'])
        print(f'  Has renal in Title: {"YES" if has_renal_in_title else "NO (ERROR!)"}')

# Show pure renal studies (no bladder mention)
pure_renal = new_renal_studies[~has_bladder]
print(f'\n\nPure renal studies (no bladder keywords): {len(pure_renal)} studies')
print('Sample titles:')
for idx, row in pure_renal.head(3).iterrows():
    print(f'  - {row["Title"][:70]}...')
    print(f'    Theme: {row["Theme"]}')

print('\n=== TEST COMPLETE ===')
