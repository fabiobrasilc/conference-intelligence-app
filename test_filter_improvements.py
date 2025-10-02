#!/usr/bin/env python3
"""
Test TA filter improvements - verify acronyms use word boundaries
and biomarkers don't cause false positives
"""

import pandas as pd
import os
import re

os.chdir(r'c:\Users\m337928\OneDrive - MerckGroup\Documents\Python Projects\conference_intelligence_app')
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv')

print('=== TESTING FILTER IMPROVEMENTS ===\n')

# Test 1: Colorectal filter should NOT catch endometrial cancer
print('Test 1: Colorectal filter excludes endometrial cancer')
print('-' * 60)
endometrial = df[df['Title'].str.contains('dMMR/MSI-H Endometrial Cancer', case=False, na=False)]

if not endometrial.empty:
    # Apply new colorectal filter logic
    keywords = ["colorectal", "colon", "rectal", "gastrointestinal", "bowel"]
    acronyms = ["CRC", "GI"]
    mask = pd.Series([False] * len(df), index=df.index)

    for keyword in keywords:
        title_match = df["Title"].str.contains(keyword, case=False, na=False, regex=False)
        theme_match = df["Theme"].str.contains(keyword, case=False, na=False, regex=False)
        mask = mask | title_match | theme_match

    for acronym in acronyms:
        pattern = r'\b' + re.escape(acronym) + r'\b'
        case_sensitive = (acronym == "GI")
        title_match = df["Title"].str.contains(pattern, case=(not case_sensitive), na=False, regex=True)
        theme_match = df["Theme"].str.contains(pattern, case=(not case_sensitive), na=False, regex=True)
        mask = mask | title_match | theme_match

    crc_studies = df[mask]
    endometrial_in_crc = endometrial.index[0] in crc_studies.index

    if endometrial_in_crc:
        print('FAIL: Endometrial study still caught by colorectal filter')
    else:
        print('PASS: Endometrial study correctly excluded')
else:
    print('WARNING: Test study not found in dataset')

# Test 2: GI acronym should be case-sensitive
print('\nTest 2: GI acronym uses word boundaries (case-sensitive)')
print('-' * 60)
gi_pattern = r'\bGI\b'
gi_matches = df['Title'].str.contains(gi_pattern, case=True, na=False, regex=True) | \
             df['Theme'].str.contains(gi_pattern, case=True, na=False, regex=True)
gi_count = gi_matches.sum()

# Check for false positives
sample_titles = df[gi_matches]['Title'].head(3).tolist()
has_giant = any('giant' in title.lower() for title in sample_titles)
has_aging = any('aging' in title.lower() for title in sample_titles)

print(f'GI matches: {gi_count} studies')
if has_giant or has_aging:
    print('FAIL: Found false positives (giant/aging)')
else:
    print('PASS: No false positives in sample')

# Test 3: Compare old vs new colorectal counts
print('\nTest 3: Colorectal filter count comparison')
print('-' * 60)

# Old filter (with biomarkers)
old_keywords = ["colorectal", "CRC", "colon", "rectal", "GI", "gastrointestinal", "bowel", "KRAS", "MSI", "microsatellite"]
old_mask = pd.Series([False] * len(df), index=df.index)
for keyword in old_keywords:
    old_mask = old_mask | df["Title"].str.contains(keyword, case=False, na=False, regex=False) | \
                          df["Theme"].str.contains(keyword, case=False, na=False, regex=False)

# New filter (without biomarkers, with word boundaries)
keywords = ["colorectal", "colon", "rectal", "gastrointestinal", "bowel"]
acronyms = ["CRC", "GI"]
new_mask = pd.Series([False] * len(df), index=df.index)

for keyword in keywords:
    new_mask = new_mask | df["Title"].str.contains(keyword, case=False, na=False, regex=False) | \
                          df["Theme"].str.contains(keyword, case=False, na=False, regex=False)

for acronym in acronyms:
    pattern = r'\b' + re.escape(acronym) + r'\b'
    case_sensitive = (acronym == "GI")
    new_mask = new_mask | df["Title"].str.contains(pattern, case=(not case_sensitive), na=False, regex=True) | \
                          df["Theme"].str.contains(pattern, case=(not case_sensitive), na=False, regex=True)

print(f'Old colorectal filter (with biomarkers): {old_mask.sum()} studies')
print(f'New colorectal filter (specific only): {new_mask.sum()} studies')
print(f'Reduction: {old_mask.sum() - new_mask.sum()} studies (removed false positives)')

# Test 4: Lung filter acronyms
print('\nTest 4: Lung cancer acronym specificity')
print('-' * 60)
lung_acronyms = ["NSCLC", "MET", "ALK", "EGFR", "KRAS"]
for acronym in lung_acronyms:
    pattern = r'\b' + re.escape(acronym) + r'\b'
    matches = df["Title"].str.contains(pattern, case=False, na=False, regex=True) | \
              df["Theme"].str.contains(pattern, case=False, na=False, regex=True)
    print(f'  {acronym}: {matches.sum()} studies (word boundary enforced)')

print('\n=== ALL TESTS COMPLETE ===')
