"""
Inspect Enrichment Cache - View enriched data statistics
Run this script to see what's in your enrichment cache
"""

import pandas as pd
import os
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Look for enriched cache files
cache_dir = Path("./data")
cache_files = list(cache_dir.glob("enriched_*.parquet"))

if not cache_files:
    print("❌ No enrichment cache found in ./data/")
    print("Set CACHE_DIR to the correct path or run this on Railway")
    exit(1)

# Load the most recent cache
cache_file = sorted(cache_files, key=os.path.getmtime)[-1]
print(f"📂 Loading cache: {cache_file.name}")
print("=" * 80)

df = pd.read_parquet(cache_file)

print(f"\n✅ Total studies in cache: {len(df)}")
print("=" * 80)

# Check enrichment quality
print("\n📊 Enrichment Statistics:")
print("-" * 80)

# Count "Unknown" values (failed enrichment)
unknown_therapy = (df['line_of_therapy'] == 'Unknown').sum()
unknown_phase = (df['phase'] == 'Unknown').sum()
empty_biomarkers = df['biomarkers'].apply(lambda x: len(x) == 0 if isinstance(x, list) else True).sum()

print(f"  Line of Therapy = 'Unknown': {unknown_therapy} studies ({unknown_therapy*100/len(df):.1f}%)")
print(f"  Phase = 'Unknown': {unknown_phase} studies ({unknown_phase*100/len(df):.1f}%)")
print(f"  Empty Biomarkers: {empty_biomarkers} studies ({empty_biomarkers*100/len(df):.1f}%)")

# Successful enrichment
successful = len(df) - unknown_therapy
print(f"\n  ✅ Successfully enriched: {successful} studies ({successful*100/len(df):.1f}%)")
print(f"  ❌ Failed enrichment: {unknown_therapy} studies ({unknown_therapy*100/len(df):.1f}%)")

# Show sample of failed studies
print("\n" + "=" * 80)
print("🔍 Sample of Failed Enrichment Studies:")
print("-" * 80)

failed_df = df[df['line_of_therapy'] == 'Unknown']
if len(failed_df) > 0:
    print(f"\nShowing first 10 of {len(failed_df)} failed studies:\n")
    for idx, row in failed_df.head(10).iterrows():
        print(f"  [{row.get('Identifier', 'N/A')}] {row.get('Title', 'N/A')[:80]}...")
else:
    print("  🎉 No failed studies found - 100% enrichment success!")

# Show sample of successful studies
print("\n" + "=" * 80)
print("✨ Sample of Successful Enrichment:")
print("-" * 80)

successful_df = df[df['line_of_therapy'] != 'Unknown']
if len(successful_df) > 0:
    sample = successful_df.head(5)
    for idx, row in sample.iterrows():
        print(f"\n  [{row.get('Identifier', 'N/A')}] {row.get('Title', 'N/A')[:60]}...")
        print(f"    Line of Therapy: {row.get('line_of_therapy', 'N/A')}")
        print(f"    Phase: {row.get('phase', 'N/A')}")
        print(f"    Biomarkers: {', '.join(row.get('biomarkers', [])) if row.get('biomarkers') else 'None'}")
        print(f"    Emerging: {row.get('is_emerging', False)}")

print("\n" + "=" * 80)
print("📈 Column Summary:")
print("-" * 80)
print(df.info())

print("\n" + "=" * 80)
print("✅ Inspection complete!")
