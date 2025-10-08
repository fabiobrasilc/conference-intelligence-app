"""
ESMO 2025 Conference Intelligence App - Simplified Architecture
Medical Affairs Platform for EMD Serono

Radical simplification following the vision:
Button → Generate Table → Inject Prompt → Stream Response

No overengineered routing, no QueryPlan abstractions, no keyword matching.
Clean, maintainable, ~2000 lines.
"""

from flask import Flask, render_template, request, jsonify, Response
import pandas as pd
import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI
from pathlib import Path
import re
import json
from typing import List, Tuple, Dict, Any, Optional
from collections import Counter
from datetime import datetime
import os
import time
from dotenv import load_dotenv
import hashlib
import io

# ============================================================================
# TIER 1 + TIER 2 IMPORTS (Enhanced Search)
# ============================================================================
from entity_resolver import expand_query_entities, resolve_drug_name
from improved_search import precompute_search_text, smart_search
from query_intelligence import analyze_query
from enhanced_search import complete_search_pipeline
from lean_synthesis import build_lean_synthesis_prompt, estimate_prompt_tokens

# ============================================================================
# UNICODE SANITIZATION (Windows compatibility)
# ============================================================================

def sanitize_unicode_for_windows(text):
    """Replace Unicode characters incompatible with Windows cp1252 codec."""
    if not text:
        return text

    replacements = {
        '\u2011': '-', '\u2013': '-', '\u2014': '-',
        '\u2018': "'", '\u2019': "'",
        '\u201c': '"', '\u201d': '"',
        '\u2026': '...', '\u00a0': ' ',
    }

    for unicode_char, replacement in replacements.items():
        text = text.replace(unicode_char, replacement)

    return text

def sanitize_data_structure(data):
    """Recursively sanitize Unicode in dicts, lists, strings. Handle NaN/NaT values."""
    if isinstance(data, dict):
        return {key: sanitize_data_structure(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [sanitize_data_structure(item) for item in data]
    elif isinstance(data, str):
        return sanitize_unicode_for_windows(data)
    elif pd.isna(data):  # Handle NaN, NaT, None
        return None
    else:
        return data

# ============================================================================
# SSE STREAMING UTILITIES
# ============================================================================

def stream_with_heartbeat(inner_gen, interval=15):
    """Wrap SSE stream with periodic pings to keep connection alive (15s interval for Railway)."""
    last = time.monotonic()

    for chunk in inner_gen:
        yield chunk
        now = time.monotonic()

        # Send heartbeat comment every 15 seconds to prevent timeout
        if now - last >= interval:
            yield ": keepalive\n\n"
            last = now
        else:
            last = now

    # Final heartbeat
    yield ": done\n\n"

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Cache-Control",
}

# ============================================================================
# FLASK APP INITIALIZATION
# ============================================================================

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_strong_fallback_secret_key_change_me")

# ============================================================================
# CONFIGURATION
# ============================================================================

CSV_FILE = Path(__file__).parent / "ESMO_2025_FINAL_20250929.csv"
CHROMA_DB_PATH = "./chroma_conference_db"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# OpenAI client with controlled connection pooling for Railway deployment
if OPENAI_API_KEY:
    import httpx

    custom_http_client = httpx.Client(
        timeout=httpx.Timeout(300.0, connect=30.0),
        limits=httpx.Limits(max_connections=3, max_keepalive_connections=1),
        transport=httpx.HTTPTransport(retries=2)
    )

    client = OpenAI(
        api_key=OPENAI_API_KEY,
        timeout=120.0,  # Increased from 60s to 120s for medium reasoning effort
        max_retries=2,
        http_client=custom_http_client
    )
else:
    client = None

# ============================================================================
# GLOBAL VARIABLES
# ============================================================================

chroma_client = None
collection = None
csv_hash_global = None
df_global = None
competitive_landscapes = {}  # Will hold loaded JSON competitive landscape data
abstracts_available = False  # Auto-detected: True if 'Abstract' column exists in dataset

# Drug Database Caches (loaded once at startup)
DRUG_DATABASE = None  # Source DataFrame from CSV
MOA_DRUG_CACHE = {}  # {"ADC": [56 drugs], "ICI": [44 drugs], ...}
TARGET_DRUG_CACHE = {}  # {"HER2": [15 drugs], "PD-1": [8 drugs], ...}
DRUG_ALIAS_MAP = {}  # {"pembro": "pembrolizumab", "ev": "enfortumab vedotin", ...}

# ============================================================================
# SYSTEM PROMPT FOR AI SYNTHESIS
# ============================================================================

MEDICAL_AFFAIRS_SYSTEM_PROMPT = """You are an expert medical affairs intelligence analyst for a pharmaceutical company.

**YOUR ROLE**:
- Synthesize conference data for medical affairs teams (MSLs, Medical Directors, Leadership)
- Focus on strategic insights: competitive landscape, KOL signals, research trends
- Cite specific studies using their Identifier (e.g., "LBA2", "628TiP")

**TONE & STYLE**:
- Professional, concise, actionable
- Use pharmaceutical industry terminology appropriately
- Be direct - no preamble or filler

**BREVITY RULES** (CRITICAL):
- 0 results found → 1-2 sentences max ("Not found at this conference. [Brief context if helpful]")
- 1 result found → 2-4 sentences (what it is, who's presenting, why it matters)
- 2-5 results → 1 short paragraph + bullet list of key studies
- 6+ results → Full synthesis (themes, notable studies, strategic implications)

**WHEN TO BE BRIEF**:
- User asks about obscure/absent drugs → Short answer, no speculation
- Simple factual queries (e.g., "What is X?") → Direct answer, 2-3 sentences
- No data found → Acknowledge briefly, suggest alternatives if relevant

**WHEN TO BE COMPREHENSIVE**:
- Multiple studies with strategic implications
- Competitive landscape questions
- Thematic analysis requests
- KOL/institution mapping

**NEVER**:
- Speculate on efficacy/safety without data
- Generate long responses when data is sparse
- Add unnecessary background/disclaimers when answer is straightforward
- Waste tokens on meta-commentary

**ALWAYS**:
- Cite study Identifiers when referencing specific presentations
- Acknowledge when abstracts are not yet available (pre-Oct 13)
- Focus on what CAN be inferred from titles, speakers, institutions
- Be helpful but efficient with token usage"""

# ============================================================================
# COMPETITIVE LANDSCAPE JSON LOADING
# ============================================================================

def load_competitive_landscapes():
    """Load all competitive landscape JSON files at startup."""
    global competitive_landscapes

    json_files = {
        "Bladder Cancer": "bladder-json.json",
        "Lung Cancer": "nsclc-json.json",
        "Colorectal Cancer": "erbi-crc-json.json",
        "Head and Neck Cancer": "erbi-HN-json.json"
    }

    for ta_name, filename in json_files.items():
        filepath = Path(__file__).parent / filename
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                competitive_landscapes[ta_name] = json.load(f)
            print(f"[LANDSCAPE] Loaded {ta_name} competitive landscape from {filename}")
        except Exception as e:
            print(f"[LANDSCAPE] ERROR loading {filename}: {e}")
            competitive_landscapes[ta_name] = None

    return competitive_landscapes

# ============================================================================
# DRUG DATABASE CACHE LOADING
# ============================================================================

def load_drug_database_cache():
    """
    Load drug database CSV and build lookup caches for fast access.

    Builds three caches:
    - MOA_DRUG_CACHE: {"ADC": [56 drugs], "ICI": [44 drugs], ...}
    - TARGET_DRUG_CACHE: {"HER2": [15 drugs], "PD-1": [8 drugs], ...}
    - DRUG_ALIAS_MAP: {"pembro": "pembrolizumab", "ev": "enfortumab vedotin", ...}

    CSV is the source of truth - easy to update, just restart app.
    """
    global DRUG_DATABASE, MOA_DRUG_CACHE, TARGET_DRUG_CACHE, DRUG_ALIAS_MAP

    try:
        # Load drug database CSV
        drug_db_path = Path(__file__).parent / "Drug_Company_names_with_MOA.csv"
        DRUG_DATABASE = pd.read_csv(drug_db_path)
        print(f"[DRUG_DATABASE] Loaded {len(DRUG_DATABASE)} drugs from database")

        # Build MOA cache
        MOA_DRUG_CACHE = {}
        for moa_class in DRUG_DATABASE['moa_class'].dropna().unique():
            drugs_in_class = DRUG_DATABASE[DRUG_DATABASE['moa_class'] == moa_class]
            drug_list = []

            for _, row in drugs_in_class.iterrows():
                # Use generic name if available, otherwise commercial name
                if pd.notna(row['drug_generic']):
                    drug_list.append(row['drug_generic'].strip())
                elif pd.notna(row['drug_commercial']):
                    drug_list.append(row['drug_commercial'].strip())

            MOA_DRUG_CACHE[moa_class] = drug_list

        print(f"[DRUG_DATABASE] Built MOA cache with {len(MOA_DRUG_CACHE)} classes:")
        # Show top classes
        for moa_class in ['ADC', 'ICI', 'TKI', 'Targeted Therapy', 'Bispecific Antibody']:
            if moa_class in MOA_DRUG_CACHE:
                print(f"  - {moa_class}: {len(MOA_DRUG_CACHE[moa_class])} drugs")

        # Build TARGET cache (extract common targets from moa_target column)
        TARGET_DRUG_CACHE = {}
        common_targets = ['HER2', 'PD-1', 'PD-L1', 'CTLA-4', 'EGFR', 'VEGF', 'FGFR', 'MET', 'TROP2', 'Nectin-4']

        for target in common_targets:
            drugs_with_target = DRUG_DATABASE[
                DRUG_DATABASE['moa_target'].str.contains(target, case=False, na=False)
            ]
            drug_list = []

            for _, row in drugs_with_target.iterrows():
                if pd.notna(row['drug_generic']):
                    drug_list.append(row['drug_generic'].strip())
                elif pd.notna(row['drug_commercial']):
                    drug_list.append(row['drug_commercial'].strip())

            if drug_list:  # Only add if we found drugs
                TARGET_DRUG_CACHE[target] = drug_list

        print(f"[DRUG_DATABASE] Built target cache with {len(TARGET_DRUG_CACHE)} targets")

        # Build ALIAS map (common abbreviations)
        DRUG_ALIAS_MAP = {
            # Checkpoint inhibitors
            "pembro": "pembrolizumab",
            "keytruda": "pembrolizumab",
            "nivo": "nivolumab",
            "opdivo": "nivolumab",
            "atezo": "atezolizumab",
            "tecentriq": "atezolizumab",
            "durva": "durvalumab",
            "imfinzi": "durvalumab",
            "avel": "avelumab",
            "bavencio": "avelumab",

            # ADCs
            "ev": "enfortumab vedotin",
            "padcev": "enfortumab vedotin",
            "sg": "sacituzumab govitecan",
            "trodelvy": "sacituzumab govitecan",
            "t-dxd": "trastuzumab deruxtecan",
            "enhertu": "trastuzumab deruxtecan",

            # Combination abbreviations (for EV+P, etc.)
            "p": "pembrolizumab",
            "n": "nivolumab",

            # Other common drugs
            "erda": "erdafitinib",
            "balversa": "erdafitinib",
        }

        print(f"[DRUG_DATABASE] Built alias map with {len(DRUG_ALIAS_MAP)} abbreviations")
        print(f"[DRUG_DATABASE] All caches ready for fast lookup")

    except Exception as e:
        print(f"[DRUG_DATABASE] ERROR: Could not load drug database - {e}")
        print(f"[DRUG_DATABASE] Continuing with empty caches")


def expand_search_terms_with_database(search_terms: List[str]) -> List[str]:
    """
    Expand search terms using drug database caches.

    Takes AI-extracted search terms and expands MOA classes/targets to actual drug names.

    Args:
        search_terms: List from classify_user_query() (e.g., ["ADC", "pembrolizumab"])

    Returns:
        Expanded list with MOA classes replaced by drug names

    Examples:
        ["ADC"] → [56 ADC drug names]
        ["pembrolizumab"] → ["pembrolizumab"] (unchanged)
        ["ICI", "pembrolizumab"] → [44 ICI drugs + "pembrolizumab"]
        ["HER2-targeted"] → [15 HER2 drugs]
    """
    if not search_terms:
        return []

    expanded = []

    for term in search_terms:
        term_lower = term.lower().strip()
        term_added = False

        # Priority 1: Check if it's an alias (most specific - like "ev", "p")
        if term_lower in DRUG_ALIAS_MAP:
            expanded.append(DRUG_ALIAS_MAP[term_lower])
            term_added = True

        # Priority 2: Check if it's a MOA class (exact match - like "ADC", "ICI")
        if not term_added:
            for moa_class, drug_list in MOA_DRUG_CACHE.items():
                if moa_class.lower() == term_lower:
                    expanded.extend(drug_list)
                    term_added = True
                    break

        # Priority 3: Check if it's a target (partial match - like "HER2", "PD-1")
        # Only match if term is at least 3 chars to avoid false matches like "P" → "PD-1"
        if not term_added and len(term_lower) >= 3:
            for target, drug_list in TARGET_DRUG_CACHE.items():
                if target.lower() == term_lower or target.lower() in term_lower:
                    expanded.extend(drug_list)
                    term_added = True
                    break

        # Priority 4: Keep as-is (already a specific drug name or keyword)
        if not term_added:
            expanded.append(term)

    # Deduplicate while preserving order
    seen = set()
    result = []
    for drug in expanded:
        drug_normalized = drug.lower().strip()
        if drug_normalized not in seen:
            seen.add(drug_normalized)
            result.append(drug)

    return result


def match_studies_with_competitive_landscape(df: pd.DataFrame, therapeutic_area: str, n: int = 200) -> pd.DataFrame:
    """
    Match studies to competitive drugs using CSV database with combination detection.

    For each study title:
    1. Search for ALL drug generic names (from CSV)
    2. Build combination name: "Drug1 + Drug2 + Chemotherapy + Radiation"
    3. Append company/MOA info for each drug found

    Args:
        df: DataFrame of conference studies
        therapeutic_area: Filter context (for logging only)
        n: Max results to return

    Returns:
        DataFrame with columns: Drug, Company, MOA Class, MOA Target, ThreatLevel, Identifier, Title
    """
    if df.empty:
        return pd.DataFrame()

    # Load CSV drug database
    try:
        drug_db_path = Path(__file__).parent / "Drug_Company_names.csv"
        drug_db = pd.read_csv(drug_db_path, encoding='utf-8-sig')
        print(f"[CSV MATCHER] Loaded {len(drug_db)} drugs from database")
    except Exception as e:
        print(f"[CSV MATCHER] ERROR: Could not load Drug_Company_names.csv: {e}")
        return pd.DataFrame()

    # EMD portfolio drugs to exclude
    emd_drugs = ['avelumab', 'bavencio', 'tepotinib', 'cetuximab', 'erbitux', 'pimicotinib']

    # Build study-to-drugs mapping
    study_drugs = {}  # identifier -> {drugs: [...], title: str}

    for _, row in df.iterrows():
        identifier = row['Identifier']
        title_lower = str(row['Title']).lower()
        found_drugs = []

        # Search for ALL drugs in this study title (generic name only)
        for _, drug_row in drug_db.iterrows():
            generic = str(drug_row['drug_generic']).strip().lower() if pd.notna(drug_row['drug_generic']) else ""

            if not generic:
                continue

            # Skip EMD portfolio
            if generic in emd_drugs:
                continue

            # Strip FDA suffixes (-ejfv, -nxki, etc.) for matching
            # Example: "enfortumab vedotin-ejfv" → "enfortumab vedotin"
            generic_base = generic.split('-')[0].strip()

            # Skip drugs with very short base names (≤3 chars) to avoid false matches
            # Examples: "bl" (from BL-B01D1), "st", "pt" match common words
            if len(generic_base) <= 3:
                continue

            # Check if drug generic name appears in title
            if generic_base in title_lower:
                company = str(drug_row['company']).strip() if pd.notna(drug_row['company']) else "Unknown"
                moa_class = str(drug_row['moa_class']).strip() if pd.notna(drug_row['moa_class']) else "Unknown"
                moa_target = str(drug_row['moa_target']).strip() if pd.notna(drug_row['moa_target']) else ""

                found_drugs.append({
                    'name': generic_base,  # Use base name without suffix
                    'company': company,
                    'moa_class': moa_class,
                    'moa_target': moa_target
                })

        if found_drugs:
            study_drugs[identifier] = {
                'drugs': found_drugs,
                'title': row['Title']
            }

    print(f"[CSV MATCHER] Found {len(study_drugs)} studies with drug matches")

    # Build results with combined drug names
    results = []

    for identifier, study_info in study_drugs.items():
        drugs = study_info['drugs']
        title = study_info['title']

        # Build combined drug name
        drug_names = [d['name'].title() for d in drugs]
        display_name = ' + '.join(drug_names)

        # Build combined company (unique companies only, preserve order)
        companies = []
        for d in drugs:
            comp = d['company']
            # Split by comma and clean
            for c in comp.split(','):
                c_clean = c.strip()
                if c_clean and c_clean not in companies:
                    companies.append(c_clean)
        company_display = ' + '.join(companies) if companies else "Unknown"

        # Build combined MOA class
        moa_classes = [d['moa_class'] for d in drugs if d['moa_class'] != 'Unknown']
        moa_class_display = ' + '.join(moa_classes) if moa_classes else 'Unknown'

        # Build combined MOA target
        moa_targets = [d['moa_target'] for d in drugs if d['moa_target']]
        moa_target_display = ' + '.join(moa_targets)

        results.append({
            'Drug': display_name,
            'Company': company_display,
            'MOA Class': moa_class_display,
            'MOA Target': moa_target_display,
            'ThreatLevel': 'CSV',
            'Identifier': identifier,
            'Title': title[:80] + '...' if len(title) > 80 else title
        })

    print(f"[CSV MATCHER] Generated {len(results)} competitive landscape entries")

    if not results:
        print(f"[MATCHER] No matches found for {therapeutic_area}")
        return pd.DataFrame()

    result_df = pd.DataFrame(results)

    # Add study count for sorting
    study_counts = result_df.groupby('Drug').size().to_dict()
    result_df['_study_count'] = result_df['Drug'].map(study_counts)

    # Sort by threat level and study count
    threat_order = {'HIGH': 1, 'MEDIUM': 2, 'LOW': 3, 'EMERGING': 4, 'CSV': 5, 'UNKNOWN': 6}
    result_df['_threat_sort'] = result_df['ThreatLevel'].map(threat_order).fillna(6)

    result_df = result_df.sort_values(['_threat_sort', '_study_count', 'Drug'], ascending=[True, False, True])
    result_df = result_df.head(n)

    # Drop internal sorting columns and ThreatLevel
    result_df = result_df.drop(columns=['_study_count', '_threat_sort', 'ThreatLevel'])

    print(f"[MATCHER] Final: {len(result_df)} studies across {result_df['Drug'].nunique()} unique drug combinations")

    return result_df

# ============================================================================
# FILTER CONFIGURATIONS
# ============================================================================

ESMO_DRUG_FILTERS = {
    "Competitive Landscape": {
        "keywords": [],
        "main_filters": [],
        "description": "All competitive drugs and broader oncology landscape",
        "show_all": True
    },
    "All EMD Portfolio": {
        "keywords": ["avelumab", "bavencio", "tepotinib", "cetuximab", "erbitux"],
        "main_filters": ["Urothelial; Avelumab", "NSCLC; Tepotinib"],
        "description": "All EMD Serono drugs across therapeutic areas"
    },
    "Avelumab Focus": {
        "keywords": ["avelumab", "bavencio"],
        "main_filters": ["Urothelial; Avelumab"],
        "description": "Avelumab/Bavencio across all indications"
    },
    "Tepotinib Focus": {
        "keywords": ["tepotinib"],
        "main_filters": ["NSCLC; Tepotinib"],
        "description": "Tepotinib in NSCLC and other indications"
    },
    "Cetuximab Focus": {
        "keywords": ["cetuximab", "erbitux"],
        "main_filters": [],
        "description": "Cetuximab/Erbitux in colorectal and head & neck"
    },
    "Cetuximab H&N": {
        "keywords": ["cetuximab", "erbitux"],
        "ta_filter": "Head and Neck Cancer",
        "main_filters": [],
        "description": "Cetuximab/Erbitux in head & neck cancer"
    },
    "Cetuximab CRC": {
        "keywords": ["cetuximab", "erbitux"],
        "ta_filter": "Colorectal Cancer",
        "main_filters": [],
        "description": "Cetuximab/Erbitux in colorectal cancer"
    }
}

ESMO_THERAPEUTIC_AREAS = {
    "All Therapeutic Areas": {
        "keywords": [],
        "exclude_if_in_title": [],
        "regex": False
    },
    "Bladder Cancer": {
        "keywords": ["bladder", "urothelial", "uroepithelial", "transitional cell", r"\bmuc\b", r"\bmibc\b", r"\bnmibc\b"],
        "exclude_if_in_title": ["renal", "kidney", "prostate", r"\brcc\b", "clear cell", "germ cell", "testicular"],
        "regex": True
    },
    "Renal Cancer": {
        "keywords": ["renal", "renal cell", r"\brcc\b", "kidney cancer", "clear cell renal"],
        "exclude_if_in_title": ["bladder", "urothelial", "prostate", "testicular"],
        "regex": True
    },
    "Lung Cancer": {
        "keywords": ["lung", "non-small cell lung cancer", "non-small-cell lung cancer", "NSCLC", "SCLC", "small cell lung",
                     r"\bMET\b", r"\bALK\b", r"\bEGFR\b", r"\bKRAS\b", r"\bBRAF\b", r"\bRET\b", r"\bROS1\b", r"\bNTRK\b"],
        "exclude_if_in_title": ["mesothelioma", "thymic", "thymoma"],
        "regex": True
    },
    "Colorectal Cancer": {
        "keywords": ["colorectal", r"\bcrc\b", "colon", "rectal", "bowel"],
        "exclude_if_in_title": ["gastric", "esophageal", "pancreatic", "hepatocellular", r"\bhcc\b", "gastroesophageal", "bile duct", "cholangiocarcinoma"],
        "regex": True
    },
    "Head and Neck Cancer": {
        "keywords": ["head and neck", "head & neck", r"\bhnscc\b", r"\bscchn\b",
                     "squamous cell carcinoma of the head", "oral", "pharyngeal", "laryngeal", "oropharyngeal", "nasopharyngeal"],
        "exclude_if_in_title": ["esophageal", "gastric", "lung", "thyroid", "salivary gland carcinoma"],
        "regex": True
    },
    "TGCT": {
        "keywords": [r"\btgct\b", r"\bpvns\b", "tenosynovial giant cell tumor", "pigmented villonodular synovitis"],
        "exclude_if_in_title": ["testicular", "germ cell tumor", "seminoma", "nonseminoma"],
        "regex": True
    }
}

ESMO_SESSION_TYPES = {
    "All Session Types": [],
    "Poster": ["Poster"],
    "ePoster": ["ePoster"],
    "Proffered Paper": ["Proffered Paper"],
    "Mini Oral Session": ["Mini Oral Session"],
    "Educational Session": ["Educational Session"],
    "Symposia": ["Symposium"],  # All symposiums EXCEPT Industry-Sponsored
    "Industry-Sponsored Symposium": ["Industry-Sponsored Symposium"],
    "Multidisciplinary Session": ["Multidisciplinary Session"],
    "Special Session": ["Special Session"],
    "Young Oncologists Session": ["Young Oncologists Session"],
    "Challenge Your Expert": ["Challenge Your Expert"],
    "Patient Advocacy Session": ["Patient Advocacy Session"],
    "EONS Session": ["Eons Session"],
    "Highlights": ["Highlights"],
    "Keynote Lecture": ["Keynote Lecture"]
}

ESMO_DATES = {
    "All Dates": [],
    "Day 1": ["10/17/2025"],
    "Day 2": ["10/18/2025"],
    "Day 3": ["10/19/2025"],
    "Day 4": ["10/20/2025"],
    "Day 5": ["10/21/2025"]
}

# ============================================================================
# PLAYBOOK PROMPTS (Simplified - One Prompt Per Button)
# ============================================================================

PLAYBOOKS = {
    "competitor": {
        "button_label": "Competitive Intelligence",
        "ai_prompt": """You are EMD Serono's medical affairs competitive intelligence analyst. Analyze competitor activity at ESMO 2025 to identify research trends, data signals, and material threats to EMD portfolio positioning.

**CRITICAL INSTRUCTIONS**:

1. **THERAPEUTIC AREA FOCUS - ABSOLUTELY CRITICAL**:
   - The tables below contain ONLY studies from the selected therapeutic area (shown in filter_guidance)
   - You MUST discuss ONLY competitors relevant to this specific TA
   - The filter_guidance section tells you EXACTLY which competitors to focus on

2. **EMD Drug Recognition - CRITICAL**:
   - If you see **avelumab**, **bavencio**, **tepotinib**, **cetuximab**, **erbitux**, or **pimicotinib** in a study:
     * CHECK if it's being COMPARED to our drug (competitor study) OR
     * CHECK if it's an EMD-SPONSORED study (our data presentation)
   - **DO NOT** label EMD-sponsored studies as "competitor threats"
   - Example: "JAVELIN Bladder Medley: avelumab + sacituzumab" → EMD combination study, NOT a sacituzumab threat
   - Example: "EV-302: enfortumab vedotin + pembrolizumab vs chemotherapy" → IS a threat (comparing competitor to standard)

3. **Three tables are provided**:
   - **Table 1: Competitor Drug Ranking** - Major competitors by # studies and MOA
   - **Table 2: Competitor Studies** - Full list of competitor abstracts with identifiers
   - **Table 3: Emerging Threats** - Novel mechanisms, early-phase signals
   - These tables contain ONLY data from the filtered TA - analyze what's IN the tables

4. **EMD Asset Context by TA**:
   - **Bladder/Urothelial**: Avelumab 1L maintenance therapy post-platinum (la/mUC)
   - **Lung/NSCLC**: Tepotinib 1L mNSCLC with MET exon 14 skipping mutations
   - **Head & Neck**: Cetuximab 1L la/mHNSCC
   - **Colorectal**: Cetuximab 1L mCRC RAS wild-type
   - **TGCT**: Pimicotinib (tenosynovial giant cell tumor, pre-launch)

5. **Anti-Hallucination**: Use ONLY data from the provided tables - never invent Abstract #s

---

**SECTION 1: COMPETITIVE ACTIVITY OVERVIEW**

Write a natural, flowing narrative paragraph (3-5 sentences) covering:
- Total competitor studies and which drugs/companies are most active (cite # from Table 1)
- MOA class distribution (what types of mechanisms dominate: ADCs, ICIs, TKIs, etc.)
- Geographic hotspots if visible from Table 2 affiliations (MD Anderson, MSK, IGR, etc.)
- EMD portfolio presence (# of EMD drug studies vs competitors, if visible)

---

**SECTION 2: COMPETITOR INTELLIGENCE SUMMARIES**

**[Table 1 and Table 2 are shown to user above]**

Based on Tables 1-2, analyze the **top 5-8 most active competitors** by study count. For each competitor, provide a concise summary using this exact format:

**[Drug Name]** ([Company]) — **X studies** at ESMO 2025

**Research Focus**: [Briefly describe the themes visible in study titles: biomarkers, combinations, resistance, safety, subgroups, etc.]

**Treatment Settings**: [List settings visible in titles: 1L, 2L+, maintenance, adjuvant, neoadjuvant, metastatic, locally advanced, biomarker-selected]

**Key Studies** (cite 2-3 highest-value abstracts):
- **(Abstract #X)** [Brief description based on title - trial name, setting, phase if visible]
- **(Abstract #Y)** [Brief description]

**Material Threat to [EMD Drug] [Indication]?**: **YES** or **NO**
[One sentence explaining why: direct competitor in same line/indication OR niche/biomarker-restricted OR earlier/later line]

[Repeat for next competitor]

---

**SECTION 3: EMERGING SIGNALS & INNOVATION**

**[Table 3: Emerging Threats is shown to user above]**

Based on Table 3, analyze the **top 3-5 highest-priority emerging signals**. Prioritize:
- Phase 1/2 studies with novel MOAs
- First-in-human trials
- Innovative combinations
- Next-generation approaches to established targets

For each emerging signal:

**[Drug/Mechanism]** — ([Company], [Institution if visible])
- **(Abstract #X)**: [Brief title summary]
- **What's Novel**: [Mechanism, target, or combination approach that's innovative]
- **Development Timeline**: [Phase 1/2/3, FIH, pivotal, etc. if stated in title]
- **Material Threat?**: [YES if targets same indication/line as EMD drug, NO if biomarker-restricted to small subset or distant line of therapy]

[Repeat for next emerging signal]

**Innovation Patterns Observed**:
[Bullet list of 3-5 patterns]:
- Novel mechanisms appearing (bispecifics, ADCs, TLR agonists, etc.)
- Combination strategies (IO+ADC, TKI+ICI, triplets, etc.)
- Next-generation approaches to established targets (next-gen MET inhibitors, improved FGFR selectivity, etc.)

---

**FORMATTING REQUIREMENTS** (CRITICAL FOR READABILITY):
- **Drug names**: Always bold
- **Section headers**: Bold and uppercase (e.g., **SECTION 1: COMPETITIVE ACTIVITY OVERVIEW**)
- **Abstract citations**: Use format **(Abstract #1234P)** in bold
- **Study summaries**: Use bullet lists with consistent formatting
- **Threat assessment**: Separate line with clear **YES** or **NO** answer in bold
- **Avoid**: Long run-on paragraphs mixing data, settings, and threat assessment
- **Tone**: Factual, concise, intelligence-focused (not defensive or strategic advice)

**WHAT THIS IS**: Competitive intelligence - competitor presence, activity, and data signals
**WHAT THIS IS NOT**: Strategic recommendations, MSL talking points, positioning advice

**OUTPUT GOAL**: Medical affairs directors should be able to scan this report and immediately understand:
1. Who's most active in this TA at ESMO 2025
2. What they're presenting (trials, settings, biomarkers)
3. Which competitors pose material threats vs niche/non-competing programs""",
        "required_tables": ["all_data"]
    },
    "kol": {
        "button_label": "KOL Analysis",
        "ai_prompt": """You are EMD Serono's medical affairs KOL intelligence analyst. Analyze the top 10 most active researchers at ESMO 2025 and provide executive KOL profiles with EMD-focused engagement priorities.

**CRITICAL INSTRUCTIONS**:
1. **Strict Scope Limitation**:
   - You are analyzing a FILTERED dataset (e.g., only Bladder Cancer abstracts if TA filter applied)
   - ONLY discuss the research visible in the provided KOL abstracts list below
   - DO NOT speculate about this KOL's work in other therapeutic areas not shown
   - DO NOT assume broader research portfolio beyond what abstracts are provided
   - If a KOL has 5 bladder cancer abstracts shown, discuss ONLY those 5

2. **Anti-Hallucination Safeguards**:
   - ONLY use information from provided Top Authors table and KOL abstracts - never invent names, institutions, or Abstract #s
   - Date/Time/Room data is available - use it for engagement guidance
   - When uncertain about any detail, omit rather than guess

3. **Stay Grounded in Conference Data**:
   - DO NOT speculate about "rising influence", "accessibility", "competitor relationships" or "thought leadership status"
   - Focus on observable facts: study counts, research topics from titles, institution affiliations, presentation dates/times
   - Avoid assumptions that cannot be verified from the dataset

4. **TGCT Clarification** (if applicable):
   - TGCT = Tenosynovial Giant Cell Tumor (PVNS), NOT testicular germ cell tumor

5. **Formatting Consistency**:
   - Use **bold** for section headers and KOL names only
   - Do NOT use italics unless quoting abstract titles
   - Use consistent bullet formatting (- for lists)

---

**SECTION 1: EXECUTIVE SUMMARY** (1 paragraph)

Write a natural, flowing narrative paragraph (not bullet lists) covering:
- KOL productivity distribution (how many with 10+, 5-10, 2-4 abstracts)
- Geographic concentration (which countries/regions dominate - be specific)
- EMD portfolio alignment (how many present direct EMD asset data vs work in adjacent competitive spaces)

Write in prose style, integrating these points naturally into 3-5 sentences.

---

**SECTION 2: TOP 10 KOL PROFILES** (Concise narrative summaries)

For each of the 10 KOLs, provide a **1-paragraph executive profile** in this format:

**Dr. [Full Name]** — [Department], [Institution], [City/Country]; **X presentations**

[Single narrative paragraph covering]:
- Research focus/contributions based on abstract titles and session types
- Treatment modalities and clinical settings visible in their work (e.g., "IO combinations in 1L setting", "ADC research in pretreated patients")
- Key studies/themes - cite Abstract #s for notable presentations
- **Portfolio relevance**: [One of three options]
  * Direct EMD asset work: "Presenting avelumab data (Abstract #X, #Y)"
  * Competitive space: "Works in IO/ADC competitive space with [competitor drugs] - no direct EMD abstracts"
  * Adjacent research: "FGFR3 biomarker research relevant to avelumab combination strategies"

*Example style*: "His contributions focus on immunotherapy in bladder cancer across clinical and symposium formats, including immune-related adverse events with sasanlimab + BCG in the CREST phase 3 study (Abstract 3078P). He is IO-oriented with translational and safety themes around IO+BCG combinations in NMIBC and educational symposium leadership. Portfolio relevance: sasanlimab+BCG safety data (Abstract 3078P) is in the IO/BCG competitive space; no direct EMD drug abstracts listed."

---

**SECTION 3: ENGAGEMENT PRIORITIES & KEY RESEARCH HIGHLIGHTS**

This section identifies TWO types of HCP engagement targets: (1) EMD-relevant opportunities and (2) Competitive intelligence targets.

---

**EMD-RELEVANT TARGETS**:

Scan the FULL filtered dataset (provided as "all_abstracts_for_engagement" table below) to identify HCPs with direct EMD portfolio relevance OR strategic value - NOT just the top 10 by volume. Look for:
- Presenting avelumab/tepotinib/cetuximab/pimicotinib data (search titles for drug names)
- Biomarker researchers relevant to EMD positioning (FGFR3, MET, nectin-4, TROP-2)
- Unmet needs research in EMD-relevant indications

For each EMD-relevant HCP found:

**Dr. [Name]** ([Institution], [Location])

- **Why Engage**: [Specify EMD asset alignment with Abstract #s OR strategic value]
  * Examples: "Presenting avelumab maintenance data (Abstract #X)"
  * "FGFR3 biomarker researcher - relevant for avelumab+erdafitinib combination discussions"

- **Key Research Highlights**:
  * **(Abstract #X)** [Title or description based on title] - Presenting [Date], [Time], [Room]
  * **(Abstract #Y)** [If multiple relevant abstracts]

- **Discussion Topics**: [2-3 tactical topics based on their research focus]
  * Unmet needs in cisplatin-ineligible bladder cancer
  * FGFR3 biomarker testing infrastructure challenges
  * Real-world experience with avelumab maintenance therapy

- **Strategic Objective**: [e.g., "Assess interest in investigator-initiated RWE study" OR "Advisory board recruitment"]

[Repeat for 2-4 EMD-relevant HCPs]

---

**COMPETITIVE INTELLIGENCE TARGETS**:

Scan the FULL filtered dataset (provided as "all_abstracts_for_engagement" table below) to identify HCPs presenting key competitor data - NOT just the top 10 by volume. Search titles for competitor drug names and mechanisms.

**CRITICAL**: ONLY analyze competitors relevant to the FILTERED therapeutic area. If Bladder Cancer filter is active, ONLY discuss bladder competitors - ignore lung/CRC/H&N/TGCT competitors entirely.

Prioritize:
- Academic medical centers (Memorial Sloan Kettering, MD Anderson, Dana-Farber, Institut Gustave Roussy, etc.)
- Metastatic/advanced disease settings (extract from session titles: "metastatic", "advanced", "mUC", "la/m")
- High-impact competitors by therapeutic area (ONLY use the TA that matches your filtered dataset):
  * **Bladder/Urothelial**: EV+P (enfortumab vedotin + pembrolizumab), erdafitinib, sacituzumab govitecan, nivolumab, durvalumab, cabozantinib
  * **Lung/NSCLC**: MET TKI competitors to tepotinib (capmatinib, crizotinib, savolitinib), osimertinib, sotorasib, adagrasib, amivantamab, pembrolizumab combos, nivolumab combos
  * **CRC**: Panitumumab, bevacizumab combos, encorafenib, tucatinib, pembrolizumab (MSI-H)
  * **H&N**: Pembrolizumab, nivolumab, durvalumab, tislelizumab
  * **TGCT**: Pexidartinib, vimseltinib (Deciphera - both competitors to pimicotinib)

Limit to 5-8 highest-priority competitive intelligence targets. For each:

**Dr. [Name]** ([Institution], [Location])

- **Why Engage**: [Specify competitor focus with Abstract #s and competitive context]
  * Example: "Presenting EV+P combination data (Abstract LBA101) - key 1L mUC competitor, gather real-world effectiveness insights and safety profile for field positioning"
  * Example: "Nivolumab + ipilimumab session (Abstract 2045P) - competitive positioning vs avelumab maintenance in IO-refractory setting"
  * Example: "Erdafitinib FGFR3+ data (Abstract 3078P) - competitor in biomarker-selected bladder cancer, understand sequencing with avelumab"

- **Key Research Highlights**:
  * **(Abstract #X)** [Title or description based on title] - Presenting [Date], [Time], [Room]

- **Discussion Topics**: [2-3 tactical topics for competitive intelligence gathering]
  * Treatment sequencing: [competitor] vs [EMD asset]
  * Safety/tolerability in community practice settings
  * Biomarker selection criteria and testing infrastructure
  * Real-world effectiveness vs clinical trial data

- **Strategic Objective**: Competitive intelligence gathering - understand investigator perspectives on [competitor] positioning vs [EMD asset]

[Repeat for 5-8 competitive intelligence HCPs]

---

**WRITING REQUIREMENTS**:
- **Audience**: Hybrid - MSLs (need engagement guidance) + Medical Directors (need KOL landscape overview)
- **Tone**: Professional, fact-based medical affairs intelligence
- **Format**: Natural narrative prose for KOL profiles, structured bullets for engagement priorities
- **Citations**: Always cite Abstract # when referencing specific studies
- **Scope**: Use ONLY provided data - do not speculate beyond what's visible in titles/affiliations/session types
- **Engagement Guidance**: Provide tactical discussion topics and strategic objectives (NOT prescriptive scripts)
- **Vocabulary**: Professional medical terminology for oncology medical affairs audience

**OUTPUT STRUCTURE**:
- Section 1: Executive Summary (landscape overview)
- Section 2: Top 10 HCP Profiles (productivity leaders)
- Section 3: Engagement Priorities (EMD-relevant + Competitive Intelligence targets from FULL dataset)""",
        "required_tables": ["top_authors", "all_abstracts_for_engagement"]
    },
    "institution": {
        "button_label": "Academic Partnership Opportunities",
        "ai_prompt": """You are EMD Serono's medical affairs partnership strategist. Analyze leading research institutions at ESMO 2025 to identify academic partnership opportunities based on research volume, therapeutic area alignment, and EMD portfolio relevance.

**CRITICAL INSTRUCTIONS**:

1. **STRICT THERAPEUTIC AREA FOCUS**:
   - You are analyzing ONLY the selected therapeutic area (shown in filter guidance below)
   - DO NOT mention or analyze other therapeutic areas
   - Example: If "Bladder Cancer" selected, discuss ONLY bladder/urothelial research - NO lung, CRC, H&N, TGCT, or renal mentions
   - Focus ALL analysis on the filtered TA

2. **Data-Driven Analysis Only**:
   - Analyze ONLY institutions shown in the Top Institutions table below
   - Focus on observable metrics: study count, TA alignment, geographic distribution
   - DO NOT speculate about "accessibility", "competitor relationships", or "partnership feasibility" without data
   - Cite Abstract #s when referencing specific institutional research

3. **Anti-Hallucination Safeguards**:
   - ONLY use information from provided Top Institutions table - never invent institution names or Abstract #s
   - If data isn't available in table, omit rather than guess
   - When uncertain, skip that detail completely

4. **EMD Portfolio Context**:
   - **Bladder/Urothelial**: Avelumab 1L maintenance therapy post-platinum (la/mUC)
   - **Lung/NSCLC**: Tepotinib 1L mNSCLC with MET exon 14 skipping mutations
   - **Head & Neck**: Cetuximab 1L la/mHNSCC
   - **Colorectal**: Cetuximab 1L mCRC RAS wild-type
   - **TGCT**: Pimicotinib (tenosynovial giant cell tumor, pre-launch)

5. **TGCT Clarification** (if applicable):
   - TGCT = Tenosynovial Giant Cell Tumor (PVNS), NOT testicular germ cell tumor

----

**SECTION 1: INSTITUTIONAL LANDSCAPE OVERVIEW**

**[Top Institutions Table is shown to user above]**

Provide strategic overview for Medical Directors (1-2 paragraphs focused ONLY on the selected TA):

- **Research Concentration**: Top 5 institutions account for what % of total abstracts in this TA? (Calculate from table)
- **Geographic Distribution**: Which regions dominate in this TA? (US vs Europe vs APAC - count from table)
- **EMD Alignment**: How many top institutions have research relevant to EMD drug in this TA? (e.g., for Bladder: avelumab-relevant research)

Write in natural prose, integrating metrics from the table. Focus ONLY on the selected therapeutic area.

----

**SECTION 2: TOP INSTITUTIONAL PROFILES** (Top 8-12 institutions by volume)

For each institution in the Top Institutions table, provide a concise research profile focused ONLY on the selected TA:

**[INSTITUTION NAME]** ([City], [Country]) — **X presentations** at ESMO 2025

**Research Specialization in [Selected TA]** (from visible abstracts):
- **Research Focus**: [Specific research themes visible in abstract titles for THIS TA only]
- **Treatment Modalities**: [IO/ADC/targeted therapy/chemotherapy based on titles]
- **Clinical Settings**: [1L/2L/maintenance/biomarker-selected based on titles]

**EMD Portfolio Alignment**:
- [If EMD drugs appear in titles, cite Abstract #s]
- [If no direct EMD work: Note relevance, e.g., "Strong bladder cancer IO combination research - relevant for avelumab collaboration discussions"]

**Partnership Considerations**:
- **TA Expertise**: [High/Medium/Low based on abstract count and research depth in this TA]
- **Research Infrastructure**: [Phase 3 trial presence = clinical trial capabilities, biomarker studies = precision medicine infrastructure]
- **Geographic Value**: [US/EU/APAC regional partnership opportunity]

[Repeat for top 8-12 institutions]

----

**SECTION 3: PARTNERSHIP OPPORTUNITIES** (For Selected TA Only)

Focus ONLY on the selected therapeutic area:

**Research Themes in [Selected TA]**:
- Key research areas visible from institutional abstracts: [List themes like IO combinations, biomarker studies, ADC research, etc.]
- Partnership opportunities: [Investigator-initiated trials, RWE collaborations, biomarker research specific to this TA]

**EMD Drug Alignment**:
- Institutions with direct EMD drug research: [List with abstract counts]
- Institutions with complementary research (biomarkers, combinations, adjacent MOAs): [List with rationale]

**Multi-Institution Opportunities**:
- Collaborative networks: [Institutions appearing together in multi-center studies]
- Regional hubs: [Geographic clusters for regional partnership strategies]

----

**FORMATTING REQUIREMENTS**:
- **Institution names**: Always bold
- **Section headers**: Bold and uppercase
- **Study counts**: Bold numbers for emphasis
- **Abstract citations**: **(Abstract #1234P)** in bold when referencing specific research
- **Lists**: Use bullet points for readability
- **Tone**: Factual, data-driven partnership analysis (not speculative assessments)

**WHAT THIS IS**: Institutional research landscape analysis for partnership planning in the selected therapeutic area
**WHAT THIS IS NOT**: Cross-TA analysis, speculative "tier rankings", or accessibility assessments without supporting data

**OUTPUT GOAL**: Medical affairs directors should understand:
1. Which institutions are most active in the SELECTED TA at ESMO 2025
2. What research themes they focus on within this TA
3. Which have EMD portfolio alignment for partnership discussions in this TA""",
        "required_tables": ["top_institutions"]
    },
    "insights": {
        "button_label": "Scientific Trends",
        "ai_prompt": """You are EMD Serono's senior medical affairs scientific intelligence analyst. Analyze scientific trends at ESMO 2025 to identify emerging biomarkers, mechanisms of action, and treatment paradigms within the selected therapeutic area.

**CRITICAL INSTRUCTIONS**:

1. **STRICT THERAPEUTIC AREA FOCUS**:
   - You are analyzing ONLY the selected therapeutic area (shown in filter guidance below)
   - DO NOT mention or analyze other therapeutic areas
   - Example: If "Bladder Cancer" selected, discuss ONLY bladder/urothelial biomarkers and MOAs - NO lung, CRC, H&N, TGCT, or renal mentions
   - Focus ALL trend analysis on the filtered TA

2. **Data-Driven Analysis Only**:
   - Analyze ONLY biomarkers/MOAs shown in the Biomarker & MOA table below
   - If a biomarker has 0 studies in the table, do NOT mention it
   - Focus on what IS present in the data, not what's missing
   - Cite Abstract #s when referencing specific studies

3. **Anti-Hallucination Safeguards**:
   - ONLY discuss biomarkers/topics that appear in the provided table
   - Skip sections with no relevant data entirely - DO NOT write "not found" or "no data"
   - When uncertain, omit rather than guess
   - Always cite Abstract # when referencing specific studies

4. **EMD Portfolio Context**:
   - **Bladder/Urothelial**: Avelumab 1L maintenance therapy post-platinum (la/mUC)
   - **Lung/NSCLC**: Tepotinib 1L mNSCLC with MET exon 14 skipping mutations
   - **Head & Neck**: Cetuximab 1L la/mHNSCC
   - **Colorectal**: Cetuximab 1L mCRC RAS wild-type
   - **TGCT**: Pimicotinib (tenosynovial giant cell tumor, pre-launch)

5. **TGCT Clarification** (if applicable):
   - TGCT = Tenosynovial Giant Cell Tumor (PVNS), NOT testicular germ cell tumor

----

**SECTION 1: SCIENTIFIC LANDSCAPE OVERVIEW**

**[Biomarker & MOA Table is shown to user above]**

- **Dominant Scientific Themes**: What are the 3-5 most active research areas based on biomarker/MOA table? (e.g., ADC research, IO biomarkers, targeted therapy)
- **Biomarker Momentum**: Which biomarkers show strongest activity based on study counts in table?
- **MOA Trends**: Which mechanisms of action dominate in this TA? (count from table: ADCs, ICIs, TKIs, etc.)
- **EMD Relevance**: How many biomarker/MOA studies are relevant to EMD drug in this TA?

Write in natural prose focused ONLY on the selected therapeutic area.

----

**SECTION 2: BIOMARKER TRENDS** (From table data only)

Analyze biomarkers visible in the Biomarker & MOA table. For each biomarker with significant activity:

**[Biomarker Name]** — **X studies** at ESMO 2025

**Research Context** (from titles):
- Treatment selection/patient stratification
- Predictive biomarker vs prognostic biomarker
- Combination therapy biomarker strategies
- Resistance biomarker research

**Key Studies** (cite 2-3 highest-value abstracts if visible):
- **(Abstract #X)** [Brief description based on title]
- **(Abstract #Y)** [Brief description]

**EMD Relevance**:
- [If relevant to EMD drug: Explain connection]
- [If not directly relevant: State "Adjacent biomarker research" or omit]

[Repeat for biomarkers with ≥3 studies in table]

----

**SECTION 3: MECHANISM OF ACTION TRENDS** (From table data only)

Analyze MOA classes visible in the Biomarker & MOA table:

**Antibody-Drug Conjugates (ADCs)** (if present in table):
- Study volume: [X studies from table]
- ADC targets visible: [List targets from table - HER2, TROP-2, Nectin-4, etc.]
- Combination strategies: [ADC+IO, ADC+chemo visible in titles]
- Key studies: **(Abstract #X, #Y)**

**Checkpoint Inhibitors / Immunotherapy** (if present in table):
- Study volume: [X studies from table]
- IO combinations: [IO+IO, IO+chemo, IO+targeted, IO+ADC visible in titles]
- Biomarker-driven IO: [PD-L1, TMB, MSI strategies]
- Key studies: **(Abstract #X, #Y)**

**Targeted Therapy** (if present in table):
- Study volume: [X studies from table]
- Pathways targeted: [FGFR, MET, EGFR, HER2, etc. from table]
- Next-generation agents: [Evolution beyond first-gen inhibitors]
- Key studies: **(Abstract #X, #Y)**

**Other Mechanisms** (if present in table):
- [Only discuss MOAs with ≥3 studies in table]
- [Examples: Bispecifics, DDR inhibitors, epigenetic modulators]

[Skip any MOA category with 0 studies - do NOT mention it]

----

**SECTION 4: TREATMENT PARADIGM INSIGHTS** (Observable from titles)

Based on visible data in the selected TA:

**Treatment Setting Distribution** (from titles):
- First-line (1L) research: [Study count visible from titles mentioning "first-line", "1L", "frontline"]
- Second-line+ (2L+) research: [Study count from "second-line", "2L", "pretreated"]
- Maintenance therapy: [Study count from "maintenance", "consolidation"]
- Biomarker-selected settings: [Studies with companion diagnostic strategies]

**Combination Strategies** (from titles):
- Most common regimen backbones: [IO+chemo, ADC+IO, doublet/triplet combinations]
- Novel combination approaches: [Emerging MOA pairings]

**Emerging Patterns** (observable from table):
- Rising biomarker use: [Increasing precision medicine strategies]
- MOA shifts: [Movement from chemotherapy to targeted/IO therapies]
- White space opportunities: [Underrepresented settings or biomarker groups]

----

**SECTION 5: EMD STRATEGIC IMPLICATIONS** (For selected TA only)

Focus ONLY on EMD drug relevant to the selected TA:

**EMD Drug Positioning Context**:
- [For Bladder: Avelumab positioning in maintenance setting]
- [For Lung: Tepotinib positioning in MET exon 14 setting]
- [For H&N: Cetuximab positioning in 1L la/mHNSCC]
- [For CRC: Cetuximab positioning in 1L mCRC RAS WT]

**Competitive Biomarker/MOA Activity**:
- Biomarkers competing with EMD positioning: [List from table with study counts]
- MOAs in same treatment setting: [List competing mechanisms]

**Differentiation Opportunities**:
- Biomarker white space: [Underserved biomarker populations relevant to EMD drug]
- Combination opportunities: [Synergistic MOAs underexplored in data]

----

**FORMATTING REQUIREMENTS**:
- **Biomarker/MOA names**: Always bold
- **Section headers**: Bold and uppercase
- **Study counts**: Bold numbers for emphasis
- **Abstract citations**: **(Abstract #1234P)** in bold
- **Lists**: Use bullet points for readability
- **Tone**: Factual scientific trend analysis (not speculative)

**WHAT THIS IS**: Scientific trend analysis based on biomarker/MOA research visible at ESMO 2025 for the selected TA
**WHAT THIS IS NOT**: Cross-TA analysis, speculation about biomarkers not in table, clinical trial design recommendations

**OUTPUT GOAL**: Medical affairs teams should understand:
1. Which biomarkers/MOAs dominate research in the SELECTED TA
2. What treatment paradigms are emerging in this TA
3. How these trends impact EMD drug positioning in this TA""",
        "required_tables": ["biomarker_moa_hits"]
    },
    "strategy": {
        "button_label": "Strategic Recommendations",
        "ai_prompt": """You are EMD Serono's medical affairs strategic intelligence analyst. Provide strategic analysis for ESMO 2025 focused on competitive positioning, key threats, and strategic opportunities within the selected therapeutic area.

**CRITICAL INSTRUCTIONS**:

1. **STRICT THERAPEUTIC AREA FOCUS**:
   - You are analyzing ONLY the selected therapeutic area (shown in filter guidance below)
   - DO NOT mention or analyze other therapeutic areas
   - Example: If "Bladder Cancer" selected, provide strategy ONLY for bladder/urothelial - NO lung, CRC, H&N, TGCT, or renal mentions
   - Focus ALL strategic analysis on the filtered TA

2. **Indication-Specific EMD Context**:
   - Provide TA-wide competitive landscape analysis
   - When discussing EMD drug positioning, be indication-specific:
     * Avelumab: **1L locally advanced/metastatic urothelial carcinoma (la/mUC), maintenance therapy post-platinum**
     * Tepotinib: **1L metastatic NSCLC (mNSCLC) with MET exon 14 skipping mutations**
     * Cetuximab (H&N): **1L locally advanced/metastatic head & neck squamous cell carcinoma (la/mHNSCC)**
     * Cetuximab (CRC): **1L metastatic colorectal cancer (mCRC), RAS wild-type**

3. **Data-Driven Analysis Only**:
   - Analyze ONLY data shown in the provided tables (Competitor, KOL, Biomarker/MOA)
   - Focus on observable patterns from titles and study counts
   - DO NOT speculate about efficacy, trial design, or clinical nuances requiring full abstracts
   - Cite Abstract #s when referencing specific studies

4. **Anti-Hallucination Safeguards**:
   - ONLY use information from provided tables - never invent Abstract #s, KOL names, or clinical details
   - If data isn't available, omit rather than guess
   - When uncertain, skip that detail completely

5. **TGCT Clarification** (if applicable):
   - TGCT = Tenosynovial Giant Cell Tumor (PVNS), NOT testicular germ cell tumor

----

**SECTION 1: EXECUTIVE SUMMARY** (Strategic imperatives)

**[Tables shown to user above: Competitor drugs, Top KOLs, Biomarker/MOA trends]**

Provide strategic overview for leadership (2-3 paragraphs focused ONLY on selected TA):

- **Competitive Landscape**: How many competitor drugs/studies in this TA? Which competitors dominate? (cite study counts from table)
- **Most Critical Threats**: Which 2-3 competitor developments pose biggest threat to EMD positioning in this TA?
- **Key Opportunities**: What white space or differentiation opportunities exist for EMD drug in this TA?
- **Strategic Priority**: What should medical affairs focus on in this TA based on ESMO data?

Write in natural prose focused ONLY on the selected therapeutic area.

----

**SECTION 2: COMPETITIVE POSITION ASSESSMENT**

**Treatment Landscape in [Selected TA]** (from table data):
- Total competitor studies: [X studies across Y drugs from Competitor table]
- Top 3 competitors: [Drug names + study counts + MOA from table]
- Treatment paradigm distribution: [1L vs 2L vs maintenance - observable from titles]

**EMD Drug Positioning** (indication-specific):
- [For Bladder: Avelumab in 1L maintenance post-platinum setting]
- [For Lung: Tepotinib in MET exon 14 1L mNSCLC setting]
- [For H&N: Cetuximab in 1L la/mHNSCC setting]
- [For CRC: Cetuximab in 1L mCRC RAS WT setting]

**Market Context** (from research patterns):
- EMD abstract volume vs competitor volume: [Compare from table]
- Research focus alignment: [How many competitor studies target same line/setting as EMD drug?]
- Biomarker selection trends: [From Biomarker table - precision medicine shift visible?]

----

**SECTION 3: COMPETITIVE THREATS** (From conference data)

Analyze top 3-5 direct competitive threats from Competitor table:

**THREAT 1: [Competitor Drug]** ([Company], [MOA from table])

- **Conference Presence**: X abstracts at ESMO 2025 (from table)
- **Clinical Settings**: [1L/2L/maintenance/combination - from titles]
- **EMD Impact**: How does this threaten EMD drug positioning in this TA?
- **Key Studies**: **(Abstract #X, #Y)** [Brief title summary]

[Repeat for 2-4 additional major threats]

**Emerging Competitive Patterns** (observable from tables):
- Treatment setting trends: [Competitors moving into earlier lines or adjacent settings?]
- Combination strategies: [Which regimen backbones threaten EMD positioning?]
- Biomarker-driven fragmentation: [Competitors using biomarkers to carve out patient subsets?]

----

**SECTION 4: STRATEGIC OPPORTUNITIES** (White space analysis)

Based on visible research gaps in the selected TA:

**Underserved Patient Populations** (from data gaps):
- Biomarker groups with low competitor activity: [From Biomarker table - which biomarkers underrepresented?]
- Treatment settings with limited research: [Which lines/settings have fewer competitor studies?]

**Treatment Paradigm Gaps** (from study distribution):
- [Example: "Maintenance therapy gap - if most competitors focus on upfront combinations"]
- Sequencing strategies: [Optimal treatment sequences understudied?]

**Combination Opportunities** (from Biomarker/MOA table):
- Synergistic MOAs underexplored: [Which MOA pairings have low study counts?]
- Biomarker-defined combinations: [Precision medicine opportunities with low competitor activity?]

**For Each Opportunity**:
- EMD Asset Fit: Which EMD drug fits this white space?
- Strategic Rationale: Why does this matter for positioning?

----

**SECTION 5: KOL ENGAGEMENT PRIORITIES** (From KOL table)

Focus ONLY on KOLs in the selected TA:

**EMD-Aligned KOLs** (presenting EMD drug data):
- [List KOLs with avelumab/tepotinib/cetuximab abstracts from table]
- Engagement priority: [Reinforce EMD messaging, Abstract #s]

**Competitive Intelligence Targets** (presenting competitor data):
- [List top KOLs by study count from table]
- Strategic value: [Understanding competitive positioning, Abstract #s]

**White Space KOLs** (researching underserved areas):
- [KOLs working in biomarker/treatment settings with EMD opportunity]
- Partnership potential: [Collaboration opportunities in white space areas]

----

**FORMATTING REQUIREMENTS**:
- **Drug/competitor names**: Always bold
- **Section headers**: Bold and uppercase
- **Study counts**: Bold numbers for emphasis
- **Abstract citations**: **(Abstract #1234P)** in bold
- **Threat levels**: Use "High/Medium/Low" with clear rationale
- **Lists**: Use bullet points for readability
- **Tone**: Strategic, actionable, data-driven (not speculative)

**WHAT THIS IS**: Strategic competitive analysis with actionable opportunities for the selected therapeutic area
**WHAT THIS IS NOT**: Cross-TA strategy, 90-day tactical plans without data support, efficacy speculation, market access recommendations

**OUTPUT GOAL**: Medical affairs leadership should understand:
1. Competitive threats in the SELECTED TA at ESMO 2025
2. White space opportunities for EMD drug in this TA
3. KOL engagement priorities specific to this TA""",
        "required_tables": ["all_data"]
    }
}

# ============================================================================
# DATA LOADING & PREPROCESSING
# ============================================================================

def file_md5(filepath):
    """Compute MD5 hash of file for change detection."""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def load_and_process_data():
    """Load ESMO CSV and prepare for analysis."""
    global df_global, csv_hash_global, chroma_client, collection, abstracts_available

    print(f"[STARTUP] Looking for CSV at: {CSV_FILE}")
    print(f"[STARTUP] CSV absolute path: {CSV_FILE.absolute()}")
    print(f"[STARTUP] Current working directory: {Path.cwd()}")
    print(f"[STARTUP] __file__ location: {Path(__file__).parent}")

    if not CSV_FILE.exists():
        print(f"[ERROR] CSV file not found at {CSV_FILE}")
        print(f"[ERROR] Listing files in {Path(__file__).parent}:")
        try:
            for f in Path(__file__).parent.iterdir():
                print(f"  - {f.name}")
        except Exception as e:
            print(f"[ERROR] Could not list directory: {e}")
        return None

    current_hash = file_md5(CSV_FILE)

    # Return cached data if unchanged
    if df_global is not None and csv_hash_global == current_hash:
        print("[DATA] Using cached dataset")
        return df_global

    print(f"[DATA] Loading {CSV_FILE.name}...")
    df = pd.read_csv(CSV_FILE, encoding='utf-8')

    print(f"[DATA] CSV loaded with {len(df)} rows and {len(df.columns)} columns")
    print(f"[DATA] Actual columns found: {list(df.columns)}")

    # Sanitize Unicode for Windows compatibility
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].apply(lambda x: sanitize_unicode_for_windows(str(x)) if pd.notna(x) else x)

    # Keep original column names from CSV for frontend compatibility
    # Expected columns: Title, Speakers, Speaker Location, Affiliation, Identifier, Room, Date, Time, Session, Theme
    expected_columns = ['Title', 'Speakers', 'Speaker Location', 'Affiliation', 'Identifier', 'Room', 'Date', 'Time', 'Session', 'Theme']
    missing_columns = set(expected_columns) - set(df.columns)
    if missing_columns:
        print(f"[WARNING] Missing expected columns: {missing_columns}")
        print(f"[WARNING] This may cause errors in the application!")

    # Fill NaN values
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].fillna('')

    csv_hash_global = current_hash
    df_global = df

    # Auto-detect abstract availability
    abstracts_available = 'Abstract' in df.columns or 'abstract' in df.columns
    if abstracts_available:
        abstract_col = 'Abstract' if 'Abstract' in df.columns else 'abstract'
        # Check if abstracts actually have content (not just empty column)
        non_empty_abstracts = df[abstract_col].notna() & (df[abstract_col].str.strip() != '')
        abstracts_count = non_empty_abstracts.sum()
        if abstracts_count > 0:
            print(f"[DATA] Full abstracts detected: {abstracts_count}/{len(df)} studies have abstract text")
        else:
            abstracts_available = False
            print(f"[DATA] Abstract column exists but is empty - treating as unavailable")
    else:
        print(f"[DATA] Full abstracts not yet available - using titles, authors, and metadata only")

    print(f"[DATA] Loaded {len(df)} studies from ESMO 2025")

    # ========================================================================
    # TIER 1 ENHANCEMENT: Precompute search_text for multi-field search
    # ========================================================================
    print(f"[TIER1] Precomputing search_text for multi-field search...")
    df = precompute_search_text(df)
    print(f"[TIER1] Search_text precomputed - enhanced search enabled")

    # ========================================================================
    # DRUG DATABASE: Load and cache MOA/target mappings
    # ========================================================================
    load_drug_database_cache()

    # Initialize ChromaDB in background (non-blocking)
    import threading
    chroma_thread = threading.Thread(target=initialize_chromadb, args=(df,), daemon=True)
    chroma_thread.start()
    print(f"[CHROMADB] Initializing in background (non-blocking)...")

    return df

def initialize_chromadb(df):
    """Initialize ChromaDB with conference data for semantic search."""
    global chroma_client, collection

    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

        # Use OpenAI embeddings if available, else default
        if OPENAI_API_KEY:
            ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=OPENAI_API_KEY,
                model_name="text-embedding-3-small"
            )
        else:
            ef = embedding_functions.DefaultEmbeddingFunction()

        collection_name = f"esmo_2025_{csv_hash_global[:8]}"

        # Check if collection already exists
        try:
            collection = chroma_client.get_collection(name=collection_name, embedding_function=ef)
            print(f"[CHROMA] Using existing collection: {collection_name}")
        except:
            # Create new collection
            collection = chroma_client.create_collection(
                name=collection_name,
                embedding_function=ef,
                metadata={"description": "ESMO 2025 Conference Abstracts"}
            )

            # Add documents to collection
            documents = []
            metadatas = []
            ids = []

            for idx, row in df.iterrows():
                doc_text = f"{row['Title']} {row['Speakers']} {row['Affiliation']} {row['Theme']}"
                documents.append(doc_text)
                metadatas.append({
                    "identifier": str(row['Identifier']),
                    "speaker": str(row['Speakers']),
                    "affiliation": str(row['Affiliation'])
                })
                ids.append(f"doc_{idx}")

            # Add in batches
            batch_size = 500
            for i in range(0, len(documents), batch_size):
                batch_docs = documents[i:i+batch_size]
                batch_meta = metadatas[i:i+batch_size]
                batch_ids = ids[i:i+batch_size]

                collection.add(
                    documents=batch_docs,
                    metadatas=batch_meta,
                    ids=batch_ids
                )

            print(f"[CHROMA] Created collection with {len(documents)} documents")

    except Exception as e:
        print(f"[CHROMA] Error initializing: {e}")
        chroma_client = None
        collection = None

# ============================================================================
# FILTER LOGIC (Therapeutic Area Filters)
# ============================================================================

def apply_therapeutic_area_filter(df: pd.DataFrame, ta_filter: str) -> pd.Series:
    """
    Apply smart therapeutic area filter with multi-field search and Title-based exclusions.

    Strategy:
    1. Search for TA keywords across ALL fields (catches edge cases like "mUC", theme mentions)
    2. If Title explicitly contains EXCLUDED term → Remove it (Title wins in conflicts)
    3. This handles: Theme says "GU" but Title says "renal cell" → Exclude

    Args:
        df: DataFrame to filter
        ta_filter: TA name from ESMO_THERAPEUTIC_AREAS

    Returns:
        Boolean mask for matching studies
    """
    if ta_filter == "All Therapeutic Areas":
        return pd.Series([True] * len(df), index=df.index)

    # Get TA configuration
    ta_config = ESMO_THERAPEUTIC_AREAS.get(ta_filter, {})
    keywords = ta_config.get("keywords", [])
    exclude_if_in_title = ta_config.get("exclude_if_in_title", [])
    use_regex = ta_config.get("regex", False)

    if not keywords:
        return pd.Series([True] * len(df), index=df.index)

    # Step 1: Broad multi-field search for TA keywords (using search_text_normalized)
    include_mask = pd.Series([False] * len(df), index=df.index)

    for keyword in keywords:
        if use_regex:
            include_mask |= df['search_text_normalized'].str.contains(keyword, case=False, na=False, regex=True)
        else:
            include_mask |= df['search_text_normalized'].str.contains(keyword, case=False, na=False, regex=False)

    # Step 2: Explicit exclusion based on Title (Title wins in conflicts)
    exclude_mask = pd.Series([False] * len(df), index=df.index)

    for exclude_term in exclude_if_in_title:
        if use_regex:
            exclude_mask |= df['Title'].str.contains(exclude_term, case=False, na=False, regex=True)
        else:
            exclude_mask |= df['Title'].str.contains(exclude_term, case=False, na=False, regex=False)

    # Step 3: Final mask = include AND NOT exclude
    final_mask = include_mask & ~exclude_mask

    return final_mask

# ============================================================================
# MULTI-FILTER LOGIC (Main Filtering Function)
# ============================================================================

def get_filtered_dataframe_multi(drug_filters: List[str], ta_filters: List[str],
                                  session_filters: List[str], date_filters: List[str]) -> pd.DataFrame:
    """
    Apply multi-selection filters with OR logic.
    Returns filtered DataFrame combining all selected filter combinations.
    """
    source_df = df_global

    if source_df is None or source_df.empty:
        return pd.DataFrame()

    # Start with empty mask (all False)
    combined_mask = pd.Series([False] * len(source_df), index=source_df.index)

    # If no filters selected, return all data (chat will use semantic search to find relevant subset)
    if not drug_filters and not ta_filters and not session_filters and not date_filters:
        return source_df

    # Handle "Competitive Landscape" drug filter (show all)
    if "Competitive Landscape" in drug_filters:
        drug_filters = list(ESMO_DRUG_FILTERS.keys())

    # Default to "All" if no selection
    if not drug_filters:
        drug_filters = ["Competitive Landscape"]
    if not ta_filters:
        ta_filters = ["All Therapeutic Areas"]
    if not session_filters:
        session_filters = ["All Session Types"]
    if not date_filters:
        date_filters = ["All Dates"]

    # Start with all True - each filter will AND to narrow down results
    combined_mask = pd.Series([True] * len(source_df), index=source_df.index)

    # Apply drug filters (OR across multiple drug selections, AND with other filter types)
    if drug_filters and "All Drugs" not in drug_filters and "Competitive Landscape" not in drug_filters:
        drug_combined_mask = pd.Series([False] * len(source_df), index=source_df.index)
        for drug_filter in drug_filters:
            drug_config = ESMO_DRUG_FILTERS.get(drug_filter, {})
            keywords = drug_config.get("keywords", [])

            # Build drug keyword mask
            drug_mask = pd.Series([False] * len(source_df), index=source_df.index)
            if keywords:
                for keyword in keywords:
                    drug_mask = drug_mask | source_df["Title"].str.contains(keyword, case=False, na=False, regex=False)

            # If drug has indication-specific TA filter (e.g., Cetuximab H&N vs CRC), apply it
            if "ta_filter" in drug_config:
                ta_name = drug_config["ta_filter"]
                ta_mask = apply_therapeutic_area_filter(source_df, ta_name)
                drug_mask = drug_mask & ta_mask

            drug_combined_mask = drug_combined_mask | drug_mask

        combined_mask = combined_mask & drug_combined_mask

    # Apply TA filters (OR across multiple TA selections, AND with other filter types)
    if ta_filters and "All Therapeutic Areas" not in ta_filters:
        ta_combined_mask = pd.Series([False] * len(source_df), index=source_df.index)
        for ta_filter in ta_filters:
            ta_mask = apply_therapeutic_area_filter(source_df, ta_filter)
            ta_combined_mask = ta_combined_mask | ta_mask
        combined_mask = combined_mask & ta_combined_mask

    # Apply session filters (OR across multiple session selections, AND with other filter types)
    # Use EXACT matching to distinguish "Poster" from "ePoster"
    if session_filters and "All Session Types" not in session_filters:
        session_combined_mask = pd.Series([False] * len(source_df), index=source_df.index)
        for session_filter in session_filters:
            if session_filter == "Symposia":
                # Special handling: Match any session containing "Symposium" EXCEPT "Industry-Sponsored Symposium"
                symposium_mask = source_df["Session"].str.contains("Symposium", case=False, na=False, regex=False)
                industry_mask = source_df["Session"] == "Industry-Sponsored Symposium"
                session_combined_mask = session_combined_mask | (symposium_mask & ~industry_mask)
            else:
                session_types = ESMO_SESSION_TYPES.get(session_filter, [])
                if session_types:
                    for session_type in session_types:
                        session_combined_mask = session_combined_mask | (source_df["Session"] == session_type)
        combined_mask = combined_mask & session_combined_mask

    # Apply date filters (OR across multiple date selections, AND with other filter types)
    # Use EXACT matching for dates
    if date_filters and "All Dates" not in date_filters:
        date_combined_mask = pd.Series([False] * len(source_df), index=source_df.index)
        for date_filter in date_filters:
            dates = ESMO_DATES.get(date_filter, [])
            if dates:
                for date in dates:
                    date_combined_mask = date_combined_mask | (source_df["Date"] == date)
        combined_mask = combined_mask & date_combined_mask

    # Apply combined mask and deduplicate
    filtered_df = source_df[combined_mask].copy()

    # Drop duplicates using base columns for deduplication
    base_columns = ['Title', 'Speakers', 'Speaker Location', 'Affiliation', 'Identifier',
                    'Room', 'Date', 'Time', 'Session', 'Theme']
    # Only use columns that exist in the DataFrame
    dedup_columns = [col for col in base_columns if col in filtered_df.columns]
    filtered_df = filtered_df.drop_duplicates(subset=dedup_columns)

    return filtered_df

# ============================================================================
# SEARCH LOGIC
# ============================================================================

def parse_boolean_query(query: str, df: pd.DataFrame, search_columns: list) -> pd.Series:
    """Parse boolean search with AND, OR, NOT operators."""
    # If no boolean operators, use simple search
    if not any(op in query.upper() for op in ['AND', 'OR', 'NOT']):
        return execute_simple_search(query, df, search_columns)

    # Parse the query into tokens and operators
    # Split by AND, OR while preserving case for search terms
    terms = []
    operators = []

    # Split query by boolean operators (case-insensitive)
    parts = re.split(r'\s+(AND|OR|NOT)\s+', query, flags=re.IGNORECASE)

    i = 0
    while i < len(parts):
        part = parts[i].strip()
        if not part:
            i += 1
            continue

        if part.upper() in ['AND', 'OR', 'NOT']:
            operators.append(part.upper())
            i += 1
        else:
            terms.append(part)
            i += 1

    # Build result mask
    if not terms:
        return pd.Series([False] * len(df), index=df.index)

    # Start with first term
    result_mask = execute_simple_search(terms[0], df, search_columns)

    # Process remaining terms with operators
    term_idx = 1
    op_idx = 0

    while term_idx < len(terms) and op_idx < len(operators):
        operator = operators[op_idx]

        if operator == 'NOT' and term_idx < len(terms):
            # NOT negates the next term and combines with previous result using AND
            not_mask = ~execute_simple_search(terms[term_idx], df, search_columns)
            result_mask = result_mask & not_mask
            term_idx += 1
            op_idx += 1
        elif operator == 'AND' and term_idx < len(terms):
            term_mask = execute_simple_search(terms[term_idx], df, search_columns)
            result_mask = result_mask & term_mask
            term_idx += 1
            op_idx += 1
        elif operator == 'OR' and term_idx < len(terms):
            term_mask = execute_simple_search(terms[term_idx], df, search_columns)
            result_mask = result_mask | term_mask
            term_idx += 1
            op_idx += 1
        else:
            op_idx += 1

    return result_mask

def execute_simple_search(keyword: str, df: pd.DataFrame, search_columns: list) -> pd.Series:
    """Execute smart search with quote support for exact matching."""
    # Initialize mask with same index as df to avoid index misalignment
    mask = pd.Series([False] * len(df), index=df.index)

    # Check if query is quoted (for exact match)
    is_quoted = (keyword.startswith('"') and keyword.endswith('"')) or (keyword.startswith("'") and keyword.endswith("'"))

    # ESMO columns (using original CSV names)
    esmo_columns = ['Title', 'Speakers', 'Speaker Location', 'Affiliation', 'Identifier', 'Room', 'Date', 'Time', 'Session', 'Theme']
    actual_columns = [col for col in esmo_columns if col in df.columns]

    if is_quoted:
        # Strip quotes and use exact matching with word boundaries
        keyword = keyword.strip('"').strip("'")
        # Use word boundaries for exact match (prevents "ATM" from matching "treatment")
        search_pattern = r'\b' + re.escape(keyword) + r'\b'

        for col in actual_columns:
            try:
                # Case-sensitive for quoted searches to match acronyms exactly
                col_mask = df[col].astype(str).str.contains(search_pattern, case=True, na=False, regex=True)
                mask = mask | col_mask
            except Exception as e:
                continue
    else:
        # No quotes - use standard smart search
        # Check if multi-word query (contains space)
        is_multi_word = ' ' in keyword

        if is_multi_word:
            # Multi-word query: Use exact phrase matching with word boundaries
            # This prevents "mini oral" from matching "medical oral nutrition"
            search_pattern = r'\b' + re.escape(keyword) + r'\b'
            for col in actual_columns:
                try:
                    col_mask = df[col].astype(str).str.contains(search_pattern, case=False, na=False, regex=True)
                    mask = mask | col_mask
                except Exception as e:
                    continue
        else:
            # Single word query: Use partial substring matching
            # This allows "avel" to match "avelumab"
            for col in actual_columns:
                try:
                    col_mask = df[col].astype(str).str.contains(keyword, case=False, na=False, regex=False)
                    mask = mask | col_mask
                except Exception as e:
                    continue

    return mask

def highlight_search_results(df: pd.DataFrame, keyword: str) -> pd.DataFrame:
    """Add HTML highlighting to search results."""
    if df.empty:
        return df

    df_highlighted = df.copy()

    # Columns to highlight
    cols_to_highlight = ['Title', 'Speakers', 'Affiliation', 'Speaker Location', 'Session', 'Theme']

    for col in cols_to_highlight:
        if col in df_highlighted.columns:
            df_highlighted[col] = df_highlighted[col].astype(str).apply(
                lambda x: re.sub(
                    f'({re.escape(keyword)})',
                    r'<mark>\1</mark>',
                    x,
                    flags=re.IGNORECASE
                ) if keyword else x
            )

    return df_highlighted

# ============================================================================
# SMART QUERY CLASSIFICATION (GPT-5-MINI)
# ============================================================================

def detect_ambiguous_drug_query(user_query: str) -> dict:
    """
    Detect ambiguous drug queries that need clarification.
    Returns clarification response if ambiguous, None otherwise.
    """
    query_lower = user_query.lower()

    # Drug abbreviations
    drug_aliases = {
        'ev': 'enfortumab vedotin', 'p': 'pembrolizumab', 'pembro': 'pembrolizumab',
        'nivo': 'nivolumab', 'ipi': 'ipilimumab', 'atezo': 'atezolizumab',
        'durva': 'durvalumab', 'treme': 'tremelimumab', 'ave': 'avelumab'
    }

    # Ambiguous patterns: "with" or "and" (without clear combination indicator)
    ambiguous_patterns = [
        r'([\w\s-]+?)\s+with\s+([\w\s-]+?)(?:\s|$|,|\?)',
        r'([\w\s-]+?)\s+and\s+([\w\s-]+?)(?:\s|$|,|\?)',
    ]

    for pattern in ambiguous_patterns:
        matches = re.findall(pattern, query_lower)
        if matches:
            for match in matches:
                drug1_raw, drug2_raw = match[0].strip(), match[1].strip()

                # Expand abbreviations if single word
                drug1 = drug_aliases.get(drug1_raw, drug1_raw) if len(drug1_raw.split()) == 1 else drug1_raw
                drug2 = drug_aliases.get(drug2_raw, drug2_raw) if len(drug2_raw.split()) == 1 else drug2_raw

                # Skip non-drug words
                skip_words = ['the', 'and', 'or', 'with', 'plus', 'versus', 'vs', 'day', 'phase', 'line', 'stage', 'new', 'studies', 'about', 'tell', 'me', 'what', 'is', 'coming', 'out', 'on']
                if drug1_raw in skip_words or drug2_raw in skip_words or len(drug1_raw) < 2 or len(drug2_raw) < 2:
                    continue

                # Found ambiguous query - return clarification
                print(f"[AMBIGUOUS QUERY DETECTED] '{drug1}' and '{drug2}' - needs clarification")

                clarification = f"""I found studies mentioning **{drug1}** and **{drug2}**. To give you the most relevant results, please clarify:

**1. Combination therapy only** - Studies where both drugs are used together (e.g., {drug1} + {drug2})
**2. All studies** - Any study mentioning either drug (broader landscape view)
**3. Comparison studies** - Head-to-head trials comparing {drug1} vs {drug2}

Please respond with **1**, **2**, or **3**, or rephrase your query."""

                return {
                    "entity_type": "clarification_needed",
                    "clarification_question": clarification,
                    "generate_table": False,
                    "table_type": None,
                    "filter_context": {},
                    "pending_drugs": [drug1, drug2],  # Store for follow-up
                    "search_terms": []
                }

    return None


def detect_meta_query(user_query: str) -> Optional[str]:
    """
    Detect meta/conversational queries and provide natural responses.

    These are queries ABOUT the app itself, not searches for conference data.
    Handle them conversationally without triggering data search pipeline.

    Args:
        user_query: User's question

    Returns:
        Natural response string if meta query, None if data query
    """
    query_lower = user_query.lower().strip()

    # Quick greetings (exact match, highest priority)
    if re.match(r"^(hi|hello|hey)(\s|!|\?|$)", query_lower):
        return ("Hi! I'm your ESMO 2025 conference intelligence assistant. "
                "Ask me about specific drugs, therapeutic areas, investigators, or let me analyze trends for you. "
                "What would you like to explore?")

    if re.match(r"^(thank|thanks|thx)", query_lower):
        return "You're welcome! Let me know if you need anything else from the ESMO 2025 data."

    # Meta-query detection: Use keyword-based instead of exact regex
    # (more flexible, catches variations like "What are your capabilities?")

    # Capability keywords (broad, catches many variations)
    capability_keywords = ["capability", "capabilities", "can you", "able to", "what do you", "what are you", "tell me what", "what can"]
    question_keywords = ["what questions", "what can i ask", "what should i ask", "what type", "what kind", "example"]
    how_keywords = ["how do you work", "how does this work", "how does it work", "explain how", "how you work"]
    about_keywords = ["who made", "who created", "who built", "what is this", "who are you"]

    # Check if query is asking about capabilities
    if any(kw in query_lower for kw in capability_keywords):
        return ("I help medical affairs teams explore ESMO 2025 conference data. I can:\n\n"
                "**Search & Filter:**\n"
                "- Find studies by drug, therapeutic area, investigator, or institution\n"
                "- Filter by date, session type, or presentation format\n\n"
                "**Analysis:**\n"
                "- Summarize research themes and trends\n"
                "- Identify key opinion leaders and institutions\n"
                "- Compare competitive data\n"
                "- Highlight strategic studies for medical affairs\n\n"
                "Try asking: *\"Show me pembrolizumab bladder cancer studies\"* or *\"What's happening on October 18th?\"*")

    # Check if query is asking what to ask
    if any(kw in query_lower for kw in question_keywords):
        return ("You can ask me about:\n\n"
                "**Drug/Treatment Searches:**\n"
                "- \"What studies feature enfortumab vedotin?\"\n"
                "- \"Show me ADC studies\"\n"
                "- \"Tell me about TROP2-targeted therapies\"\n\n"
                "**KOL & Institution:**\n"
                "- \"Which studies is Giuseppe Curigliano presenting?\"\n"
                "- \"Show me Memorial Sloan Kettering presentations\"\n\n"
                "**Thematic Analysis:**\n"
                "- \"Summarize checkpoint inhibitor combinations\"\n"
                "- \"What are the trends in bladder cancer?\"\n\n"
                "**Logistics:**\n"
                "- \"What bladder sessions are on 10/18?\"\n"
                "- \"What time is KEYNOTE-905?\"")

    # Check if query is asking how it works
    if any(kw in query_lower for kw in how_keywords):
        return ("I search through ESMO 2025 conference data (4,686 studies) to find relevant presentations based on your query.\n\n"
                "**Behind the scenes:**\n"
                "1. I analyze your question to understand what you're looking for\n"
                "2. I expand drug abbreviations (e.g., \"EV\" → enfortumab vedotin)\n"
                "3. I search across titles, speakers, institutions, and themes\n"
                "4. I synthesize findings into strategic insights for medical affairs\n\n"
                "Full abstracts will be available October 13th - until then, I analyze titles and presenter data.")

    # Check if query is asking about origin
    if any(kw in query_lower for kw in about_keywords):
        return ("I'm a medical affairs intelligence tool built for analyzing ESMO 2025 conference data. "
                "I combine AI synthesis with conference program data to help teams identify strategic insights, "
                "track competitors, and engage with key opinion leaders.")

    return None


def detect_unambiguous_combination(user_query: str) -> dict:
    """
    Detect ONLY unambiguous combination queries (+ or "plus").
    Returns combination classification if detected, None otherwise.
    """
    query_lower = user_query.lower()

    # Drug abbreviations
    drug_aliases = {
        'ev': 'enfortumab vedotin', 'p': 'pembrolizumab', 'pembro': 'pembrolizumab',
        'nivo': 'nivolumab', 'ipi': 'ipilimumab', 'atezo': 'atezolizumab',
        'durva': 'durvalumab', 'treme': 'tremelimumab', 'ave': 'avelumab',
        'erda': 'erdafitinib', 'saci': 'sacituzumab govitecan', 'sg': 'sacituzumab govitecan'
    }

    # ONLY unambiguous patterns
    unambiguous_patterns = [
        r'([\w\s-]+?)\s*\+\s*([\w\s-]+?)(?:\s|$|,|\?)',  # drug1 + drug2
        r'([\w\s-]+?)\s+plus\s+([\w\s-]+?)(?:\s|$|,|\?)',  # drug1 plus drug2
        r'([\w-]+)[/-]([\w-]+)',  # EV/P format
    ]

    for pattern in unambiguous_patterns:
        matches = re.findall(pattern, query_lower)
        if matches:
            for match in matches:
                drug1_raw, drug2_raw = match[0].strip(), match[1].strip()

                # Expand abbreviations if single word
                drug1 = drug_aliases.get(drug1_raw, drug1_raw) if len(drug1_raw.split()) == 1 else drug1_raw
                drug2 = drug_aliases.get(drug2_raw, drug2_raw) if len(drug2_raw.split()) == 1 else drug2_raw

                # Skip non-drugs
                skip_words = ['the', 'and', 'or', 'with', 'versus', 'vs', 'day', 'phase', 'line', 'stage']
                if drug1_raw in skip_words or drug2_raw in skip_words or len(drug1_raw) < 2 or len(drug2_raw) < 2:
                    continue

                search_terms = [f"{drug1} {drug2}", f"{drug1} + {drug2}", f"{drug1} plus {drug2}"]

                print(f"[COMBINATION DETECTED] '{drug1_raw}' + '{drug2_raw}' → '{drug1} + {drug2}'")

                return {
                    "entity_type": "drug",
                    "search_terms": search_terms,
                    "generate_table": True,
                    "table_type": "drug_studies",
                    "filter_context": {"drug": f"{drug1} + {drug2}", "ta": None, "date": None, "session": None},
                    "top_n": 20,
                    "is_combination": True,
                    "clarification_question": None
                }

    return None


def detect_competitor_query(user_message: str, ta_filters: Optional[list] = None) -> Optional[List[str]]:
    """
    AI-powered competitor detection using drug database context.

    Detects queries like "show me competitor data" and determines which drugs
    are competitors to EMD Serono's avelumab based on indication and MOA.

    Args:
        user_message: User's query
        ta_filters: Active therapeutic area filters (e.g., ["bladder"])

    Returns:
        List of competitor drug names, or None if not a competitor query
    """
    # Quick check: does query mention "competitor" or "competition"?
    query_lower = user_message.lower()
    if "competitor" not in query_lower and "competition" not in query_lower and "competitive" not in query_lower:
        return None

    # Build TA context
    ta_context = ", ".join(ta_filters) if ta_filters else "bladder cancer (primary indication)"

    # Get available MOA classes from cache
    moa_summary = []
    for moa_class in ['ICI', 'ADC', 'TKI', 'Bispecific Antibody', 'Targeted Therapy']:
        if moa_class in MOA_DRUG_CACHE:
            moa_summary.append(f"- {moa_class}: {len(MOA_DRUG_CACHE[moa_class])} drugs")

    prompt = f"""You are analyzing a competitor intelligence query for EMD Serono's medical affairs team.

**COMPANY CONTEXT**:
- User company: EMD Serono (Merck KGaA/Pfizer)
- Key product: Avelumab (Bavencio)
- Drug class: PD-L1 checkpoint inhibitor (ICI)
- Primary indication: First-line maintenance metastatic urothelial/bladder cancer
- Current therapeutic area filter: {ta_context}

**DRUG DATABASE AVAILABLE**:
{chr(10).join(moa_summary)}

**USER QUERY**: "{user_message}"

**TASK**: Determine which drugs are COMPETITORS to avelumab in this context.

**REASONING**:
1. Avelumab is an ICI (checkpoint inhibitor) for bladder cancer
2. Direct competitors = other ICIs approved/studied in bladder cancer
3. Example competitors: pembrolizumab (Keytruda), nivolumab (Opdivo), atezolizumab (Tecentriq), durvalumab (Imfinzi)
4. May also include ADCs if they compete for same patient population (e.g., enfortumab vedotin)
5. EXCLUDE avelumab itself (don't show own product data)

**RETURN JSON**:
{{
  "is_competitor_query": true/false,
  "user_product": "avelumab",
  "competitor_drugs": ["drug1", "drug2", ...],
  "rationale": "brief 1-sentence explanation"
}}

**EXAMPLES**:
Query: "Show me competitor data" (bladder filter active)
Response: {{"is_competitor_query": true, "user_product": "avelumab", "competitor_drugs": ["pembrolizumab", "nivolumab", "atezolizumab", "durvalumab"], "rationale": "Other ICIs competing in 1L maintenance bladder cancer"}}

Query: "Compare our data to competitors" (bladder filter)
Response: {{"is_competitor_query": true, "user_product": "avelumab", "competitor_drugs": ["pembrolizumab", "nivolumab", "atezolizumab", "durvalumab", "enfortumab vedotin"], "rationale": "ICIs and leading ADC competing for same patient population"}}
"""

    try:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=[{"role": "user", "content": prompt}],
            text={"verbosity": "medium"},
            max_output_tokens=300
        )

        output_text = response.output_text
        print(f"[COMPETITOR DETECTION DEBUG] Raw AI response: {output_text[:500]}")

        # Strip markdown code blocks if present
        if output_text.startswith("```json"):
            output_text = output_text.replace("```json", "").replace("```", "").strip()
        elif output_text.startswith("```"):
            output_text = output_text.replace("```", "").strip()

        result = json.loads(output_text)

        if result.get("is_competitor_query"):
            competitor_drugs = result.get("competitor_drugs", [])
            print(f"[COMPETITOR DETECTION] Identified {len(competitor_drugs)} competitors: {competitor_drugs}")
            print(f"[COMPETITOR DETECTION] Rationale: {result.get('rationale')}")
            return competitor_drugs

        return None

    except Exception as e:
        print(f"[COMPETITOR DETECTION ERROR] {e}")
        print(f"[COMPETITOR DETECTION DEBUG] Failed to parse AI response")
        return None


def classify_user_query(user_message: str, conversation_history: list = None) -> dict:
    """
    Use GPT-5-mini to classify user query and extract search parameters.
    Returns structured JSON for dataset querying and table generation.
    """
    # Build conversation context if available
    history_context = ""
    if conversation_history and len(conversation_history) > 0:
        recent = conversation_history[-2:]  # Last 2 exchanges
        history_lines = []
        for exchange in recent:
            history_lines.append(f"User: {exchange.get('user', '')}")
            history_lines.append(f"Assistant: {exchange.get('assistant', '')[:200]}...")  # Truncate AI response
        history_context = "\n\n**CONVERSATION CONTEXT** (use to resolve pronouns like 'him', 'it', 'that'):\n" + "\n".join(history_lines)

    classification_prompt = f"""You are a query classifier for ESMO 2025 conference intelligence. Think like a medical affairs professional attending the conference.

**USER QUERY**: "{user_message}"{history_context}

**YOUR TASK**: Classify the query intent and return JSON for intelligent table generation. Use conversation context to resolve pronouns.

**AVAILABLE DATA**: Title, Speakers, Speaker Location, Affiliation, Identifier, Room, Date, Time, Session, Theme

**RETURN FORMAT** (JSON only, no explanation):
{{
  "entity_type": "drug" | "hcp" | "institution" | "session_type" | "date" | "therapeutic_area" | "drug_class" | "general" | "clarification_needed",
  "search_terms": ["term1", "term2"],
  "generate_table": true | false,
  "table_type": "author_publications" | "author_ranking" | "drug_studies" | "drug_class_ranking" | "institution_ranking" | "session_list" | null,
  "clarification_question": "Ask user for specifics if query is too vague" or null,
  "filter_context": {{
    "drug": "drug name if mentioned" or null,
    "ta": "therapeutic area if mentioned" or null,
    "date": "Day X if mentioned" or null,
    "session": "session type if mentioned" or null
  }},
  "top_n": 10
}}

**CLASSIFICATION PATTERNS** (95%+ coverage):

**1. SPECIFIC PERSON QUERIES** (author_publications table)
"Who is Andrea Necchi?" | "Tell me about Dr. Necchi" | "Necchi publications" | "What is Andrea Necchi presenting?"
→ {{"entity_type": "hcp", "search_terms": ["Andrea Necchi", "Necchi"], "generate_table": true, "table_type": "author_publications", "filter_context": {{}}, "top_n": 20}}

**2. TOP AUTHORS/SPEAKERS QUERIES** (author_ranking table)
"Who are the most active speakers?" | "Top 10 authors" | "Most prolific researchers" | "Leading KOLs" | "Who's presenting the most?"
→ {{"entity_type": "hcp", "search_terms": [], "generate_table": true, "table_type": "author_ranking", "filter_context": {{}}, "top_n": 10}}

**3. SPECIFIC DRUG QUERIES** (drug_studies table)
"What is enfortumab vedotin?" | "Tell me about EV" | "Avelumab data" | "Studies on pembrolizumab" | "Keytruda results"
→ {{"entity_type": "drug", "search_terms": ["enfortumab vedotin", "EV", "enfortumab"], "generate_table": true, "table_type": "drug_studies", "filter_context": {{"drug": "enfortumab vedotin"}}, "top_n": 20}}

NOTE: Drug combinations (EV + P, nivo plus ipi) are handled by pre-classification rules - you won't see them.

**4. DRUG CLASS/MOA QUERIES** (drug_class_ranking table)
"What is the most common drug class?" | "Show me drug classes" | "ADC vs ICI representation" | "Top MOA classes" | "What mechanisms are being studied?"
→ {{"entity_type": "drug_class", "search_terms": [], "generate_table": true, "table_type": "drug_class_ranking", "filter_context": {{}}, "top_n": 15}}

**5. INSTITUTION QUERIES** (institution_ranking table)
"Most active institutions" | "Top 15 hospitals" | "Leading research centers" | "Where is the research coming from?" | "Academic centers in bladder cancer"
→ {{"entity_type": "institution", "search_terms": [], "generate_table": true, "table_type": "institution_ranking", "filter_context": {{}}, "top_n": 15}}

**6. SESSION/SCHEDULE QUERIES** (session_list table)
"What posters are on day 3?" | "All presentations on Friday" | "Proffered papers in lung cancer" | "When are the oral sessions?" | "Show me symposia"
→ {{"entity_type": "session_type", "search_terms": ["poster"], "generate_table": true, "table_type": "session_list", "filter_context": {{"date": "Day 3"}}, "top_n": 50}}

**7. BIOMARKER/MECHANISM SPECIFIC QUERIES** (session_list table to show all studies)
"What's new in METex14?" | "Show me FGFR3 studies" | "HER2-positive data" | "PD-L1 biomarker studies" | "KRAS G12C research"
→ {{"entity_type": "drug", "search_terms": ["MET exon 14", "METex14"], "generate_table": true, "table_type": "session_list", "filter_context": {{}}, "top_n": 50}}

**CRITICAL RULE FOR BIOMARKER/MECHANISM QUERIES**:
- search_terms should ONLY include the biomarker/mechanism variations (e.g., ["MET exon 14", "METex14"])
- DO NOT include the therapeutic area (e.g., "NSCLC", "bladder cancer") in search_terms
- DO NOT include disease stage modifiers (e.g., "metastatic", "advanced") in search_terms
- User's active filters already handle TA/stage filtering
- Keep search_terms focused on the SPECIFIC biomarker/mutation only

**8. TREND/ANALYSIS QUERIES** (no table, just AI analysis)
"What are the latest trends?" | "Summarize immunotherapy data" | "Key takeaways" | "Emerging biomarkers" (too vague)
→ {{"entity_type": "general", "search_terms": ["immunotherapy"], "generate_table": false, "table_type": null, "filter_context": {{}}, "top_n": 15}}

**8. COMPARATIVE QUERIES** (generate_table: false, AI will analyze)
"Compare avelumab vs pembrolizumab" | "EV+pembro vs EV alone" | "ADCs vs ICIs" | "Phase 3 vs Phase 2 data"
→ {{"entity_type": "general", "search_terms": ["avelumab", "pembrolizumab", "comparison"], "generate_table": false, "table_type": null, "filter_context": {{}}, "top_n": 20}}

**9. VAGUE/UNCLEAR QUERIES** (ask for clarification)
"Tell me more" | "What else?" | "Interesting" | "Update me"
→ {{"entity_type": "clarification_needed", "clarification_question": "What specific topic, drug, researcher, or therapeutic area would you like to explore?", "generate_table": false, "table_type": null, "filter_context": {{}}, "top_n": 10}}

**KEY RULES**:
- Extract NUMBER from query ("top 15" → top_n: 15)
- Default top_n: 10 for rankings, 20 for entity searches, 50 for session lists
- If query mentions specific person name → author_publications (not ranking)
- If query asks "who are the most/top" → author_ranking (not specific author)
- If query mentions specific drug → drug_studies table
- If query asks about drug classes/MOAs → drug_class_ranking table
- If too vague → set clarification_needed with helpful question
- Recognize drug aliases: EV=enfortumab vedotin, pembro=pembrolizumab, nivo=nivolumab, atezo=atezolizumab
- **CRITICAL**: Avoid generic acronyms like "ADC", "ICI", "BDC", "MOA" as search terms - use full drug names only
- **CRITICAL**: For drug searches, prioritize FULL drug names over abbreviations to avoid false matches

**DRUGS**: avelumab (Bavencio), tepotinib, cetuximab (Erbitux), enfortumab vedotin (EV, Padcev), pembrolizumab (Keytruda), nivolumab (Opdivo), durvalumab (Imfinzi), atezolizumab (Tecentriq), disitamab vedotin (DV)

**THERAPEUTIC AREAS**: bladder/urothelial cancer, NSCLC, lung cancer, colorectal (CRC), head & neck (H&N, HNSCC), renal (RCC), gastric, breast, melanoma"""

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=[{"role": "user", "content": classification_prompt}],
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            max_output_tokens=400
        )

        classification = json.loads(response.output_text)
        return classification

    except Exception as e:
        print(f"[CLASSIFICATION ERROR] {e}")
        return {
            "entity_type": "general",
            "search_terms": [],
            "generate_table": False,
            "table_type": None,
            "filter_context": {},
            "top_n": 15
        }


def apply_filters_from_context(df: pd.DataFrame, filter_context: dict) -> pd.DataFrame:
    """Apply filters based on classification context."""
    filtered = df.copy()

    # Apply TA filter using ESMO_THERAPEUTIC_AREAS
    if filter_context.get("ta"):
        ta_name = filter_context["ta"]
        # Try to find matching TA in ESMO_THERAPEUTIC_AREAS (case-insensitive)
        ta_config = None
        for key, config in ESMO_THERAPEUTIC_AREAS.items():
            if ta_name.lower() in key.lower() or key.lower() in ta_name.lower():
                ta_config = config
                break

        if ta_config and ta_config.get("keywords"):
            mask = pd.Series([False] * len(filtered))
            for keyword in ta_config["keywords"]:
                mask |= filtered['Title'].str.contains(keyword, case=False, na=False)

            # Apply exclusions if present
            if ta_config.get("exclusions"):
                for exclusion in ta_config["exclusions"]:
                    mask &= ~filtered['Title'].str.contains(exclusion, case=False, na=False)

            filtered = filtered[mask]
        else:
            # Fallback to direct keyword search
            mask = filtered['Title'].str.contains(filter_context["ta"], case=False, na=False)
            filtered = filtered[mask]

    # Apply drug filter - just search for the drug name in Title
    if filter_context.get("drug"):
        drug_name = filter_context["drug"]
        mask = filtered['Title'].str.contains(drug_name, case=False, na=False)
        filtered = filtered[mask]

    # Apply session filter
    if filter_context.get("session"):
        filtered = filtered[filtered['Session'].str.contains(filter_context["session"], case=False, na=False)]

    # Apply date filter
    if filter_context.get("date"):
        # Extract date pattern (e.g., "Day 3" -> "10/19/2025")
        date_str = filter_context["date"]
        if "day" in date_str.lower():
            date_config = ESMO_DATES.get(date_str, [])
            if date_config:
                mask = pd.Series([False] * len(filtered))
                for date_val in date_config:
                    mask |= filtered['Date'].str.contains(date_val, case=False, na=False)
                filtered = filtered[mask]
        else:
            filtered = filtered[filtered['Date'].str.contains(date_str, case=False, na=False)]

    return filtered


def dataframe_to_custom_html(df: pd.DataFrame) -> str:
    """Convert dataframe to HTML table with data-full-text attributes for custom tooltips."""
    if df.empty:
        return ""

    headers = df.columns.tolist()

    # Build table HTML manually with data-full-text attributes
    html = '<table class="table table-sm table-striped">\n<thead>\n<tr>'
    for header in headers:
        html += f'<th>{header}</th>'
    html += '</tr>\n</thead>\n<tbody>\n'

    for _, row in df.iterrows():
        html += '<tr>'
        for header in headers:
            value = str(row[header]) if pd.notna(row[header]) else ''
            # Escape HTML but preserve existing tags (for search highlighting)
            display_value = value
            html += f'<td data-full-text="{value}">{display_value}</td>'
        html += '</tr>\n'

    html += '</tbody>\n</table>'
    return html

def generate_entity_table(classification: dict, df: pd.DataFrame) -> tuple:
    """Generate appropriate table based on classification."""

    table_type = classification.get("table_type")
    search_terms = classification.get("search_terms", [])
    filter_ctx = classification.get("filter_context", {})
    top_n = classification.get("top_n", 10)

    # For entity searches (drug, author), search the FULL dataset first
    # Then optionally narrow by TA/date AFTER finding the entity
    # This ensures we find "disitamab vedotin" even if filter_context has TA filters

    if table_type in ["drug_studies", "author_publications"]:
        # Use full dataset for entity search (find specific drug/author regardless of filters)
        filtered_df = df.copy()
    else:
        # Apply filter context for ranking/aggregation tables (author_ranking, institution_ranking, etc.)
        filtered_df = apply_filters_from_context(df, filter_ctx)

    if table_type == "author_publications":
        # Search for author in Speakers column
        if not search_terms:
            return "", pd.DataFrame()

        print(f"[AUTHOR SEARCH] Searching for: {search_terms} in {len(filtered_df)} records")

        mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
        for term in search_terms:
            term_mask = filtered_df['Speakers'].str.contains(term, case=False, na=False)
            matches = term_mask.sum()
            print(f"[AUTHOR SEARCH] Term '{term}' found {matches} matches")
            mask |= term_mask

        results = filtered_df[mask][['Identifier', 'Title', 'Speakers', 'Affiliation', 'Session', 'Room', 'Date']].head(top_n)

        print(f"[AUTHOR SEARCH] Total results: {len(results)}")

        if results.empty:
            no_results_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>📊 Author Search: {search_terms[0]}</h6>
<p class='text-muted' style='margin: 0;'>No presentations found for "{search_terms[0]}" in the ESMO 2025 dataset. Try searching for the full name or last name only.</p>
</div>"""
            return no_results_html, results

        table_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>📊 Publications by {search_terms[0]} ({len(results)} found)</h6>
{dataframe_to_custom_html(results)}
</div>"""
        return table_html, results

    elif table_type == "author_ranking":
        # Generate top authors ranking (like KOL button)
        print(f"[AUTHOR RANKING] Generating top {top_n} authors from {len(filtered_df)} records")

        # Use existing generate_top_authors_table function
        ranking_df = generate_top_authors_table(filtered_df, n=top_n)

        if ranking_df.empty:
            no_results_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>📊 Top {top_n} Most Active Speakers</h6>
<p class='text-muted' style='margin: 0;'>No speaker data available in the current dataset.</p>
</div>"""
            return no_results_html, ranking_df

        context_str = ""
        if filter_ctx.get('ta'):
            context_str = f" in {filter_ctx.get('ta')}"
        elif filter_ctx.get('drug'):
            context_str = f" for {filter_ctx.get('drug')}"

        table_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>📊 Top {top_n} Most Active Speakers{context_str}</h6>
{dataframe_to_custom_html(ranking_df)}
</div>"""
        return table_html, ranking_df

    elif table_type == "drug_studies":
        # Simple approach: AI extracts drug names → match against Drug_Company_names.csv → search titles
        if not search_terms:
            return "", pd.DataFrame()

        print(f"[DRUG SEARCH] Raw search terms from AI: {search_terms}")

        # Load drug database
        try:
            drug_db_path = Path(__file__).parent / "Drug_Company_names.csv"
            drug_db = pd.read_csv(drug_db_path, encoding='utf-8-sig')
        except Exception as e:
            print(f"[DRUG SEARCH] Could not load Drug_Company_names.csv: {e}")
            drug_db = None

        # Step 1: Match search terms to known drugs in database
        matched_drugs = []
        if drug_db is not None:
            for term in search_terms:
                term_lower = term.lower().strip()
                # Skip empty or very short search terms
                if not term_lower or len(term_lower) < 3:
                    continue

                for _, drug_row in drug_db.iterrows():
                    commercial = str(drug_row['drug_commercial']).lower().strip() if pd.notna(drug_row['drug_commercial']) else ""
                    generic = str(drug_row['drug_generic']).lower().strip() if pd.notna(drug_row['drug_generic']) else ""

                    # Skip empty drug names (prevents empty string matching)
                    if not commercial:
                        commercial = None
                    if not generic:
                        generic = None

                    # Match if term is in commercial/generic name or vice versa
                    # BUT: Skip if either string is empty/None to prevent false matches
                    matched = False
                    if commercial and (term_lower in commercial or commercial in term_lower):
                        matched = True
                    elif generic and (term_lower in generic or generic in term_lower):
                        matched = True

                    if matched:
                        # Use generic name WITHOUT suffix (e.g., "enfortumab vedotin" not "enfortumab vedotin-ejfv")
                        drug_name = str(drug_row['drug_generic']).strip() if pd.notna(drug_row['drug_generic']) else str(drug_row['drug_commercial']).strip()

                        # Remove suffixes like "-ejfv", "-nxki", etc. (keep base name only)
                        drug_name = drug_name.split('-')[0].strip()

                        if drug_name and drug_name not in matched_drugs:
                            matched_drugs.append(drug_name)
                            print(f"[DRUG SEARCH] Matched '{term}' → '{drug_name}'")
                        break

        # If no database matches, use search terms as-is
        if not matched_drugs:
            matched_drugs = search_terms
            print(f"[DRUG SEARCH] No database matches, using raw terms")

        print(f"[DRUG SEARCH] Final drug list: {matched_drugs}")

        # Step 2: If multiple drugs → AND logic (combination), else → OR logic (single drug)
        if len(matched_drugs) >= 2:
            print(f"[DRUG SEARCH] Multiple drugs detected → AND logic (all must be present)")
            mask = pd.Series([True] * len(filtered_df), index=filtered_df.index)
            for drug in matched_drugs:
                drug_mask = filtered_df['Title'].str.contains(drug, case=False, na=False)
                matches = drug_mask.sum()
                print(f"[DRUG SEARCH] '{drug}' appears in {matches} titles")
                mask &= drug_mask
            final_count = mask.sum()
            print(f"[DRUG SEARCH] Result: {final_count} studies with ALL {len(matched_drugs)} drugs")
        else:
            print(f"[DRUG SEARCH] Single drug → OR logic")
            mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
            for drug in matched_drugs:
                drug_mask = filtered_df['Title'].str.contains(drug, case=False, na=False)
                matches = drug_mask.sum()
                print(f"[DRUG SEARCH] '{drug}' found in {matches} titles")
                mask |= drug_mask

        results = filtered_df[mask][['Identifier', 'Title', 'Speakers', 'Affiliation', 'Session', 'Room', 'Date']].head(top_n)

        # Try to find MOA info for the searched drug
        moa_class = "Unknown"
        moa_target = "Unknown"
        if drug_db is not None and search_terms:
            search_term = search_terms[0].lower()
            for _, drug_row in drug_db.iterrows():
                commercial = str(drug_row['drug_commercial']).lower() if pd.notna(drug_row['drug_commercial']) else ""
                generic = str(drug_row['drug_generic']).lower() if pd.notna(drug_row['drug_generic']) else ""
                if search_term in commercial or search_term in generic or commercial in search_term or generic in search_term:
                    moa_class = str(drug_row['moa_class']) if pd.notna(drug_row['moa_class']) else "Unknown"
                    moa_target = str(drug_row['moa_target']) if pd.notna(drug_row['moa_target']) else "Unknown"
                    break

        # Add MOA columns to results
        results['MOA Class'] = moa_class
        results['MOA Target'] = moa_target

        print(f"[DRUG SEARCH] Total results: {len(results)}, MOA: {moa_class} ({moa_target})")

        if results.empty:
            no_results_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>💊 Drug Search: {search_terms[0]}</h6>
<p class='text-muted' style='margin: 0;'>No studies found in the ESMO 2025 dataset mentioning "{search_terms[0]}". This drug may not be featured at this conference.</p>
</div>"""
            return no_results_html, results

        table_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>💊 Studies mentioning {search_terms[0]} ({len(results)} found)</h6>
<p class='text-muted small' style='margin: 0 0 8px 0;'>MOA: {moa_class} | Target: {moa_target}</p>
{dataframe_to_custom_html(results)}
</div>"""
        return table_html, results

    elif table_type == "institution_ranking":
        # Count publications per institution
        institution_counts = filtered_df['Affiliation'].value_counts().head(top_n)
        ranking_df = pd.DataFrame({
            'Rank': range(1, len(institution_counts) + 1),
            'Institution': institution_counts.index,
            'Publications': institution_counts.values
        })

        context_str = f" in {filter_ctx.get('ta', 'all areas')}" if filter_ctx.get('ta') else ""
        table_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>🏥 Top {top_n} Most Active Institutions{context_str}</h6>
{dataframe_to_custom_html(ranking_df)}
</div>"""
        return table_html, ranking_df

    elif table_type == "drug_class_ranking":
        # FAST: Use pattern matching for common MOA classes instead of drug database
        print(f"[DRUG CLASS RANKING] Fast MOA analysis of {len(filtered_df)} studies")

        # Define MOA patterns (most common mechanisms in oncology)
        moa_patterns = {
            "ICI (Immune Checkpoint Inhibitor)": [
                "pembrolizumab", "nivolumab", "atezolizumab", "durvalumab", "avelumab",
                "ipilimumab", "tremelimumab", "tislelizumab", "toripalimab", "sintilimab",
                "pd-1", "pd-l1", "ctla-4", "checkpoint", "anti-pd"
            ],
            "ADC (Antibody-Drug Conjugate)": [
                "enfortumab", "sacituzumab", "trastuzumab deruxtecan", "disitamab",
                "datopotamab", "patritumab", "mirvetuximab", "tisotumab",
                "antibody-drug", "adc", "conjugate", "vedotin", "deruxtecan", "govitecan"
            ],
            "Targeted Therapy - FGFR": [
                "erdafitinib", "pemigatinib", "futibatinib", "infigratinib", "fgfr"
            ],
            "Targeted Therapy - MET": [
                "tepotinib", "capmatinib", "savolitinib", "crizotinib", "met inhibitor", "met exon"
            ],
            "Targeted Therapy - EGFR": [
                "osimertinib", "erlotinib", "gefitinib", "afatinib", "dacomitinib",
                "amivantamab", "cetuximab", "panitumumab", "egfr"
            ],
            "Targeted Therapy - HER2": [
                "tucatinib", "neratinib", "lapatinib", "pyrotinib", "her2"
            ],
            "Chemotherapy": [
                "carboplatin", "cisplatin", "gemcitabine", "paclitaxel", "docetaxel",
                "5-fu", "fluorouracil", "oxaliplatin", "irinotecan", "chemotherapy"
            ],
            "Antiangiogenic": [
                "bevacizumab", "ramucirumab", "lenvatinib", "cabozantinib", "regorafenib",
                "sorafenib", "sunitinib", "pazopanib", "vegf", "antiangiogenic"
            ],
            "PARP Inhibitor": [
                "olaparib", "niraparib", "rucaparib", "talazoparib", "parp"
            ],
            "CDK4/6 Inhibitor": [
                "palbociclib", "ribociclib", "abemaciclib", "cdk4", "cdk6"
            ]
        }

        # Count MOA occurrences using vectorized operations
        moa_counts = {}

        for moa_class, patterns in moa_patterns.items():
            count = 0
            # Create regex pattern for all drug names in this MOA
            pattern = '|'.join([re.escape(p) for p in patterns])

            # Count studies mentioning this MOA (vectorized)
            mask = filtered_df['Title'].str.contains(pattern, case=False, na=False, regex=True)
            count = mask.sum()

            if count > 0:
                moa_counts[moa_class] = count
                print(f"[DRUG CLASS RANKING] {moa_class}: {count} studies")

        if not moa_counts:
            no_results_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>💊 Drug Class Distribution</h6>
<p class='text-muted' style='margin: 0;'>No drug MOA classes detected in the current dataset.</p>
</div>"""
            return no_results_html, pd.DataFrame()

        # Create ranking dataframe
        ranking_df = pd.DataFrame(list(moa_counts.items()), columns=['MOA Class', '# Studies'])
        ranking_df = ranking_df.sort_values('# Studies', ascending=False).head(top_n)
        ranking_df['Rank'] = range(1, len(ranking_df) + 1)
        ranking_df = ranking_df[['Rank', 'MOA Class', '# Studies']]

        context_str = ""
        if filter_ctx.get('ta'):
            context_str = f" in {filter_ctx.get('ta')}"

        table_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>💊 Top {top_n} Drug Classes by Study Count{context_str}</h6>
{dataframe_to_custom_html(ranking_df)}
</div>"""
        return table_html, ranking_df

    elif table_type == "session_list":
        # Filter by session type or search terms in Title
        if search_terms:
            mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)

            # DEBUG: Let's see what we're searching for
            print(f"[SESSION_LIST] Searching for terms: {search_terms}")

            for term in search_terms:
                # Multiple search strategies to catch ALL variations
                term_lower = term.lower()

                # Strategy 1: Search across Title, Speakers, and Affiliation (like retrieve_comprehensive_data)
                term_mask_1 = (
                    filtered_df['Title'].str.contains(term, case=False, na=False, regex=False) |
                    filtered_df['Speakers'].str.contains(term, case=False, na=False, regex=False) |
                    filtered_df['Affiliation'].str.contains(term, case=False, na=False, regex=False)
                )

                # Strategy 2: Normalized search (remove spaces, hyphens, parentheses) on Title
                term_normalized = term_lower.replace(" ", "").replace("-", "").replace("exon", "ex")
                title_normalized = filtered_df['Title'].str.lower().str.replace(" ", "", regex=False).str.replace("-", "", regex=False).str.replace("(", "", regex=False).str.replace(")", "", regex=False)
                term_mask_2 = title_normalized.str.contains(term_normalized, na=False, regex=False)

                # Strategy 3: MET-specific flexible search
                # Catches: "METex14", "MET exon 14", "MET Exon 14 Skipping", etc.
                if "met" in term_lower and ("ex" in term_lower or "exon" in term_lower):
                    # Search for "metex14" OR "metexon14" anywhere in normalized title
                    # This catches "(METex14)", "MET exon 14 skipping", etc.
                    term_mask_3 = (
                        title_normalized.str.contains("metex14", na=False, regex=False) |
                        title_normalized.str.contains("metexon14", na=False, regex=False)
                    )
                else:
                    term_mask_3 = pd.Series([False] * len(filtered_df), index=filtered_df.index)

                # Combine all strategies
                combined_mask = term_mask_1 | term_mask_2 | term_mask_3
                mask |= combined_mask

                # DEBUG: Show what each term found
                matches_1 = term_mask_1.sum()
                matches_2 = term_mask_2.sum()
                matches_3 = term_mask_3.sum()
                matches_total = combined_mask.sum()
                print(f"[SESSION_LIST] Term '{term}': multi-field={matches_1}, normalized={matches_2}, MET-specific={matches_3}, total={matches_total}")

            results = filtered_df[mask]
            print(f"[SESSION_LIST] Total results after all terms: {len(results)}")
        else:
            results = filtered_df

        results = results[['Identifier', 'Title', 'Speakers', 'Room', 'Time', 'Date']].head(top_n)

        context_str = " matching criteria" if filter_ctx else ""
        table_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>📅 Sessions{context_str} ({len(results)} found)</h6>
{dataframe_to_custom_html(results)}
</div>"""
        return table_html, results

    return "", pd.DataFrame()

# ============================================================================
# TABLE GENERATION FUNCTIONS
# ============================================================================

def generate_top_authors_table(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Generate top N authors by unique abstracts."""
    try:
        print(f"[TABLE] generate_top_authors_table called with {len(df)} rows")
        if df.empty:
            print(f"[TABLE] Input dataframe is empty")
            return pd.DataFrame()

        # Filter out rows with empty/null speaker names before grouping
        df_with_speakers = df[df['Speakers'].notna() & (df['Speakers'].str.strip() != '')]
        print(f"[TABLE] Found {len(df_with_speakers)} rows with speakers")

        if df_with_speakers.empty:
            print(f"[TABLE] No speakers found after filtering")
            return pd.DataFrame()

        # Count unique studies per speaker
        author_counts = df_with_speakers.groupby('Speakers').agg({
            'Identifier': 'count',
            'Affiliation': 'first',
            'Speaker Location': 'first'
        }).reset_index()

        author_counts.columns = ['Speaker', '# Studies', 'Affiliation', 'Location']
        author_counts = author_counts.sort_values('# Studies', ascending=False).head(n)

        print(f"[TABLE] Generated authors table with {len(author_counts)} rows")
        return author_counts

    except Exception as e:
        print(f"[TABLE] ERROR in generate_top_authors_table: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

def generate_top_institutions_table(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """Generate top N institutions by unique abstracts."""
    if df.empty:
        return pd.DataFrame()

    # Normalize institution names (extract main institution from complex affiliations)
    def normalize_institution(affiliation):
        if pd.isna(affiliation) or affiliation == '' or str(affiliation).strip() == '':
            return None  # Return None for empty/invalid so we can filter out

        # Remove department/division prefixes
        aff = re.sub(r'^Department of [^,]+,\s*', '', str(affiliation), flags=re.IGNORECASE)
        aff = re.sub(r'^Division of [^,]+,\s*', '', aff, flags=re.IGNORECASE)
        aff = re.sub(r'^Institute of [^,]+,\s*', '', aff, flags=re.IGNORECASE)
        aff = re.sub(r'^School of [^,]+,\s*', '', aff, flags=re.IGNORECASE)
        aff = re.sub(r'^Faculty of [^,]+,\s*', '', aff, flags=re.IGNORECASE)
        aff = re.sub(r'^Center for [^,]+,\s*', '', aff, flags=re.IGNORECASE)
        aff = re.sub(r'^Centre for [^,]+,\s*', '', aff, flags=re.IGNORECASE)

        # Extract main institution (first part before comma)
        parts = aff.split(',')
        if len(parts) > 0:
            institution = parts[0].strip()

            # Filter out generic terms and single city names
            generic_terms = [
                'department of medicine', 'school of medicine', 'institute of pathology',
                'division of oncology', 'department of oncology', 'medical oncology',
                'clinical oncology', 'radiation oncology', 'medicine', 'oncology',
                'pathology', 'surgery', 'radiology', 'pharmacy'
            ]

            # Check if institution is too short (likely just a city) or generic
            if len(institution) < 10 or institution.lower() in generic_terms:
                # Try second part if available (might be the actual institution name)
                if len(parts) > 1:
                    institution = parts[1].strip()
                    # Still filter out if too short
                    if len(institution) < 10:
                        return None
                else:
                    return None

            if institution:  # Only return if non-empty
                return institution
        return None

    df['normalized_institution'] = df['Affiliation'].apply(normalize_institution)

    # Filter out None/empty institutions before grouping
    df_with_institutions = df[df['normalized_institution'].notna()]

    if df_with_institutions.empty:
        return pd.DataFrame()

    # Fuzzy merge similar institution names
    def get_canonical_name(institution):
        """Map similar institution names to canonical form."""
        inst_lower = institution.lower()

        # IRCCS variants
        if 'irccs' in inst_lower and ('san raffaele' in inst_lower or 'raffaele' in inst_lower):
            return 'IRCCS San Raffaele Hospital'
        if 'fondazione irccs' in inst_lower or 'irccs istituto' in inst_lower:
            # Generic IRCCS - use original name
            return institution

        # Dana-Farber variants (with or without partners)
        if 'dana-farber' in inst_lower or 'dana farber' in inst_lower:
            return 'Dana-Farber Cancer Institute'

        # MD Anderson variants
        if 'md anderson' in inst_lower or 'anderson cancer' in inst_lower:
            return 'MD Anderson Cancer Center'

        # Memorial Sloan Kettering variants
        if 'sloan kettering' in inst_lower or 'mskcc' in inst_lower or 'memorial sloan' in inst_lower:
            return 'Memorial Sloan Kettering Cancer Center'

        # Johns Hopkins variants
        if 'johns hopkins' in inst_lower:
            return 'Johns Hopkins University'

        # Cleveland Clinic variants
        if 'cleveland clinic' in inst_lower:
            return 'Cleveland Clinic'

        # Mayo Clinic variants
        if 'mayo clinic' in inst_lower:
            return 'Mayo Clinic'

        # Default: return original
        return institution

    df_with_institutions['canonical_institution'] = df_with_institutions['normalized_institution'].apply(get_canonical_name)

    # Count unique studies per canonical institution
    inst_counts = df_with_institutions.groupby('canonical_institution').agg({
        'Identifier': 'count',
        'Speaker Location': lambda x: ', '.join(x.unique()[:3])  # Top 3 locations
    }).reset_index()

    inst_counts.columns = ['Institution', '# Studies', 'Locations']
    inst_counts = inst_counts.sort_values('# Studies', ascending=False).head(n)

    return inst_counts

def generate_biomarker_moa_table(df: pd.DataFrame) -> pd.DataFrame:
    """Generate comprehensive biomarker/MOA hits table."""
    if df.empty:
        return pd.DataFrame()

    # Comprehensive biomarker and MOA keywords (biological mechanisms only, no treatment terms)
    biomarkers_moas = [
        # Checkpoint inhibitors & IO targets
        "PD-1", "PD-L1", "CTLA-4", "LAG-3", "TIM-3", "TIGIT", "ICOS",
        # ADC targets
        "Nectin-4", "TROP-2", "HER2", "HER3", "CEACAM5", "FOLR1", "Claudin 18.2",
        # FGFR pathway
        "FGFR3", "FGFR2", "FGFR1", "FGFR4", "FGFR",
        # Tyrosine kinases
        "EGFR", "ALK", "ROS1", "MET", "KRAS", "BRAF", "RET", "NTRK",
        # Mismatch repair / microsatellite
        "MSI-H", "dMMR", "MSI",
        # Tumor mutational burden
        "TMB-high", "TMB",
        # Circulating biomarkers
        "ctDNA", "CTC",
        # DNA damage response
        "PARP", "ATR", "ATM", "BRCA1", "BRCA2", "BRCA", "HRD", "DDR",
        # Angiogenesis
        "VEGF", "VEGFR", "VEGFR2",
        # PI3K/AKT/mTOR pathway
        "PI3K", "AKT", "mTOR", "PIK3CA",
        # Cell cycle
        "CDK4/6", "CDK4", "CDK6",
        # WNT/beta-catenin
        "WNT", "beta-catenin",
        # Epigenetic
        "EZH2", "IDH1", "IDH2",
        # Heme targets
        "CD38", "BCMA", "CD20", "CD19",
        # Emerging targets
        "DLL3", "CLDN18.2", "B7-H3", "NaPi2b",
        # Resistance biomarkers
        "NRG1", "ERBB2", "ERBB3"
    ]

    results = []
    for keyword in biomarkers_moas:
        # Use word boundaries for short acronyms to prevent false matches
        if len(keyword) <= 6 and keyword.isupper():
            # Case-sensitive search with word boundaries for acronyms
            pattern = r'\b' + re.escape(keyword) + r'\b'
            mask = df['Title'].str.contains(pattern, case=True, na=False, regex=True)
        else:
            # Case-insensitive for longer terms
            mask = df['Title'].str.contains(keyword, case=False, na=False)

        if mask.sum() > 0:
            # Get matching studies
            matching_studies = df[mask]

            # Collect identifiers (handle NaN/empty values)
            identifiers = matching_studies['Identifier'].fillna('n/a').tolist()
            identifier_str = ', '.join([str(x) if x != 'n/a' else 'n/a' for x in identifiers[:10]])  # Limit to first 10
            if len(identifiers) > 10:
                identifier_str += f', +{len(identifiers) - 10} more'

            # Collect unique sessions
            sessions = matching_studies['Session'].fillna('n/a').unique().tolist()
            session_str = ', '.join([str(s)[:20] for s in sessions[:3]])  # First 3 sessions, truncated
            if len(sessions) > 3:
                session_str += f', +{len(sessions) - 3} more'

            results.append({
                'Biomarker/MOA': keyword,
                '# Studies': mask.sum(),
                'Identifiers': identifier_str,
                'Sessions': session_str
            })

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values('# Studies', ascending=False)

    return result_df

def classify_studies_with_drug_db(df: pd.DataFrame, therapeutic_area: str) -> pd.DataFrame:
    """
    Fast string-matching approach with MOA appending for combinations.
    Detects multiple drugs per abstract and creates ONE entry with concatenated MOAs.

    Args:
        df: DataFrame with 'Title' and 'Identifier' columns
        therapeutic_area: E.g., "Bladder Cancer", "Lung Cancer"

    Returns:
        DataFrame with columns: Drug, Company, MOA_Class, MOA_Target, Identifier, Title, Study_Type
    """
    if df.empty:
        return pd.DataFrame()

    print(f"[DRUG MATCHER] Classifying {len(df)} studies for {therapeutic_area} using drug database")

    # Load drug database
    try:
        drug_db_path = Path(__file__).parent / "Drug_Company_names.csv"
        drug_db = pd.read_csv(drug_db_path, encoding='utf-8-sig')
        print(f"[DRUG MATCHER] Loaded drug database with {len(drug_db)} drugs")
    except Exception as e:
        print(f"[DRUG MATCHER] ERROR: Could not load Drug_Company_names.csv: {e}")
        return pd.DataFrame()

    # EMD portfolio drugs to skip (unless in combination with competitor)
    emd_drugs = ['avelumab', 'bavencio', 'tepotinib', 'cetuximab', 'erbitux', 'pimicotinib']

    # Build drug lookup dictionary
    drug_lookup = {}
    for _, row in drug_db.iterrows():
        commercial = str(row['drug_commercial']).strip().lower() if pd.notna(row['drug_commercial']) else ""
        generic = str(row['drug_generic']).strip().lower() if pd.notna(row['drug_generic']) else ""
        company = str(row['company']).strip() if pd.notna(row['company']) else "Unknown"
        moa_class = str(row['moa_class']).strip() if pd.notna(row['moa_class']) else "Unknown"
        moa_target = str(row['moa_target']).strip() if pd.notna(row['moa_target']) else "Unknown"

        # Store both commercial and generic names
        if commercial:
            drug_lookup[commercial] = {
                'display_name': generic if generic else commercial,
                'company': company,
                'moa_class': moa_class,
                'moa_target': moa_target
            }
        if generic:
            # Handle base names (e.g., "enfortumab vedotin" from "enfortumab vedotin-ejfv")
            base_generic = generic.split('-')[0].strip() if '-' in generic else generic
            drug_lookup[generic] = {
                'display_name': generic,
                'company': company,
                'moa_class': moa_class,
                'moa_target': moa_target
            }
            if base_generic != generic:
                drug_lookup[base_generic] = {
                    'display_name': base_generic,
                    'company': company,
                    'moa_class': moa_class,
                    'moa_target': moa_target
                }

    # Process each abstract (444 drugs × 158 abstracts = ~70k comparisons, should be fast)
    results = []
    print(f"[DRUG MATCHER] Processing {len(df)} abstracts against {len(drug_lookup)} drugs...")

    for _, row in df.iterrows():
        title = row['Title'].lower()
        identifier = row['Identifier']

        # Find all drugs mentioned in this title
        # Use word boundaries for short drug names to avoid false matches (e.g., "pt" matching "patients")
        detected_drugs = []
        for drug_name, drug_info in drug_lookup.items():
            # Skip very short strings (≤2 chars) - too many false positives
            if len(drug_name) <= 2:
                continue

            # For short strings (3-5 chars), require word boundaries
            if len(drug_name) <= 5:
                import re
                pattern = r'\b' + re.escape(drug_name) + r'\b'
                if re.search(pattern, title):
                    detected_drugs.append((drug_name, drug_info))
            else:
                # Longer drug names can use simple substring matching
                if drug_name in title:
                    detected_drugs.append((drug_name, drug_info))

        # Remove duplicates (e.g., if both "enfortumab vedotin" and "enfortumab vedotin-ejfv" matched)
        # Keep the longer match
        unique_drugs = []
        for drug_name, drug_info in detected_drugs:
            # Check if this is a substring of any other detected drug
            is_substring = False
            for other_name, _ in detected_drugs:
                if drug_name != other_name and drug_name in other_name:
                    is_substring = True
                    break
            if not is_substring:
                unique_drugs.append((drug_name, drug_info))

        # Filter out EMD-only studies (but keep EMD + competitor combinations)
        non_emd_drugs = []
        emd_count = 0
        for drug_name, drug_info in unique_drugs:
            if drug_name in emd_drugs:
                emd_count += 1
            else:
                non_emd_drugs.append((drug_name, drug_info))

        # Skip if only EMD drugs detected
        if emd_count > 0 and len(non_emd_drugs) == 0:
            continue

        # Use non-EMD drugs (or all drugs if no EMD detected)
        final_drugs = non_emd_drugs if non_emd_drugs else unique_drugs

        if not final_drugs:
            continue

        # Build result entry
        if len(final_drugs) == 1:
            # Monotherapy
            drug_name, drug_info = final_drugs[0]
            results.append({
                'Drug': drug_info['display_name'],
                'Company': drug_info['company'],
                'MOA Class': drug_info['moa_class'],
                'MOA Target': drug_info['moa_target'],
                'Identifier': identifier,
                'Title': row['Title'],  # Full title, no truncation
                'Study Type': 'Monotherapy'
            })
        else:
            # Combination - append MOAs
            drug_names = []
            companies = []
            moa_classes = []
            moa_targets = []

            for drug_name, drug_info in final_drugs:
                drug_names.append(drug_info['display_name'])
                companies.append(drug_info['company'])
                moa_classes.append(drug_info['moa_class'])
                moa_targets.append(drug_info['moa_target'])

            results.append({
                'Drug': ' + '.join(drug_names),
                'Company': ' + '.join(companies),
                'MOA Class': ' + '.join(moa_classes),
                'MOA Target': '; '.join(moa_targets),
                'Identifier': identifier,
                'Title': row['Title'],  # Full title, no truncation
                'Study Type': 'Combination'
            })

    result_df = pd.DataFrame(results)

    # Sort alphabetically by Drug column (combinations will sort by first drug name)
    if not result_df.empty:
        result_df = result_df.sort_values('Drug', ascending=True)

    print(f"[DRUG MATCHER] Found {len(result_df)} competitor studies ({len([r for r in results if r['Study Type'] == 'Monotherapy'])} monotherapy, {len([r for r in results if r['Study Type'] == 'Combination'])} combination)")

    return result_df

def generate_competitor_table(df: pd.DataFrame, indication_keywords: list = None, focus_moa_classes: list = None, n: int = 200) -> pd.DataFrame:
    """
    LEGACY: Generate competitor drugs table using CSV with MOA/target data.
    Enhanced to detect combination therapies and prevent double-counting.

    Args:
        df: Dataframe to search
        indication_keywords: Keywords to filter by indication (e.g., ["bladder", "urothelial"])
        focus_moa_classes: MOA classes to focus on (e.g., ["ICI", "ADC", "Targeted Therapy"])
        n: Max results
    """
    if df.empty:
        return pd.DataFrame()

    print(f"[COMPETITOR] Generating table with indication_keywords: {indication_keywords}, MOA filters: {focus_moa_classes}")

    # Load drug database with MOA data
    try:
        drug_db_path = Path(__file__).parent / "Drug_Company_names.csv"
        drug_db = pd.read_csv(drug_db_path, encoding='utf-8-sig')
        print(f"[COMPETITOR] Loaded drug database with {len(drug_db)} drugs")
    except Exception as e:
        print(f"[COMPETITOR] ERROR: Could not load Drug_Company_names.csv: {e}")
        return pd.DataFrame()

    # EMD portfolio drugs to exclude from competitor list
    emd_drugs = ['avelumab', 'bavencio', 'tepotinib', 'cetuximab', 'erbitux', 'pimicotinib']

    # Build a drug name lookup for combination detection
    drug_lookup = {}
    for _, row in drug_db.iterrows():
        commercial = str(row['drug_commercial']).strip().lower() if pd.notna(row['drug_commercial']) else ""
        generic = str(row['drug_generic']).strip().lower() if pd.notna(row['drug_generic']) else ""
        moa_class = str(row['moa_class']).strip() if pd.notna(row['moa_class']) else ""

        if commercial:
            drug_lookup[commercial] = {'generic': generic, 'moa_class': moa_class}
        if generic:
            # Handle base names (e.g., "enfortumab vedotin" from "enfortumab vedotin-ejfv")
            base_generic = generic.split('-')[0].strip() if '-' in generic else generic
            drug_lookup[generic] = {'commercial': commercial, 'moa_class': moa_class}
            if base_generic != generic:
                drug_lookup[base_generic] = {'commercial': commercial, 'moa_class': moa_class}

    # Track processed abstracts to avoid duplicates in combinations
    processed_abstracts = set()
    results = []

    # Skip combination detection for now - it's too slow and causing timeouts
    # TODO: Optimize this in the future by only checking filtered abstracts
    combination_studies = []
    print(f"[COMPETITOR] Combination detection temporarily disabled for performance")

    # Second pass: Process monotherapy studies
    for _, drug_row in drug_db.iterrows():
        commercial = str(drug_row['drug_commercial']).strip() if pd.notna(drug_row['drug_commercial']) else ""
        generic = str(drug_row['drug_generic']).strip() if pd.notna(drug_row['drug_generic']) else ""
        company = str(drug_row['company']).strip() if pd.notna(drug_row['company']) else ""
        moa_class = str(drug_row['moa_class']).strip() if pd.notna(drug_row['moa_class']) else ""
        moa_target = str(drug_row['moa_target']).strip() if pd.notna(drug_row['moa_target']) else ""

        # Skip if no valid drug names
        if not commercial and not generic:
            continue

        # Skip EMD portfolio drugs
        if generic.lower() in emd_drugs or commercial.lower() in emd_drugs:
            continue

        # Filter by MOA class if specified
        if focus_moa_classes and moa_class and moa_class not in focus_moa_classes:
            continue

        # Determine drug display name early for debugging
        drug_display_name = generic if generic else commercial

        # Build search mask for this drug
        mask = pd.Series([False] * len(df), index=df.index)

        if commercial:
            mask = mask | df['Title'].str.contains(commercial, case=False, na=False, regex=False)
        if generic:
            # For generic names, also search for base name (e.g., "enfortumab vedotin" from "enfortumab vedotin-ejfv")
            mask = mask | df['Title'].str.contains(generic, case=False, na=False, regex=False)

            # Also try base name without suffix (split on hyphen and take first part if multi-word)
            base_generic = generic.split('-')[0].strip() if '-' in generic else generic
            if base_generic != generic and len(base_generic.split()) > 1:  # Only if it's a multi-word drug name
                mask = mask | df['Title'].str.contains(base_generic, case=False, na=False, regex=False)

        # Filter by indication keywords if specified - CRITICAL FIX
        original_mask_count = mask.sum()
        if indication_keywords and mask.any():
            indication_mask = pd.Series([False] * len(df), index=df.index)
            for keyword in indication_keywords:
                indication_mask = indication_mask | df['Title'].str.contains(keyword, case=False, na=False, regex=False)
            # Apply indication filter to ensure only studies with indication keywords are included
            original_count = mask.sum()
            mask = mask & indication_mask  # This should filter to ONLY studies with indication keywords
            filtered_count = mask.sum()
            if original_count > 0 and filtered_count == 0:
                # Drug was found but not in the right indication, skip entirely
                print(f"[COMPETITOR] Skipping {drug_display_name}: {original_count} studies found but 0 match indication")
                continue
            if filtered_count > 0:
                print(f"[COMPETITOR] {drug_display_name}: {original_count} total -> {filtered_count} after indication filter")
        elif indication_keywords:
            # No drug matches at all
            continue

        matching_abstracts = df[mask]

        if len(matching_abstracts) == 0:
            continue

        # Add all matching studies (combination detection disabled for now)
        for _, row in matching_abstracts.iterrows():
            results.append({
                'Drug': drug_display_name,
                'Company': company,
                'MOA Class': moa_class,
                'MOA Target': moa_target,
                'Identifier': row['Identifier'],
                'Title': row['Title'][:80] + '...' if len(row['Title']) > 80 else row['Title']
            })

    if not results:
        print(f"[COMPETITOR] No competitor drugs found")
        return pd.DataFrame()

    result_df = pd.DataFrame(results)

    # Add study count per drug for sorting (internal use)
    study_counts = result_df.groupby('Drug').size().to_dict()
    result_df['_study_count'] = result_df['Drug'].map(study_counts)

    # Drop duplicates and sort by study count
    result_df = result_df.drop_duplicates(subset=['Drug', 'Identifier'])
    result_df = result_df.sort_values(['_study_count', 'Drug'], ascending=[False, True])
    result_df = result_df.head(n)

    # Drop the internal sorting column before returning
    result_df = result_df.drop(columns=['_study_count'])

    print(f"[COMPETITOR] Found {len(result_df)} abstracts from {result_df['Drug'].nunique()} unique drugs")
    return result_df

def generate_drug_moa_ranking(competitor_df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """
    Generate summary ranking table showing # of studies per drug and MOA class.

    Args:
        competitor_df: Output from generate_competitor_table()
        n: Max drugs to show in ranking
    """
    if competitor_df.empty:
        return pd.DataFrame()

    # Group by drug and aggregate
    ranking = competitor_df.groupby(['Drug', 'Company', 'MOA Class']).agg({
        'Identifier': 'count'
    }).reset_index()

    ranking.columns = ['Drug', 'Company', 'MOA Class', '# Studies']
    ranking = ranking.sort_values('# Studies', ascending=False).head(n)

    print(f"[DRUG RANKING] Generated ranking with {len(ranking)} drugs")
    return ranking

def generate_emerging_threats_table(df: pd.DataFrame, indication_keywords: list = None, n: int = 20) -> pd.DataFrame:
    """
    Identify emerging threats: novel mechanisms, innovative combinations, early phase signals.

    Args:
        df: Dataframe to search
        indication_keywords: Keywords to filter by indication (e.g., ["bladder", "urothelial"])
        n: Max results to return
    """
    if df.empty:
        return pd.DataFrame()

    # IMPORTANT: Filter out Educational Sessions and entries without Identifiers
    # These are session titles/speakers, not actual research abstracts
    df = df[df['Identifier'].notna() & (df['Identifier'].str.strip() != '')].copy()
    print(f"[EMERGING] Analyzing {len(df)} actual studies (excluded non-abstract entries)")

    if df.empty:
        print("[EMERGING] No studies left after filtering session titles")
        return pd.DataFrame()

    try:
        drug_db_path = Path(__file__).parent / "Drug_Company_names.csv"
        drug_db = pd.read_csv(drug_db_path, encoding='utf-8-sig')
        print(f"[EMERGING] Loaded drug database with {len(drug_db)} drugs")
    except Exception as e:
        print(f"[EMERGING] ERROR: Could not load Drug_Company_names.csv: {e}")
        return pd.DataFrame()

    # EMD portfolio to exclude
    emd_drugs = ['avelumab', 'bavencio', 'tepotinib', 'cetuximab', 'erbitux', 'pimicotinib']

    # Find drugs with 3-5 mentions (emerging, not established)
    emerging = []
    for _, drug_row in drug_db.iterrows():
        commercial = str(drug_row['drug_commercial']).strip() if pd.notna(drug_row['drug_commercial']) else ""
        generic = str(drug_row['drug_generic']).strip() if pd.notna(drug_row['drug_generic']) else ""
        company = str(drug_row['company']).strip() if pd.notna(drug_row['company']) else ""
        moa_class = str(drug_row['moa_class']).strip() if pd.notna(drug_row['moa_class']) else "Unknown"
        moa_target = str(drug_row['moa_target']).strip() if pd.notna(drug_row['moa_target']) else "Unknown"

        if not commercial and not generic:
            continue

        # Skip EMD portfolio drugs
        if generic.lower() in emd_drugs or commercial.lower() in emd_drugs:
            continue

        # Build search mask
        mask = pd.Series([False] * len(df), index=df.index)
        if commercial:
            mask = mask | df['Title'].str.contains(commercial, case=False, na=False, regex=False)
        if generic:
            mask = mask | df['Title'].str.contains(generic, case=False, na=False, regex=False)

            # Also try base name without suffix (e.g., "enfortumab vedotin" from "enfortumab vedotin-ejfv")
            base_generic = generic.split('-')[0].strip() if '-' in generic else generic
            if base_generic != generic and len(base_generic.split()) > 1:
                mask = mask | df['Title'].str.contains(base_generic, case=False, na=False, regex=False)

        # Filter by indication keywords
        if indication_keywords:
            indication_mask = pd.Series([False] * len(df), index=df.index)
            for keyword in indication_keywords:
                indication_mask = indication_mask | df['Title'].str.contains(keyword, case=False, na=False, regex=False)
            mask = mask & indication_mask

        matching = df[mask]
        count = len(matching)

        # Emerging: 3-5 mentions (clear signal, not established)
        if 3 <= count <= 5:
            drug_name = generic if generic else commercial
            sample_title = matching.iloc[0]['Title'] if not matching.empty else ""

            emerging.append({
                'Drug': drug_name,
                'Company': company,
                'MOA Class': moa_class,
                'MOA Target': moa_target,
                '# Studies': count,
                'Sample Title': sample_title[:80] + '...' if len(sample_title) > 80 else sample_title
            })

    result_df = pd.DataFrame(emerging)
    if not result_df.empty:
        result_df = result_df.sort_values('# Studies', ascending=False).head(n)
        print(f"[EMERGING] Found {len(result_df)} emerging threats")

    return result_df

# ============================================================================
# INTELLIGENT QUERY ANALYSIS & SYNTHESIS HELPERS
# ============================================================================

def extract_filter_keywords_from_query(user_query: str) -> list:
    """
    Use ultra-fast AI (GPT-5-nano) to extract filter keywords from user query.

    This replaces hardcoded keyword lists and works across ALL therapeutic areas.

    Examples:
    - "metastatic bladder cancer" → ["metastatic", "advanced"]
    - "MIBC" → ["muscle invasive", "MIBC", "locally advanced"]
    - "first-line NSCLC" → ["first-line", "1L", "treatment-naive"]
    - "HER2+ breast cancer" → ["HER2-positive", "HER2+", "her2"]

    Returns: List of keywords to search in study titles
    """
    if not client:
        print("[FILTER EXTRACTION] OpenAI client not available, skipping AI extraction")
        return []

    extraction_prompt = f"""Extract filter keywords from this medical query for searching conference abstract TITLES.

User Query: "{user_query}"

Return a JSON list of keywords that should appear in abstract titles to match this query.

**RULES**:
1. Extract clinical settings: metastatic/advanced, early-stage, MIBC/NMIBC, 1L/2L, adjuvant/neoadjuvant, maintenance
2. Include common abbreviations and synonyms
3. Return ONLY keywords that would appear in study TITLES (not general concepts)
4. Maximum 5 keywords
5. If query is too general (e.g., "latest trends"), return empty list []

**EXAMPLES**:

Query: "metastatic bladder cancer mechanisms"
→ ["metastatic", "advanced", "stage IV"]

Query: "MIBC immunotherapy"
→ ["muscle invasive", "MIBC", "locally advanced"]

Query: "first-line NSCLC"
→ ["first-line", "1L", "treatment-naive", "frontline"]

Query: "HER2-positive breast cancer"
→ ["HER2-positive", "HER2+", "her2"]

Query: "METex14 skipping mNSCLC"
→ ["MET exon 14", "METex14", "MET ex14"]

Query: "neoadjuvant therapy outcomes"
→ ["neoadjuvant", "pre-surgery", "pre-operative"]

Query: "What are the latest trends?" (too general)
→ []

Return ONLY a JSON array, no explanation."""

    try:
        response = client.responses.create(
            model="gpt-5-nano",  # Ultra-fast extraction using GPT-5-nano
            input=[{"role": "user", "content": extraction_prompt}],
            reasoning={"effort": "minimal"},  # Minimal reasoning for simple extraction
            text={"verbosity": "low"},
            max_output_tokens=100  # Very short response
        )

        keywords = json.loads(response.output_text)
        print(f"[FILTER EXTRACTION] GPT-5-nano extracted {len(keywords)} keywords in {response.usage.total_tokens} tokens")
        return keywords if isinstance(keywords, list) else []

    except Exception as e:
        print(f"[FILTER EXTRACTION] Error: {e}")
        return []


def detect_query_intent(user_query: str) -> dict:
    """
    Detect query intent to route to appropriate synthesis strategy.

    Returns:
        {
            "intent": "comparative" | "synthesis" | "specific_data" | "predictive" | "exploratory",
            "verbosity": "quick" | "comprehensive",  # Detected from query
            "entities": [...],  # Extracted entities (drugs, biomarkers, etc)
            "comparison_type": "efficacy" | "safety" | "biomarkers" | None
        }
    """
    query_lower = user_query.lower()

    # Detect verbosity preference (GPT-5 accepts: "low", "medium", "high")
    verbosity = "medium"  # Default
    if any(word in query_lower for word in ["quick", "brief", "summary", "tldr", "short"]):
        verbosity = "low"
    elif any(word in query_lower for word in ["comprehensive", "detailed", "in-depth", "thorough", "complete"]):
        verbosity = "high"

    # Detect intent patterns
    if any(word in query_lower for word in ["compare", "vs", "versus", "difference between", "how does"]):
        intent = "comparative"
    elif any(word in query_lower for word in ["predict", "forecast", "trend", "what will", "next year"]):
        intent = "predictive"
    elif any(word in query_lower for word in ["what was the", "what's the", "show me the", "give me the"]):
        intent = "specific_data"
    elif any(word in query_lower for word in ["find", "identify", "which studies", "who is"]):
        intent = "exploratory"
    else:
        intent = "synthesis"  # Default: synthesize insights

    return {
        "intent": intent,
        "verbosity": verbosity,
        "entities": [],  # Will be filled by classify_user_query
        "comparison_type": None  # Will be determined if comparative
    }


def retrieve_comprehensive_data(user_query: str, filtered_df: pd.DataFrame, classification: dict, max_studies: int = None) -> pd.DataFrame:
    """
    Retrieve ALL relevant studies based on user query - no random sampling.

    Uses multi-stage filtering:
    1. Apply user's query filters (from classification)
    2. Detect clinical setting keywords (metastatic, MIBC, NMIBC, etc.)
    3. Semantic search if available
    4. Return ALL matches (or intelligently limited set)

    Args:
        user_query: User's natural language question
        filtered_df: Pre-filtered dataframe (by TA, drug, session, date)
        classification: Query classification from classify_user_query
        max_studies: Maximum studies to return (None = no limit, use AI reasoning to filter)

    Returns:
        DataFrame with ALL relevant studies for comprehensive synthesis
    """
    print(f"[COMPREHENSIVE RETRIEVAL] Starting with {len(filtered_df)} pre-filtered studies")

    # STEP 1: Use AI to extract SPECIFIC filter keywords (only for sub-filtering, not for main search)
    # Skip if search_terms already exist from classification (those are more precise!)
    if not classification.get('search_terms'):
        filter_keywords = extract_filter_keywords_from_query(user_query)

        # Apply AI-extracted filter keywords if any were found
        if filter_keywords:
            print(f"[COMPREHENSIVE RETRIEVAL] AI extracted filter keywords: {filter_keywords}")
            keyword_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)

            for keyword in filter_keywords:
                # IMPROVED: Handle keywords flexibly
                keyword_normalized = keyword.lower().replace(" ", "").replace("-", "")

                # Search both the keyword as-is AND the normalized version
                keyword_mask |= (
                    filtered_df['Title'].str.contains(keyword, case=False, na=False, regex=False) |
                    filtered_df['Title'].str.lower().str.replace(" ", "").str.replace("-", "").str.replace("(", "").str.replace(")", "").str.contains(keyword_normalized, na=False, regex=False)
                )

            filtered_by_keywords = filtered_df[keyword_mask]
            if len(filtered_by_keywords) > 0:
                print(f"[COMPREHENSIVE RETRIEVAL] Filtered to {len(filtered_by_keywords)} studies matching AI-extracted keywords")
                filtered_df = filtered_by_keywords
            else:
                print(f"[COMPREHENSIVE RETRIEVAL] No studies matched AI keywords, keeping full dataset")
    else:
        print(f"[COMPREHENSIVE RETRIEVAL] Using classification search_terms, skipping GPT-5-nano extraction")

    # STEP 2: Extract search terms from classification
    search_terms = classification.get('search_terms', [])

    # STEP 2.5: Expand search terms using drug database caches (ADC → 56 drugs, ICI → 44 drugs, etc.)
    if search_terms:
        original_count = len(search_terms)
        search_terms = expand_search_terms_with_database(search_terms)
        if len(search_terms) != original_count:
            print(f"[DRUG DATABASE] Expanded {original_count} search terms → {len(search_terms)} drugs")
            print(f"[DRUG DATABASE] Sample expanded terms: {search_terms[:5]}")

    if not search_terms:
        # No specific search terms - return all filtered data (including clinical setting filter)
        print(f"[COMPREHENSIVE RETRIEVAL] No search terms, using filtered dataset ({len(filtered_df)} studies)")
        return filtered_df

    # STEP 3: Match search terms to Drug_Company_names.csv and apply AND/OR logic
    # Skip drug database matching for biomarker/mechanism queries (session_list)
    table_type = classification.get('table_type')

    if table_type == 'session_list':
        # For biomarker/mechanism queries, use search terms directly without drug database matching
        print(f"[COMPREHENSIVE RETRIEVAL] Session list query detected - skipping drug database matching")
        matched_drugs = search_terms
    else:
        # Load drug database for actual drug queries
        try:
            drug_db_path = Path(__file__).parent / "Drug_Company_names.csv"
            drug_db = pd.read_csv(drug_db_path, encoding='utf-8-sig')
        except Exception as e:
            print(f"[COMPREHENSIVE RETRIEVAL] Could not load Drug_Company_names.csv: {e}")
            drug_db = None

        # Match search terms to known drugs
        matched_drugs = []
        if drug_db is not None:
            for term in search_terms:
                term_lower = term.lower().strip()
                # Skip empty or very short search terms
                if not term_lower or len(term_lower) < 3:
                    continue

                for _, drug_row in drug_db.iterrows():
                    commercial = str(drug_row['drug_commercial']).lower().strip() if pd.notna(drug_row['drug_commercial']) else ""
                    generic = str(drug_row['drug_generic']).lower().strip() if pd.notna(drug_row['drug_generic']) else ""

                    # Skip empty drug names (prevents empty string matching)
                    if not commercial:
                        commercial = None
                    if not generic:
                        generic = None

                    # Match if term is in commercial/generic name or vice versa
                    # BUT: Skip if either string is empty/None to prevent false matches
                    matched = False
                    if commercial and (term_lower in commercial or commercial in term_lower):
                        matched = True
                    elif generic and (term_lower in generic or generic in term_lower):
                        matched = True

                    if matched:
                        drug_name = str(drug_row['drug_generic']).strip() if pd.notna(drug_row['drug_generic']) else str(drug_row['drug_commercial']).strip()
                        drug_name = drug_name.split('-')[0].strip()  # Remove suffixes
                        if drug_name and drug_name not in matched_drugs:
                            matched_drugs.append(drug_name)
                            print(f"[COMPREHENSIVE RETRIEVAL] Matched '{term}' -> '{drug_name}'")
                        break

        # If no matches, use search terms as-is
        if not matched_drugs:
            matched_drugs = search_terms
            print(f"[COMPREHENSIVE RETRIEVAL] No database matches, using raw terms")

    print(f"[COMPREHENSIVE RETRIEVAL] Final drug list: {matched_drugs}")

    # For session_list (biomarkers/mechanisms), always use OR logic (search terms are variations of same thing)
    # For drug_studies with multiple drugs, use AND logic (drug combinations like "EV + P")
    if table_type == 'session_list':
        print(f"[COMPREHENSIVE RETRIEVAL] Session list → OR logic (search term variations)")
        relevant_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
        for term in matched_drugs:
            term_mask = (
                filtered_df['Title'].str.contains(term, case=False, na=False) |
                filtered_df['Speakers'].str.contains(term, case=False, na=False) |
                filtered_df['Affiliation'].str.contains(term, case=False, na=False)
            )
            relevant_mask |= term_mask  # OR logic
    elif len(matched_drugs) >= 2:
        print(f"[COMPREHENSIVE RETRIEVAL] Multiple drugs → AND logic (all must be present)")
        relevant_mask = pd.Series([True] * len(filtered_df), index=filtered_df.index)
        for drug in matched_drugs:
            drug_mask = (
                filtered_df['Title'].str.contains(drug, case=False, na=False) |
                filtered_df['Speakers'].str.contains(drug, case=False, na=False) |
                filtered_df['Affiliation'].str.contains(drug, case=False, na=False)
            )
            relevant_mask &= drug_mask  # AND logic
    else:
        print(f"[COMPREHENSIVE RETRIEVAL] Single drug → OR logic")
        relevant_mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
        for drug in matched_drugs:
            drug_mask = (
                filtered_df['Title'].str.contains(drug, case=False, na=False) |
                filtered_df['Speakers'].str.contains(drug, case=False, na=False) |
                filtered_df['Affiliation'].str.contains(drug, case=False, na=False)
            )
            relevant_mask |= drug_mask  # OR logic

    relevant_studies = filtered_df[relevant_mask]
    print(f"[COMPREHENSIVE RETRIEVAL] Found {len(relevant_studies)} studies matching search terms: {search_terms}")

    # Skip semantic expansion for session_list (biomarker) queries - we want exact matches only
    # If semantic search available and we have few results, expand with related studies
    if collection and len(relevant_studies) < 10 and table_type != 'session_list':
        try:
            results = collection.query(
                query_texts=[user_query],
                n_results=min(50, len(filtered_df))
            )

            if results and results['ids']:
                result_indices = [int(doc_id.replace('doc_', '')) for doc_id in results['ids'][0]]
                semantic_results = df_global.iloc[result_indices]
                semantic_results = semantic_results[semantic_results.index.isin(filtered_df.index)]

                # Combine with search term results
                combined = pd.concat([relevant_studies, semantic_results]).drop_duplicates()
                print(f"[COMPREHENSIVE RETRIEVAL] Expanded to {len(combined)} studies using semantic search")
                relevant_studies = combined
        except Exception as e:
            print(f"[COMPREHENSIVE RETRIEVAL] Semantic search failed: {e}")

    # Apply intelligent limiting if needed
    if max_studies and len(relevant_studies) > max_studies:
        print(f"[COMPREHENSIVE RETRIEVAL] Limiting to {max_studies} most relevant studies")
        # Prioritize: Session type (Proffered Paper > Mini Oral > Poster)
        session_priority = {'Proffered Paper': 1, 'Mini Oral Session': 2, 'Poster': 3, 'ePoster': 4}
        relevant_studies['_priority'] = relevant_studies['Session'].map(session_priority).fillna(5)
        relevant_studies = relevant_studies.sort_values('_priority').head(max_studies)
        relevant_studies = relevant_studies.drop(columns=['_priority'])

    return relevant_studies


def build_synthesis_prompt_pre_abstract(user_query: str, relevant_data: pd.DataFrame, classification: dict, verbosity: str = "medium", intent: str = "synthesis") -> str:
    """
    Build synthesis prompt for PRE-ABSTRACT state (only titles, authors, affiliations available).

    Focus on EXPECTATIONS based on:
    - Study titles (what topics/drugs/biomarkers)
    - Author expertise (who's presenting)
    - Institution prestige (where research is from)
    - Session type (oral vs poster, symposia vs educational)
    """

    # Format study data for AI - handle different table types
    # Standard columns: Identifier, Title, Speakers, Affiliation, Session, Date, Time
    # But some tables (drug_class_ranking, author_ranking, etc.) have different structures
    available_columns = list(relevant_data.columns)

    # Try to get standard columns, fall back to whatever is available
    desired_columns = ['Identifier', 'Title', 'Speakers', 'Affiliation', 'Session', 'Date', 'Time']
    columns_to_use = [col for col in desired_columns if col in available_columns]

    if not columns_to_use:
        # If none of the standard columns exist, use all available columns
        data_for_synthesis = relevant_data.to_markdown(index=False)
    else:
        data_for_synthesis = relevant_data[columns_to_use].to_markdown(index=False)

    if verbosity == "quick":
        synthesis_instructions = """Provide a CONCISE synthesis (3-5 key bullet points):
- Main research themes visible from titles
- Notable institutions/researchers
- Key drugs/mechanisms mentioned
- What to expect when full abstracts are released"""
    else:
        synthesis_instructions = """Provide a COMPREHENSIVE synthesis organized as:

**1. RESEARCH LANDSCAPE** (what's being presented):
- Dominant themes from study titles (mechanisms, biomarkers, treatment settings)
- Drug/therapy focus distribution
- Clinical development stages visible (Phase 1/2/3, early/late-line)

**2. KEY OPINION LEADER SIGNALS** (who's presenting):
- Leading institutions and their research focus
- Notable researcher names and their contributions
- Geographic distribution of research

**3. WHAT TO EXPECT** (anticipatory analysis):
- Based on titles and investigators, what data quality/impact is likely?
- Which presentations are high-priority for medical affairs?
- What questions remain unanswered (to be clarified when abstracts drop)?

**4. ROLE-SPECIFIC IMPLICATIONS**:
- **For MSLs**: Key discussion topics and KOL engagement opportunities
- **For Medical Directors**: Strategic positioning and portfolio implications
- **For Leadership**: Competitive landscape shifts and investment priorities"""

    prompt = f"""You are a medical affairs research analyst. Full conference abstracts are NOT YET AVAILABLE (release: Oct 13th).

Your task: Synthesize insights from study TITLES, AUTHORS, and SESSION INFO to help medical affairs prepare.

**USER QUESTION**: {user_query}

**AVAILABLE DATA**: Titles, authors, affiliations, session types, dates/times
**YOUR SCOPE**: {len(relevant_data)} relevant studies

**CRITICAL**: Since abstracts aren't available yet:
- Focus on WHAT'S BEING STUDIED (from titles)
- WHO'S PRESENTING (author expertise, institution prestige)
- WHEN/WHERE (session type indicates data maturity: oral > poster)
- DO NOT speculate about efficacy, safety, or clinical outcomes
- DO analyze expected themes, research priorities, and strategic implications

{synthesis_instructions}

**STUDY DATA** ({len(relevant_data)} studies):
{data_for_synthesis}

Synthesize insights based on the available metadata. Be analytical but acknowledge data limitations."""

    return prompt


def build_synthesis_prompt_post_abstract(user_query: str, relevant_data: pd.DataFrame, classification: dict, verbosity: str = "medium", intent: str = "synthesis") -> str:
    """
    Build synthesis prompt for POST-ABSTRACT state (full abstract text available).

    Focus on DATA SYNTHESIS:
    - Efficacy signals across studies
    - Safety patterns
    - Biomarker correlations
    - Treatment paradigm insights
    """

    # Get abstract column name
    abstract_col = 'Abstract' if 'Abstract' in relevant_data.columns else 'abstract'

    # Format study data INCLUDING abstracts for AI
    relevant_with_abstracts = relevant_data[relevant_data[abstract_col].notna() & (relevant_data[abstract_col].str.strip() != '')]

    if len(relevant_with_abstracts) == 0:
        print("[SYNTHESIS] Warning: No abstracts available for selected studies")
        return build_synthesis_prompt_pre_abstract(user_query, relevant_data, classification, verbosity)

    # Format for synthesis - include full abstracts
    # Handle missing columns gracefully
    formatted_abstracts = []
    for idx, row in relevant_with_abstracts.iterrows():
        # Try to get each field, use 'N/A' if missing
        identifier = row.get('Identifier', row.get('identifier', 'N/A'))
        title = row.get('Title', row.get('title', 'N/A'))
        speakers = row.get('Speakers', row.get('speakers', 'N/A'))
        affiliation = row.get('Affiliation', row.get('affiliation', 'N/A'))
        session = row.get('Session', row.get('session', 'N/A'))
        date = row.get('Date', row.get('date', 'N/A'))
        time = row.get('Time', row.get('time', 'N/A'))

        formatted_abstracts.append(f"""
**Abstract {identifier}**: {title}
**Authors**: {speakers} ({affiliation})
**Session**: {session} | {date} at {time}

**FULL ABSTRACT**:
{row[abstract_col][:2000]}{"..." if len(str(row[abstract_col])) > 2000 else ""}
---""")

    abstracts_text = "\n".join(formatted_abstracts[:50])  # Limit to 50 abstracts max to avoid token limits

    if verbosity == "quick":
        synthesis_instructions = """Provide a CONCISE data synthesis (5-7 bullet points):
- Key efficacy signals (ORR, PFS ranges across studies)
- Safety patterns (common AEs, dose-limiting toxicities)
- Biomarker insights (predictive/prognostic correlations)
- Consensus vs controversy across studies"""
    else:
        synthesis_instructions = """Provide a COMPREHENSIVE data synthesis:

**1. EFFICACY SYNTHESIS** (what the DATA shows):
- Response rates (ORR, DCR) - ranges and patterns
- Survival outcomes (PFS, OS) - median values and subgroup variations
- Treatment settings (1L, 2L+, maintenance) - efficacy by line
- Consensus: Where do multiple studies agree?
- Controversy: Where do results diverge?

**2. SAFETY PROFILE** (across all studies):
- Common adverse events (grade 3+ frequency)
- Dose-limiting toxicities
- Treatment discontinuation rates
- Class effects vs drug-specific signals

**3. BIOMARKER INSIGHTS** (predictive value):
- Which biomarkers predict response?
- Biomarker-selected vs unselected populations
- Cut-point validation across studies

**4. TREATMENT PARADIGM IMPLICATIONS**:
- Optimal treatment sequencing
- Combination strategies (what works with what?)
- Patient selection criteria
- Clinical practice impact

**5. ROLE-SPECIFIC IMPLICATIONS**:
- **For MSLs**: Key data talking points for HCP conversations
- **For Medical Directors**: Positioning vs competitors, evidence gaps
- **For Leadership**: Portfolio impact, partnership opportunities"""

    prompt = f"""You are a senior medical affairs scientific analyst synthesizing FULL ABSTRACT DATA from ESMO 2025.

**USER QUESTION**: {user_query}

**YOUR TASK**: Synthesize collective insights across {len(relevant_with_abstracts)} abstracts with FULL TEXT.

**CRITICAL INSTRUCTIONS**:
1. DO NOT list or describe individual abstracts
2. SYNTHESIZE patterns, trends, and insights ACROSS studies
3. ALWAYS cite Abstract #s when referencing specific data points
4. Identify where studies agree (consensus) and disagree (controversy)
5. Extract quantitative data (ORR, PFS, safety rates) when available
6. Focus on clinical implications and strategic insights

{synthesis_instructions}

**FULL ABSTRACTS** ({len(relevant_with_abstracts)} studies with complete data):
{abstracts_text}

Provide evidence-based synthesis grounded in the abstract data above."""

    return prompt


def add_role_specific_implications(synthesis_text: str, user_query: str, relevant_data: pd.DataFrame) -> str:
    """
    Auto-generate role-specific implications footer.
    Called after main synthesis to add tactical guidance for different roles.
    """

    # This would be added to the AI synthesis as a separate section
    # For now, we'll include it in the main prompt above
    # Future: Could be a second AI call or template-based

    return synthesis_text  # Placeholder - handled in prompts above


# ============================================================================
# AI STREAMING FUNCTIONS
# ============================================================================

def stream_openai_tokens(prompt: str, model: str = "gpt-5-mini", reasoning_effort: str = "medium", verbosity: str = "medium", system_prompt: str = None):
    """
    Stream tokens from OpenAI for SSE.

    Args:
        prompt: User prompt/query
        model: Model to use
        reasoning_effort: "low", "medium", or "high"
        verbosity: "low", "medium", or "high"
        system_prompt: Optional system prompt (defaults to MEDICAL_AFFAIRS_SYSTEM_PROMPT)
    """
    if not client:
        print("[OPENAI] ERROR: Client not initialized")
        yield "data: " + json.dumps({"text": "OpenAI API key not configured."}) + "\n\n"
        return

    # Map our verbosity terms to GPT-5 accepted values
    verbosity_map = {
        "quick": "low",
        "comprehensive": "high",
        "low": "low",
        "medium": "medium",
        "high": "high"
    }
    gpt5_verbosity = verbosity_map.get(verbosity, "medium")

    # Use default system prompt if not provided
    if system_prompt is None:
        system_prompt = MEDICAL_AFFAIRS_SYSTEM_PROMPT

    try:
        print(f"[OPENAI] Creating streaming response with model: {model}, reasoning: {reasoning_effort}, verbosity: {gpt5_verbosity}")
        print(f"[OPENAI] System prompt: {len(system_prompt)} chars")

        # Build messages with system prompt
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        stream = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": reasoning_effort},
            text={"verbosity": gpt5_verbosity},
            max_output_tokens=6000,  # Increased for comprehensive analysis
            stream=True
        )

        token_count = 0
        for event in stream:
            if event.type == "response.output_text.delta":
                token_count += 1
                yield "data: " + json.dumps({"text": event.delta}) + "\n\n"
            elif event.type == "response.done":
                # Check finish reason
                if hasattr(event, 'response') and hasattr(event.response, 'finish_reason'):
                    print(f"[OPENAI] Finish reason: {event.response.finish_reason}")

        print(f"[OPENAI] Streaming complete. Tokens sent: {token_count}")
        yield "data: [DONE]\n\n"

    except Exception as e:
        print(f"[OPENAI] ERROR: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        yield "data: " + json.dumps({"error": str(e)}) + "\n\n"

# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/health')
def health():
    """Health check endpoint for Railway (lightweight, no data loading required)."""
    return {"status": "ok", "service": "cosmic"}, 200

@app.route('/')
def index():
    """Render main page."""
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    """Get filtered conference data for Data Explorer tab."""
    # Get filter parameters
    drug_filters = request.args.getlist('drug_filters[]') or request.args.getlist('drug_filters') or []
    ta_filters = request.args.getlist('ta_filters[]') or request.args.getlist('ta_filters') or []
    session_filters = request.args.getlist('session_filters[]') or request.args.getlist('session_filters') or []
    date_filters = request.args.getlist('date_filters[]') or request.args.getlist('date_filters') or []

    # Apply multi-filters
    filtered_df = get_filtered_dataframe_multi(drug_filters, ta_filters, session_filters, date_filters)

    # Only limit display to 50 rows when NO filters are active (performance optimization)
    filters_active = bool(drug_filters or ta_filters or session_filters or date_filters)
    if not filters_active:
        display_df = filtered_df.head(50)
    else:
        display_df = filtered_df  # Show all filtered results

    # Convert to records for JSON serialization
    data_records = display_df[['Title', 'Speakers', 'Affiliation', 'Speaker Location', 'Identifier', 'Room',
                                 'Session', 'Date', 'Time', 'Theme']].to_dict('records')

    # Sanitize Unicode
    data_records = sanitize_data_structure(data_records)

    # Build filter summary with all filter types
    drugs_summary = ', '.join(drug_filters) if drug_filters else 'All Drugs'
    tas_summary = ', '.join(ta_filters) if ta_filters else 'All Therapeutic Areas'
    sessions_summary = ', '.join(session_filters) if session_filters else 'All Session Types'
    dates_summary = ', '.join(date_filters) if date_filters else 'All Days'

    return jsonify({
        "data": data_records,
        "count": len(filtered_df),
        "showing": len(display_df),
        "total": len(df_global) if df_global is not None else 4686,
        "filter_context": {
            "total_sessions": len(filtered_df),
            "total_available": len(df_global) if df_global is not None else 4686,
            "filter_summary": f"{drugs_summary} + {tas_summary} + {sessions_summary} + {dates_summary}",
            "filters_active": bool(drug_filters or ta_filters or session_filters or date_filters)
        }
    })

@app.route('/api/search')
def search_data():
    """Search conference data with boolean operators."""
    keyword = request.args.get('keyword', '')

    # Get filter parameters
    drug_filters = request.args.getlist('drug_filters[]') or request.args.getlist('drug_filters') or []
    ta_filters = request.args.getlist('ta_filters[]') or request.args.getlist('ta_filters') or []
    session_filters = request.args.getlist('session_filters[]') or request.args.getlist('session_filters') or []
    date_filters = request.args.getlist('date_filters[]') or request.args.getlist('date_filters') or []

    # When searching with no filters, we need to search the FULL dataset, not just first 50
    # So if no filters are active, use the full dataset instead of calling get_filtered_dataframe_multi
    if not drug_filters and not ta_filters and not session_filters and not date_filters:
        filtered_df = df_global.copy()
    else:
        # Apply multi-filters first
        filtered_df = get_filtered_dataframe_multi(drug_filters, ta_filters, session_filters, date_filters)

    if keyword:
        # Apply search to filtered results
        search_columns = ['Title', 'Speakers', 'Affiliation', 'Speaker Location', 'Identifier', 'Room',
                         'Session', 'Date', 'Time', 'Theme']
        search_mask = parse_boolean_query(keyword, filtered_df, search_columns)
        filtered_df = filtered_df[search_mask]

        # Highlight search results
        filtered_df = highlight_search_results(filtered_df, keyword)

    # Only limit display to 50 rows when NO filters AND NO keyword (performance optimization)
    filters_active = bool(drug_filters or ta_filters or session_filters or date_filters or keyword)
    if not filters_active:
        display_df = filtered_df.head(50)
    else:
        display_df = filtered_df  # Show all filtered/search results

    # Convert to records
    data_records = display_df[['Title', 'Speakers', 'Affiliation', 'Speaker Location', 'Identifier', 'Room',
                                 'Session', 'Date', 'Time', 'Theme']].to_dict('records')

    # Sanitize Unicode
    data_records = sanitize_data_structure(data_records)

    # Build filter summary with all filter types
    drugs_summary = ', '.join(drug_filters) if drug_filters else 'All Drugs'
    tas_summary = ', '.join(ta_filters) if ta_filters else 'All Therapeutic Areas'
    sessions_summary = ', '.join(session_filters) if session_filters else 'All Session Types'
    dates_summary = ', '.join(date_filters) if date_filters else 'All Days'

    return jsonify({
        "data": data_records,
        "count": len(filtered_df),
        "keyword": keyword,
        "showing": len(display_df),
        "total": len(df_global) if df_global is not None else 4686,
        "filter_context": {
            "total_sessions": len(filtered_df),
            "total_available": len(df_global) if df_global is not None else 4686,
            "filter_summary": f"{drugs_summary} + {tas_summary} + {sessions_summary} + {dates_summary}",
            "filters_active": bool(drug_filters or ta_filters or session_filters or date_filters)
        }
    })

@app.route('/api/export')
def export_data():
    """Export filtered data to Excel."""
    # Get filter parameters
    drug_filters = request.args.getlist('drug_filters[]') or request.args.getlist('drug_filters') or []
    ta_filters = request.args.getlist('ta_filters[]') or request.args.getlist('ta_filters') or []
    session_filters = request.args.getlist('session_filters[]') or request.args.getlist('session_filters') or []
    date_filters = request.args.getlist('date_filters[]') or request.args.getlist('date_filters') or []

    keyword = request.args.get('keyword', '')

    # Apply multi-filters
    filtered_df = get_filtered_dataframe_multi(drug_filters, ta_filters, session_filters, date_filters)

    if keyword:
        search_columns = ['study_title', 'speaker', 'affiliation', 'location', 'identifier',
                         'session_category', 'date', 'time', 'main_filters']
        search_mask = parse_boolean_query(keyword, filtered_df, search_columns)
        filtered_df = filtered_df[search_mask]

    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        filtered_df.to_excel(writer, sheet_name='ESMO 2025 Data', index=False)

    output.seek(0)

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"esmo_2025_export_{timestamp}.xlsx"

    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/api/conference/info')
def get_conference_info():
    """Get conference metadata."""
    return jsonify({
        "conference_name": "ESMO 2025",
        "total_studies": len(df_global) if df_global is not None else 0,
        "available_filters": {
            "drug_filters": list(ESMO_DRUG_FILTERS.keys()),
            "ta_filters": list(ESMO_THERAPEUTIC_AREAS.keys()),
            "session_filters": list(ESMO_SESSION_TYPES.keys()),
            "date_filters": list(ESMO_DATES.keys())
        }
    })

# ============================================================================
# PLAYBOOK/BUTTON ROUTES (Simplified Streaming)
# ============================================================================

@app.route('/api/playbook/<playbook_key>/stream')
def stream_playbook(playbook_key):
    """
    Simplified playbook streaming endpoint.

    Flow: Get filters → Generate table → Build prompt → Stream AI response
    """
    if playbook_key not in PLAYBOOKS:
        return jsonify({"error": "Invalid playbook"}), 404

    # Get filter parameters
    drug_filters = request.args.getlist('drug_filters[]') or request.args.getlist('drug_filters') or []
    ta_filters = request.args.getlist('ta_filters[]') or request.args.getlist('ta_filters') or []
    session_filters = request.args.getlist('session_filters[]') or request.args.getlist('session_filters') or []
    date_filters = request.args.getlist('date_filters[]') or request.args.getlist('date_filters') or []

    playbook = PLAYBOOKS[playbook_key]

    def generate():
        try:
            print(f"[PLAYBOOK] Starting {playbook_key} with filters: drugs={drug_filters}, tas={ta_filters}")

            # 1. For COMPETITOR button: Drug filter is for FOCUS, not dataset filtering
            # Apply filters to get dataset
            if playbook_key == "competitor":
                # For competitor intelligence, drug_filters guide which EMD drug's competitors to focus on
                # TA filters still apply to narrow therapeutic area scope
                if ta_filters or session_filters or date_filters:
                    filtered_df = get_filtered_dataframe_multi([], ta_filters, session_filters, date_filters)
                else:
                    filtered_df = df_global
                print(f"[PLAYBOOK] Competitor mode: Using dataset with {len(filtered_df)} studies (drug filter used for competitor focus)")
            else:
                # For other buttons, apply all filters normally
                if not drug_filters and not ta_filters and not session_filters and not date_filters:
                    filtered_df = df_global
                else:
                    filtered_df = get_filtered_dataframe_multi(drug_filters, ta_filters, session_filters, date_filters)
                print(f"[PLAYBOOK] Filtered dataset: {len(filtered_df)} studies")

            if filtered_df.empty:
                print(f"[PLAYBOOK] ERROR: No data after filtering")
                yield "data: " + json.dumps({"error": "No data matches the selected filters."}) + "\n\n"
                return

            # 2. Generate table(s) based on playbook requirements
            tables_data = {}
            print(f"[PLAYBOOK] Required tables: {playbook.get('required_tables', [])}")

            if "top_authors" in playbook.get("required_tables", []):
                print(f"[PLAYBOOK] Generating top authors table...")
                authors_table = generate_top_authors_table(filtered_df, n=10)
                tables_data["top_authors"] = authors_table.to_markdown(index=False) if not authors_table.empty else "No author data available"

                # Send table as SSE event (frontend expects: title, columns, rows as objects)
                if not authors_table.empty:
                    print(f"[PLAYBOOK] Sending authors table with {len(authors_table)} rows")
                    try:
                        table_data = {
                            "title": "Top 10 Authors",
                            "columns": list(authors_table.columns),
                            "rows": sanitize_data_structure(authors_table.to_dict('records'))
                        }
                        print(f"[PLAYBOOK] Table data prepared, attempting to send...")
                        yield "data: " + json.dumps(table_data) + "\n\n"
                        print(f"[PLAYBOOK] Table sent successfully")
                    except Exception as e:
                        print(f"[PLAYBOOK] ERROR sending table: {type(e).__name__}: {str(e)}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"[PLAYBOOK] WARNING: Authors table is empty")

                # For KOL analysis, provide ALL abstracts from each top author (not samples)
                if playbook_key == "kol" and not authors_table.empty:
                    kol_abstracts = []
                    for speaker in authors_table['Speaker'].head(10):
                        speaker_data = filtered_df[filtered_df['Speakers'] == speaker][['Identifier', 'Title', 'Affiliation', 'Session', 'Date', 'Time', 'Room']]
                        if not speaker_data.empty:
                            kol_abstracts.append(f"\n**{speaker}** ({len(speaker_data)} abstracts):\n{speaker_data.to_markdown(index=False)}")

                    if kol_abstracts:
                        tables_data["kol_abstracts"] = "\n".join(kol_abstracts)

            # For KOL analysis, also provide FULL filtered dataset for engagement priority analysis (Section 3)
            if "all_abstracts_for_engagement" in playbook.get("required_tables", []):
                print(f"[PLAYBOOK] Providing full dataset ({len(filtered_df)} abstracts) for engagement priority analysis...")
                # Provide full dataset with key columns for finding EMD-relevant and competitive intelligence targets
                engagement_data = filtered_df[['Speakers', 'Identifier', 'Title', 'Affiliation', 'Session', 'Date', 'Time', 'Room']].copy()
                # Limit to reasonable size (e.g., 200 rows max to avoid token limits)
                if len(engagement_data) > 200:
                    print(f"[PLAYBOOK] WARNING: Dataset has {len(engagement_data)} abstracts, limiting to 200 for engagement analysis")
                    engagement_data = engagement_data.head(200)
                tables_data["all_abstracts_for_engagement"] = engagement_data.to_markdown(index=False)

            if "top_institutions" in playbook.get("required_tables", []):
                inst_table = generate_top_institutions_table(filtered_df, n=15)
                tables_data["top_institutions"] = inst_table.to_markdown(index=False) if not inst_table.empty else "No institution data available"

                if not inst_table.empty:
                    yield "data: " + json.dumps({
                        "title": "Top 15 Institutions",
                        "columns": list(inst_table.columns),
                        "rows": sanitize_data_structure(inst_table.to_dict('records'))
                    }) + "\n\n"

            if "biomarker_moa_hits" in playbook.get("required_tables", []):
                bio_table = generate_biomarker_moa_table(filtered_df)
                tables_data["biomarker_moa"] = bio_table.to_markdown(index=False) if not bio_table.empty else "No biomarker data available"

                if not bio_table.empty:
                    yield "data: " + json.dumps({
                        "title": "Biomarker/MOA Hits",
                        "columns": list(bio_table.columns),
                        "rows": sanitize_data_structure(bio_table.to_dict('records'))
                    }) + "\n\n"

            if "all_data" in playbook.get("required_tables", []):
                # For competitor button, use JSON competitive landscape matching
                if playbook_key == "competitor":
                    # Determine therapeutic area for context
                    therapeutic_area = ta_filters[0] if ta_filters and len(ta_filters) > 0 else "All Therapeutic Areas"

                    # Use JSON-based competitive landscape matching
                    print(f"[COMPETITOR] Using JSON competitive landscape matcher...")
                    competitor_table = match_studies_with_competitive_landscape(filtered_df, therapeutic_area)

                    print(f"[PLAYBOOK] Generated competitor table with {len(competitor_table)} studies")
                    tables_data["competitor_abstracts"] = competitor_table.to_markdown(index=False) if not competitor_table.empty else "No competitor drugs found"

                    if not competitor_table.empty:
                        # Table 1: Drug/MOA Ranking Summary
                        ranking_table = generate_drug_moa_ranking(competitor_table, n=20)
                        if not ranking_table.empty:
                            print(f"[PLAYBOOK] Sending drug ranking table with {len(ranking_table)} drugs")
                            yield "data: " + json.dumps({
                                "title": f"Competitor Drug Ranking ({len(ranking_table)} drugs)",
                                "subtitle": "Drug database matching with MOA appending for combinations",
                                "columns": list(ranking_table.columns),
                                "rows": sanitize_data_structure(ranking_table.to_dict('records'))
                            }) + "\n\n"
                            tables_data["drug_ranking"] = ranking_table.to_markdown(index=False)

                        # Table 2: Full competitor studies list
                        print(f"[PLAYBOOK] Sending competitor table with {len(competitor_table)} studies")
                        yield "data: " + json.dumps({
                            "title": f"Competitor Studies ({len(competitor_table)} abstracts)",
                            "subtitle": "Combinations shown as single entries with appended MOAs (e.g., 'ADC + ICI')",
                            "columns": list(competitor_table.columns),
                            "rows": sanitize_data_structure(competitor_table.to_dict('records'))
                        }) + "\n\n"

                        # Table 3: Emerging Threats
                        try:
                            print(f"[PLAYBOOK] Starting emerging threats analysis on FULL {len(filtered_df)} studies...")

                            # Use keyword matching to identify emerging threats
                            def is_emerging_threat(row):
                                title = str(row['Title']).lower()
                                return any(keyword in title for keyword in [
                                    'adc', 'antibody-drug conjugate', 'bispecific', 'tce', 'bite',
                                    'car-t', 'radioligand', 'nectin-4', 'trop-2', 'fgfr',
                                    '+', ' plus ', ' in combination'
                                ])

                            emerging_threats_base = filtered_df[filtered_df.apply(is_emerging_threat, axis=1)].copy()
                            print(f"[PLAYBOOK] Identified {len(emerging_threats_base)} emerging threats")

                            if not emerging_threats_base.empty:
                                # Run drug matcher on emerging threats to get MOA data
                                print(f"[PLAYBOOK] Running drug matcher on {len(emerging_threats_base)} emerging threat studies...")
                                emerging_with_moa = classify_studies_with_drug_db(emerging_threats_base, therapeutic_area)
                                print(f"[PLAYBOOK] Drug matcher returned {len(emerging_with_moa)} studies with drug/MOA data")

                                # Step 3: Merge MOA data back with original emerging threats
                                # Keep ALL emerging threats, add MOA data where available
                                emerging_threats_display = emerging_threats_base.merge(
                                    emerging_with_moa[['Identifier', 'Drug', 'Company', 'MOA Class', 'MOA Target']],
                                    on='Identifier',
                                    how='left'
                                )

                                # Fill missing MOA data with "Not in DB"
                                emerging_threats_display['Drug'] = emerging_threats_display['Drug'].fillna('Not in Drug DB')
                                emerging_threats_display['Company'] = emerging_threats_display['Company'].fillna('Unknown')
                                emerging_threats_display['MOA Class'] = emerging_threats_display['MOA Class'].fillna('See Title')
                                emerging_threats_display['MOA Target'] = emerging_threats_display['MOA Target'].fillna('See Title')

                                # Step 4: Add Setting/Novelty column
                                def extract_setting_novelty(title):
                                    """Extract treatment setting, line of therapy, and novelty indicators from title"""
                                    title_lower = str(title).lower()
                                    flags = []

                                    # Line of therapy
                                    if '1l' in title_lower or 'first-line' in title_lower or 'first line' in title_lower:
                                        flags.append('1L')
                                    elif '2l' in title_lower or 'second-line' in title_lower or 'second line' in title_lower:
                                        flags.append('2L')
                                    elif '3l' in title_lower or 'third-line' in title_lower:
                                        flags.append('3L')

                                    if 'maintenance' in title_lower:
                                        flags.append('Maintenance')
                                    if 'adjuvant' in title_lower:
                                        flags.append('Adjuvant')
                                    if 'neoadjuvant' in title_lower:
                                        flags.append('Neoadjuvant')

                                    # Development stage
                                    if 'first-in-human' in title_lower or 'first in human' in title_lower:
                                        flags.append('First-in-Human')
                                    elif 'phase 1' in title_lower or 'phase i ' in title_lower or ' phase i:' in title_lower:
                                        flags.append('Phase 1')
                                    elif 'phase 2' in title_lower or 'phase ii' in title_lower:
                                        flags.append('Phase 2')
                                    elif 'phase 3' in title_lower or 'phase iii' in title_lower:
                                        flags.append('Phase 3')

                                    # Novelty indicators
                                    if 'novel' in title_lower:
                                        flags.append('Novel')
                                    if 'investigational' in title_lower:
                                        flags.append('Investigational')
                                    if 'first' in title_lower and 'result' in title_lower:
                                        flags.append('First Results')

                                    # Disease state
                                    if 'metastatic' in title_lower or ' muc' in title_lower:
                                        flags.append('Metastatic')
                                    if 'locally advanced' in title_lower or 'la/m' in title_lower:
                                        flags.append('Locally Advanced')
                                    if 'mibc' in title_lower or 'muscle-invasive' in title_lower:
                                        flags.append('MIBC')
                                    if 'nmibc' in title_lower or 'non-muscle-invasive' in title_lower:
                                        flags.append('NMIBC')

                                    # Biomarker selection
                                    if 'fgfr' in title_lower:
                                        flags.append('FGFR+')
                                    if 'pd-l1' in title_lower:
                                        flags.append('PD-L1+')
                                    if 'her2' in title_lower:
                                        flags.append('HER2+')
                                    if 'platinum-resistant' in title_lower or 'cisplatin-ineligible' in title_lower:
                                        flags.append('Platinum-Resistant/Ineligible')

                                    return ' | '.join(flags) if flags else 'Not Specified'

                                emerging_threats_display['Setting/Novelty'] = emerging_threats_display['Title'].apply(extract_setting_novelty)

                                # Select final columns
                                emerging_threats_display = emerging_threats_display[[
                                    'Identifier', 'Title', 'Drug', 'Company', 'MOA Class',
                                    'Setting/Novelty', 'Speakers', 'Affiliation'
                                ]].copy()

                                # NO LIMIT - show all emerging threats
                                original_count = len(emerging_threats_display)

                                print(f"[PLAYBOOK] Displaying {len(emerging_threats_display)} emerging threat studies")
                                tables_data["emerging_threats"] = emerging_threats_display.to_markdown(index=False)

                                subtitle = "Studies with novel mechanisms, combinations, or biomarkers requiring medical affairs attention"
                                if original_count > 50:
                                    subtitle += f" (showing first 50 of {original_count})"

                                yield "data: " + json.dumps({
                                    "title": f"Emerging Threats ({len(emerging_threats_display)} studies)",
                                    "subtitle": subtitle,
                                    "columns": list(emerging_threats_display.columns),
                                    "rows": sanitize_data_structure(emerging_threats_display.to_dict('records'))
                                }) + "\n\n"
                            else:
                                print(f"[PLAYBOOK] WARNING: No emerging threats identified - filter may be too strict")

                        except Exception as e:
                            error_msg = f"[PLAYBOOK] ERROR in emerging threats analysis: {str(e)}"
                            print(error_msg)
                            import traceback
                            traceback.print_exc()

                            # Yield error as visible table so user can see what went wrong
                            yield "data: " + json.dumps({
                                "title": "⚠️ Emerging Threats Error",
                                "subtitle": f"Error: {str(e)}",
                                "columns": ["Error Message"],
                                "rows": [{"Error Message": str(e) + " - Check console for full traceback"}]
                            }) + "\n\n"

                    if competitor_table.empty:
                        print(f"[PLAYBOOK] WARNING: No competitor drugs found in dataset")

                    # REMOVED: full_dataset_context - tables already contain all necessary data
                    # Competitor Studies table + Emerging Threats table provide sufficient context
                    # Adding 50 more studies bloats prompt unnecessarily

                else:
                    # For strategy or other buttons, provide sample abstracts
                    sample_df = filtered_df.head(50)[['Identifier', 'Title', 'Speakers', 'Affiliation']]
                    tables_data["abstracts"] = sample_df.to_markdown(index=False)

                    if not sample_df.empty:
                        yield "data: " + json.dumps({
                            "title": "Sample Abstracts (First 50)",
                            "columns": list(sample_df.columns),
                            "rows": sanitize_data_structure(sample_df.to_dict('records'))
                        }) + "\n\n"

            # 3. Build prompt with table data injected
            prompt_template = playbook["ai_prompt"]

            # Inject table data into prompt
            table_context = "\n\n".join([f"**{key.upper()}**:\n{value}" for key, value in tables_data.items()])

            ta_context = f"Therapeutic Area Filter: {', '.join(ta_filters) if ta_filters else 'All Therapeutic Areas'}"
            drug_context = f"Drug Filter: {', '.join(drug_filters) if drug_filters else 'Competitive Landscape'}"

            # For competitive intelligence, provide TA-specific guidance
            filter_guidance = ""
            if playbook_key == "competitor" and ta_filters and "All Therapeutic Areas" not in ta_filters:
                # Map TA selection to relevant EMD drugs and key competitors
                ta_competitor_focus = {
                    "Bladder Cancer": {
                        "emd_drug": "Avelumab",
                        "indication": "1L maintenance metastatic urothelial carcinoma post-platinum",
                        "key_competitors": ["enfortumab vedotin (EV)", "EV+pembrolizumab (EV+P)", "pembrolizumab", "nivolumab", "durvalumab", "atezolizumab", "sacituzumab govitecan", "erdafitinib", "disitamab vedotin"],
                        "emerging_threats": ["ADCs", "combination therapies", "FGFR inhibitors"]
                    },
                    "Lung Cancer": {
                        "emd_drug": "Tepotinib",
                        "indication": "1L NSCLC with MET exon 14 skipping mutations",
                        "key_competitors": ["capmatinib", "savolitinib", "crizotinib", "osimertinib", "alectinib", "selpercatinib", "pralsetinib", "pembrolizumab", "amivantamab"],
                        "emerging_threats": ["next-gen MET inhibitors", "MET-targeting ADCs", "bispecific antibodies"]
                    },
                    "Colorectal Cancer": {
                        "emd_drug": "Cetuximab",
                        "indication": "1L metastatic CRC (EGFR+, RAS wild-type)",
                        "key_competitors": ["panitumumab", "bevacizumab", "pembrolizumab", "nivolumab", "regorafenib", "trifluridine/tipiracil", "fruquintinib", "encorafenib+cetuximab"],
                        "emerging_threats": ["HER2-targeting agents", "KRAS G12C inhibitors", "novel combinations"]
                    },
                    "Head & Neck Cancer": {
                        "emd_drug": "Cetuximab",
                        "indication": "1L locally advanced/metastatic HNSCC",
                        "key_competitors": ["pembrolizumab", "nivolumab", "durvalumab", "panitumumab", "toripalimab", "retifanlimab"],
                        "emerging_threats": ["novel ICIs", "ADCs in HNSCC", "targeted therapies"]
                    },
                    "Renal Cancer": {
                        "emd_drug": "None (monitoring competitive landscape)",
                        "indication": "Advanced/metastatic RCC",
                        "key_competitors": ["pembrolizumab+axitinib", "nivolumab+ipilimumab", "lenvatinib+pembrolizumab", "cabozantinib", "belzutifan"],
                        "emerging_threats": ["HIF-2α inhibitors", "novel combinations", "ADCs"]
                    },
                    "TGCT": {
                        "emd_drug": "Pimicotinib (pre-launch)",
                        "indication": "Tenosynovial giant cell tumor",
                        "key_competitors": ["pexidartinib", "vimseltinib", "imatinib"],
                        "emerging_threats": ["next-gen CSF1R inhibitors", "combination approaches"]
                    }
                }

                selected_ta = ta_filters[0] if ta_filters else None
                if selected_ta in ta_competitor_focus:
                    focus = ta_competitor_focus[selected_ta]
                    competitor_list = "', '".join(focus["key_competitors"])
                    filter_guidance = f"\n\n**COMPETITIVE ANALYSIS FOCUS FOR {selected_ta.upper()}**:\n"
                    filter_guidance += f"- **Primary EMD Asset**: {focus['emd_drug']} in {focus['indication']}\n"
                    filter_guidance += f"- **Key Competitors to Analyze**: '{competitor_list}'\n"
                    filter_guidance += f"- **Emerging Threat Categories**: {', '.join(focus['emerging_threats'])}\n"
                    filter_guidance += f"- **Analysis Scope**: The tables below contain ONLY {selected_ta} studies. Focus exclusively on competitors relevant to this therapeutic area."

            full_prompt = f"""{prompt_template}

**CONFERENCE DATA CONTEXT**:
{drug_context}
{ta_context}
Total Studies in Filtered Dataset: {len(filtered_df)}{filter_guidance}

**DATA PROVIDED**:
{table_context}

Based on the data provided above, write a comprehensive analysis following the framework."""

            print(f"[PLAYBOOK] Full prompt length: {len(full_prompt)} chars")
            print(f"[PLAYBOOK] Tables in prompt: {list(tables_data.keys())}")

            # 4. Stream AI response token by token
            print(f"[PLAYBOOK] Starting OpenAI streaming...")
            # Use low reasoning for CI button to avoid timeout with large prompts
            reasoning_effort = "low" if playbook_key == "competitor" else "medium"
            for token_event in stream_openai_tokens(full_prompt, reasoning_effort=reasoning_effort):
                yield token_event
            print(f"[PLAYBOOK] OpenAI streaming completed")

        except Exception as e:
            print(f"[PLAYBOOK] EXCEPTION in generate(): {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            yield "data: " + json.dumps({"error": f"Streaming error: {str(e)}"}) + "\n\n"

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)

# ============================================================================
# CHAT ROUTE (Simplified Streaming)
# ============================================================================

@app.route('/api/chat/stream', methods=['POST'])
def stream_chat_api():
    """
    Enhanced chat streaming endpoint with intelligent synthesis.

    Flow: Get query → Detect intent → Apply filters → Retrieve ALL relevant data →
          Generate tables if needed → Build synthesis prompt → Stream response
    """
    user_query = request.json.get('message', '').strip()
    conversation_history = request.json.get('conversation_history', [])

    # Get filter parameters
    drug_filters = request.json.get('drug_filters', [])
    ta_filters = request.json.get('ta_filters', [])
    session_filters = request.json.get('session_filters', [])
    date_filters = request.json.get('date_filters', [])

    if not user_query:
        return "data: " + json.dumps({"error": "No message provided"}) + "\n\n", 400

    def generate():
        try:
            # 1a. Check for UNAMBIGUOUS combinations FIRST (EV + P, nivo plus ipi)
            combination_override = detect_unambiguous_combination(user_query)
            if combination_override:
                classification = combination_override
                print(f"[COMBINATION OVERRIDE] Unambiguous combination detected, skipping AI")
                print(f"[QUERY CLASSIFICATION] {classification}")
            else:
                # 1b. Check for AMBIGUOUS drug queries (EV and pembro, EV with pembro)
                ambiguous_check = detect_ambiguous_drug_query(user_query)
                if ambiguous_check:
                    classification = ambiguous_check
                    print(f"[AMBIGUOUS QUERY] Needs clarification")
                    print(f"[QUERY CLASSIFICATION] {classification}")
                else:
                    # 1c. Use AI classification for everything else
                    classification = classify_user_query(user_query, conversation_history)
                    print(f"[QUERY CLASSIFICATION] {classification}")

            # 1.5. Detect query intent for synthesis routing
            intent_data = detect_query_intent(user_query)
            print(f"[INTENT DETECTION] Intent: {intent_data['intent']}, Verbosity: {intent_data['verbosity']}")

            # 1.6. Check for competitor intelligence query
            competitor_drugs = detect_competitor_query(user_query, ta_filters)
            if competitor_drugs:
                # Override classification search_terms with competitor drugs
                print(f"[COMPETITOR INTELLIGENCE] Detected competitor query")
                print(f"[COMPETITOR INTELLIGENCE] Searching for: {competitor_drugs}")
                classification['search_terms'] = competitor_drugs
                classification['entity_type'] = 'drug'
                classification['generate_table'] = True
                classification['table_type'] = 'drug_studies'

            # 2. Handle clarification requests (vague queries)
            if classification.get('entity_type') == 'clarification_needed':
                clarification_text = classification.get('clarification_question',
                    "Could you please be more specific? For example, you could ask about:\n\n" +
                    "• **Data synthesis**: 'What's the latest on ADCs in bladder cancer?'\n" +
                    "• **Comparisons**: 'Compare EV+P vs avelumab maintenance'\n" +
                    "• **Specific queries**: 'Show me studies on FGFR3 biomarkers'\n" +
                    "• **Trends**: 'Predict which mechanism will dominate next year'\n\n" +
                    "You can also specify: '**quick summary**' or '**comprehensive analysis**'")

                yield "data: " + json.dumps({"text": clarification_text}) + "\n\n"
                yield "data: [DONE]\n\n"
                return

            # 3. Apply filters to get relevant dataset
            filtered_df = get_filtered_dataframe_multi(drug_filters, ta_filters, session_filters, date_filters)

            if filtered_df.empty:
                yield "data: " + json.dumps({"text": "No data matches your current filters. Please adjust filters and try again."}) + "\n\n"
                yield "data: [DONE]\n\n"
                return

            # 4. Generate entity table if needed (KEEP THIS - tables are valuable!)
            table_html = ""
            table_data = pd.DataFrame()

            if classification.get('generate_table'):
                # IMPORTANT: Pass filtered_df instead of df_global so searches work within the filter
                table_html, table_data = generate_entity_table(classification, filtered_df)

                if table_html:
                    # Send table FIRST as a separate event
                    yield "data: " + json.dumps({"table": sanitize_unicode_for_windows(table_html)}) + "\n\n"
                    print(f"[CHAT] Table generated with {len(table_data)} rows")

            # 5. NEW: Retrieve ALL relevant data for comprehensive synthesis (no sampling!)
            # IMPORTANT: Always use retrieve_comprehensive_data for synthesis, not table_data
            # Table data is capped at top_n (usually 50) for display, but AI needs full dataset
            relevant_data = retrieve_comprehensive_data(
                user_query=user_query,
                filtered_df=filtered_df,
                classification=classification,
                max_studies=None  # No limit - let AI handle all relevant data
            )
            print(f"[CHAT] Retrieved {len(relevant_data)} relevant studies for synthesis")

            # 6. Build intelligent synthesis prompt based on abstract availability
            if abstracts_available:
                print(f"[CHAT] Building POST-ABSTRACT synthesis prompt")
                synthesis_prompt = build_synthesis_prompt_post_abstract(
                    user_query=user_query,
                    relevant_data=relevant_data,
                    classification=classification,
                    verbosity=intent_data['verbosity'],
                    intent=intent_data['intent']
                )
            else:
                print(f"[CHAT] Building PRE-ABSTRACT synthesis prompt (titles/authors only)")
                synthesis_prompt = build_synthesis_prompt_pre_abstract(
                    user_query=user_query,
                    relevant_data=relevant_data,
                    classification=classification,
                    verbosity=intent_data['verbosity'],
                    intent=intent_data['intent']
                )

            # Add table context if table was shown
            if classification.get('generate_table'):
                if not table_data.empty:
                    table_note = f"\n\n**NOTE**: A data table with {len(table_data)} studies has been shown to the user above. DO NOT repeat the table data. Instead, synthesize insights and patterns from the data."
                else:
                    table_note = f"\n\n**NOTE**: The requested entity was not found. Explain why and suggest alternatives."
                synthesis_prompt += table_note

            print(f"[CHAT] Synthesis prompt length: {len(synthesis_prompt)} chars")

            # 7. Stream AI synthesis response
            print(f"[CHAT] Starting AI streaming with {intent_data['verbosity']} verbosity")
            for token_event in stream_openai_tokens(synthesis_prompt, reasoning_effort="medium", verbosity=intent_data['verbosity']):
                yield token_event

            print(f"[CHAT] Synthesis complete")

        except Exception as e:
            print(f"[CHAT] ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            yield "data: " + json.dumps({"error": f"Chat error: {str(e)}"}) + "\n\n"
            yield "data: [DONE]\n\n"

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)


# ============================================================================
# ENHANCED CHAT ENDPOINT (TIER 1 + TIER 2)
# ============================================================================

@app.route('/api/chat/enhanced', methods=['POST'])
def stream_chat_api_enhanced():
    """
    Enhanced chat endpoint using Tier 1 + Tier 2 search intelligence.

    Improvements over original:
    - Entity resolver for automatic drug/institution normalization
    - Query intelligence for intent detection
    - Multi-field search (Title, Session, Theme, Speakers, Affiliation, etc.)
    - Lean synthesis prompts (80% fewer tokens)
    - Dynamic verbosity based on query complexity
    - Comprehensive debug logging

    Usage: Change frontend to call '/api/chat/enhanced' instead of '/api/chat/stream'
    """
    user_query = request.json.get('message', '').strip()
    conversation_history = request.json.get('conversation_history', [])

    # Get filter parameters
    drug_filters = request.json.get('drug_filters', [])
    ta_filters = request.json.get('ta_filters', [])
    session_filters = request.json.get('session_filters', [])
    date_filters = request.json.get('date_filters', [])

    if not user_query:
        return jsonify({"error": "No message provided"}), 400

    def generate():
        try:
            print(f"\n{'='*70}")
            print(f"[ENHANCED CHAT] User query: {user_query}")
            print(f"[ENHANCED CHAT] TA filters: {ta_filters}")
            print(f"{'='*70}\n")

            # 0. Check for meta/conversational queries (handle naturally without data search)
            meta_response = detect_meta_query(user_query)
            if meta_response:
                print(f"[META QUERY] Detected conversational query, responding naturally")
                yield "data: " + json.dumps({"text": meta_response}) + "\n\n"
                yield "data: [DONE]\n\n"
                return

            # 1. Check for competitor intelligence query
            competitor_drugs = detect_competitor_query(user_query, ta_filters)
            if competitor_drugs:
                # Override user query to search for specific competitors
                original_query = user_query
                user_query_modified = f"Studies on {', '.join(competitor_drugs[:3])} and other competitors"
                print(f"[COMPETITOR OVERRIDE] Original query: {original_query}")
                print(f"[COMPETITOR OVERRIDE] Modified to search: {competitor_drugs}")

            # 1. Apply existing filters to get base dataset
            filtered_df = get_filtered_dataframe_multi(drug_filters, ta_filters, session_filters, date_filters)

            if filtered_df.empty:
                yield "data: " + json.dumps({"text": "No data matches your current filters. Please adjust filters and try again."}) + "\n\n"
                yield "data: [DONE]\n\n"
                return

            print(f"[ENHANCED CHAT] Filtered dataset: {len(filtered_df)} rows")

            # 2. Convert TA filters to keywords for smart_search
            ta_keywords = []
            if 'Bladder Cancer' in ta_filters:
                ta_keywords.extend(['bladder', 'urothelial'])
            if 'Lung Cancer' in ta_filters:
                ta_keywords.extend(['lung', 'nsclc', 'sclc'])
            if 'Colorectal Cancer' in ta_filters:
                ta_keywords.extend(['colorectal', 'colon', 'rectal'])
            if 'Head and Neck Cancer' in ta_filters:
                ta_keywords.extend(['head and neck', 'hnsc', 'hnscc'])

            # Get current date for temporal filtering
            current_date = datetime.now().strftime("%m/%d/%Y")

            # 3. Run enhanced search pipeline
            response_data = complete_search_pipeline(
                df=filtered_df,
                user_query=user_query,
                ta_keywords=ta_keywords if ta_keywords else None,
                current_date=current_date,
                debug=True  # Enable debug logging
            )

            print(f"[ENHANCED CHAT] Pipeline response type: {response_data.get('type')}")
            print(f"[ENHANCED CHAT] Results count: {len(response_data.get('table', []))}")

            # 4. Handle clarification needed
            if response_data.get('status') == 'clarification_needed':
                clarification_text = response_data['question']
                yield "data: " + json.dumps({"text": clarification_text}) + "\n\n"
                yield "data: [DONE]\n\n"
                return

            # 5. Handle factual responses (no AI needed)
            if response_data.get('type') == 'factual_answer':
                answer_text = response_data.get('answer', '')
                yield "data: " + json.dumps({"text": answer_text}) + "\n\n"

                # Send table if available
                results_table = response_data.get('table')
                if results_table is not None and not results_table.empty:
                    table_html = results_table.to_html(classes='table table-striped', index=False, escape=False)
                    yield "data: " + json.dumps({"table": sanitize_unicode_for_windows(table_html)}) + "\n\n"

                yield "data: [DONE]\n\n"
                return

            # 6. Handle list responses (with optional AI synthesis)
            if response_data.get('type') == 'list_filtered':
                answer_text = response_data.get('answer', '')
                yield "data: " + json.dumps({"text": answer_text}) + "\n\n"

                # Send table
                results_table = response_data.get('table')
                if results_table is not None and not results_table.empty:
                    table_html = results_table.to_html(classes='table table-striped', index=False, escape=False)
                    yield "data: " + json.dumps({"table": sanitize_unicode_for_windows(table_html)}) + "\n\n"

                yield "data: [DONE]\n\n"
                return

            # 7. Handle no results
            if response_data.get('type') == 'no_results':
                answer_text = response_data.get('answer', 'No studies found matching your criteria.')
                yield "data: " + json.dumps({"text": answer_text}) + "\n\n"
                yield "data: [DONE]\n\n"
                return

            # 8. Handle AI synthesis (complex queries)
            if response_data.get('type') in ['ai_synthesis', 'comparison']:
                results_table = response_data.get('table', pd.DataFrame())

                # Send table first if available
                if not results_table.empty:
                    table_html = results_table.to_html(classes='table table-striped', index=False, escape=False)
                    yield "data: " + json.dumps({"table": sanitize_unicode_for_windows(table_html)}) + "\n\n"
                    print(f"[ENHANCED CHAT] Table sent with {len(results_table)} rows")

                # Get synthesis prompt
                synthesis_prompt = response_data.get('prompt')

                if synthesis_prompt:
                    print(f"[ENHANCED CHAT] Streaming AI synthesis...")
                    print(f"[ENHANCED CHAT] Prompt tokens: {response_data.get('prompt_tokens', 'unknown')}")

                    # Determine reasoning effort
                    verbosity = response_data.get('verbosity', 'medium')
                    reasoning_effort = {
                        'minimal': 'low',
                        'quick': 'low',
                        'medium': 'medium',
                        'detailed': 'medium'
                    }.get(verbosity, 'medium')

                    # Stream AI response
                    for token_event in stream_openai_tokens(synthesis_prompt, reasoning_effort=reasoning_effort):
                        yield token_event

                    print(f"[ENHANCED CHAT] AI streaming completed")
                else:
                    yield "data: " + json.dumps({"text": "No studies found matching your criteria."}) + "\n\n"

                yield "data: [DONE]\n\n"
                return

            # Fallback
            yield "data: " + json.dumps({"text": "I couldn't process your request. Please try rephrasing."}) + "\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            print(f"[ENHANCED CHAT] ERROR: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            yield "data: " + json.dumps({"error": f"Chat error: {str(e)}"}) + "\n\n"
            yield "data: [DONE]\n\n"

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)


# ============================================================================
# APPLICATION STARTUP
# ============================================================================

# Load data at module level (works for both development and production servers like Gunicorn)
print("\n" + "="*80)
print("ESMO 2025 Conference Intelligence App - Initializing")
print("="*80 + "\n")

df_global = load_and_process_data()
load_competitive_landscapes()

if df_global is None:
    print("\n[ERROR] Failed to load conference data. Application cannot start.")
    print("[ERROR] Make sure ESMO_2025_FINAL_20250929.csv is in the application directory.")
    print("[ERROR] Current directory:", Path.cwd())
    print("[ERROR] Expected location:", CSV_FILE.absolute())
else:
    print(f"\n[SUCCESS] Application ready with {len(df_global)} conference studies")
    print(f"[INFO] ChromaDB: {'Initialized' if collection else 'Not available'}")
    print(f"[INFO] OpenAI API: {'Configured' if client else 'Not configured'}")
    print(f"[INFO] Competitive Landscapes: {len([k for k, v in competitive_landscapes.items() if v])} loaded")
    print(f"[INFO] Abstract Availability: {'ENABLED - Full data synthesis' if abstracts_available else 'DISABLED - Using titles/authors only (until Oct 13th)'}")

    print("="*80 + "\n")

if __name__ == '__main__':
    if df_global is None:
        print("[ERROR] Cannot start server - no data loaded.")
        exit(1)

    print("Starting Flask development server...")
    print("="*80 + "\n")

    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=5001,  # Port 5001 to avoid conflicts with testing on 5000
        debug=False,  # Changed to False for production readiness
        threaded=True
    )
