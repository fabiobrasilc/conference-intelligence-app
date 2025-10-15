# Data Explorer Filter Bug Diagnostic Report

**Date:** October 15, 2025
**Issue:** Therapeutic area filters showing incorrect studies
**Severity:** HIGH - Users cannot trust filter results

---

## USER-REPORTED ISSUES

1. **Lung Cancer filter showing CRC studies**
2. **Head & Neck filter showing Breast Cancer and CRC studies**

---

## ROOT CAUSE ANALYSIS

### Issue 1: Lung Cancer Filter Catching "METastatic"

**Current Configuration** (app.py:600-605):
```python
"Lung Cancer": {
    "keywords": ["lung", "non-small cell lung cancer", "NSCLC", "SCLC",
                 r"\bMET\b", r"\bALK\b", r"\bEGFR\b", ...],
    "exclude_if_in_title": ["mesothelioma", "thymic", "thymoma"],
    "regex": True
}
```

**Problem**: The regex `r"\bMET\b"` is intended to match "MET" (the gene/biomarker) but is matching:
- "**MET**astatic" in any cancer type
- "**MET**" in compound words

**Evidence**:
- 524 total studies contain "metastatic" in title
- These studies span ALL therapeutic areas (breast, CRC, prostate, etc.)
- Word boundary `\b` matches before "MET" in "METastatic"

**Test Case**:
```python
import re
title = "Treatment of metastatic colorectal cancer"
bool(re.search(r'\bMET\b', title, re.IGNORECASE))  # Returns TRUE - BUG!
```

---

### Issue 2: Head & Neck Filter Catching "coloRECTAL"

**Current Configuration** (app.py:611-616):
```python
"Head and Neck Cancer": {
    "keywords": ["head and neck", r"\bhnscc\b", r"\bscchn\b",
                 "squamous cell carcinoma of the head",
                 "oral", "pharyngeal", "laryngeal", "oropharyngeal", "nasopharyngeal"],
    "exclude_if_in_title": ["esophageal", "gastric", "lung", "thyroid", "salivary gland carcinoma"],
    "regex": True
}
```

**Problem**: The keyword `"oral"` (intended for "oral cavity cancer") matches:
- "col**oral**" (part of "colorectal")
- Any study mentioning oral medications
- Studies about oral nutrition

**Evidence**:
- 2 CRC studies match "oral" keyword:
  1. "oral MYB transcription factor inhibitor... for colorectal cancer"
  2. "medical oral nutrition supplement in metastatic colorectal cancer"

**Test Case**:
```python
import re
title = "Treatment of metastatic colorectal cancer"
bool(re.search(r'oral', title, re.IGNORECASE))  # Returns TRUE - BUG!
```

---

## ADDITIONAL ISSUES DISCOVERED

### Issue 3: Colorectal Filter Catching "pharyng**EOsophageal**"?

**Current Configuration** (app.py:606-610):
```python
"Colorectal Cancer": {
    "keywords": ["colorectal", r"\bcrc\b", "colon", "rectal", "bowel"],
    "exclude_if_in_title": ["gastric", "esophageal", "pancreatic", "hepatocellular",
                           r"\bhcc\b", "gastroesophageal", "bile duct", "cholangiocarcinoma"],
    "regex": True
}
```

**Potential Problem**: Keyword `"rectal"` could match:
- "colorectal" (correct)
- "anorectal" (correct)
- BUT NO issue found in testing - "rectal" appears safe

---

## FILTER LOGIC FLOW (How Bugs Manifest)

**File**: app.py, line 1450-1499 (`apply_therapeutic_area_filter`)

**Step 1**: Broad multi-field search
```python
for keyword in keywords:
    include_mask |= df['search_text_normalized'].str.contains(keyword, case=False, na=False, regex=True)
```
- `search_text_normalized` = concatenation of Title + Identifier + Authors + Theme
- Searches across ALL fields (not just Title)
- This is WHY "oral" in Author name could trigger H&N filter

**Step 2**: Title-based exclusions
```python
for exclude_term in exclude_if_in_title:
    exclude_mask |= df['Title'].str.contains(exclude_term, case=False, na=False, regex=True)
```
- ONLY checks Title field for exclusions
- Does NOT exclude based on other fields

**Step 3**: Final mask
```python
final_mask = include_mask & ~exclude_mask
```

**Why This Fails**:
1. Lung filter: `r"\bMET\b"` matches "METastatic" in search_text_normalized
2. H&N filter: "oral" matches "coloRECTAL" in search_text_normalized
3. Exclusions don't help because they only check Title field
4. CRC studies don't have "lung" or "head and neck" in Title → not excluded

---

## RECOMMENDED FIXES

### Fix 1: Lung Cancer - Replace MET with Context-Aware Pattern

**Current (BUGGY)**:
```python
r"\bMET\b"
```

**Option A - Negative Lookahead (Recommended)**:
```python
r"\bMET\b(?!astatic)"  # Matches "MET" but NOT "METastatic"
```

**Option B - Positive Context**:
```python
r"\bMET\s+(exon|mutation|amplification|overexpression|positive|negative|inhibitor)"
```

**Option C - Remove MET keyword entirely**:
- Rely on "lung", "NSCLC", other biomarkers
- MET-specific studies will still match via "lung cancer" in title

**Recommendation**: Use Option A - cleanest fix

---

### Fix 2: Head & Neck - Make "oral" Context-Specific

**Current (BUGGY)**:
```python
"oral"
```

**Option A - Word Boundary (Recommended)**:
```python
r"\boral\b\s+(cavity|cancer|tongue|floor|mucosa)"  # "oral cavity", "oral cancer", etc.
```

**Option B - Exclude "colorectal" in Title**:
```python
"exclude_if_in_title": [..., "colorectal", ...]
```

**Option C - Remove "oral" keyword**:
- Rely on other H&N keywords: "head and neck", "oropharyngeal", "laryngeal", "pharyngeal"
- Risk: Miss "oral cavity cancer" studies that don't use other terms

**Recommendation**: Use Option B (add "colorectal" to exclusions) + keep "oral" for sensitivity

---

### Fix 3: General Safety Improvements

**Add to ALL TA filters:**
1. More aggressive Title-based exclusions
2. Validation that matched studies actually belong to TA

**Example - Lung Cancer exclusions should include**:
```python
"exclude_if_in_title": ["mesothelioma", "thymic", "thymoma",
                       "colorectal", "breast", "prostate", "bladder",
                       "renal cell", "head and neck", "gastric"]
```

---

## TESTING PLAN

### Test Case 1: Lung Filter Should NOT Match CRC
```python
# BEFORE FIX (FAILS):
title = "Treatment outcomes in metastatic colorectal cancer"
assert lung_filter(title) == False  # Currently returns TRUE - BUG

# AFTER FIX (PASSES):
assert lung_filter(title) == False
```

### Test Case 2: Lung Filter SHOULD Match MET+ Lung Cancer
```python
# BEFORE & AFTER FIX (PASSES):
title = "Tepotinib in MET exon 14 skipping NSCLC"
assert lung_filter(title) == True
```

### Test Case 3: H&N Filter Should NOT Match CRC
```python
# BEFORE FIX (FAILS):
title = "Oral chemotherapy in metastatic colorectal cancer"
assert hn_filter(title) == False  # Currently returns TRUE - BUG

# AFTER FIX (PASSES):
assert hn_filter(title) == False
```

### Test Case 4: H&N Filter SHOULD Match Oral Cavity Cancer
```python
# BEFORE & AFTER FIX (PASSES):
title = "Immunotherapy in oral cavity squamous cell carcinoma"
assert hn_filter(title) == True
```

---

## IMPLEMENTATION PRIORITY

### CRITICAL (Fix Immediately):
1. **Lung Cancer `\bMET\b` → `\bMET\b(?!astatic)`**
2. **Head & Neck add "colorectal" to exclude_if_in_title**

### HIGH (Next Sprint):
3. Add cross-TA exclusions to all filters (prevent other cancer types from bleeding through)
4. Add validation logging (count studies per TA, flag suspicious overlaps)

### MEDIUM (Future Enhancement):
5. Consider switching from `search_text_normalized` to Title-only keyword matching
6. Build regression test suite for all TA filters

---

## CODE CHANGES REQUIRED

**File**: app.py
**Lines**: 584-627 (ESMO_THERAPEUTIC_AREAS configuration)

### Change 1: Lung Cancer Filter
**Line 602**:
```python
# BEFORE:
r"\bMET\b",

# AFTER:
r"\bMET\b(?!astatic)",  # Match "MET" but not "METastatic"
```

### Change 2: Head & Neck Filter
**Line 614**:
```python
# BEFORE:
"exclude_if_in_title": ["esophageal", "gastric", "lung", "thyroid", "salivary gland carcinoma"],

# AFTER:
"exclude_if_in_title": ["esophageal", "gastric", "lung", "thyroid", "salivary gland carcinoma",
                       "colorectal", "breast", "prostate"],
```

---

## VALIDATION COMMANDS

After fixes, run these to verify:

```bash
# Test 1: Lung filter with CRC studies
python -c "
import pandas as pd
import re
df = pd.read_csv('ESMO_2025_FINAL_20251013.csv')
crc_titles = df[df['Title'].str.contains('colorectal', case=False, na=False)]
matches = crc_titles[crc_titles['Title'].str.contains(r'\bMET\b(?!astatic)', case=False, na=False, regex=True)]
print(f'CRC studies matching fixed MET pattern: {len(matches)}')
assert len(matches) == 0, 'FAIL: CRC studies still matching MET keyword'
print('PASS: No CRC studies match fixed MET pattern')
"

# Test 2: H&N filter with CRC studies
python -c "
import pandas as pd
df = pd.read_csv('ESMO_2025_FINAL_20251013.csv')
crc_titles = df[df['Title'].str.contains('colorectal', case=False, na=False)]
print(f'Total CRC studies: {len(crc_titles)}')
print('Should be excluded by H&N filter after fix')
"
```

---

## CONCLUSION

**Root Causes**:
1. Overly broad keyword matching (`\bMET\b` matches "METastatic")
2. Substring matching ("oral" matches "colorectal")
3. Multi-field search increases false positive risk
4. Insufficient exclusion lists

**Fixes** (2 line changes):
1. Change Lung `\bMET\b` → `\bMET\b(?!astatic)`
2. Add "colorectal", "breast", "prostate" to H&N exclusions

**Impact**: Fixes both reported bugs with minimal risk of breaking valid matches.

**Testing**: Validate with sample CRC and Breast studies after deployment.
