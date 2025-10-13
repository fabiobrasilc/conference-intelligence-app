"""
Deep Intelligence Report Generator using GPT-5
===============================================

This script generates comprehensive, deeply-reasoned intelligence reports
for Medical Affairs professionals using OpenAI's gpt-5 model with high
reasoning effort and high verbosity.

ARCHITECTURE:
  - ONE Librarian cache per button (e.g., librarian_competitor.json)
  - ONE Journalist cache per button (e.g., journalist_competitor.json)
  - Each cache contains ALL 7 therapeutic areas
  - Supports partial regeneration (update just one TA)

USAGE:

  # Generate/regenerate ONE therapeutic area for a button:
  python generate_deep_intelligence.py --button <BUTTON> --ta "<TA_NAME>"

  # Generate/regenerate ALL therapeutic areas for a button:
  python generate_deep_intelligence.py --button <BUTTON>

  # Generate/regenerate ALL buttons × ALL TAs:
  python generate_deep_intelligence.py --all

AVAILABLE BUTTONS:
  - competitor    Competitive Intelligence
  - kol           KOL Intelligence
  - institution   Institution Intelligence
  - insights      Research Insights
  - strategic     Strategic Priorities

AVAILABLE THERAPEUTIC AREAS:
  - "Bladder Cancer"
  - "Lung Cancer"
  - "Colorectal Cancer"
  - "Head and Neck Cancer"
  - "Renal Cancer"
  - "TGCT"
  - "Merkel Cell"

EXAMPLES:

  # Generate/regenerate Bladder Cancer Competitor Intelligence
  python generate_deep_intelligence.py --button competitor --ta "Bladder Cancer"

  # Result:
  # - Updates: cache/librarian_competitor.json (Bladder section only)
  # - Updates: cache/journalist_competitor.json (Bladder report only)
  # - Preserves: Other 6 TAs if they exist in the caches

  # Generate/regenerate ALL TAs for Competitor Intelligence
  python generate_deep_intelligence.py --button competitor

  # Result:
  # - Updates: cache/librarian_competitor.json (all 7 TAs)
  # - Updates: cache/journalist_competitor.json (all 7 TA reports)

  # Force re-extract Librarian when abstracts are released
  python generate_deep_intelligence.py --button competitor --ta "Bladder Cancer" --refresh-librarian
"""

import sys
import os
import json
import argparse
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import hashlib
import pandas as pd
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app import (
    df_global,
    get_filtered_dataframe_multi,
    match_studies_with_competitive_landscape,  # Used in strategic button
    generate_drug_moa_ranking,  # Used in strategic button
    generate_top_authors_table,  # Used in kol/strategic buttons
    generate_top_institutions_table,  # Used in institution button
    generate_biomarker_moa_table,  # Used in insights button
    ESMO_THERAPEUTIC_AREAS
)
from openai import OpenAI

# Import Librarian V2 + Tagger pipeline
from librarian_v2 import librarian_process_all, load_aliases
from tagger import tag_and_aggregate

# Initialize OpenAI client with extended timeout for deep research
client = OpenAI(timeout=3600)  # 1 hour timeout for deep research

# Configuration
THERAPEUTIC_AREAS = [
    "Bladder Cancer",
    "Lung Cancer",
    "Colorectal Cancer",
    "Head and Neck Cancer",
    "Renal Cancer",
    "TGCT",
    "Merkel Cell"
]

BUTTON_TYPES = [
    "competitor",
    "kol",
    "institution",
    "insights",
    "strategic"
]

# Chief Editor Quality Control (for insights button)
# Set to True to enable QC review layer (adds ~30s per report)
# Set to False to skip QC and use journalist output directly
ENABLE_CHIEF_EDITOR = True

# Therapeutic Area Medical Terminology Synonyms (for PubMed/CT.gov queries)
TA_MEDICAL_SYNONYMS = {
    "Bladder Cancer": ["bladder cancer", "urothelial carcinoma", "bladder carcinoma", "transitional cell carcinoma"],
    "Lung Cancer": ["lung cancer", "non-small cell lung cancer", "NSCLC", "small cell lung cancer", "SCLC", "lung carcinoma"],
    "Colorectal Cancer": ["colorectal cancer", "colon cancer", "rectal cancer", "CRC", "colorectal carcinoma"],
    "Head and Neck Cancer": ["head and neck cancer", "head and neck squamous cell carcinoma", "HNSCC", "oropharyngeal cancer"],
    "Renal Cancer": ["renal cell carcinoma", "RCC", "kidney cancer", "renal cancer"],
    "TGCT": ["tenosynovial giant cell tumor", "TGCT", "pigmented villonodular synovitis", "PVNS"],
    "Merkel Cell": ["merkel cell carcinoma", "MCC", "merkel cell cancer"]
}

# EMD Serono Portfolio Context
EMD_PORTFOLIO = {
    "Bladder Cancer": {
        "primary_asset": "Avelumab (Bavencio)",
        "indication": "1L maintenance therapy for locally advanced or metastatic urothelial carcinoma",
        "pivotal_trial": "JAVELIN Bladder 100",
        "approval_year": 2020,
        "nccn_status": "Category 1 preferred",
        "key_competitors": [
            "enfortumab vedotin + pembrolizumab (EV-302)",
            "pembrolizumab monotherapy",
            "nivolumab",
            "sacituzumab govitecan",
            "erdafitinib (FGFR+)"
        ]
    },
    "Lung Cancer": {
        "primary_asset": "Tepotinib (Tepmetko)",
        "indication": "Metastatic NSCLC with MET exon 14 skipping mutations (METex14)",
        "pivotal_trial": "VISION",
        "approval_year": 2021,
        "approval_status": "FDA traditional approval (Feb 15, 2024); plasma CDx approved Nov 2024",
        "nccn_status": "NCCN-preferred for METex14 NSCLC",
        "key_competitors": [
            "capmatinib (METex14)",
            "telisotuzumab vedotin (c-MET IHC 3+)",
            "savolitinib + osimertinib (MET-driven EGFR resistance)",
            "amivantamab + lazertinib (EGFR + MET dual targeting)",
            "crizotinib (METamp, off-label)"
        ]
    },
    "Colorectal Cancer": {
        "primary_asset": "Cetuximab (Erbitux) [1L]; Precemtabart Tocentecan (M9140) [Pipeline 3L+]",
        "indication": "Cetuximab: 1L mCRC (RAS WT, left-sided preferred). Precem-TcT: 3L+ MSS/pMMR mCRC (CEACAM5-selected, investigational)",
        "pivotal_trial": "Cetuximab: CRYSTAL (2004). Precem-TcT: PROCEADE programs ongoing (Phase 1 ASCO 2025; registrational 3L+ path planned)",
        "approval_year": "Cetuximab: 2004. Precem-TcT: In development",
        "nccn_status": "Cetuximab: Category 1 (1L RAS WT). Precem-TcT: Investigational (3L+ white space)",
        "pipeline_asset_detail": "Precem-TcT is an anti-CEACAM5 ADC with exatecan (Topo-I) payload, showing bystander killing for heterogeneous antigen expression. Phase 1 CRC data (ASCO 2025) showed encouraging activity, manageable safety, dose ~2.8 mg/kg Q3W. Strategic positioning: 3L+ MSS/pMMR post-chemo/biologics where TAS-102±bev, regorafenib, fruquintinib yield modest ORR (1-5%). Differentiation on response depth/durability, especially post-irinotecan. Requires CEACAM5 IHC/NGS companion Dx.",
        "key_competitors": [
            "panitumumab (1L anti-EGFR)",
            "bevacizumab (1L/2L anti-VEGF)",
            "pembrolizumab (1L MSI-H)",
            "adagrasib + cetuximab (2L+ KRAS G12C)",
            "sotorasib + panitumumab (2L+ KRAS G12C)",
            "fruquintinib (3L+ VEGFR TKI)",
            "TAS-102 ± bevacizumab (3L+)",
            "tucatinib + trastuzumab (HER2+ 3L+)",
            "TROP2 ADCs (datopotamab deruxtecan, sacituzumab govitecan - 3L+ trials)",
            "CEACAM5 ADCs (emerging class competition)"
        ]
    },
    "Head and Neck Cancer": {
        "primary_asset": "Cetuximab (Erbitux)",
        "indication": "R/M HNSCC: 1L cetuximab+platinum/5-FU (EXTREME) for PD-L1 <1 or IO-ineligible. LA-HNSCC: cetuximab+RT for cisplatin-ineligible patients",
        "pivotal_trial": "EXTREME (2006) - established cetuximab+chemo as 1L R/M standard; cetuximab+RT data from Bonner trial",
        "approval_year": 2006,
        "nccn_status": "Category 1 (EXTREME regimen for R/M; cetuximab+RT for LA cisplatin-ineligible)",
        "strategic_positioning": "IO (KEYNOTE-048) dominates 1L R/M in CPS ≥1, but cetuximab retains critical niches: PD-L1 <1, IO-refractory, rapid response needs, HPV-negative enrichment, cisplatin-ineligible LA. Sole approved anti-EGFR mAb in HNSCC.",
        "key_competitors": [
            "pembrolizumab + chemo (1L R/M CPS ≥1, KEYNOTE-048 dominance)",
            "pembrolizumab mono (1L R/M CPS ≥20)",
            "nivolumab (2L+ post-platinum)",
            "perioperative pembrolizumab (KEYNOTE-689, curative LA approved June 2025)",
            "petosemtamab (EGFR/LGR5 bispecific, phase 3 - potential 1L/2L threat)",
            "HER3-DXd, TROP2 ADCs (R/M trials, refractory settings)",
            "toripalimab, tislelizumab, durvalumab (regional IO competition)"
        ]
    },
    "Renal Cancer": {
        "primary_asset": "Avelumab + Axitinib (Bavencio + Inlyta)",
        "indication": "1L advanced renal cell carcinoma",
        "pivotal_trial": "JAVELIN Renal 101",
        "approval_year": 2019,
        "nccn_status": "Other Recommended (Category 2A) - not preferred due to lack of OS benefit vs sunitinib",
        "esmo_status": "Not recommended over OS-positive regimens (pembro+axi, nivo+cabo, pembro+lenva)",
        "strategic_reality": "Approved but niche positioning; OS-proven IO/TKI doublets dominate market share",
        "key_competitors": [
            "pembrolizumab + axitinib (OS-positive, preferred)",
            "nivolumab + cabozantinib (OS-positive, preferred)",
            "lenvatinib + pembrolizumab (OS-positive, preferred)",
            "nivolumab + ipilimumab (Category 1, durable OS)",
            "belzutifan + lenvatinib (HIF-2α combo, late-line emerging)"
        ]
    },
    "TGCT": {
        "primary_asset": "Pimicotinib",
        "indication": "Tenosynovial giant cell tumor (TGCT)",
        "indication_note": "EMD Serono/Merck KGaA acquired worldwide commercialization rights from Abbisko",
        "pivotal_trial": "MANEUVER",
        "approval_year": "In development",
        "nccn_status": "Investigational",
        "key_competitors": [
            "vimseltinib (Deciphera)",
            "pexidartinib (Daiichi Sankyo) - approved for TGCT"
        ]
    },
    "Merkel Cell": {
        "primary_asset": "Avelumab (Bavencio)",
        "indication": "Metastatic or recurrent locally advanced Merkel cell carcinoma",
        "pivotal_trial": "JAVELIN Merkel 200",
        "approval_year": 2017,
        "approval_type": "First MCC-specific approval; accelerated approval",
        "nccn_status": "Preferred option (Category 2A) for unresectable regional/metastatic disease",
        "key_competitors": [
            "pembrolizumab (preferred, accelerated approval 2018)",
            "nivolumab (NCCN-listed)",
            "retifanlimab (accelerated approval March 2023)",
            "adjuvant pembrolizumab (STAMP trial - practice-changing if positive)",
            "adjuvant avelumab (ADAM trial - ongoing)"
        ]
    }
}


# ============================================================================
# LANDSCAPE CONTEXT LOADING
# ============================================================================

def load_landscape_context_for_section1(ta: str) -> Dict:
    """
    Load TA-specific landscape context from landscape_context.json for Section 1.
    Returns dict with treatment_paradigm, recent_approvals, key_trials, etc.
    """
    try:
        landscape_file = Path(__file__).parent / "landscape_context.json"
        with open(landscape_file, 'r', encoding='utf-8') as f:
            landscape_data = json.load(f)

        # Map TA names to landscape_context.json keys
        ta_mapping = {
            "Bladder Cancer": "Bladder Cancer",
            "Lung Cancer": "Non-Small Cell Lung Cancer",
            "Colorectal Cancer": "Colorectal Cancer",
            "Head and Neck Cancer": "Head and Neck Cancer",
            "TGCT": "Tenosynovial Giant Cell Tumor",
            "Renal Cancer": "Renal Cell Carcinoma",
            "Merkel Cell": "Merkel Cell Carcinoma"
        }

        landscape_key = ta_mapping.get(ta)
        if landscape_key and landscape_key in landscape_data.get("therapeutic_areas", {}):
            return landscape_data["therapeutic_areas"][landscape_key]
        else:
            return None
    except Exception as e:
        print(f"[LANDSCAPE] Could not load context for {ta}: {e}")
        return None


# ============================================================================
# TA-SPECIFIC COMPETITOR GUIDANCE
# ============================================================================

def get_ta_specific_competitor_guidance(ta: str) -> str:
    """
    Returns TA-specific instructions for what constitutes a 'competitor' for competitive intelligence analysis.
    This ensures reports focus on true market share threats to EMD assets.
    """
    guidance = {
        "Lung Cancer": """
**FOR LUNG CANCER: Focus ONLY on MET-altered NSCLC competitors**
- TRUE COMPETITORS (analyze in detail): MET TKIs (capmatinib, savolitinib, crizotinib), MET ADCs (telisotuzumab vedotin), MET bispecifics (amivantamab), EGFR+MET combinations that threaten tepotinib's METex14/METamp market share
- EXCLUDE from competitor analysis: EGFR-only, ALK, ROS1, KRAS, BRAF (unless combined with MET), broad IO studies, melanoma/thyroid studies
- Context is fine, but Section 2 "Competitor Activity" should focus on drugs that directly compete with tepotinib for MET-altered NSCLC patients""",

        "Colorectal Cancer": """
**FOR COLORECTAL CANCER: Exclude EMD Serono/Merck KGaA assets from competitor analysis**
- EXCLUDE cetuximab-based regimens (cetuximab is OUR asset in CRC, not a competitor)
- EXCLUDE precemtabart tocentecan (M9140) - this is OUR pipeline ADC
- TRUE COMPETITORS: panitumumab, pembrolizumab, bevacizumab, KRAS G12C doublets, fruquintinib, TAS-102, other ADCs (TROP2, HER2), other CEACAM5 ADCs""",

        "Head and Neck Cancer": """
**FOR HEAD AND NECK CANCER: Exclude EMD Serono/Merck KGaA assets from competitor analysis**
- EXCLUDE cetuximab-based regimens (cetuximab is OUR asset in HNSCC, not a competitor)
- TRUE COMPETITORS: pembrolizumab, nivolumab, durvalumab, petosemtamab (EGFR/LGR5 bispecific), ADCs (HER3-DXd, TROP2-DXd), other novel EGFR-targeting agents""",

        "Merkel Cell": """
**FOR MERKEL CELL CARCINOMA: Exclude EMD Serono/Merck KGaA assets from competitor analysis**
- EXCLUDE avelumab-based regimens (avelumab/Bavencio is OUR asset in MCC, not a competitor)
- TRUE COMPETITORS: pembrolizumab, nivolumab, retifanlimab, investigational IO combinations, adjuvant IO trials (STAMP with pembro, ADAM with avelumab is OURS)""",

        "Bladder Cancer": """
**FOR BLADDER CANCER: Exclude EMD Serono/Merck KGaA assets from competitor analysis**
- EXCLUDE avelumab-based regimens (avelumab/Bavencio 1L maintenance is OUR asset, not a competitor)
- TRUE COMPETITORS: EV+pembrolizumab, nivolumab, pembrolizumab, sacituzumab govitecan, erdafitinib, other IO and ADC competitors""",

        "Renal Cancer": """
**FOR RENAL CANCER: Exclude EMD Serono/Merck KGaA assets from competitor analysis**
- EXCLUDE avelumab+axitinib regimens (this is OUR combination, not a competitor)
- TRUE COMPETITORS: pembrolizumab+axitinib, nivolumab+cabozantinib, pembrolizumab+lenvatinib, nivolumab+ipilimumab, belzutifan combinations, other IO/TKI doublets"""
    }

    return guidance.get(ta, "**GENERAL COMPETITOR FOCUS**: Analyze all non-EMD therapeutic regimens as competitors. Exclude any EMD Serono/Merck KGaA assets from competitor sections.")


# ============================================================================
# CONSOLIDATED CACHING HELPERS
# ============================================================================

def ta_to_key(ta: str) -> str:
    """Convert TA name to cache key format."""
    return ta.lower().replace(" ", "_")

def load_librarian_cache(button: str) -> dict:
    """
    Load consolidated Librarian cache for a button.
    Returns dict with TA keys, or empty dict if file doesn't exist.
    """
    cache_file = Path(__file__).parent / "cache" / f"librarian_{button}.json"

    if cache_file.exists():
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return {}

def save_librarian_cache(button: str, cache_data: dict):
    """Save consolidated Librarian cache for a button."""
    cache_file = Path(__file__).parent / "cache" / f"librarian_{button}.json"

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)

def update_librarian_for_ta(button: str, ta: str, ta_records, force: bool = False):
    """
    Update Librarian cache for ONE TA (append/replace pattern).
    Preserves other TAs in the consolidated cache.
    Converts DataFrames to JSON-serializable format.
    """
    import pandas as pd

    ta_key = ta_to_key(ta)
    cache_data = load_librarian_cache(button)

    if ta_key in cache_data and not force:
        print(f"[LIBRARIAN] {ta} already cached for {button}. Use --refresh-librarian to regenerate.")
        return False

    # Convert DataFrames to serializable format
    serializable_records = {}
    for key, value in ta_records.items():
        if isinstance(value, pd.DataFrame):
            serializable_records[key] = {
                "columns": list(value.columns),
                "rows": value.to_dict('records')
            }
        else:
            serializable_records[key] = value

    cache_data[ta_key] = serializable_records
    save_librarian_cache(button, cache_data)

    print(f"[LIBRARIAN] Updated {button} cache with {ta} data")
    return True

def load_journalist_cache(button: str) -> dict:
    """
    Load consolidated Journalist cache for a button.
    Returns dict with TA keys, or empty dict if file doesn't exist.
    """
    cache_file = Path(__file__).parent / "cache" / f"journalist_{button}.json"

    if cache_file.exists():
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return {}

def save_journalist_cache(button: str, cache_data: dict):
    """Save consolidated Journalist cache for a button."""
    cache_file = Path(__file__).parent / "cache" / f"journalist_{button}.json"

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)

def update_journalist_for_ta(button: str, ta: str, metadata: dict, analysis: str):
    """
    Update Journalist cache for ONE TA (append/replace pattern).
    Preserves other TAs in the consolidated cache.
    """
    ta_key = ta_to_key(ta)
    cache_data = load_journalist_cache(button)

    cache_data[ta_key] = {
        "metadata": metadata,
        "analysis": analysis
    }

    save_journalist_cache(button, cache_data)

    report_length = len(analysis)
    print(f"[JOURNALIST] Updated {button} cache with {ta} report ({report_length:,} characters)")


def enrich_kol_with_external_data(speaker_name: str, affiliation: str, ta: str, max_pubs: int = 10, max_trials: int = 10) -> dict:
    """
    Enrich KOL profile with PubMed publications and ClinicalTrials.gov data.

    Args:
        speaker_name: Full name of KOL (e.g., "Matthew D. Galsky")
        affiliation: Institution affiliation
        ta: Therapeutic area (for context-specific queries)
        max_pubs: Maximum publications to retrieve (default 10)
        max_trials: Maximum trials to retrieve (default 10)

    Returns:
        dict with keys: 'publications' (list), 'trials' (list), 'summary_stats'
    """
    result = {
        'publications': [],
        'trials': [],
        'summary_stats': {'pub_count': 0, 'trial_count': 0}
    }

    # Get TA-specific medical synonyms
    ta_keywords = TA_MEDICAL_SYNONYMS.get(ta, [ta.lower()])
    ta_query_part = " OR ".join([f'"{kw}"' for kw in ta_keywords])

    print(f"[API]     Querying PubMed for {speaker_name}...")

    # ========== PubMed API Query ==========
    try:
        # Build PubMed query: Author name + TA keywords + past 5 years
        api_key = 'a67284fcad76aef86e7e6281b44e59224508'
        date_query = '2020:2025[pdat]'  # Past 5 years

        # Try full name first
        author_query = f'{speaker_name}[Author]'
        full_query = f'{author_query} AND ({ta_query_part}) AND {date_query}'

        # Step 1: Search for PMIDs
        search_url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={urllib.parse.quote(full_query)}&retmax={max_pubs}&retmode=json&api_key={api_key}'

        with urllib.request.urlopen(search_url, timeout=10) as response:
            search_data = json.loads(response.read().decode())
            pmids = search_data.get('esearchresult', {}).get('idlist', [])

        # If 0 results and name has 3+ parts, try without last part
        # (e.g., "Enrique Grande Pulido" → "Enrique Grande")
        if not pmids and len(speaker_name.split()) >= 3:
            name_parts = speaker_name.split()
            shorter_name = " ".join(name_parts[:-1])
            print(f"[API]       No results with full name, trying: {shorter_name}")

            author_query = f'{shorter_name}[Author]'
            full_query = f'{author_query} AND ({ta_query_part}) AND {date_query}'
            search_url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={urllib.parse.quote(full_query)}&retmax={max_pubs}&retmode=json&api_key={api_key}'

            time.sleep(0.11)  # Rate limit
            with urllib.request.urlopen(search_url, timeout=10) as response:
                search_data = json.loads(response.read().decode())
                pmids = search_data.get('esearchresult', {}).get('idlist', [])

        if pmids:
            # Step 2: Fetch publication details
            pmid_list = ",".join(pmids)
            fetch_url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid_list}&retmode=xml&api_key={api_key}'

            time.sleep(0.11)  # Rate limit: 10 requests/sec with API key

            with urllib.request.urlopen(fetch_url, timeout=15) as response:
                xml_data = response.read().decode()
                root = ET.fromstring(xml_data)

                for article in root.findall('.//PubmedArticle'):
                    try:
                        title_elem = article.find('.//ArticleTitle')
                        journal_elem = article.find('.//Journal/Title')
                        year_elem = article.find('.//PubDate/Year')
                        pmid_elem = article.find('.//PMID')

                        title = title_elem.text if title_elem is not None else "Unknown"
                        journal = journal_elem.text if journal_elem is not None else "Unknown"
                        year = year_elem.text if year_elem is not None else "Unknown"
                        pmid = pmid_elem.text if pmid_elem is not None else None

                        pub_data = {
                            'title': title,
                            'journal': journal,
                            'year': year
                        }
                        if pmid:
                            pub_data['pmid'] = pmid
                            pub_data['url'] = f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/'

                        result['publications'].append(pub_data)
                    except Exception as e:
                        print(f"[API]       Error parsing publication: {e}")
                        continue

            # Sort by year (most recent first) - return ALL (up to 10) for AI to select most relevant
            result['publications'].sort(key=lambda x: x.get('year', '0'), reverse=True)

            result['summary_stats']['pub_count'] = len(pmids)
            print(f"[API]       Found {len(pmids)} publications (2020-2025)")
        else:
            print(f"[API]       No publications found")

    except Exception as e:
        print(f"[API]       PubMed API error: {e}")

    print(f"[API]     Querying ClinicalTrials.gov for {speaker_name}...")

    # ========== ClinicalTrials.gov API Query ==========
    try:
        # Build CT.gov query: Author name + TA keywords
        # CT.gov uses "SEARCH[StudyType] AND SEARCH[Condition]" format
        # We'll use the person field for investigator name
        ct_query = f'{speaker_name} AND ({" OR ".join(ta_keywords)})'

        # CT.gov API v2 (newer endpoint)
        ct_url = f'https://clinicaltrials.gov/api/v2/studies?query.term={urllib.parse.quote(ct_query)}&pageSize={max_trials}&format=json'

        time.sleep(1.0)  # Rate limit: 1 request/sec

        with urllib.request.urlopen(ct_url, timeout=15) as response:
            ct_data = json.loads(response.read().decode())
            studies = ct_data.get('studies', [])

            for study in studies:
                try:
                    protocol = study.get('protocolSection', {})
                    identification = protocol.get('identificationModule', {})
                    status = protocol.get('statusModule', {})
                    contacts = protocol.get('contactsLocationsModule', {})

                    nct_id = identification.get('nctId', 'Unknown')
                    title = identification.get('briefTitle', 'Unknown')
                    overall_status = status.get('overallStatus', 'Unknown')

                    # Try to determine role (PI vs listed)
                    role = "Listed"

                    # Check central contacts for PI
                    central_contacts = contacts.get('centralContacts', [])
                    for contact in central_contacts:
                        if speaker_name.lower() in contact.get('name', '').lower():
                            role = "Principal Investigator"
                            break

                    # Check overall officials for Study Chair/PI
                    officials = contacts.get('overallOfficials', [])
                    for official in officials:
                        if speaker_name.lower() in official.get('name', '').lower():
                            role = official.get('role', 'Listed')
                            break

                    result['trials'].append({
                        'nct_id': nct_id,
                        'title': title,
                        'status': overall_status,
                        'role': role,
                        'url': f'https://clinicaltrials.gov/study/{nct_id}'
                    })

                except Exception as e:
                    print(f"[API]       Error parsing trial: {e}")
                    continue

            result['summary_stats']['trial_count'] = len(studies)
            print(f"[API]       Found {len(studies)} trials")

    except Exception as e:
        print(f"[API]       ClinicalTrials.gov API error: {e}")

    return result


def enrich_institution_with_trials(institution_name: str, ta: str, max_trials: int = 50) -> dict:
    """
    Enrich institution profile with ClinicalTrials.gov data (2015-2025).

    Returns up to 5 most relevant trials (blend of recent + active + high phase).
    Filters out Terminated/Unknown status trials.

    Args:
        institution_name: Full institution name (e.g., "MD Anderson Cancer Center")
        ta: Therapeutic area (e.g., "Bladder Cancer")
        max_trials: Maximum trials to fetch (default 50, will filter to top 5)

    Returns:
        dict with keys: 'trials' (list), 'total_count', 'active_count'
    """
    result = {
        'trials': [],
        'total_count': 0,
        'active_count': 0
    }

    # Get TA-specific condition keywords
    ta_keywords = TA_MEDICAL_SYNONYMS.get(ta, [ta.lower()])
    condition_query = " OR ".join(ta_keywords)

    print(f"[API]     Querying ClinicalTrials.gov for {institution_name}...")

    try:
        # Build ClinicalTrials.gov API v2 query
        base_url = "https://clinicaltrials.gov/api/v2/studies"

        # Try multiple name variants (institution names vary in CT.gov)
        name_variants = [
            institution_name,  # Full name
            institution_name.split(',')[0].strip(),  # Remove city if present
        ]

        # Add common abbreviations
        if "MD Anderson" in institution_name:
            name_variants.append("MD Anderson Cancer Center")
        if "Memorial Sloan" in institution_name:
            name_variants.append("Memorial Sloan Kettering")

        all_trials = []

        for name_variant in name_variants:
            params = {
                "query.spons": name_variant,  # Search collaborators/sponsors
                "query.cond": condition_query,
                "filter.advanced": "AREA[StartDate]RANGE[2015-01-01,2025-12-31]",
                "pageSize": max_trials,
                "format": "json",
                "fields": "NCTId,BriefTitle,Phase,OverallStatus,StartDate,CompletionDate"
            }

            response = urllib.request.urlopen(
                base_url + "?" + urllib.parse.urlencode(params),
                timeout=15
            )
            data = json.loads(response.read().decode())

            studies = data.get('studies', [])
            all_trials.extend(studies)

            if studies:
                print(f"[API]       Found {len(studies)} trials with '{name_variant}'")
                break  # Use first variant that returns results

            time.sleep(1)  # Rate limiting

        if not all_trials:
            print(f"[API]       No trials found")
            return result

        # Process and filter trials
        processed_trials = []
        for study in all_trials:
            try:
                protocol = study.get('protocolSection', {})
                identification = protocol.get('identificationModule', {})
                status_module = protocol.get('statusModule', {})
                design = protocol.get('designModule', {})

                nct_id = identification.get('nctId', 'Unknown')
                title = identification.get('briefTitle', 'Unknown')

                # Extract phase
                phases = design.get('phases', [])
                phase = phases[0] if phases else 'Phase Not Specified'

                # Extract status
                overall_status = status_module.get('overallStatus', 'Unknown')

                # Filter out Terminated/Unknown/Withdrawn
                if overall_status in ['Terminated', 'Unknown', 'Withdrawn', 'Suspended']:
                    continue

                # Extract dates
                start_date_struct = status_module.get('startDateStruct', {})
                start_date = start_date_struct.get('date', 'Unknown')

                completion_date_struct = status_module.get('completionDateStruct', {})
                completion_date = completion_date_struct.get('date', 'Unknown')

                # Count as active if recruiting/active
                if overall_status in ['Recruiting', 'Active, not recruiting', 'Enrolling by invitation']:
                    result['active_count'] += 1

                processed_trials.append({
                    'nct_id': nct_id,
                    'title': title,
                    'phase': phase,
                    'status': overall_status,
                    'start_date': start_date,
                    'completion_date': completion_date,
                    'url': f'https://clinicaltrials.gov/study/{nct_id}',
                    'is_active': overall_status in ['Recruiting', 'Active, not recruiting', 'Enrolling by invitation']
                })
            except Exception as e:
                print(f"[API]       Error parsing trial: {e}")
                continue

        result['total_count'] = len(processed_trials)

        # Tag trials for EMD/competitor relevance
        emd_keywords = ['avelumab', 'bavencio', 'pimicotinib', 'vimseltinib']
        competitor_keywords = [
            'pembrolizumab', 'keytruda', 'nivolumab', 'opdivo', 'atezolizumab', 'tecentriq',
            'durvalumab', 'imfinzi', 'cemiplimab', 'libtayo', 'enfortumab vedotin', 'padcev',
            'sacituzumab govitecan', 'trodelvy', 'erdafitinib', 'balversa'
        ]

        for trial in processed_trials:
            title_lower = trial['title'].lower()
            trial['is_emd'] = any(kw in title_lower for kw in emd_keywords)
            trial['is_competitor'] = any(kw in title_lower for kw in competitor_keywords)

        # Get 5 most recent trials (by start date)
        recent_trials = sorted(processed_trials, key=lambda x: x['start_date'], reverse=True)[:5]

        # Get 5 most EMD/competitor-relevant trials
        relevant_trials = [t for t in processed_trials if t['is_emd'] or t['is_competitor']]
        relevant_trials.sort(key=lambda t: (t['is_emd'], t['is_competitor'], t['start_date']), reverse=True)
        relevant_trials = relevant_trials[:5]

        # Combine and deduplicate
        combined = {t['nct_id']: t for t in (recent_trials + relevant_trials)}
        result['trials'] = list(combined.values())[:10]  # Max 10 total
        result['recent_trials'] = recent_trials
        result['relevant_trials'] = relevant_trials

        print(f"[API]       Returning {len(result['trials'])} trials: {len(recent_trials)} recent, {len(relevant_trials)} EMD/competitor-relevant ({result['active_count']} active)")

    except Exception as e:
        print(f"[API]       ClinicalTrials.gov API error: {e}")

    return result


# ============================================================================
# PROMPT BUILDERS - Generate prompts for each button type
# ============================================================================

def build_competitor_intelligence_prompt(ta: str, filtered_df, tables_data: Dict) -> str:
    """
    Build comprehensive prompt for competitor intelligence deep research.
    """
    portfolio = EMD_PORTFOLIO.get(ta, {})

    # Load landscape context if available
    landscape_context = load_landscape_context_for_section1(ta)
    landscape_context_str = ""
    if landscape_context:
        landscape_context_str = f"""

**CURATED COMPETITIVE LANDSCAPE CONTEXT ({ta})**:
Use this vetted information as the foundation for Section 1, combining it with your medical knowledge:

- **Treatment Paradigm**: {landscape_context.get('treatment_paradigm', 'N/A')}
- **Recent Approvals**: {landscape_context.get('recent_approvals', 'N/A')}
- **Key Trials**: {landscape_context.get('key_trials', 'N/A')}
- **Emerging Competitors**: {landscape_context.get('emerging_competitors', 'N/A')}
- **Guideline Updates**: {landscape_context.get('guideline_updates', 'N/A')}
"""

    prompt = f"""
You are a senior Medical Affairs competitive intelligence analyst at EMD Serono/Merck KGaA.
Generate a comprehensive competitive intelligence report for {ta} based on ESMO 2025 conference data.

**EMD SERONO CONTEXT**:
- Primary Asset: {portfolio.get('primary_asset', 'None')}
- Indication: {portfolio.get('indication', 'N/A')}
- Conference: ESMO 2025
- Total Studies in Dataset: {len(filtered_df)}
{landscape_context_str}

**INSTRUCTIONS - DO NOT INCLUDE THESE IN YOUR RESPONSE**:

For Section 1 (Competitive Landscape Overview):
- Use the curated landscape context above (when provided) combined with your medical knowledge
- Integrate this with the ESMO 2025 conference data to provide strategic competitive insights
- Focus on how the current landscape affects EMD Serono/Merck KGaA's positioning
- **INCLUDE our EMD Serono/Merck KGaA assets in Section 1.2 and 1.3** - this section explains our competitive position, so tepotinib/avelumab/cetuximab SHOULD appear here

For Section 2 (ESMO 2025 Competitor Activity Analysis):
- Base your analysis ONLY on the data tables provided below
- You have study TITLES only (no abstracts yet available)
- Do NOT mention drugs or data not present in the tables
- Focus on what the study titles and trial designs suggest
- **CRITICAL COMPETITOR FOCUS FOR SECTION 2 ONLY**:
{get_ta_specific_competitor_guidance(ta)}

**DATA TABLES PROVIDED**:
{tables_data.get('table_context', '')}

**YOUR TASK**: Generate a report following this EXACT structure (do not include the bracketed instructions above):

# Competitive Intelligence Report: {ta} at ESMO 2025

## Executive Summary
Write a concise 3-4 sentence paragraph covering:
- What's the most significant competitor activity at ESMO 2025 (based on the data)
- Key implications for EMD Serono/Merck KGaA's {portfolio.get('primary_asset', 'portfolio')}
- Top 2-3 priority actions for Medical Affairs

IMPORTANT: Begin with language like "ESMO 2025 {ta} competitor activity centers on..." to clearly indicate this is competitive landscape analysis, not all conference activity.

---

## 1. Competitive Landscape Overview
*Context current as of January 2025. Verify critical details with latest NCCN/ESMO guidelines.*

### 1.1 Current Treatment Paradigm in {ta}
- What are the current NCCN/ESMO guidelines for treating {ta}?
- What is the standard treatment sequence (1L, 2L, 3L+)?
- Where does EMD's {portfolio.get('primary_asset', 'portfolio')} fit in the current treatment algorithm?

### 1.2 Approved Competitive Drugs
- Which drugs are currently FDA/EMA approved for {ta}?
- What are their labeled indications and positioning?
- Any recent label expansions, withdrawals, or regulatory updates?

### 1.3 EMD Serono/Merck KGaA's Competitive Position
- How does {portfolio.get('primary_asset', 'portfolio')} compare to competitors?
- What are our key clinical differentiators?
- What are the main competitive threats to our market position?

---

## 2. ESMO 2025 Competitor Activity Analysis

**ADAPTIVE STRUCTURE INSTRUCTIONS**:
- **High activity (10+ studies)**: Use all subsections 2.1, 2.2, 2.3, 2.4 with full detail
- **Moderate activity (3-9 studies)**: Use subsections 2.1, 2.2, 2.4; merge 2.3 into 2.2 if appropriate
- **Limited activity (1-2 studies)**: Consolidate into streamlined analysis - avoid repetition across subsections. Focus on depth over structure.

### 2.1 Competitor Presentation Volume and Focus

**IMPORTANT: Start with a brief summary of TOP competitor DRUG REGIMENS by volume** (use the EXACT counts you will report in the detailed analysis below - be consistent!):

Example format:
"At ESMO 2025, the most prominent competitor regimens by presentation volume were:
1. Enfortumab vedotin + pembrolizumab (EV+P): 10 studies
2. Pembrolizumab monotherapy: 8 studies
3. Nivolumab combinations: 6 studies
[Continue for top 8-10 DRUG regimens...]"

**CRITICAL RULES**:
- List ONLY actual drug/regimen names (e.g., "EV+P", "nivolumab+ipilimumab", "tepotinib"), NOT abstract categories like "Invited Discussant", "emerging therapies", "long-term care", "biomarker analysis"
- The counts MUST match exactly what you report in the detailed regimen list below (e.g., "EV+P (Count: X)")
- Do not recount or reinterpret - use the same numbers consistently throughout Section 2.1
- If the dataset has very few actual drug competitors (e.g., Lung Cancer with only MET-specific drugs), it's OK to list just 2-3 regimens rather than padding with non-drug categories

---

**FORMATTING: Use STRUCTURED LIST ONLY - NO TABLES**

**IMPORTANT MINDSET**: Include ALL studies involving competitor regimens, not just new treatment trials. This includes:
- Therapeutic trials (Phase 1/2/3)
- Biomarker/companion diagnostic studies
- Real-world evidence analyses
- Translational/correlative studies
- CNS penetration studies
- Prognostic tool development
- Any study demonstrating competitor positioning, evidence-building, or strategic development

After the volume summary above, present detailed drug/regimen activity as a numbered list:

**1. Drug/Regimen (Count: X studies)**
   - **MOA Class:** ADC + ICI / TKI / etc.
   - **Development Phase:** Phase 3 / Real-world / Biomarker / Translational / Mixed
   - **Key Abstracts:** LBA2, 3094P, 3089P, etc.
   - **Brief note:** One sentence on significance (include all study types - treatment, biomarker, RWE, etc.)

**2. Next Drug/Regimen (Count: X studies)**
   - **MOA Class:** ...
   - **Development Phase:** ...
   - **Key Abstracts:** ...
   - **Brief note:** ...

Then provide analysis:
- Which MOA classes dominate?
- Any surprising new entrants?
- What types of evidence are competitors building (treatment, biomarker, RWE)?
- Strategic implications for EMD

### 2.2 High-Priority Competitor Studies

**FORMATTING: Use STRUCTURED NUMBERED LIST (not table) to avoid truncation:**

**For LIMITED activity (1-2 studies)**: Provide in-depth analysis of each study without creating redundant subsections. Focus on strategic implications, investigator/institutional context, and competitive positioning.

**For MODERATE/HIGH activity**: Use standard structure:

**1. [Abstract ID] Drug/Regimen - Study Title (abbreviated)**
   - **Investigators:** Lead author — Institution
   - **Session:** Date/Session Type (LBA/Proffered/Poster)
   - **Strategic Relevance:** Why this matters to EMD (2-3 sentences with full detail)

**2. [Abstract ID] Drug/Regimen - Study Title (abbreviated)**
   - **Investigators:** ...
   - **Session:** ...
   - **Strategic Relevance:** ...

Focus on:
- Late-breaking abstracts (LBA#) - highest impact
- Phase 3 studies that could change guidelines
- Direct competitors to EMD's asset/indication
- Combination therapies threatening current standards

### 2.3 Emerging Threats and Novel Approaches

**ONLY INCLUDE THIS SUBSECTION IF:**
- There are 3+ studies with distinct mechanisms/approaches, OR
- There are clear emerging threats beyond standard competitive activity

**FORMATTING: Use STRUCTURED NUMBERED LIST (not table):**

**1. [Abstract ID] Drug/Mechanism - Threat Type**
   - **Phase:** X
   - **Why This Is a Threat:** Full explanation (2-3 sentences, no truncation)

**2. [Abstract ID] Drug/Mechanism - Threat Type**
   - **Phase:** X
   - **Why This Is a Threat:** ...

Include:
- Novel MOAs (ADCs, bispecifics, radioligands, TKIs)
- Biomarker-driven strategies (FGFR+, HER2+, NECTIN4+)
- First-in-human or innovative designs (perioperative, neoadjuvant)

### 2.4 Geographic and Institutional Patterns

**FORMATTING: Use STRUCTURED LISTS ONLY - NO TABLES**

**Geographic Distribution:**
- **United States:** List top institutions and their focus areas
- **Europe:** List top institutions and their focus areas
- **Asia/China:** List top institutions and their focus areas
- **Other regions:** Brief mention if significant

**Top KOLs** (≥2 high-impact abstracts):
- **Name — Institution:** List of abstract IDs and focus
- **Name — Institution:** List of abstract IDs and focus

**Regional Patterns and Insights:**
- Bullet points on what each region focuses on
- Strategic implications for Medical Affairs engagement

---

**WRITING REQUIREMENTS**:
1. **NO TABLES ANYWHERE** - Use structured numbered/bulleted lists only
2. **Section 1**: Use the current landscape context provided + your medical knowledge for accurate strategic insights
3. **Section 2**: ONLY discuss what's explicitly in the data provided - no hallucination allowed
4. Be specific with abstract identifiers (LBA2, 3094P, etc.) when discussing ESMO data
5. Analyze ALL major competitors in the data, not just the #1 drug
6. Write for Medical Affairs professionals (MSLs, Medical Directors, leadership)
7. Use professional oncology terminology
8. Focus on actionable intelligence, not generic observations
9. **CRITICAL:** Do NOT include a "Notes and Recommendations for Medical Affairs" section at the end
10. End the report after Section 2.4 Geographic and Institutional Patterns
"""

    return prompt


def build_kol_intelligence_prompt(ta: str, filtered_df, tables_data: Dict) -> str:
    """Build comprehensive prompt for KOL intelligence deep research with external API enrichment."""
    portfolio = EMD_PORTFOLIO.get(ta, {})

    # Build therapeutic area-specific market context
    market_context = ""
    if ta == "Merkel Cell":
        market_context = """
**MARKET CONTEXT (Merkel Cell Carcinoma):**
- Rare cancer: ~3,000 US cases/year (~400-500 at ESMO-relevant institutions)
- Highly immunogenic: ~80% Merkel cell polyomavirus-driven
- EMD Market Position: Avelumab (Bavencio) was FIRST immunotherapy approved for MCC (2017, accelerated approval)
- Current Standard: Avelumab or pembrolizumab as first-line for metastatic MCC (both NCCN-preferred)
- Strategic Implication: Small KOL network means EMD can engage nearly ALL active MCC researchers
- Adjuvant Setting: ADAM trial (adjuvant avelumab) ongoing; STAMP (adjuvant pembrolizumab) results at this ESMO may establish new standard
"""
    elif ta == "Bladder Cancer":
        market_context = """
**MARKET CONTEXT (Bladder Cancer):**
- Common GU malignancy: ~82,000 US cases/year
- EMD Market Position: Avelumab 1L maintenance (JAVELIN Bladder 100) is NCCN Category 1 preferred since 2020
- Strategic Threat: EV-302 (enfortumab vedotin + pembrolizumab) shows OS benefit in 1L setting, may pressure maintenance paradigm
- Large KOL network: Focus on thought leaders with maintenance/1L positioning influence
"""
    elif ta == "Lung Cancer":
        market_context = """
**MARKET CONTEXT (Lung Cancer):**
- Largest oncology indication: ~235,000 US cases/year
- EMD Market Position: Tepotinib (Tepmetko) for METex14 NSCLC (NCCN-preferred, rare ~3% NSCLC)
- Small targetable subset within large indication means niche KOL network focused on MET alterations
- Strategic Focus: MET-driven resistance, combinations, biomarker strategies
"""
    # Add other TAs as needed

    # Load competitor intelligence cache for competitor drug context
    competitor_context = ""
    try:
        ci_cache_file = Path(__file__).parent / "cache" / "journalist_competitor.json"
        if ci_cache_file.exists():
            with open(ci_cache_file, 'r', encoding='utf-8') as f:
                ci_cache = json.load(f)
            ta_key = ta_to_key(ta)
            if ta_key in ci_cache:
                competitor_context = f"\n**COMPETITOR DRUGS IN {ta} (from CI cache):**\n"
                competitor_context += "Use this context to identify KOLs presenting competitor drug studies.\n"
                competitor_context += f"Key competitors: {', '.join(portfolio.get('key_competitors', []))}\n\n"
    except Exception as e:
        print(f"[JOURNALIST] Could not load CI cache for competitor context: {e}")

    prompt = f"""
You are a senior Medical Affairs KOL management strategist at EMD Serono/Merck KGaA.
Generate an HCP-CENTRIC KOL intelligence report for {ta} based on ESMO 2025 data.

CRITICAL INSTRUCTIONS:
- Structure: LANDSCAPE OVERVIEW first, then INDIVIDUAL KOL DEEP DIVES, then SUMMARY TABLE
- You have ENRICHED KOL PROFILES with PubMed publications (2015-2025) and ClinicalTrials.gov trial involvement
- Use external data to provide MEDICAL CONTEXT about why each KOL matters (research output, not speculation)
- Identify KOLs with competitor drug trial involvement (especially PI or Study Chair)
- Be DATA-DRIVEN: cite specific publications (year, title), trial NCT IDs, ESMO study identifiers
- NO generic recommendations like "send thank-you notes" or "MLR approval" - focus on INTELLIGENCE, not process
- NO "specific discussion topics" - MSLs know what to ask; focus on WHY each KOL matters
- Keep it CONCISE: This is intelligence, not an execution playbook

LIMITATIONS TO ACKNOWLEDGE:
- Co-authorship networks: NOT available (conference data has single speaker per study)
- Historical KOL presence: NOT available (ESMO 2025 snapshot only, cannot assess if repeat presenter)
- Explicitly state these limitations in landscape overview
{market_context}
CONTEXT:
- EMD Serono Asset: {portfolio.get('primary_asset', 'None')}
- Therapeutic Area: {ta}
- Conference: ESMO 2025
- Total Studies: {len(filtered_df)}
{competitor_context}

DATA PROVIDED:
{tables_data.get('table_context', '')}

================================================================================
INSTRUCTIONS (DO NOT INCLUDE ANY OF THIS SECTION IN YOUR OUTPUT):
================================================================================

1. DEDUPLICATION: Each HCP should appear EXACTLY ONCE. If you already profiled an HCP, skip them entirely (no heading, no "[Profile already above]", nothing).

2. COMPETITOR TAGS: In enriched data, you'll see "is_competitor_presenter: True" flags. DO NOT include "[COMPETITOR STUDY PRESENTER]" text in your output. Simply note in the Executive Summary that they present competitor studies.

3. SECTION HEADERS: Use clean headers. Write "**Conference Activity & Why They Matter:**" NOT "**Conference Activity & Why They Matter (BLENDED SECTION):**"

4. PUBLICATIONS: List only the 5 MOST RECENT publications (sorted by year, descending). Do NOT add "← COMPETITOR" or "← EMD-aligned" tags. Use the full enriched publication data to inform your "Why They Matter" analysis (e.g., note if they publish on competitor assets), but only list the 5 most recent in the Publications section.

5. TRIALS: List up to 3 most recent trials (ClinicalTrials.gov typically returns trials in reverse chronological order). If trial_count = 0, omit the entire Trial Involvement section.

================================================================================
OUTPUT STRUCTURE (COPY THIS EXACTLY, FILLING IN BRACKETS WITH DATA):
================================================================================

# HCP Engagement Priorities: {ta} at ESMO 2025

## Executive Summary
- **Top 3 Priority HCPs:** [Name] ([Institution]) - [1-line rationale]
- **Conference presence:** [N] HCPs tracked with [N] LBAs, [N] orals, [N] posters
- **Geography:** US [N]%, EU [N]%, Asia [N]%
- **Competitor involvement:** [N] of tracked HCPs presenting competitor drug studies
- **Highest-impact opportunity:** [1-2 sentences]
- **Data limitation note:** "Co-authorship networks and historical KOL presence not assessed (single conference snapshot)"

---

## 1. Priority HCP Profiles

### [Full Name] – [Institution Name]

[1-2 sentence introduction: who they are, where from, what known for]

**Conference Activity & Why They Matter:**
[Flowing narrative integrating their ESMO presentation(s) with strategic relevance. Format: [Identifier] - [Type]: [Title]. Date/Time: [Date], [Time]. Room: [Room]. Then explain why this matters for EMD positioning.]

**Latest Publications (2020-2025):**
- ([Year]) [Title]. [Journal]. [PubMed](url)
- ([Year]) [Title]. [Journal]. [PubMed](url)
- ([Year]) [Title]. [Journal]. [PubMed](url)
- ([Year]) [Title]. [Journal]. [PubMed](url)
- ([Year]) [Title]. [Journal]. [PubMed](url)

[ONLY IF trial_count > 0:]
**Trial Involvement (ClinicalTrials.gov):**
- [[NCT ID]](url): [Role] - [Title] - [Status]
- [[NCT ID]](url): [Role] - [Title] - [Status]
- [[NCT ID]](url): [Role] - [Title] - [Status]

---

[Repeat for each unique HCP]

---

## 2. Competitor Study Presenters (MSL Engagement Opportunities)

If competitor studies data is provided in "HIGH-PRIORITY COMPETITOR STUDIES" section:

List each competitor study with full presentation details for MSL engagement planning:

**[Abstract ID]** - [Title]
- **Presenters:** [Names from data]
- **Date/Time:** [Date], [Time]
- **Room:** [Room]
- **Session:** [Session type]

If no competitor studies data provided, skip this section entirely.

---

## 3. Conference Logistics

**Daily Schedule Highlights:**

Only include this section if there are CONFLICTS or HIGH-PRIORITY sessions:
- If multiple must-attend presentations overlap: List the conflict and suggest priority
- If there's a single must-attend LBA: Note it as "Priority session"
- If all presentations are posters with no conflicts: State "No scheduling conflicts; all presentations accessible during poster sessions"

Example format (only if conflicts exist):
- [Date] [Time]: [Session Type] ([HCP Name]) - [Room] → **Must Attend** [if LBA or critical]
- [Date] [Time]: Concurrent posters in [Room] ([List HCP names]) → Accessible during poster session

---

END REPORT

**WHAT NOT TO INCLUDE:**
- ❌ NO "specific discussion topics" sections
- ❌ NO "post-conference follow-up timeline" (that's project management, not intelligence)
- ❌ NO "internal alignment needs" (compliance/governance, not KOL intel)
- ❌ NO generic recommendations like "send thank-you notes" or "request poster PDFs"
- ❌ NO "Research Landscape Insights" as separate section (integrate into landscape overview)
- ❌ NO "KOL Competitor Engagement Assessment" as separate section (integrate into individual profiles)

**ABSOLUTELY CRITICAL - NO TABLES:**
- ❌ DO NOT CREATE ANY MARKDOWN TABLES (no | pipes | formatting |)
- ❌ DO NOT create "Summary Table", "KOL Roster Table", or any table format
- ❌ Tables don't render properly in the application UI
- ✅ Use PROSE, bullet points, and numbered lists ONLY
- ✅ If you need to summarize multiple HCPs, use bullet points with names bolded

**CRITICAL:**
- Be CONCISE - this is intelligence for busy Medical Directors and MSLs
- Focus on DATA and CONTEXT, not execution steps
- If there are fewer than 10 notable KOLs, only profile the ones that matter (don't pad with marginal researchers)
- Use EXACT publication titles from PubMed - DO NOT paraphrase or shorten titles
"""

    return prompt


def build_institution_intelligence_prompt(ta: str, filtered_df, tables_data: Dict) -> str:
    """Build institution intelligence prompt for MSL territory planning."""
    portfolio = EMD_PORTFOLIO.get(ta, {})

    prompt = f"""
You are a Medical Affairs intelligence analyst at EMD Serono/Merck KGaA.
Generate an institution-centric HCP engagement report for {ta} based on ESMO 2025 data.

CONTEXT:
- EMD Serono Asset: {portfolio.get('primary_asset', 'None')}
- Therapeutic Area: {ta}
- Conference: ESMO 2025
- Total Studies: {len(filtered_df)}

DATA PROVIDED:
{tables_data.get('table_context', '')}

================================================================================
INSTRUCTIONS (DO NOT INCLUDE ANY OF THIS SECTION IN YOUR OUTPUT):
================================================================================

1. This report is for MSL territory planning and engagement optimization
2. Focus on actionable data: who is presenting, when, where
3. Trial engagement data shows institutional research capabilities (2015-2025)
4. Use enriched institution data (ClinicalTrials.gov) to contextualize expertise
5. Geographic directory must list EVERY speaker for complete territory coverage

================================================================================
OUTPUT STRUCTURE (COPY THIS EXACTLY, FILLING IN BRACKETS WITH DATA):
================================================================================

# HCP Engagement Priorities by Institution: {ta} at ESMO 2025

## Executive Summary
- **Top 5 Institutions:** [List institutions with presentation counts]
- **Geographic Distribution:** US [N]%, EU [N]%, Asia [N]%
- **Total Unique Speakers:** [N] speakers from [N] institutions
- **Trial Engagement Snapshot:** [X] institutions with active trials in {ta}

---

## 1. Top 10 Institutions (Deep Dive)

### [Institution Name] – [City, Country]
**[N] presentations at ESMO 2025**

**Research Focus at ESMO 2025:**
[2-3 sentence synthesis of presentation themes based on titles. Example: "Focused on PD-1/PD-L1 checkpoint inhibitors in 1L NSCLC, with 4 studies on durvalumab combinations. Also presenting biomarker-driven patient selection strategies and real-world effectiveness data."]

**Trial Engagement Profile (2015-2025):**
[ONLY include if trial data exists in enriched profiles]
- **Total {ta} Trials:** [N] trials as collaborator
- **Active Trials:** [N] currently recruiting

**Latest Trials (5 most recent by start date):**
  - [[NCT ID]](url): [Title] ([Phase], [Status], Started [Year])
  - [[NCT ID]](url): [Title] ([Phase], [Status], Started [Year])
  [List 5 most recent trials that are NOT EMD-sponsored or major competitor trials]

**Relevant to EMD Serono/Merck KGaA:**
  - [[NCT ID]](url): [Title] ([Phase], [Status], Started [Year]) [EMD-ALIGNED]
  - [[NCT ID]](url): [Title] ([Phase], [Status], Started [Year]) [COMPETITOR]
  [List ALL trials tagged with either [EMD-ALIGNED] or [COMPETITOR]]
  [EMD-ALIGNED trials: avelumab, bavencio, pimicotinib, vimseltinib, tepotinib]
  [COMPETITOR trials: pembrolizumab, nivolumab, atezolizumab, durvalumab, enfortumab vedotin, sacituzumab govitecan, erdafitinib]
  [If no EMD or competitor trials, write: "None identified in ClinicalTrials.gov (2015-2025)"]

[If NO trial data: Skip this entire section]

**Key Presenters & Sessions:**
Group by presenter name to avoid repetition. Format:
- **[Name]:**
  - [Abstract ID]: [Title]. ([Date], [Time], [Room], [Session Type])
  - [Abstract ID]: [Title]. ([Date], [Time], [Room], [Session Type])
[Consolidate all sessions under each unique presenter name]

---

[Repeat for each of top 10 institutions]

---

## 2. Geographic Distribution Summary

**United States ([N] institutions, [N] presentations)**
- Top 3 US institutions: [List]

**Europe ([N] institutions, [N] presentations)**
- Top 3 EU institutions: [List]

**Asia ([N] institutions, [N] presentations)**
- Top 3 Asia institutions: [List]

---

## 3. Complete Speaker Directory by Geography

For comprehensive MSL territory planning, below is every institution presenting in {ta} at ESMO 2025, organized by geography.

**CRITICAL CANONICALIZATION INSTRUCTIONS:**
The raw speaker directory data contains full affiliations with departments/divisions. You MUST intelligently canonicalize institution names:

**Examples of what to do:**
- "Dana-Farber Cancer Institute, Boston, MA" + "Department of Medical Oncology, Dana-Farber Cancer Institute" + "Dana-Farber/Brigham and Women's Hospital" → ALL become "Dana-Farber Cancer Institute" with combined speaker list
- "Division of Solid Tumor Oncology, Department of Medicine, University Hospitals Cleveland Medical Center, Case Western..." → Extract "University Hospitals Cleveland Medical Center"
- "Department of Urology, MD Anderson Cancer Center, Madrid, Spain" → "MD Anderson Cancer Center, Madrid"
- "Memorial Sloan Kettering Cancer Center, NY" + "Department of Medicine, Memorial Sloan Kettering" → "Memorial Sloan Kettering Cancer Center"
- "University of Texas MD Anderson Cancer Center" + "MD Anderson Cancer Center, Houston" → "MD Anderson Cancer Center, Houston"
- "Perelman School of Medicine, University of Pennsylvania" + "University of Pennsylvania / Abramson Cancer Center" → "University of Pennsylvania"
- "Yale New Haven Hospital / Yale School of Medicine" → "Yale University / Yale Cancer Center"

**Rules:**
1. Strip department/division/center prefixes but keep the actual institution name
2. For long affiliations, extract the main hospital/university/cancer center name
3. Differentiate by LOCATION when institutions have multiple sites (e.g., MD Anderson Madrid vs Houston)
4. Merge obvious variants (Dana-Farber vs Dana Farber vs Department of X, Dana-Farber)
5. **MERGE DUPLICATES AGGRESSIVELY**: If two institutions share >80% name similarity AND same location, they are the SAME institution
6. If one institution name is a subset of another (e.g., "Mayo Clinic" vs "Mayo Clinic Rochester"), merge under the more specific name
7. After merging, update speaker counts to reflect combined totals (e.g., if merging 3 + 5 speakers, show "(8)" not "(1)")
8. Use your reasoning - you're smart enough to identify which affiliations refer to the same place!

**CRITICAL: NO TRUNCATION IN SECTION 1 (Top 10 Deep Dive)**
- ❌ FORBIDDEN: "... (other MSK presenters)" or "... and X more presenters"
- ✅ REQUIRED: List EVERY SINGLE presenter explicitly with their full presentation details
- If an institution has 12 presenters, list all 12 - do not summarize or truncate

**Output Format:**

**[Country Name] ([N] institutions after canonicalization, [N] total speakers)**

- [Canonicalized Institution Name] ([N] speakers): [Speaker 1], [Speaker 2], [Speaker 3], ...
- [Canonicalized Institution Name] ([N] speakers): [Speaker 1], [Speaker 2], ...

[Continue for all countries, organized alphabetically]

[Format: Comma-separated speaker names, compact format]

---

END REPORT

**DO NOT INCLUDE:**
- ❌ NO "Notes & next steps" section
- ❌ NO "suggested for MSL teams" recommendations
- ❌ NO "Prioritise outreach" guidance
- ❌ NO generic action items or follow-up suggestions
"""

    return prompt


def build_research_insights_prompt(ta: str, filtered_df, tables_data: Dict) -> str:
    """Build comprehensive prompt for research insights deep research."""
    portfolio = EMD_PORTFOLIO.get(ta, {})

    # Extract regimen groups and unmet need signals from tables_data
    regimen_groups = tables_data.get('regimen_groups', [])
    unmet_need_signals = tables_data.get('unmet_need_signals', [])

    # Build regimen context
    regimen_context = ""
    if regimen_groups:
        regimen_context = "\n**KEY REGIMEN GROUPS (≥3 studies each):**\n"
        for regimen in regimen_groups:
            regimen_context += f"- {regimen['regimen']} ({regimen['count']} studies)\n"
            regimen_context += f"  Example studies: {', '.join(regimen['examples'][:3])}\n"

    # Build unmet need context
    unmet_need_context = ""
    if unmet_need_signals:
        unmet_need_context = "\n**UNMET NEED SIGNALS:**\n"
        for signal in unmet_need_signals:
            unmet_need_context += f"- {signal['category']}: {signal['count']} studies\n"

    prompt = f"""
You are a senior Medical Affairs research intelligence analyst.
Generate a comprehensive research insights report for {ta} based on ESMO 2025 data.

You may use your medical knowledge to provide clinical context for questions and unmet needs.

CONTEXT:
- Therapeutic Area: {ta}
- Conference: ESMO 2025
- Total Studies: {len(filtered_df)}

DATA PROVIDED:
{tables_data.get('table_context', '')}
{regimen_context}
{unmet_need_context}

**CRITICAL INSTRUCTIONS:**

1. **ADAPT TO DATA VOLUME** - Be proportional:
   - If 500 studies in TA → Go deep, identify trends
   - If 5 studies in TA → Be concise, focus on what's there
   - If a section has no data → Say "Limited data" and move on in 1-2 sentences
   - Don't invent categories when data doesn't support them

2. **PROPORTIONALITY EXAMPLES**:
   - If only 3 institutions → say "3 institutions presenting" (not "Top 10")
   - If no regimens have ≥3 studies → skip Section 2.2 entirely or state "No regimen clusters emerged"
   - If biomarker data sparse → acknowledge in 1-2 sentences, don't force a section

3. **FLEXIBILITY**:
   - You may reorder or merge sections based on what the data shows
   - You may adjust subsection titles to match actual themes
   - Skip empty sections entirely rather than writing "No data available"

4. **NO TABLES** - Everything must be narrative format with examples

5. **NO STRATEGIC RECOMMENDATIONS** - Focus on evidence gaps and scientific trends

6. **GUIDELINES**:
   - Use specific study identifiers as examples (e.g., "Study 1234P demonstrated...")
   - Provide medical context where helpful (e.g., "Post-progression in bladder cancer typically...")
   - NO cross-trial efficacy comparisons (different populations, designs)
   - Be honest about data limitations

---

**SUGGESTED STRUCTURE** (adapt as needed):

# Research Insights & Trends: {ta} at ESMO 2025

## Executive Summary
Synthesize 3-5 most significant developments in novel mechanisms, biomarker advances, regimen evolution, and evidence gaps. Be proportional to data volume.

## 1. Emerging Mechanisms & Targets

**Focus**: Novel MOAs, technology platforms (ADCs, bispecifics, cell therapy), clinical proof-of-concept

**Example format**:
> The meeting featured three distinct novel MOA categories: [describe]. Notable examples include Study 1234P exploring [mechanism] with preliminary ORR of [X]%, and Study 5678MO investigating [platform]...

## 2. Evidence Gaps & Unmet Needs

**THIS IS THE CORE MEDICAL AFFAIRS VALUE SECTION**

### 2.1 Clinical Questions Being Addressed

Identify what questions the field is actively pursuing:
- Post-progression settings (after standard therapy)
- Special populations (elderly, brain mets, poor performance status)
- Sequencing strategies
- Biomarker-selected populations
- Resistance mechanisms

**Example format**:
> Post-progression after [standard therapy] remains a priority, with [N] studies addressing this gap. Study 1234P evaluated [approach] in patients progressing on [prior therapy]...

### 2.2 Key Regimen Evolution

**ONLY INCLUDE IF ≥3 studies per regimen**

For regimens with ≥3 studies, synthesize evolution themes:
- What dose/schedule variations are being tested?
- What populations are being explored?
- What endpoints are prioritized?

**Example format**:
> **Enfortumab vedotin + Pembrolizumab (8 studies)**: The field is actively exploring earlier-line positioning (Studies 1234P, 5678MO) and special populations including brain metastases (Study 9012P). Emerging questions center on optimal dosing in frail elderly patients...

Limit to 200-300 words per regimen. Synthesize insights, don't just list studies.

### 2.3 White Space Analysis

Where are there gaps in the evidence? What populations, settings, or questions are NOT being addressed?

## 3. Biomarker & Precision Medicine Landscape

**Focus**: Biomarker prevalence data, predictive enrichment strategies, resistance mechanisms

**Example format**:
> PD-L1 selection was evaluated across [N] studies, with enrichment thresholds ranging from [X]% to [Y]%. Novel biomarker approaches included [describe Study 1234P's ctDNA strategy]...

## 4. Translational & Early-Phase Research

**Focus**: First-in-human studies, Phase 1 data, 3-5 year pipeline signals

## 5. Safety & Tolerability Insights

**Focus**: Grade 3/4 AE rates, dose optimization strategies, special population tolerability

## 6. Innovation Watchlist

**NO TABLES - Narrative format, grouped by priority**

**Example format**:
> **High Priority: Next-generation KRAS G12C inhibitor (Study LBA123, Dana-Farber)**
> This Phase 2 study demonstrated a 38% ORR with median PFS of 6.2 months in heavily pretreated colorectal cancer, suggesting potential for activity in KRAS G12C beyond lung cancer. Key innovation: [describe mechanism refinement]. Relevance to field: [implications].

---

**REMINDER**: Adapt this structure based on data volume. If you only have 10 studies, you might combine sections 4-5 into one paragraph. Your job is to extract maximum medical affairs value from whatever data exists.
"""

    return prompt


def build_strategic_priorities_prompt(ta: str, filtered_df, tables_data: Dict) -> str:
    """Build comprehensive prompt for strategic priorities deep research."""
    portfolio = EMD_PORTFOLIO.get(ta, {})

    prompt = f"""
You are a senior Medical Affairs strategic planning executive at EMD Serono/Merck KGaA.
Generate a comprehensive strategic priorities report for {ta} based on ESMO 2025 data.

CONTEXT:
- EMD Serono Asset: {portfolio.get('primary_asset', 'None')}
- Therapeutic Area: {ta}
- Conference: ESMO 2025
- Total Studies: {len(filtered_df)}

DATA PROVIDED:
{tables_data.get('table_context', '')}

Generate a comprehensive report following this EXACT structure:

# Strategic Priorities Report: {ta} at ESMO 2025

## Executive Summary
- Critical strategic imperatives
- Portfolio positioning assessment
- Medical Affairs priorities

## 1. Portfolio Positioning Assessment

### 1.1 Current Market Position
- EMD's competitive standing in {ta}
- Market share trends and dynamics
- Strengths, weaknesses, opportunities, threats

### 1.2 Competitive Dynamics
- Key competitive shifts at ESMO
- Emerging threats to portfolio
- Defensive strategies required

### 1.3 Lifecycle Management
- Current asset maturity assessment
- Line extension opportunities
- Next-generation planning needs

## 2. ESMO 2025 Strategic Signals

### 2.1 Market-Shaping Data
- Presentations influencing guidelines
- Payer-relevant outcomes
- Real-world evidence impact

### 2.2 Disruptive Innovations
- Technologies threatening current paradigm
- New entrants to monitor
- Platform shifts requiring response

### 2.3 Partnership Signals
- Collaboration announcements
- M&A indicators
- Licensing opportunities

## 3. Medical Affairs Strategic Plan

### 3.1 Near-Term Priorities (0-6 months)
- ESMO data response strategy
- KOL engagement imperatives
- Publication planning updates
- Medical education priorities

### 3.2 Mid-Term Priorities (6-18 months)
- Evidence generation plans
- Guideline influence strategy
- Market access support
- Competitive differentiation

### 3.3 Long-Term Vision (18+ months)
- Portfolio evolution strategy
- Innovation pipeline needs
- Capability building requirements

## 4. Cross-Functional Integration

### 4.1 R&D Alignment
- Clinical development priorities
- Translational research focus
- Innovation partnership needs

### 4.2 Commercial Synergies
- Market access implications
- Promotional strategy alignment
- Customer engagement priorities

### 4.3 External Affairs
- Policy implications
- Patient advocacy engagement
- Healthcare system partnerships

## 5. Executive Recommendations

### 5.1 Portfolio Decisions
- Investment priorities
- Divestment considerations
- Resource reallocation needs

### 5.2 Organizational Capabilities
- Talent acquisition priorities
- Technology infrastructure needs
- Process optimization opportunities

### 5.3 Risk Mitigation
- Competitive defense strategies
- Regulatory preparedness
- Market access contingencies

## 6. Action Plan & Metrics
- 90-day immediate actions
- Success metrics and KPIs
- Governance and review cadence
"""

    return prompt


def extract_regimen_groups(filtered_df, ta: str, min_studies: int = 3) -> List[Dict]:
    """
    Detect and group studies by treatment regimen (≥3 studies threshold).

    Returns list of dicts: [
        {'regimen': 'EV+Pembrolizumab', 'count': 8, 'examples': ['1234P', '5678MO', ...]},
        ...
    ]
    """
    # TA-specific regimen patterns
    REGIMEN_PATTERNS = {
        'Bladder Cancer': {
            'EV+Pembrolizumab': [r'enfortumab.{0,30}pembrolizumab', r'EV\+P', r'pembrolizumab.{0,30}enfortumab'],
            'Sacituzumab': [r'sacituzumab', r'\bSG\b', r'Trodelvy'],
            'Erdafitinib': [r'erdafitinib', r'Balversa', r'FGFR inhibitor'],
            'Nivolumab': [r'nivolumab', r'Opdivo'],
            'Durvalumab': [r'durvalumab', r'Imfinzi'],
        },
        'Lung Cancer': {
            'Osimertinib': [r'osimertinib', r'Tagrisso'],
            'Amivantamab': [r'amivantamab', r'Rybrevant'],
            'Lorlatinib': [r'lorlatinib', r'Lorbrena'],
            'Alectinib': [r'alectinib', r'Alecensa'],
            'Tepotinib': [r'tepotinib', r'Tepmetko'],
        },
        'Colorectal Cancer': {
            'FOLFOX': [r'FOLFOX', r'oxaliplatin.{0,20}5-FU'],
            'FOLFIRI': [r'FOLFIRI', r'irinotecan.{0,20}5-FU'],
            'Bevacizumab': [r'bevacizumab', r'Avastin'],
            'Cetuximab': [r'cetuximab', r'Erbitux'],
            'Panitumumab': [r'panitumumab', r'Vectibix'],
        },
        'Renal Cancer': {
            'Nivolumab+Ipilimumab': [r'nivolumab.{0,20}ipilimumab', r'nivo.{0,10}ipi'],
            'Pembrolizumab+Lenvatinib': [r'pembrolizumab.{0,20}lenvatinib', r'pembro.{0,10}lenva'],
            'Cabozantinib': [r'cabozantinib', r'Cabometyx'],
            'Lenvatinib+Everolimus': [r'lenvatinib.{0,20}everolimus'],
        },
        'Head and Neck Cancer': {
            'Pembrolizumab': [r'pembrolizumab', r'Keytruda'],
            'Nivolumab': [r'nivolumab', r'Opdivo'],
            'Cetuximab': [r'cetuximab', r'Erbitux'],
        }
    }

    # Get patterns for this TA (default to empty if TA not in dict)
    ta_patterns = REGIMEN_PATTERNS.get(ta, {})

    # Count matches for each regimen
    regimen_counts = {}
    regimen_examples = {}

    for regimen, patterns in ta_patterns.items():
        matches = filtered_df[
            filtered_df['Title'].str.contains('|'.join(patterns), case=False, na=False, regex=True)
        ]

        if len(matches) >= min_studies:
            regimen_counts[regimen] = len(matches)
            # Get up to 5 example identifiers
            regimen_examples[regimen] = matches['Identifier'].head(5).tolist()

    # Format as list of dicts, sorted by count (descending)
    regimen_groups = [
        {
            'regimen': regimen,
            'count': count,
            'examples': regimen_examples[regimen]
        }
        for regimen, count in sorted(regimen_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    print(f"[REGIMEN] Found {len(regimen_groups)} regimen groups with ≥{min_studies} studies")
    return regimen_groups


def extract_unmet_need_signals(filtered_df) -> List[Dict]:
    """
    Tag studies addressing unmet needs based on keyword patterns.

    Returns list of dicts: [
        {'category': 'Post-progression', 'count': 15},
        {'category': 'Brain metastases', 'count': 8},
        ...
    ]
    """
    UNMET_NEED_PATTERNS = {
        'Post-progression': [
            r'post.{0,10}progression',
            r'refractory',
            r'previously treated',
            r'after.{0,15}(failure|progression)',
            r'second-line',
            r'third-line',
            r'\b2L\b',
            r'\b3L\b'
        ],
        'Brain metastases': [
            r'brain metastas',
            r'CNS metastas',
            r'intracranial',
            r'leptomeningeal'
        ],
        'Elderly patients': [
            r'elderly',
            r'geriatric',
            r'age.{0,5}≥\s*70',
            r'age.{0,5}≥\s*75',
            r'older patient'
        ],
        'Poor performance status': [
            r'PS\s*[2-4]',
            r'ECOG\s*[2-4]',
            r'performance status\s*[2-4]',
            r'poor performance'
        ],
        'Sequencing strategies': [
            r'sequenc(e|ing)',
            r'treatment sequence',
            r'optimal order',
            r'rechallenge',
            r're-challenge'
        ],
        'Resistance mechanisms': [
            r'resistance',
            r'acquired resistance',
            r'mechanism.{0,10}resistance',
            r'bypass.{0,10}resistance'
        ],
        'Rare mutations': [
            r'rare mutation',
            r'uncommon alteration',
            r'low-frequency',
            r'atypical mutation'
        ]
    }

    # Count matches for each category
    signal_counts = {}

    for category, patterns in UNMET_NEED_PATTERNS.items():
        matches = filtered_df[
            filtered_df['Title'].str.contains('|'.join(patterns), case=False, na=False, regex=True)
        ]

        if len(matches) > 0:
            signal_counts[category] = len(matches)

    # Format as list of dicts, sorted by count (descending)
    unmet_need_signals = [
        {
            'category': category,
            'count': count
        }
        for category, count in sorted(signal_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    print(f"[UNMET NEEDS] Found {len(unmet_need_signals)} unmet need signal categories")
    return unmet_need_signals


def prepare_table_data(button_type: str, ta: str, filtered_df, refresh_librarian: bool = False) -> Dict:
    """
    Prepare all necessary tables for a given button type.
    Returns formatted table data for inclusion in prompts.
    """
    tables_data = {}
    table_context_parts = []

    print(f"[PREP] Preparing tables for {button_type} - {ta}")
    print(f"[PREP] Filtered dataset: {len(filtered_df)} studies")

    if button_type == "competitor":
        # CONSOLIDATED CACHING: Librarian -> Tagger -> Structured Data

        # Step 1: Load or extract Librarian data (consolidated caching)
        ta_key = ta_to_key(ta)
        librarian_cache = load_librarian_cache(button_type)

        if ta_key in librarian_cache and not refresh_librarian:
            print(f"[LIBRARIAN] Loading {ta} data from consolidated cache...")
            librarian_records = librarian_cache[ta_key]
            print(f"[LIBRARIAN] Loaded {len(librarian_records)} studies from cache")
        else:
            if refresh_librarian:
                print(f"[LIBRARIAN] --refresh-librarian flag set, regenerating {ta} data...")
            else:
                print(f"[LIBRARIAN] {ta} not found in cache, extracting...")

            print(f"[LIBRARIAN] Running extraction on {len(filtered_df)} {ta} studies...")
            librarian_records = librarian_process_all(ta, batch_size=20)

            # Update consolidated cache
            update_librarian_for_ta(button_type, ta, librarian_records, force=refresh_librarian)

        # Step 2: Load aliases and run Tagger
        aliases = load_aliases(ta)
        print(f"[TAGGER] Normalizing entities...")
        tagged_data = tag_and_aggregate(librarian_records, aliases)

        # Step 3: Prepare regimen summary (NOT full data yet - two-step approach)
        stats = tagged_data['stats']
        competitor_regimens = tagged_data['competitor_regimens']
        emerging_regimens = tagged_data['emerging_regimens']
        regimen_counts = tagged_data['regimen_counts']
        biomarker_counts = tagged_data['biomarker_counts']

        print(f"[PREP] Extracted {stats['total_studies']} studies")
        print(f"[PREP] Found {stats['unique_regimens']} regimens ({stats['competitor_regimens_found']} competitors, {stats['emerging_regimens_found']} emerging)")
        print(f"[PREP] Found {stats['unique_biomarkers']} biomarkers")

        # STEP 1 PROMPT: Ask AI to identify important regimens (NO full data yet)
        structured_summary = f"""**COMPETITOR INTELLIGENCE DATA ({ta})**

**Study Extraction Summary:**
- Total studies analyzed: {stats['total_studies']}
- Studies with treatment regimens: {stats['studies_with_regimen']}
- Studies with biomarker mentions: {stats['studies_with_biomarkers']}

**Top Treatment Regimens (by study count):**
"""
        for regimen, count in list(regimen_counts.items())[:15]:
            tag = "★ COMPETITOR" if regimen in competitor_regimens else "○ Emerging"
            structured_summary += f"- {regimen}: {count} studies [{tag}]\n"

        structured_summary += f"""
**Top Biomarkers (by study count):**
"""
        for biomarker, count in list(biomarker_counts.items())[:10]:
            structured_summary += f"- {biomarker}: {count} studies\n"

        structured_summary += f"""

**TASK**: Based on the regimen counts above, identify the TOP 10-15 most important regimens/keywords
for competitive intelligence analysis. Return as a JSON list of search terms.

Example: ["enfortumab vedotin", "pembrolizumab", "disitamab vedotin", "avelumab", ...]

Focus on:
- High study count regimens
- Direct competitors to avelumab
- Novel ADC/IO combinations
- Biomarker-driven therapies
"""

        # Store tagged_data for use in Step 2 (keyword-based filtering)
        tables_data["competitor_intelligence"] = tagged_data
        tables_data["regimen_summary"] = structured_summary
        table_context_parts.append(structured_summary)

    elif button_type == "kol":
        # Generate KOL-specific tables
        authors_table = generate_top_authors_table(filtered_df, n=30)
        if not authors_table.empty:
            tables_data["top_authors"] = authors_table
            table_context_parts.append(f"**TOP AUTHORS TABLE:**\n{authors_table.to_markdown(index=False)}\n")

            # Add ESMO presentation samples from top KOLs (with logistics)
            top_kol_abstracts = []
            for speaker in authors_table['Speaker'].head(10):
                speaker_studies = filtered_df[filtered_df['Speakers'].str.contains(speaker, na=False)].head(3)
                if not speaker_studies.empty:
                    top_kol_abstracts.append(speaker_studies[['Identifier', 'Title', 'Speakers', 'Affiliation', 'Date', 'Time', 'Room', 'Session']])

            if top_kol_abstracts:
                kol_studies = pd.concat(top_kol_abstracts).drop_duplicates()
                tables_data["kol_studies"] = kol_studies
                table_context_parts.append(f"**KOL ESMO 2025 PRESENTATIONS (with logistics):**\n{kol_studies.to_markdown(index=False)}\n")

            # ENHANCEMENT: Enrich top 10 KOLs with PubMed + ClinicalTrials.gov data
            print(f"[LIBRARIAN] Enriching top 10 KOLs with external API data (PubMed + ClinicalTrials.gov)...")
            enriched_kols = []
            for idx, row in authors_table.head(10).iterrows():
                speaker_name = row['Speaker']
                affiliation = row['Affiliation']
                print(f"[LIBRARIAN]   - Enriching: {speaker_name} ({affiliation})")

                external_data = enrich_kol_with_external_data(speaker_name, affiliation, ta)
                enriched_kols.append({
                    'speaker': speaker_name,
                    'affiliation': affiliation,
                    'location': row['Location'],
                    'esmo_studies': row['# Studies'],
                    'recent_publications': external_data.get('publications', []),
                    'clinical_trials': external_data.get('trials', []),
                    'pub_count_5yr': external_data.get('summary_stats', {}).get('pub_count', 0),
                    'trial_count': external_data.get('summary_stats', {}).get('trial_count', 0),
                    'is_competitor_presenter': False  # Will be updated below
                })

            # ENHANCEMENT: Add competitor study presenters from CI cache (Section 2.2 High-Priority Studies)
            print(f"[LIBRARIAN] Checking CI cache for competitor study presenters...")
            ci_cache_path = Path(__file__).parent / "cache" / "deep_intelligence" / f"competitor_{ta_to_key(ta)}.json"
            competitor_studies_list = []  # Store competitor study details for the journalist

            if ci_cache_path.exists():
                try:
                    with open(ci_cache_path, 'r', encoding='utf-8') as f:
                        ci_data = json.load(f)

                    # Extract investigator names from Section 2.2 High-Priority Competitor Studies
                    analysis_text = ci_data.get('analysis', '')

                    # Find Section 2.2
                    import re
                    section_2_2_start = analysis_text.find('### 2.2 High-Priority Competitor Studies')
                    section_2_3_start = analysis_text.find('### 2.3', section_2_2_start)

                    if section_2_2_start != -1:
                        section_2_2 = analysis_text[section_2_2_start:section_2_3_start if section_2_3_start != -1 else section_2_2_start + 15000]

                        # Parse each study entry (format: "1. Abstract ID — Title")
                        study_pattern = r'\d+\.\s+([A-Z0-9]+)\s+—\s+(.*?)\n\s+-\s*Investigators?:\s*([^—\n]+)'
                        study_matches = re.findall(study_pattern, section_2_2, re.DOTALL)

                        print(f"[LIBRARIAN]   Found {len(study_matches)} competitor studies in CI Section 2.2")

                        # For each competitor study, find full presentation details
                        for abstract_id, title_snippet, investigators in study_matches:
                            # Match to filtered_df to get full presentation details
                            matching_study = filtered_df[filtered_df['Identifier'].str.contains(abstract_id, na=False, case=False)]
                            if not matching_study.empty:
                                study_row = matching_study.iloc[0]
                                competitor_studies_list.append({
                                    'identifier': study_row['Identifier'],
                                    'title': study_row['Title'],
                                    'speakers': study_row.get('Speakers', investigators.strip()),
                                    'date': study_row.get('Date', 'Date TBD'),
                                    'time': study_row.get('Time', 'Time TBD'),
                                    'room': study_row.get('Room', 'Room TBD'),
                                    'session': study_row.get('Session', 'Session TBD')
                                })

                        print(f"[LIBRARIAN]   Matched {len(competitor_studies_list)} competitor studies to presentation details")

                        # Also collect investigator names for marking existing KOLs
                        competitor_presenters = set()
                        for _, _, investigators in study_matches:
                            names = [n.strip() for n in investigators.split(',')]
                            competitor_presenters.update(names)

                        print(f"[LIBRARIAN]   Found {len(competitor_presenters)} unique investigators in CI Section 2.2")

                        # Mark existing enriched KOLs if they're competitor presenters
                        for kol in enriched_kols:
                            if kol['speaker'] in competitor_presenters:
                                kol['is_competitor_presenter'] = True
                                print(f"[LIBRARIAN]     ✓ {kol['speaker']} is high-priority competitor presenter")

                        # Add NEW competitor presenters not already in top 10 (limit to top 5 by presentation count)
                        # Normalize names for comparison (strip spaces, lowercase)
                        existing_names = {kol['speaker'].strip().lower() for kol in enriched_kols}
                        new_competitor_presenters = {name for name in competitor_presenters
                                                      if name.strip().lower() not in existing_names}

                        # Match names to filtered_df and sort by presentation count
                        new_presenter_data = []
                        for presenter in new_competitor_presenters:
                            presenter_studies = filtered_df[filtered_df['Speakers'].str.contains(presenter, na=False, case=False)]
                            if not presenter_studies.empty:
                                new_presenter_data.append({
                                    'name': presenter,
                                    'count': len(presenter_studies),
                                    'affiliation': presenter_studies.iloc[0]['Affiliation'],
                                    'location': presenter_studies.iloc[0].get('Speaker Location', 'Unknown')
                                })

                        # Sort by presentation count and take top 5
                        new_presenter_data.sort(key=lambda x: x['count'], reverse=True)

                        for presenter_info in new_presenter_data[:5]:  # Limit to 5 additional presenters
                            print(f"[LIBRARIAN]   + Adding CI high-priority presenter: {presenter_info['name']} ({presenter_info['count']} studies)")

                            external_data = enrich_kol_with_external_data(presenter_info['name'], presenter_info['affiliation'], ta)
                            enriched_kols.append({
                                'speaker': presenter_info['name'],
                                'affiliation': presenter_info['affiliation'],
                                'location': presenter_info['location'],
                                'esmo_studies': presenter_info['count'],
                                'recent_publications': external_data.get('publications', []),
                                'clinical_trials': external_data.get('trials', []),
                                'pub_count_5yr': external_data.get('summary_stats', {}).get('pub_count', 0),
                                'trial_count': external_data.get('summary_stats', {}).get('trial_count', 0),
                                'is_competitor_presenter': True
                            })

                        if len(new_presenter_data) > 5:
                            print(f"[LIBRARIAN]   (Limited to top 5 of {len(new_presenter_data)} new competitor presenters)")

                    else:
                        print(f"[LIBRARIAN]   Warning: Section 2.2 not found in CI cache")

                except Exception as e:
                    print(f"[LIBRARIAN]   Warning: Failed to load CI cache - {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"[LIBRARIAN]   No CI cache found at {ci_cache_path}")

            # Add enriched KOL profiles to table context
            if enriched_kols:
                tables_data["enriched_kol_profiles"] = enriched_kols

                # Create summary table for AI Journalist
                enrichment_summary = ["**ENRICHED HCP PROFILES (Top KOLs + Competitor Study Presenters, with PubMed + ClinicalTrials.gov data):**\n"]
                for kol in enriched_kols:
                    # Add competitor flag if applicable
                    comp_flag = " [COMPETITOR STUDY PRESENTER]" if kol.get('is_competitor_presenter', False) else ""
                    kol_summary = f"\n**{kol['speaker']}**{comp_flag} ({kol['affiliation']}, {kol['location']})\n"
                    kol_summary += f"  - ESMO 2025 Presentations: {kol['esmo_studies']}\n"
                    kol_summary += f"  - Publications (2020-2025): {kol['pub_count_5yr']}\n"
                    kol_summary += f"  - Clinical Trials (Listed): {kol['trial_count']}\n"

                    # Add 5 most recent publications with full data
                    if kol['recent_publications']:
                        kol_summary += f"  - Latest Publications (2020-2025, showing 5 most recent):\n"
                        for pub in kol['recent_publications'][:5]:  # Only pass 5 most recent
                            journal = pub.get('journal', 'Journal not specified')
                            url = pub.get('url', '')
                            if url:
                                kol_summary += f"    * ({pub['year']}) {pub['title']} {journal}. [PubMed]({url})\n"
                            else:
                                kol_summary += f"    * ({pub['year']}) {pub['title']} {journal}.\n"

                        # For context: mention if there are more publications beyond the 5 shown
                        if len(kol['recent_publications']) > 5:
                            kol_summary += f"    * [{len(kol['recent_publications']) - 5} additional publications 2020-2025 not listed]\n"

                    # Add clinical trials with roles and URLs
                    if kol['clinical_trials']:
                        kol_summary += f"  - Clinical Trial Involvement:\n"
                        for trial in kol['clinical_trials'][:3]:
                            url = trial.get('url', '')
                            if url:
                                kol_summary += f"    * [{trial['role']}] [{trial['nct_id']}]({url}): {trial['title']} ({trial['status']})\n"
                            else:
                                kol_summary += f"    * [{trial['role']}] {trial['nct_id']}: {trial['title']} ({trial['status']})\n"

                    enrichment_summary.append(kol_summary)

                table_context_parts.append("\n".join(enrichment_summary))
                print(f"[LIBRARIAN] Successfully enriched {len(enriched_kols)} KOL profiles")

                # Add competitor studies for MSL engagement opportunities
                if competitor_studies_list:
                    competitor_summary = ["\n**HIGH-PRIORITY COMPETITOR STUDIES (for MSL Engagement):**"]
                    competitor_summary.append(f"Total competitor studies from CI cache: {len(competitor_studies_list)}\n")
                    for study in competitor_studies_list:
                        competitor_summary.append(f"\n**{study['identifier']}** - {study['title']}")
                        competitor_summary.append(f"  Presenters: {study['speakers']}")
                        competitor_summary.append(f"  Date/Time: {study['date']}, {study['time']}")
                        competitor_summary.append(f"  Room: {study['room']}")
                        competitor_summary.append(f"  Session: {study['session']}\n")
                    table_context_parts.append("\n".join(competitor_summary))

    elif button_type == "institution":
        # Generate institution-specific tables
        inst_table = generate_top_institutions_table(filtered_df, n=30)
        if not inst_table.empty:
            tables_data["top_institutions"] = inst_table
            table_context_parts.append(f"**TOP INSTITUTIONS TABLE:**\n{inst_table.to_markdown(index=False)}\n")

            # Enrich top 10 institutions with ClinicalTrials.gov data
            print(f"[LIBRARIAN] Enriching top 10 institutions with ClinicalTrials.gov trial data...")
            enriched_institutions = []

            for idx, row in inst_table.head(10).iterrows():
                institution_name = row['Institution']
                presentation_count = row['# Studies']

                print(f"[LIBRARIAN]   - Enriching: {institution_name}")

                # Get trial data
                trial_data = enrich_institution_with_trials(institution_name, ta)

                # Get all presenters from this institution
                inst_presenters = filtered_df[
                    filtered_df['Affiliation'].str.contains(institution_name, na=False, case=False)
                ]

                # Build enriched institution profile
                enriched_institutions.append({
                    'institution': institution_name,
                    'presentation_count': presentation_count,
                    'total_trials': trial_data['total_count'],
                    'active_trials': trial_data['active_count'],
                    'top_trials': trial_data['trials'],
                    'presenters': inst_presenters[['Speakers', 'Identifier', 'Title', 'Date', 'Time', 'Room', 'Session']].to_dict('records')
                })

            # Build enriched context for journalist
            enriched_context = ["**ENRICHED INSTITUTION PROFILES (Top 10 with ClinicalTrials.gov Data):**\n"]
            for inst in enriched_institutions:
                inst_summary = f"\n**{inst['institution']}**\n"
                inst_summary += f"  - ESMO 2025 Presentations: {inst['presentation_count']}\n"
                inst_summary += f"  - Clinical Trials (2015-2025): {inst['total_trials']} total, {inst['active_trials']} active\n"

                # Pass both recent trials and relevant trials separately to journalist
                trial_data_from_enrich = enrich_institution_with_trials(institution_name, ta)  # This is redundant but leaving for now

                if inst['top_trials']:
                    # Get recent trials (exclude EMD and competitor trials from Latest to avoid duplication)
                    recent_trials_list = [t for t in inst['top_trials'] if not t.get('is_emd') and not t.get('is_competitor')][:5]
                    # Get BOTH EMD-sponsored AND competitor trials for the "Relevant" section
                    relevant_trials_list = [t for t in inst['top_trials'] if t.get('is_emd') or t.get('is_competitor')]

                    inst_summary += f"  - Latest Trials (5 most recent):\n"
                    for trial in recent_trials_list:
                        year = trial['start_date'][:4] if trial['start_date'] != 'Unknown' else 'Unknown'
                        inst_summary += f"    * [{trial['nct_id']}]({trial['url']}): {trial['title']} ({trial['phase']}, {trial['status']}, Started {year})\n"

                    if relevant_trials_list:
                        inst_summary += f"  - Relevant to EMD Serono/Merck KGaA:\n"
                        for trial in relevant_trials_list:
                            year = trial['start_date'][:4] if trial['start_date'] != 'Unknown' else 'Unknown'
                            # Tag EMD-sponsored trials with [EMD-ALIGNED], competitors with [COMPETITOR]
                            tag = '[EMD-ALIGNED]' if trial.get('is_emd') else '[COMPETITOR]'
                            inst_summary += f"    * [{trial['nct_id']}]({trial['url']}): {trial['title']} ({trial['phase']}, {trial['status']}, Started {year}) {tag}\n"
                    else:
                        inst_summary += f"  - Relevant to EMD Serono/Merck KGaA: None identified in ClinicalTrials.gov (2015-2025)\n"

                inst_summary += f"  - Key Presenters at ESMO 2025 ({len(inst['presenters'])} total):\n"
                for presenter in inst['presenters'][:5]:  # Show first 5
                    inst_summary += f"    * {presenter['Speakers']} - {presenter['Identifier']}: {presenter['Title']} ({presenter['Date']}, {presenter['Time']}, {presenter['Room']})\n"

                if len(inst['presenters']) > 5:
                    inst_summary += f"    * ... and {len(inst['presenters']) - 5} more presenters\n"

                enriched_context.append(inst_summary)

            table_context_parts.append("\n".join(enriched_context))
            print(f"[LIBRARIAN] Successfully enriched {len(enriched_institutions)} institutions")

            # Also add complete speaker directory data (for Section 3)
            # Pass RAW affiliations - let the AI journalist canonicalize intelligently
            print(f"[LIBRARIAN] Building complete speaker directory by geography (raw affiliations)...")

            speaker_directory = {}
            for idx, row in filtered_df.iterrows():
                if pd.notna(row.get('Speakers')) and pd.notna(row.get('Affiliation')):
                    speakers = [s.strip() for s in row['Speakers'].split(',')]
                    institution = row['Affiliation']  # Use RAW affiliation - AI will canonicalize
                    location = row.get('Speaker Location', 'Unknown')

                    # Parse geography (Country, State if US)
                    country = location.split(',')[-1].strip() if ',' in location else location

                    if country not in speaker_directory:
                        speaker_directory[country] = {}

                    if institution not in speaker_directory[country]:
                        speaker_directory[country][institution] = set()

                    for speaker in speakers:
                        speaker_directory[country][institution].add(speaker)

            # Format for journalist
            directory_context = ["\n**COMPLETE SPEAKER DIRECTORY BY GEOGRAPHY:**\n"]
            for country in sorted(speaker_directory.keys()):
                total_institutions = len(speaker_directory[country])
                total_speakers = sum(len(speakers) for speakers in speaker_directory[country].values())
                directory_context.append(f"\n**{country} ({total_institutions} institutions, {total_speakers} speakers)**")

                for institution in sorted(speaker_directory[country].keys()):
                    speakers = sorted(speaker_directory[country][institution])
                    directory_context.append(f"  - {institution} ({len(speakers)} speakers): {', '.join(speakers)}")

            table_context_parts.append("\n".join(directory_context))
            print(f"[LIBRARIAN] Speaker directory complete: {len(speaker_directory)} countries")

    elif button_type == "insights":
        # Extract regimen groups (≥3 studies threshold)
        print(f"[LIBRARIAN] Extracting regimen groups...")
        regimen_groups = extract_regimen_groups(filtered_df, ta, min_studies=3)
        tables_data["regimen_groups"] = regimen_groups

        # Extract unmet need signals
        print(f"[LIBRARIAN] Detecting unmet need signals...")
        unmet_need_signals = extract_unmet_need_signals(filtered_df)
        tables_data["unmet_need_signals"] = unmet_need_signals

        # Generate research insights tables
        biomarker_table = generate_biomarker_moa_table(filtered_df)
        if not biomarker_table.empty:
            tables_data["biomarker_moa"] = biomarker_table
            table_context_parts.append(f"**BIOMARKER/MOA TABLE:**\n{biomarker_table.to_markdown(index=False)}\n")

        # Novel studies (phase 1, first-in-human, etc.)
        novel_studies = filtered_df[
            filtered_df['Title'].str.contains(
                'phase 1|phase i|first-in-human|novel|investigational',
                case=False, na=False
            )
        ].head(30)[['Identifier', 'Title', 'Speakers', 'Affiliation']]

        if not novel_studies.empty:
            tables_data["novel_studies"] = novel_studies
            table_context_parts.append(f"**NOVEL/EARLY-PHASE STUDIES:**\n{novel_studies.to_markdown(index=False)}\n")

    elif button_type == "strategic":
        # Generate strategic overview tables
        # Competition overview
        competitor_table = match_studies_with_competitive_landscape(filtered_df, ta)
        if not competitor_table.empty:
            ranking_table = generate_drug_moa_ranking(competitor_table, n=10)
            tables_data["competitive_landscape"] = ranking_table
            table_context_parts.append(f"**COMPETITIVE LANDSCAPE:**\n{ranking_table.to_markdown(index=False)}\n")

        # Top institutions and KOLs
        authors_table = generate_top_authors_table(filtered_df, n=10)
        if not authors_table.empty:
            tables_data["key_stakeholders"] = authors_table
            table_context_parts.append(f"**KEY OPINION LEADERS:**\n{authors_table.to_markdown(index=False)}\n")

        # High-impact studies (assume late-breaking or oral presentations)
        high_impact = filtered_df[
            filtered_df['Session'].str.contains('Late-Breaking|Oral|Presidential', case=False, na=False)
        ].head(20)[['Identifier', 'Title', 'Speakers', 'Session']]

        if not high_impact.empty:
            tables_data["high_impact_studies"] = high_impact
            table_context_parts.append(f"**HIGH-IMPACT PRESENTATIONS:**\n{high_impact.to_markdown(index=False)}\n")

    # Store final table context
    tables_data["table_context"] = "\n".join(table_context_parts)

    return tables_data


def chief_editor_review(journalist_report: str, ta: str, filtered_df, button_type: str) -> Dict:
    """
    Chief Editor QC layer: Review journalist output for quality issues.

    Returns dict with:
        - status: "APPROVED" | "NEEDS_REVISION" | "SKIPPED"
        - issues: List of identified issues (if any)
        - revised_report: Revised text (only if NEEDS_REVISION and auto-fixed)
    """
    if not ENABLE_CHIEF_EDITOR:
        print(f"[CHIEF EDITOR] Quality control DISABLED (ENABLE_CHIEF_EDITOR=False)")
        return {"status": "SKIPPED", "issues": []}

    if button_type != "insights":
        # Only run Chief Editor on insights button for now
        return {"status": "SKIPPED", "issues": []}

    print(f"\n[CHIEF EDITOR] Reviewing journalist output for quality...")
    print(f"[CHIEF EDITOR] Report length: {len(journalist_report)} characters")
    print(f"[CHIEF EDITOR] Dataset size: {len(filtered_df)} studies")

    prompt = f"""You are the Chief Editor reviewing a draft Medical Affairs research insights report.

**YOUR TASK**: Review the draft report for quality issues and provide structured feedback.

**REVIEW CHECKLIST**:

1. **Proportionality Issues**:
   - Does the report match the data volume?
   - Example: If only 5 studies exist, does the report say "Top 10 institutions"?
   - Example: If only 3 institutions present, does it force a "Top 10" ranking?
   - Are empty sections acknowledged honestly or filled with generic fluff?

2. **Generic Statements**:
   - Are claims backed by specific study examples (e.g., "Study 1234P demonstrated...")?
   - Or is it vague (e.g., "Many studies explored...")?
   - Are numbers/statistics provided where possible?

3. **Missing Caveats**:
   - Does the report acknowledge data limitations?
   - Does it warn against cross-trial efficacy comparisons?
   - Are confidence levels appropriate for preliminary data?

4. **Structural Issues**:
   - Are there empty sections that should be removed?
   - Are sections combined unnecessarily?
   - Is the structure adapted to the data, or is it rigidly following a template?

5. **Clinical Relevance**:
   - Does the report focus on evidence gaps and unmet needs (core Medical Affairs value)?
   - Or is it drifting into strategy/recommendations (which were excluded)?

---

**CONTEXT**:
- Therapeutic Area: {ta}
- Total Studies: {len(filtered_df)}
- Button Type: {button_type}

**DRAFT REPORT**:

{journalist_report}

---

**OUTPUT FORMAT** (JSON only):

```json
{{
  "status": "APPROVED" or "NEEDS_REVISION",
  "issues": [
    {{"type": "proportionality", "description": "Says 'Top 10' but only 3 institutions exist", "severity": "high"}},
    {{"type": "generic", "description": "Section 2.1 lacks specific study examples", "severity": "medium"}},
    ...
  ],
  "overall_assessment": "Brief 1-2 sentence summary of quality"
}}
```

**SEVERITY LEVELS**:
- "high": Major issue that misrepresents data (e.g., proportionality errors)
- "medium": Detracts from quality but doesn't misrepresent (e.g., missing examples)
- "low": Minor stylistic issue

If the report is high quality with no major issues, return:
```json
{{
  "status": "APPROVED",
  "issues": [],
  "overall_assessment": "Report is well-proportioned, backed by specific examples, and acknowledges data limitations appropriately."
}}
```
"""

    try:
        start_time = time.time()

        # Use gpt-5-mini with medium reasoning (as specified by user)
        response = client.responses.create(
            model="gpt-5-mini",
            input=[{"role": "user", "content": prompt}],
            reasoning={"effort": "medium"},
            text={"verbosity": "medium"},
            max_output_tokens=4000
        )

        # Extract response text
        review_text = response.output_text or ""

        if not review_text and response.output:
            for item in response.output:
                if hasattr(item, 'type') and item.type == 'message' and hasattr(item, 'content'):
                    for content_item in item.content:
                        if hasattr(content_item, 'text'):
                            review_text = content_item.text
                            break

        review_time = time.time() - start_time
        print(f"[CHIEF EDITOR] Review completed in {review_time:.1f}s")

        # Parse JSON from response
        try:
            # Extract JSON from markdown code blocks if present
            if "```json" in review_text:
                json_start = review_text.find("```json") + 7
                json_end = review_text.find("```", json_start)
                review_text = review_text[json_start:json_end].strip()
            elif "```" in review_text:
                json_start = review_text.find("```") + 3
                json_end = review_text.find("```", json_start)
                review_text = review_text[json_start:json_end].strip()

            review_data = json.loads(review_text)

            # Log results
            status = review_data.get("status", "UNKNOWN")
            issues = review_data.get("issues", [])

            print(f"[CHIEF EDITOR] Status: {status}")
            print(f"[CHIEF EDITOR] Issues found: {len(issues)}")

            if issues:
                print(f"[CHIEF EDITOR] Issue breakdown:")
                for issue in issues:
                    severity = issue.get("severity", "unknown")
                    issue_type = issue.get("type", "unknown")
                    description = issue.get("description", "")
                    print(f"[CHIEF EDITOR]   - [{severity.upper()}] {issue_type}: {description}")

            return review_data

        except json.JSONDecodeError as e:
            print(f"[CHIEF EDITOR] WARNING: Could not parse JSON response: {e}")
            print(f"[CHIEF EDITOR] Raw response: {review_text[:500]}...")
            return {
                "status": "APPROVED",
                "issues": [],
                "overall_assessment": "Review completed but JSON parsing failed - approving by default"
            }

    except Exception as e:
        print(f"[CHIEF EDITOR] ERROR during review: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "APPROVED",
            "issues": [],
            "overall_assessment": "Review failed - approving by default"
        }


def generate_deep_intelligence(button_type: str, ta: str, refresh_librarian: bool = False):
    """
    Generate a single deep intelligence report using gpt-5 with high reasoning and verbosity.
    Updates consolidated caches (librarian_{button}.json and journalist_{button}.json).

    Args:
        button_type: One of ['competitor', 'kol', 'institution', 'insights', 'strategic']
        ta: Therapeutic area name
        refresh_librarian: If True, force re-run Librarian extraction (ignore cache)

    Returns:
        None (updates consolidated cache files)
    """
    print(f"\n{'='*80}")
    print(f"[DEEP] Generating {button_type.upper()} Intelligence for {ta}")
    print(f"{'='*80}\n")

    # Step 1: Filter dataset
    filtered_df = get_filtered_dataframe_multi([], [ta], [], [])
    print(f"[DEEP] Filtered dataset: {len(filtered_df)} studies")

    if filtered_df.empty:
        print(f"[DEEP] ERROR: No studies found for {ta}")
        return None

    # Step 2: Prepare table data
    tables_data = prepare_table_data(button_type, ta, filtered_df, refresh_librarian)

    # Step 2.5: Save librarian data to cache
    print(f"[LIBRARIAN] Saving enriched data to cache...")
    update_librarian_for_ta(
        button=button_type,
        ta=ta,
        ta_records=tables_data,
        force=refresh_librarian
    )

    # Step 3: Build appropriate prompt
    prompt_builders = {
        "competitor": build_competitor_intelligence_prompt,
        "kol": build_kol_intelligence_prompt,
        "institution": build_institution_intelligence_prompt,
        "insights": build_research_insights_prompt,
        "strategic": build_strategic_priorities_prompt
    }

    prompt_builder = prompt_builders.get(button_type)
    if not prompt_builder:
        print(f"[DEEP] ERROR: Unknown button type {button_type}")
        return None

    prompt = prompt_builder(ta, filtered_df, tables_data)

    print(f"[DEEP] Prompt length: {len(prompt)} characters")

    # Step 3.5: Two-step AI approach for competitor intelligence (ai_assistant.py pattern)
    if button_type == "competitor" and "regimen_summary" in tables_data:
        print(f"\n[TWO-STEP] Implementing ai_assistant.py pattern for competitor intelligence...")

        # STEP 1: Get important keywords from AI based on regimen summary
        print(f"[STEP 1] Asking AI to identify important regimens/keywords...")
        try:
            # Use standard Chat Completions API (not Responses API) for keyword extraction
            keyword_response = client.chat.completions.create(
                model="gpt-4o-mini",  # Fast model for keyword extraction
                messages=[
                    {"role": "system", "content": "Extract important drug/regimen keywords for competitive intelligence analysis. Return ONLY a JSON array of search terms, no other text."},
                    {"role": "user", "content": tables_data["regimen_summary"]}
                ],
                temperature=0.3,
                max_tokens=500
            )

            keyword_text = keyword_response.choices[0].message.content
            print(f"[STEP 1] AI response length: {len(keyword_text)} chars")
            print(f"[STEP 1] AI raw response: {keyword_text[:200]}...")

            # Clean up response - remove markdown code blocks if present
            cleaned_text = keyword_text.strip()
            if cleaned_text.startswith("```"):
                # Remove markdown code block markers
                lines = cleaned_text.split('\n')
                if lines[0].startswith("```"):
                    lines = lines[1:]  # Remove first line (```json or ```)
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]  # Remove last line (```)
                cleaned_text = '\n'.join(lines).strip()

            # Parse keywords
            keywords = json.loads(cleaned_text)

            # FILTER OUT EMD SERONO DRUGS (not competitors - these are OUR drugs!)
            # Check if any EMD drug name appears ANYWHERE in the keyword string
            emd_drugs = ["avelumab", "bavencio", "tepotinib", "tepmetko", "cetuximab", "erbitux", "pimicotinib"]
            keywords_filtered = []
            removed = []

            for kw in keywords:
                # Check if ANY EMD drug appears in this keyword
                contains_emd_drug = any(emd_drug in kw.lower() for emd_drug in emd_drugs)
                if contains_emd_drug:
                    removed.append(kw)
                else:
                    keywords_filtered.append(kw)

            if removed:
                print(f"[STEP 1] Removed EMD Serono drug keywords: {removed}")

            keywords = keywords_filtered
            print(f"[STEP 1] AI identified {len(keywords)} competitor keywords")
            # Print keywords safely (avoid Unicode encoding errors on Windows)
            for kw in keywords:
                try:
                    print(f"  - {kw}")
                except UnicodeEncodeError:
                    print(f"  - {kw.encode('ascii', 'replace').decode('ascii')}")

            # STEP 2: Filter LIBRARIAN DATA using keywords (not raw CSV!)
            print(f"[STEP 2] Filtering Librarian-extracted studies with AI keywords...")
            librarian_records = tables_data["competitor_intelligence"]["tagged_records"]

            # Filter librarian records by regimen field (more accurate than CSV Title)
            pattern = '|'.join([re.escape(k) for k in keywords])
            matching_row_ids = []
            for record in librarian_records:
                regimen = record.get('regimen', '')
                title = record.get('title', '')
                # Check both regimen and title fields for keywords
                if re.search(pattern, regimen, re.IGNORECASE) or re.search(pattern, title, re.IGNORECASE):
                    matching_row_ids.append(record['row_id'])

            print(f"[STEP 2] Matched {len(matching_row_ids)}/{len(librarian_records)} Librarian studies")

            # Join back to filtered_df to get full row data (Speakers, Affiliation, etc.)
            important_studies = filtered_df[filtered_df['Identifier'].isin(matching_row_ids)]
            print(f"[STEP 2] Joined to CSV: {len(important_studies)} studies with full data")

            # STEP 3: Send FULL DataFrame to AI (all columns!)
            print(f"[STEP 3] Preparing full study data with all columns...")
            study_table_markdown = important_studies[[
                'Identifier', 'Title', 'Speakers', 'Affiliation', 'Date', 'Session'
            ]].to_markdown(index=False)

            print(f"[STEP 3] Generated markdown table: {len(study_table_markdown)} chars")

            # Add to prompt - DO NOT include the JSON keyword list (issue #2)
            prompt = prompt + f"""

**DETAILED STUDY DATA FOR YOUR ANALYSIS:**

Here are ALL {len(important_studies)} studies matching the top competitive regimens with FULL details:

{study_table_markdown}

**IMPORTANT INSTRUCTIONS:**
- Use this data to generate your competitive intelligence tables in Section 2
- Include Abstract ID (Identifier column) in all tables
- Include Lead investigators (Speakers column) where relevant
- Include Institutions (Affiliation column) for geographic analysis
- Include Presentation date/session (Date, Session columns) for prioritization
- DO NOT hallucinate study counts - count directly from the table above
- When creating tables in Section 2, extract data directly from the markdown table above
- DO NOT include the keyword list in your output - start directly with your Executive Summary

**TABLE FORMATTING RULES (CRITICAL - AVOID TRUNCATION):**
- Keep table cells CONCISE - max 50 characters per cell to avoid "..." truncation
- Drug names: Use abbreviations (e.g., "EV+P" not "Enfortumab vedotin + pembrolizumab")
- Threat descriptions: Max 8-10 words, use fragments not sentences
- Mechanisms: Use shorthand (e.g., "Nectin-4 ADC" not "Next-generation Nectin-4 antibody-drug conjugate")
- If content won't fit concisely, use table for key facts + bullet points below for details
"""

            print(f"[TWO-STEP] Enhanced prompt with full study data. New length: {len(prompt)} chars")

        except Exception as e:
            print(f"[TWO-STEP ERROR] Failed to apply two-step pattern: {e}")
            import traceback
            traceback.print_exc()
            print(f"[TWO-STEP] Falling back to original prompt without enhancement")

    # Step 4: Call OpenAI model
    # Change model here as needed: "gpt-5-mini", "gpt-4o", "gpt-4o-mini", etc.
    model = "gpt-5-mini"
    print(f"[DEEP] Using model: {model}")

    try:
        start_time = time.time()

        # Build messages
        messages = [
            {"role": "system", "content": "You are a senior Medical Affairs strategic intelligence analyst with deep expertise in oncology and pharmaceutical competitive intelligence. Generate comprehensive, actionable reports for medical affairs professionals.\n\nRespond in GitHub-Flavored Markdown only (no HTML). Begin with one # H1 title, then use ##/### headings, short paragraphs, bullet/numbered lists, and tables when useful. Do not put the whole reply in a code block; use fenced code blocks only for actual code or JSON. Preserve line breaks."},
            {"role": "user", "content": prompt}
        ]

        print(f"[DEEP] Starting analysis with high reasoning and high verbosity...")

        response = client.responses.create(
            model=model,
            input=messages,
            reasoning={"effort": "high"},  # MEDIUM: Balance reasoning with output length
            text={"verbosity": "high"},      # HIGH: Comprehensive reports
            max_output_tokens=64000      # Doubled to prevent publication title truncation
        )

        # Debug response structure
        print(f"[DEBUG] response.output_text exists: {hasattr(response, 'output_text')}")
        print(f"[DEBUG] response.output exists: {hasattr(response, 'output')}")

        analysis_text = response.output_text or ""
        print(f"[DEBUG] output_text length: {len(analysis_text)}")

        if response.output:
            print(f"[DEBUG] output array has {len(response.output)} items")
            for idx, item in enumerate(response.output):
                print(f"[DEBUG] Item {idx}: type={getattr(item, 'type', 'UNKNOWN')}")

        # If output_text is empty, extract from output array
        if not analysis_text and response.output:
            print(f"[DEBUG] Extracting from output array...")
            for item in response.output:
                if hasattr(item, 'type') and item.type == 'message' and hasattr(item, 'content'):
                    for content_item in item.content:
                        if hasattr(content_item, 'text'):
                            analysis_text = content_item.text
                            print(f"[DEBUG] Found text in output array: {len(analysis_text)} chars")
                            break

        generation_time = time.time() - start_time

        print(f"[DEEP] Generated {len(analysis_text or '')} characters in {generation_time:.1f}s")

    except Exception as e:
        print(f"[DEEP] ERROR calling OpenAI: {e}")
        import traceback
        traceback.print_exc()
        return None

    # Step 4.5: Chief Editor Quality Control (if enabled)
    chief_editor_feedback = chief_editor_review(
        journalist_report=analysis_text,
        ta=ta,
        filtered_df=filtered_df,
        button_type=button_type
    )

    # Store Chief Editor feedback in metadata (for debugging/transparency)
    qc_metadata = {
        "chief_editor_enabled": ENABLE_CHIEF_EDITOR,
        "qc_status": chief_editor_feedback.get("status", "UNKNOWN"),
        "qc_issues_count": len(chief_editor_feedback.get("issues", [])),
        "qc_assessment": chief_editor_feedback.get("overall_assessment", "")
    }

    # Log high-severity issues to console
    if chief_editor_feedback.get("status") == "NEEDS_REVISION":
        high_severity_issues = [
            issue for issue in chief_editor_feedback.get("issues", [])
            if issue.get("severity") == "high"
        ]
        if high_severity_issues:
            print(f"\n[CHIEF EDITOR] ⚠️  QUALITY WARNING: {len(high_severity_issues)} high-severity issue(s) detected:")
            for issue in high_severity_issues:
                print(f"[CHIEF EDITOR]   - {issue.get('type', 'unknown')}: {issue.get('description', '')}")
            print(f"[CHIEF EDITOR] Report will be saved as-is. Manual review recommended.")

    # Step 5: Structure cache data
    cache_data = {
        "metadata": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "model": model,
            "button_type": button_type,
            "therapeutic_area": ta,
            "dataset_size": len(filtered_df),
            "generation_time_seconds": generation_time,
            "report_length": len(analysis_text),
            **qc_metadata  # Include Chief Editor feedback
        },
        "tables": {
            # Store key tables for display
            key: {
                "columns": list(df.columns) if hasattr(df, 'columns') else [],
                "rows": df.to_dict('records') if hasattr(df, 'to_dict') else []
            }
            for key, df in tables_data.items()
            if key != "table_context" and hasattr(df, 'to_dict')
        },
        "analysis": analysis_text
    }

    # Step 6: Save to consolidated cache
    update_journalist_for_ta(
        button=button_type,
        ta=ta,
        metadata=cache_data["metadata"],
        analysis=analysis_text
    )

    print(f"\n[DEEP] Successfully generated deep intelligence:")
    print(f"[DEEP]   Button: {button_type}")
    print(f"[DEEP]   TA: {ta}")
    print(f"[DEEP]   Updated: cache/journalist_{button_type}.json")
    print(f"[DEEP]   Report length: {len(analysis_text)} characters")
    print(f"[DEEP]   Generation time: {generation_time:.1f}s")


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description='Generate deep intelligence reports using gpt-5-mini with high reasoning')
    parser.add_argument('--button', type=str, choices=BUTTON_TYPES,
                       help='Button type to generate')
    parser.add_argument('--ta', type=str,
                       help='Therapeutic area name')
    parser.add_argument('--all', action='store_true',
                       help='Generate all 30 combinations')
    parser.add_argument('--refresh-librarian', action='store_true',
                       help='Force re-run Librarian extraction (ignore cache). Use when abstracts are released.')

    args = parser.parse_args()

    print(f"\n{'='*80}")
    print(f"ESMO 2025 Deep Intelligence Generator")
    print(f"{'='*80}\n")
    print(f"Dataset loaded: {len(df_global)} studies")

    if args.button and args.ta:
        # Single TA generation mode
        print(f"\nMode: Single TA Report Generation")
        print(f"Button: {args.button}")
        print(f"TA: {args.ta}\n")

        generate_deep_intelligence(args.button, args.ta, args.refresh_librarian)

        print(f"\n[SUCCESS] Deep intelligence generation complete!")
        print(f"  Updated: cache/librarian_{args.button}.json ({args.ta} section)")
        print(f"  Updated: cache/journalist_{args.button}.json ({args.ta} report)")

    elif args.button and not args.ta:
        # All TAs for one button mode
        print(f"\nMode: All TAs for {args.button.upper()}")
        print(f"Will generate/regenerate all {len(THERAPEUTIC_AREAS)} TAs\n")

        for i, ta in enumerate(THERAPEUTIC_AREAS, 1):
            print(f"\n[{i}/{len(THERAPEUTIC_AREAS)}] Generating {args.button} for {ta}...")
            generate_deep_intelligence(args.button, ta, args.refresh_librarian)

            # Add delay between reports to avoid rate limits
            if i < len(THERAPEUTIC_AREAS):
                time.sleep(2)

        print(f"\n[SUCCESS] All TAs generated for {args.button}!")
        print(f"  Updated: cache/librarian_{args.button}.json (all {len(THERAPEUTIC_AREAS)} TAs)")
        print(f"  Updated: cache/journalist_{args.button}.json (all {len(THERAPEUTIC_AREAS)} reports)")

    elif args.all:
        # Full batch mode - all buttons × all TAs
        print(f"\nMode: Full Batch Generation")
        print(f"Combinations: {len(BUTTON_TYPES)} buttons × {len(THERAPEUTIC_AREAS)} TAs = {len(BUTTON_TYPES) * len(THERAPEUTIC_AREAS)} reports\n")

        # Estimate cost
        estimated_cost_per_report = 0.05  # gpt-5 high reasoning
        estimated_total_cost = len(BUTTON_TYPES) * len(THERAPEUTIC_AREAS) * estimated_cost_per_report
        print(f"[WARNING] ESTIMATED COST: ${estimated_total_cost:.2f} ({len(BUTTON_TYPES) * len(THERAPEUTIC_AREAS)} reports @ ~${estimated_cost_per_report:.2f} each)")
        confirm = input("Proceed? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Batch generation cancelled.")
            sys.exit(0)

        for i, (button, ta) in enumerate(
            [(b, t) for b in BUTTON_TYPES for t in THERAPEUTIC_AREAS], 1
        ):
            print(f"\n[{i}/{len(BUTTON_TYPES) * len(THERAPEUTIC_AREAS)}] Generating {button} for {ta}...")
            generate_deep_intelligence(button, ta, args.refresh_librarian)

            # Add delay between API calls to avoid rate limits
            if i < len(BUTTON_TYPES) * len(THERAPEUTIC_AREAS):
                time.sleep(2)

        # Summary
        print(f"\n{'='*80}")
        print(f"BATCH COMPLETE")
        print(f"{'='*80}\n")
        print(f"[SUCCESS] Generated {len(BUTTON_TYPES) * len(THERAPEUTIC_AREAS)} reports")
        print(f"[SUCCESS] Updated {len(BUTTON_TYPES)} consolidated cache pairs")

    else:
        parser.print_help()
        print("\nExamples:")
        print("  python generate_deep_intelligence.py --button competitor --ta \"Bladder Cancer\"")
        print("  python generate_deep_intelligence.py --button competitor --ta \"Bladder Cancer\" --refresh-librarian")
        print("  python generate_deep_intelligence.py --all")
        sys.exit(1)


if __name__ == "__main__":
    # Add pandas import here since we use it in table preparation
    import pandas as pd
    main()