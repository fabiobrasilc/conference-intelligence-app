"""Test simplified Lung Cancer filter"""
import pandas as pd

df = pd.read_csv('ESMO_2025_FINAL_20251013.csv')

# Test simplified keywords
lung_keywords = ['NSCLC', 'non-small cell lung cancer', 'non-small-cell lung cancer']
pattern = '|'.join(lung_keywords)

mask = df['Title'].str.contains(pattern, case=False, na=False)

print(f"Total studies matching Lung keywords: {mask.sum()}")
print(f"\nSample titles (first 5):")
for title in df[mask]['Title'].head(5):
    print(f"  - {title}")

# Check if we're accidentally including SCLC
sclc_in_results = df[mask]['Title'].str.contains('small cell lung|SCLC', case=False, na=False, regex=True).sum()
print(f"\nStudies mentioning SCLC in results: {sclc_in_results}")

# Check themes
print(f"\nThemes of matched studies:")
theme_counts = df[mask]['Theme'].value_counts().head(10)
print(theme_counts)
