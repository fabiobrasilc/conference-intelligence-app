#!/usr/bin/env python3
"""Test improved colorectal filter - should exclude other GI cancers"""

import pandas as pd
import os
import sys
sys.path.insert(0, r'c:\Users\m337928\OneDrive - MerckGroup\Documents\Python Projects\conference_intelligence_app')

os.chdir(r'c:\Users\m337928\OneDrive - MerckGroup\Documents\Python Projects\conference_intelligence_app')

# Import the updated filter function
from app import apply_colorectal_cancer_filter

df = pd.read_csv('ESMO_2025_FINAL_20250929.csv')

print('=== TESTING IMPROVED COLORECTAL FILTER ===\n')

# Apply new filter
mask = apply_colorectal_cancer_filter(df)
crc_studies = df[mask]

print(f'Total results: {len(crc_studies)} studies\n')

# Check for non-CRC GI cancers
print('Checking for non-CRC GI tumor contamination:')
print('=' * 80)

other_gi_keywords = {
    'gastric': 'Gastric cancer',
    'esophageal': 'Esophageal cancer',
    'pancreatic': 'Pancreatic cancer',
    'hepatocellular': 'Hepatocellular carcinoma',
    'HCC': 'HCC (hepatocellular)',
    'liver cancer': 'Liver cancer',
    'biliary': 'Biliary tract cancer',
    'cholangiocarcinoma': 'Cholangiocarcinoma',
    'gastroesophageal': 'Gastroesophageal junction',
    'GEJ': 'GEJ cancer'
}

total_contamination = 0
for kw, description in other_gi_keywords.items():
    if kw.isupper():  # Acronym
        import re
        pattern = r'\b' + re.escape(kw) + r'\b'
        matches = crc_studies['Title'].str.contains(pattern, case=False, na=False, regex=True) | \
                  crc_studies['Theme'].str.contains(pattern, case=False, na=False, regex=True)
    else:
        matches = crc_studies['Title'].str.contains(kw, case=False, na=False, regex=False) | \
                  crc_studies['Theme'].str.contains(kw, case=False, na=False, regex=False)

    count = matches.sum()
    total_contamination += count

    if count > 0:
        print(f'{description}: {count} studies')
        # Check if these have CRC in title (legitimate)
        matches_df = crc_studies[matches]
        has_crc_in_title = matches_df['Title'].str.contains('colorectal|colon|rectal|CRC', case=False, na=False, regex=True)
        legitimate = has_crc_in_title.sum()
        false_positive = count - legitimate

        if false_positive > 0:
            print(f'  - Legitimate (CRC in title): {legitimate}')
            print(f'  - FALSE POSITIVES: {false_positive}')
            # Show example
            fp_example = matches_df[~has_crc_in_title].iloc[0] if false_positive > 0 else None
            if fp_example is not None:
                print(f'    Example FP: {fp_example["Title"][:65]}...')
        else:
            print(f'  - All legitimate (have CRC terms in title)')

if total_contamination == 0:
    print('PASS: No other GI cancer contamination!')

print('\n' + '=' * 80)
print('Theme breakdown (top 10):')
print('=' * 80)
theme_counts = crc_studies['Theme'].value_counts().head(10)
for theme, count in theme_counts.items():
    print(f'{count:4d} - {theme}')

print('\n' + '=' * 80)
print('Sample colorectal studies:')
print('=' * 80)
for idx, row in crc_studies.head(5).iterrows():
    print(f'\n- {row["Title"][:75]}...')
    print(f'  Theme: {row["Theme"]}')

print('\n=== TEST COMPLETE ===')
