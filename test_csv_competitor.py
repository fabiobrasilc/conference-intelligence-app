import pandas as pd

df_test = pd.DataFrame({
    'Title': [
        'Enfortumab vedotin in bladder cancer patients',
        'Pembrolizumab plus enfortumab vedotin combination in urothelial cancer',
        'Avelumab maintenance therapy for metastatic urothelial carcinoma',
        'Tepotinib in NSCLC with MET exon 14 skipping mutations'
    ],
    'Identifier': ['#101', '#102', '#103', '#104']
})

drug_db = pd.read_csv('Drug_Company_names.csv', encoding='utf-8-sig')

indication_keywords = ['bladder', 'urothelial', 'uroepithelial']
focus_moa_classes = ['ICI', 'ADC', 'Targeted Therapy', 'Bispecific Antibody']
emd_drugs = ['avelumab', 'bavencio', 'tepotinib', 'cetuximab', 'erbitux', 'pimicotinib']

results = []
for _, drug_row in drug_db.iterrows():
    generic = str(drug_row['drug_generic']).strip() if pd.notna(drug_row['drug_generic']) else ''
    if not generic:
        continue

    if generic.lower() in emd_drugs:
        continue

    moa_class = str(drug_row['moa_class']).strip() if pd.notna(drug_row['moa_class']) else ''
    if focus_moa_classes and moa_class and moa_class not in focus_moa_classes:
        continue

    company = str(drug_row['company']).strip() if pd.notna(drug_row['company']) else ''

    # Search for drug
    mask = pd.Series([False] * len(df_test), index=df_test.index)
    mask = mask | df_test['Title'].str.contains(generic, case=False, na=False, regex=False)

    # Also try base name
    base_generic = generic.split('-')[0].strip() if '-' in generic else generic
    if base_generic != generic and len(base_generic.split()) > 1:
        mask = mask | df_test['Title'].str.contains(base_generic, case=False, na=False, regex=False)

    # Filter by indication
    if mask.any():
        indication_mask = pd.Series([False] * len(df_test), index=df_test.index)
        for keyword in indication_keywords:
            indication_mask = indication_mask | df_test['Title'].str.contains(keyword, case=False, na=False, regex=False)
        mask = mask & indication_mask

    matching = df_test[mask]
    if len(matching) > 0:
        results.append({'Drug': generic, 'Company': company, 'MOA Class': moa_class, '# Studies': len(matching)})

print(f'Found {len(results)} competitors:')
for r in results:
    print(f"  {r['Drug']} ({r['Company']}) - MOA: {r['MOA Class']} - {r['# Studies']} studies")
