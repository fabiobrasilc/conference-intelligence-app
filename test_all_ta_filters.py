#!/usr/bin/env python3
"""Test all TA filters to see which ones are working"""

import pandas as pd
import os
import re

os.chdir(r'c:\Users\m337928\OneDrive - MerckGroup\Documents\Python Projects\conference_intelligence_app')
df = pd.read_csv('ESMO_2025_FINAL_20250929.csv')

# Test each TA filter
ta_filters = {
    'Bladder Cancer': ['bladder', 'urothelial', 'uroepithelial', 'transitional cell', 'GU', 'genitourinary'],
    'Renal Cancer': ['renal', 'renal cell', 'RCC'],
    'Lung Cancer': ['NSCLC', 'non-small cell lung cancer', 'non-small-cell lung cancer', 'MET', 'ALK', 'EGFR', 'KRAS'],
    'Colorectal Cancer': ['colorectal', 'CRC', 'colon', 'rectal', 'GI', 'gastrointestinal', 'bowel', 'KRAS', 'MSI', 'microsatellite'],
    'Head and Neck Cancer': ['head and neck', 'head & neck', 'H&N', 'HNSCC', 'SCCHN', 'squamous cell carcinoma of the head', 'oral', 'pharyngeal', 'laryngeal'],
    'TGCT': ['TGCT', 'PVNS', 'tenosynovial giant cell tumor', 'pigmented villonodular synovitis']
}

print(f'Total dataset: {len(df)} studies\n')
print('Testing TA Filters:')
print('=' * 60)

for ta_name, keywords in ta_filters.items():
    mask = pd.Series([False] * len(df), index=df.index)

    keyword_results = {}
    for keyword in keywords:
        if keyword == 'GU':
            pattern = r'\bGU\b'
            title_matches = df['Title'].str.contains(pattern, case=True, na=False, regex=True)
            theme_matches = df['Theme'].str.contains(pattern, case=True, na=False, regex=True)
        elif len(keyword.split()) > 1:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            title_matches = df['Title'].str.contains(pattern, case=False, na=False, regex=True)
            theme_matches = df['Theme'].str.contains(pattern, case=False, na=False, regex=True)
        else:
            title_matches = df['Title'].str.contains(keyword, case=False, na=False, regex=False)
            theme_matches = df['Theme'].str.contains(keyword, case=False, na=False, regex=False)

        keyword_mask = title_matches | theme_matches
        keyword_results[keyword] = keyword_mask.sum()
        mask = mask | keyword_mask

    count = mask.sum()
    status = 'OK' if count > 0 and count < 4686 else 'ERROR'
    print(f'\n{ta_name}: {count} results [{status}]')

    if count == 4686:
        print('  ERROR: Returning ALL results (filter not working)')
        print('  Keyword breakdown:')
        for kw, kw_count in keyword_results.items():
            print(f'    - "{kw}": {kw_count} matches')
    elif count == 0:
        print('  ERROR: No results found')
    elif count < 20:
        print('  WARNING: Very few results, may need more keywords')

print('\n' + '=' * 60)
