"""Test updated TA filter exclusions"""
import re
import sys

# Fix Windows encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Test 1: Lung Cancer - SCLC exclusion should not exclude NSCLC
print("="*60)
print("TEST 1: Lung Cancer SCLC Exclusion")
print("="*60)

test_titles = [
    "Small cell lung cancer treatment outcomes",
    "Non-small cell lung cancer with EGFR mutations",
    "Advanced SCLC in elderly patients",
    "NSCLC with METex14 skipping mutations",
    "Treatment of small-cell lung carcinoma"
]

exclude_pattern = r'(?<!non-)small.?cell.?lung|\bSCLC\b'

for title in test_titles:
    match = re.search(exclude_pattern, title, re.IGNORECASE)
    status = "EXCLUDED ❌" if match else "INCLUDED ✅"
    print(f"{status}: {title}")

print("\nExpected:")
print("  - Small cell lung cancer: EXCLUDED ✅")
print("  - Non-small cell lung cancer: INCLUDED ✅")
print("  - SCLC: EXCLUDED ✅")
print("  - NSCLC: INCLUDED ✅")

# Test 2: Head & Neck - Should exclude gynecological/sarcoma
print("\n" + "="*60)
print("TEST 2: Head & Neck Gynecological/Sarcoma Exclusion")
print("="*60)

hn_test_titles = [
    "Squamous cell carcinoma of the head and neck",
    "Oropharyngeal cancer treatment",
    "Cervical cancer HPV-positive",
    "Uterine sarcoma management",
    "Ovarian cancer outcomes",
    "Oral cavity squamous cell carcinoma",
    "Soft tissue sarcoma of the neck"
]

hn_exclude_pattern = r'cervical|uterine|ovarian|endometrial|sarcoma|melanoma|merkel'

for title in hn_test_titles:
    match = re.search(hn_exclude_pattern, title, re.IGNORECASE)
    status = "EXCLUDED ❌" if match else "INCLUDED ✅"
    print(f"{status}: {title}")

print("\nExpected:")
print("  - Head and neck SCC: INCLUDED ✅")
print("  - Oropharyngeal: INCLUDED ✅")
print("  - Cervical cancer: EXCLUDED ✅")
print("  - Uterine/Ovarian: EXCLUDED ✅")
print("  - Sarcoma: EXCLUDED ✅")
print("  - Oral cavity: INCLUDED ✅")
