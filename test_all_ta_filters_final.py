#!/usr/bin/env python3
"""
Comprehensive test of all TA filters - verify counts and show sample results
"""

import pandas as pd
import os
import sys
sys.path.insert(0, r'c:\Users\m337928\OneDrive - MerckGroup\Documents\Python Projects\conference_intelligence_app')

os.chdir(r'c:\Users\m337928\OneDrive - MerckGroup\Documents\Python Projects\conference_intelligence_app')

# Import the actual filter functions from app.py
from app import (
    apply_bladder_cancer_filter,
    apply_renal_cancer_filter,
    apply_lung_cancer_filter,
    apply_colorectal_cancer_filter,
    apply_head_neck_cancer_filter,
    apply_tgct_filter
)

df = pd.read_csv('ESMO_2025_FINAL_20250929.csv')

print('=' * 80)
print('COMPREHENSIVE TA FILTER TESTING - ESMO 2025')
print('=' * 80)
print(f'Total dataset: {len(df)} studies\n')

# Test each filter
filters = [
    ("Bladder Cancer", apply_bladder_cancer_filter),
    ("Renal Cancer", apply_renal_cancer_filter),
    ("Lung Cancer", apply_lung_cancer_filter),
    ("Colorectal Cancer", apply_colorectal_cancer_filter),
    ("Head and Neck Cancer", apply_head_neck_cancer_filter),
    ("TGCT", apply_tgct_filter)
]

for filter_name, filter_func in filters:
    print(f'\n{filter_name}')
    print('-' * 80)

    mask = filter_func(df)
    filtered = df[mask]
    count = len(filtered)

    print(f'Results: {count} studies')

    # Show sample titles
    if count > 0:
        print(f'\nSample titles (first 3):')
        for idx, row in filtered.head(3).iterrows():
            title = row['Title'][:75] + '...' if len(row['Title']) > 75 else row['Title']
            print(f'  - {title}')
            print(f'    Theme: {row["Theme"]}')

    # Quality check - look for obvious mismatches
    if count > 0:
        themes = filtered['Theme'].value_counts().head(5)
        print(f'\nTop 5 themes:')
        for theme, theme_count in themes.items():
            print(f'  - {theme}: {theme_count} studies')

    if count == 0:
        print('  WARNING: No results found - filter may be too restrictive')
    elif count > 1000 and filter_name not in ["Lung Cancer", "Colorectal Cancer"]:
        print('  WARNING: Very high count - filter may be too broad')

print('\n' + '=' * 80)
print('TESTING COMPLETE')
print('=' * 80)
