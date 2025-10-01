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
        timeout=60.0,
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
    "All Therapeutic Areas": {"keywords": []},
    "Bladder Cancer": {
        "keywords": ["bladder", "urothelial", "uroepithelial", "transitional cell", "GU", "genitourinary"],
        "exclusions": ["prostate"]
    },
    "Renal Cancer": {
        "keywords": ["renal", "renal cell", "RCC"]
    },
    "Lung Cancer": {
        "keywords": ["lung", "non-small cell lung cancer", "non-small-cell lung cancer", "NSCLC", "MET", "ALK", "EGFR", "KRAS"]
    },
    "Colorectal Cancer": {
        "keywords": ["colorectal", "CRC", "colon", "rectal", "bowel"],
        "exclusions": ["gastric", "esophageal", "pancreatic", "hepatocellular", "HCC"]
    },
    "Head and Neck Cancer": {
        "keywords": ["head and neck", "head & neck", "H&N", "HNSCC", "SCCHN",
                     "squamous cell carcinoma of the head", "oral", "pharyngeal", "laryngeal"]
    },
    "TGCT": {
        "keywords": ["TGCT", "PVNS", "tenosynovial giant cell tumor", "pigmented villonodular synovitis"]
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
        "ai_prompt": """You are EMD Serono's senior competitive intelligence analyst for medical affairs. Conduct a comprehensive competitive landscape analysis of ESMO 2025 to identify strategic threats, opportunities, and positioning insights for the EMD oncology portfolio (avelumab, tepotinib, cetuximab, pimicotinib).

**EXECUTIVE SUMMARY** (2-3 paragraphs):
Provide a strategic overview of the competitive landscape:
- Overall competitive intensity: How many abstracts feature competitor drugs? Which therapeutic areas show highest competitive activity?
- Dominant competitive threats: Which competitor assets have the strongest presence at this conference?
- EMD portfolio visibility: How does avelumab/tepotinib/cetuximab presence compare to competitors in their respective indications?
- Strategic implications: What are the 2-3 most significant competitive developments that require immediate medical affairs attention?

**EMD PORTFOLIO COMPETITIVE POSITIONING**:

*Avelumab (Bavencio) - METASTATIC Bladder Cancer & Maintenance Therapy*:
- Conference presence: Search all abstracts for "avelumab" or "Bavencio". If found, provide Abstract #, presenter, institution, and study focus.
- If absent: Analyze the competitive void - what are competitors presenting in METASTATIC bladder/urothelial cancer maintenance space?
- Competitive context: How many abstracts feature enfortumab vedotin, pembrolizumab, nivolumab, or other IO agents in metastatic bladder cancer?

*Tepotinib - NSCLC MET Alterations*:
- Conference presence: Search for "tepotinib" mentions. If found, cite Abstract # and context.
- MET landscape: How many abstracts discuss MET alterations, MET inhibitors, or MET-targeted therapy in NSCLC?
- Competitive MET inhibitors: Any capmatinib, crizotinib, or other MET-targeting agents? Cite Abstract #.
- NSCLC targeted therapy context: Broader landscape of targeted therapy in lung cancer (EGFR, ALK, ROS1, KRAS, etc.)

*Cetuximab - Colorectal & Head & Neck Cancer*:
- Conference presence: Search for "cetuximab" or "Erbitux". Document findings with Abstract #.
- Anti-EGFR landscape: How many abstracts feature EGFR-targeted therapy in CRC or H&N cancer?
- Competitive anti-EGFR agents: Panitumumab presence? Other EGFR inhibitors?
- Therapeutic area context: Overall activity in colorectal and head & neck oncology

*Pimicotinib - TGCT/CSF1R*:
- Search for pimicotinib, TGCT, tenosynovial giant cell tumor, or CSF1R mentions
- Document any findings with Abstract # (likely low volume given rare indication)

**MAJOR COMPETITOR DEEP-DIVE ANALYSIS**:

For each major competitor drug or regimen, provide a dedicated paragraph analyzing its conference presence and strategic threat. Structure each paragraph as:
1. Quantify presence (e.g., "Enfortumab vedotin appears in X abstracts across Y settings")
2. Clinical settings and indications (metastatic, perioperative, adjuvant, maintenance, etc.)
3. Notable study types (pivotal phase 3, real-world evidence, combination trials, biomarker studies)
4. Strategic implications for EMD portfolio
5. Always cite Abstract # for key studies

*Critical Competitors to Analyze* (dedicate one paragraph each):

**Enfortumab Vedotin (EV) & EV+Pembrolizumab (EV+P)**:
This is the #1 competitive threat in bladder cancer. Provide comprehensive analysis:
- Total abstract count featuring EV or EV+P
- Breakdown by setting: 1L metastatic, 2L+ metastatic, perioperative, maintenance
- Monotherapy vs. combination (especially EV+P as new standard of care in mUC)
- Real-world evidence presentations (utilization, outcomes, safety)
- Expansion beyond bladder (if any)
- Cite all relevant Abstract #s

**Pembrolizumab (Keytruda)**:
- Total abstract volume (one of the most studied checkpoint inhibitors)
- Indications covered (bladder, lung, CRC, H&N, other)
- Treatment settings (1L, maintenance, adjuvant, neoadjuvant, perioperative)
- Combination strategies (pembro + chemo, pembro + ADC, pembro + targeted)
- Notable phase 3 trials or practice-changing data
- Cite key Abstract #s

**Nivolumab (Opdivo)**:
- Conference presence (abstract count)
- Primary indications and settings
- Combination approaches (nivo + ipi, nivo + chemo, others)
- Long-term follow-up or survival data
- Cite Abstract #s

**Durvalumab (Imfinzi)**:
- Abstract volume
- Primary focus areas (NMIBC? MIBC? Metastatic? Perioperative?)
- Combination strategies
- Notable studies
- Cite Abstract #s

**Atezolizumab (Tecentriq)**:
- Conference activity level
- Indications and settings
- Key studies and strategic positioning
- Cite Abstract #s

**Sacituzumab Govitecan (SG)**:
- Presence at conference (abstract count)
- Indications (breast, bladder, other)
- Monotherapy vs. combination
- Strategic threat level
- Cite Abstract #s

**Other ADCs** (Disitamab vedotin, Trastuzumab deruxtecan, Datopotamab deruxtecan, others):
- Identify which ADCs appear in abstracts
- For each: indication, setting, abstract count
- Emerging ADC class trends
- Cite Abstract #s

**FGFR Inhibitors** (Erdafitinib, pemigatinib, futibatinib, others):
- Which FGFR inhibitors appear?
- Volume, indications, biomarker selection
- Strategic positioning vs. avelumab in bladder cancer
- Cite Abstract #s

**Other Targeted Therapies** (KRAS inhibitors, HER2-targeted, ALK/ROS1, etc.):
- Identify which agents appear
- Volume and strategic relevance to EMD portfolio
- Cite Abstract #s

**Emerging/Novel Agents**:
- Any new mechanisms or investigational agents with notable presence
- Strategic watch items
- Cite Abstract #s

**COMPETITIVE STRATEGY PATTERNS**:

*Indication Expansion Strategies*:
- Which competitors are aggressively expanding into new tumor types?
- Basket trial evidence or pan-tumor biomarker strategies?
- Movement into earlier disease stages (adjuvant/neoadjuvant from metastatic)?

*Combination Regimen Development*:
- Most common combination backbones being tested?
- Novel doublet or triplet regimens showing momentum?
- Which combinations pose threats to EMD monotherapy or current combinations?

*Biomarker-Driven Positioning*:
- Competitors using biomarkers to carve out specific patient populations?
- Companion diagnostic strategies evident from abstracts?
- Precision medicine approaches that could fragment EMD's addressable populations?

**INSTITUTIONAL & KOL COMPETITIVE INTELLIGENCE**:

*Leading Institutions Driving Competitor Research*:
- Top 5-10 cancer centers with high competitor drug abstract volume
- Institutional specialization (e.g., "MD Anderson: heavy EV+P and pembrolizumab activity in GU")
- Geographic hubs of competitive activity

*Key Opinion Leaders in Competitive Space*:
- Identify 5-8 high-profile KOLs presenting multiple competitor abstracts
- For each: Name, institution, which competitor drugs they're studying, therapeutic focus
- Strategic consideration: Are these KOLs accessible for EMD engagement despite competitor ties?

**COMPETITIVE THREATS & STRATEGIC OPPORTUNITIES**:

*Immediate Competitive Threats*:
- New data that could shift treatment paradigms in EMD-relevant indications
- Aggressive competitor expansion into EMD core markets
- Emerging mechanisms or modalities that could displace current standards

*White Space Opportunities*:
- Therapeutic areas with high unmet need but low competitor activity
- Biomarker populations underserved by current competitive landscape
- Treatment settings where competitors are not yet advancing (e.g., maintenance therapy gaps)


**WRITING REQUIREMENTS**:
- Natural narrative prose - flowing paragraphs, not bullet lists in the analysis (use bullets only for section structure)
- Always cite Abstract # when referencing competitor studies
- Integrate quantitative data (e.g., "Pembrolizumab appeared in 87 abstracts (43% of all IO studies)...")
- Use only information from provided abstracts - if data unavailable, state "not found in current dataset"
- Objective competitive intelligence tone - fact-based, not defensive or dismissive of competitors
- Focus on actionable intelligence for medical affairs leadership
- Professional medical vocabulary appropriate for Vice President/Medical Director audience

**OUTPUT STRUCTURE**:
Clear section headers with analytical paragraphs. This should read as a comprehensive competitive intelligence briefing for medical affairs executive leadership preparing for strategic planning.""",
        "required_tables": ["all_data"]
    },
    "kol": {
        "button_label": "KOL Analysis",
        "ai_prompt": """You are EMD Serono's medical affairs KOL intelligence analyst. Analyze the most active and influential researchers presenting at ESMO 2025 based on presentation volume and research focus.

**EXECUTIVE SUMMARY** (2-3 paragraphs):
Provide a strategic overview of the KOL landscape:
- How many unique researchers are in the top tier? What is the distribution of productivity (e.g., 3 researchers with 10+ abstracts vs. many with 2-3)?
- What therapeutic areas dominate among top KOLs? Which tumor types have the most active thought leadership?
- Geographic distribution: Which countries/regions have the most prolific researchers at this conference?
- EMD portfolio relevance: How many top KOLs work in GU cancers (bladder/urothelial), lung cancer (NSCLC), GI cancers (CRC), or head & neck?

**INDIVIDUAL KOL PROFILES** (Deep-dive on each top researcher):
For each of the top 10-15 most active researchers by abstract count, provide a comprehensive profile:

*Identity & Affiliation*:
- Full name, primary institutional affiliation, and geographic location (city/country)
- Total number of presentations at this conference

*Research Specialization*:
- Primary tumor type focus: Which cancer(s) dominate their abstracts? (e.g., "predominantly urothelial cancer with some broader GU oncology work")
- Treatment modality expertise: Are they focused on immunotherapy? Targeted therapy? Chemotherapy? ADCs? Combination regimens?
- Clinical setting: Do they primarily work in metastatic disease? Adjuvant/neoadjuvant? Maintenance therapy? Biomarker-selected populations?
- Phase of development: Early-phase trials? Pivotal studies? Real-world evidence? Translational/correlative research?

*Scientific Themes in Their Work*:
Based on their abstract titles, identify:
- Key biomarkers mentioned in their research (PD-L1, FGFR, HER2, MET, TMB, ctDNA, MSI, etc.)
- Mechanisms of action: Checkpoint inhibitors (PD-1/PD-L1)? Tyrosine kinase inhibitors? ADCs? Novel targets?
- Treatment approaches: Monotherapy vs. combinations? Specific regimen types (IO+chemo, IO+IO, doublets/triplets)?
- Any recurring themes across their abstracts (e.g., focus on resistance mechanisms, sequencing strategies, predictive biomarkers)

*Portfolio Relevance*:
- Does this KOL present any work on avelumab (bladder/urothelial, maintenance)? Cite Abstract #
- Any tepotinib-relevant research (NSCLC, MET alterations)? Cite Abstract #
- Cetuximab-related work (colorectal, head & neck, EGFR)? Cite Abstract #
- Pimicotinib or TGCT research? Cite Abstract #
- If no direct EMD drug work: Note adjacent competitive space or therapeutic area overlap

*Cross-Indication Reach*:
- Does this researcher work across multiple tumor types? (Important for platform drug strategy)
- Breadth of expertise: Single disease-focused vs. multi-indication researcher

**COLLECTIVE RESEARCH PATTERNS**:
Across the top 10-15 KOLs, what patterns emerge?

*Therapeutic Area Concentration*:
- Which cancer types have the deepest KOL bench? (e.g., "8 of 15 top KOLs focus primarily on lung cancer")
- Are certain therapeutic areas underrepresented among top KOLs despite high abstract volume?

*Treatment Modality Trends*:
- What percentage of top KOLs work extensively with immunotherapy? Targeted therapy? ADCs?
- Which specific drug classes or mechanisms appear most frequently in top KOL abstracts?

*Geographic & Institutional Patterns*:
- Where are top KOLs geographically concentrated? (US, specific European countries, Asia-Pacific)
- Do multiple top KOLs come from the same institution (potential institutional hub)?

**NOTABLE RESEARCH EXAMPLES** (6-10 highlights):
Select the most important or representative presentations from top KOLs:
- For each: Abstract #, KOL name, institution, brief description of research focus based on title
- Prioritize: (1) EMD portfolio relevance, (2) high-impact KOLs in strategic TAs, (3) novel research directions
- Always cite Abstract # (Identifier) when referencing specific studies

**KOL INTELLIGENCE SUMMARY**:
Synthesize key observations for medical affairs planning:
- Which therapeutic areas have the strongest thought leadership at this conference?
- Are there "platform KOLs" who work across multiple indications relevant to EMD's portfolio?
- Geographic or institutional clusters of top KOL activity in EMD-relevant therapeutic areas
- Any top KOLs who are currently presenting competitor data but work in EMD therapeutic areas (engagement opportunity)

**WRITING REQUIREMENTS**:
- Write in natural narrative prose - use flowing paragraphs, not bullet lists in the analysis itself (bullets only for section structure)
- Always cite Abstract # when referencing specific studies (e.g., "Dr. Jones presents work on FGFR3-altered urothelial cancer (Abstract #2847)...")
- Integrate quantitative data naturally (e.g., "Five of the top 15 KOLs (33%) focus primarily on genitourinary cancers...")
- Use only information from the provided Top Authors table and their associated abstracts - if data is unavailable, state "not available in current dataset"
- Maintain professional medical affairs analytical tone
- Focus on describing KOL expertise and research focus - avoid tactical engagement recommendations
- Professional medical vocabulary appropriate for Medical Director audience

**OUTPUT STRUCTURE**:
Clear section headers with each section written as analytical paragraphs. This should read as a KOL intelligence briefing for medical affairs leadership.""",
        "required_tables": ["top_authors"]
    },
    "institution": {
        "button_label": "Institution Analysis",
        "ai_prompt": """You are EMD Serono's medical affairs institutional intelligence analyst. Conduct comprehensive analysis of leading research institutions at ESMO 2025 to identify strategic academic partnerships, regional research hubs, and institutional capabilities relevant to EMD's oncology portfolio.

**EXECUTIVE SUMMARY** (2-3 paragraphs):
Provide strategic overview of the institutional landscape:
- How many unique institutions are represented among top presenters? What is the concentration (e.g., top 5 institutions account for X% of abstracts)?
- Which countries/regions dominate institutional research leadership at this conference?
- What is the distribution between comprehensive cancer centers, academic medical centers, and community/regional hospitals?
- Which institutions show strongest alignment with EMD therapeutic areas (GU cancers, lung, GI, H&N)?

**TOP INSTITUTION PROFILES** (Deep-dive on each leading center):
For each of the top 10-15 institutions by abstract volume, provide comprehensive analysis:

*Identity & Classification*:
- Full institutional name and geographic location (city, country)
- Total number of presentations at this conference
- Institution type: NCI-designated comprehensive cancer center? Academic medical center? Regional center?

*Research Focus & Therapeutic Expertise*:
- Primary tumor types: Which cancers dominate this institution's presentations?
- Treatment modality expertise: Strengths in immunotherapy? Targeted therapy? ADCs?
- Clinical trial leadership: High volume of phase 3 trials? Early-phase research?

*EMD Portfolio Relevance*:
- Does this institution present any avelumab studies? (Cite Abstract #)
- Any tepotinib-related research? (Cite Abstract #)
- Cetuximab studies in CRC or H&N? (Cite Abstract #)
- If no direct EMD studies: Therapeutic area overlap? Competitive drug research in EMD-relevant indications?

**INSTITUTIONAL RESEARCH CAPABILITIES**:

*Therapeutic Area Specialization*:
- GU oncology (bladder, renal) leaders: Which institutions dominate? Abstract counts?
- Lung cancer centers: Top institutions for NSCLC research?
- GI oncology hubs: Leading colorectal and other GI cancer centers?
- Head & neck cancer expertise: Which institutions show strength?

*Research Modality Strengths*:
- Immunotherapy hubs: Institutions with high IO research volume
- ADC research centers: Leading institutions for antibody-drug conjugate studies
- Targeted therapy expertise: Centers with precision oncology/biomarker programs

**GEOGRAPHIC & COLLABORATIVE PATTERNS**:

*Regional Research Hubs*:
- North America: Leading US institutions? Canadian centers?
- Europe: Dominant countries (Germany, France, UK, Italy, Spain)? Top European centers?
- Asia-Pacific: Active institutions in China, Japan, Korea, Australia?

*Institutional Collaboration Networks*:
- Multi-center trial collaborations: Which institutions frequently co-present?
- Academic consortia: Evidence of cooperative group involvement?
- International networks: Cross-border institutional partnerships?

**INSTITUTIONAL RESEARCH EXAMPLES** (6-10 highlights):
Select the most notable or representative institutional research:
- For each: Institution name, Abstract #, study focus, why it demonstrates institutional capability
- Prioritize: (1) EMD portfolio-relevant institutions, (2) High-impact research from top centers
- Always cite Abstract # (Identifier)

**WRITING REQUIREMENTS**:
- Natural narrative prose - flowing paragraphs, not bullet lists in analysis (bullets only for section structure)
- Always cite Abstract # when referencing institutional research
- Integrate quantitative data naturally (e.g., "Memorial Sloan Kettering presented 23 abstracts, representing 8% of all GU oncology studies...")
- Use only information from Top Institutions table and associated abstracts - if unavailable, state "not available in current dataset"
- Maintain professional analytical tone focused on institutional capabilities
- Professional vocabulary appropriate for Medical Director/VP Medical Affairs audience

**OUTPUT STRUCTURE**:
Clear section headers with analytical paragraphs. This should read as an institutional intelligence briefing for medical affairs leadership planning academic partnerships.""",
        "required_tables": ["top_institutions"]
    },
    "insights": {
        "button_label": "Scientific Trends",
        "ai_prompt": """You are EMD Serono's senior medical affairs scientific intelligence analyst. Conduct comprehensive trend analysis of ESMO 2025 to identify emerging scientific themes, biomarker developments, and evolving treatment paradigms that could impact EMD's oncology strategy.

**EXECUTIVE SUMMARY** (2-3 paragraphs):
Provide strategic overview of the scientific landscape:
- What are the 3-5 dominant scientific themes at this conference? (e.g., ADC expansion, biomarker-driven precision medicine, IO combinations, resistance mechanisms)
- Which biomarkers and mechanisms of action show the strongest momentum based on abstract volume?
- Are there emerging treatment paradigms that could reshape standards of care in EMD-relevant therapeutic areas?
- What scientific gaps or unmet needs are evident from the research presented?

**BIOMARKER & MOLECULAR LANDSCAPE**:

Analyze the biomarker/MOA table provided and describe trends:

*Checkpoint Inhibitor Biomarkers*:
- PD-L1 expression: How many studies focus on PD-L1? What contexts (patient selection, predictive biomarker, resistance)?
- Tumor mutational burden (TMB): Volume of TMB-focused research? High vs. low TMB strategies?
- Microsatellite instability (MSI/dMMR): Activity level? Which tumor types?
- Novel IO biomarkers (LAG-3, TIM-3, TIGIT): Any emerging checkpoint targets beyond PD-1/PD-L1/CTLA-4?

*Precision Oncology Biomarkers*:
- FGFR alterations: Study volume for FGFR1/2/3/4? Which tumor types? Patient selection strategies?
- HER2: How many HER2-focused studies? Beyond traditional HER2+ indications (breast/gastric) to HER2-low or other tumors?
- MET alterations: Conference activity on MET exon 14 skipping, MET amplification, MET overexpression?
- KRAS mutations: Study volume on KRAS G12C and other KRAS variants? Which tumor types?
- Other actionable alterations: ALK, ROS1, BRAF, RET, NTRK, BRCA - which show significant research activity?

*Emerging Biomarker Themes*:
- Circulating tumor DNA (ctDNA): How many studies use ctDNA for MRD detection, treatment monitoring, or biomarker discovery?
- Immune signatures beyond PD-L1: Any research on tumor immune microenvironment, immune gene signatures, or composite biomarkers?
- Resistance biomarkers: Studies focused on mechanisms of resistance to IO, targeted therapy, or ADCs?

**MECHANISM OF ACTION TRENDS**:

*Antibody-Drug Conjugates (ADCs)*:
- Overall ADC momentum: Based on biomarker table, how many ADC-focused studies?
- ADC targets: Which ADC targets show research activity? (HER2, TROP-2, Nectin-4, CEACAM5, others)
- Tumor type expansion: Are ADCs moving into new indications beyond breast/bladder?
- Combination strategies: ADCs + IO, ADCs + chemo, ADC doublets?

*Checkpoint Inhibitors & IO Combinations*:
- IO monotherapy vs. combinations: What's the balance?
- IO+IO combinations: Which checkpoint combinations are being studied?
- IO+chemotherapy: Still a dominant paradigm or declining?
- IO+targeted therapy: Novel combinations gaining traction?
- IO+ADC: Emerging paradigm?

*Targeted Therapy Evolution*:
- Tyrosine kinase inhibitors (TKIs): Which pathways show activity? (EGFR, ALK, MET, FGFR, VEGFR, etc.)
- Next-generation targeted agents: Evolution beyond first-gen inhibitors?
- Multi-kinase vs. selective inhibitors: Which approach dominates?
- Resistance-focused agents: Drugs designed for resistance settings?

*DNA Damage Response & Cell Cycle*:
- PARP inhibitors: Research volume? Which tumor types beyond ovarian/breast?
- Other DDR targets: ATR, ATM, CHK1/2, WEE1 activity?
- CDK4/6 inhibitors: Beyond breast cancer?

*Novel Mechanisms*:
- Epigenetic targets: EZH2, IDH, other epigenetic modulators?
- Immunomodulatory agents beyond checkpoint inhibitors?
- Bispecific antibodies or other novel formats?
- Cell therapy (CAR-T, TCR-T) presence?

**TREATMENT PARADIGM EVOLUTION**:

*Treatment Settings & Sequencing*:
- Neoadjuvant/adjuvant momentum: How many studies in early-stage/perioperative settings vs. metastatic?
- Maintenance therapy: Research activity in maintenance strategies? Which agents?
- Treatment sequencing: Studies addressing optimal sequencing of therapies?
- Consolidation approaches: Emerging paradigms?

*Combination Regimen Complexity*:
- Monotherapy vs. doublet vs. triplet: What's the distribution?
- Which combination backbones are most studied? (IO+chemo, IO+targeted, etc.)
- De-escalation strategies: Any research on reducing treatment intensity in responding patients?

*Biomarker-Driven Treatment Selection*:
- Precision medicine momentum: How many studies use biomarkers to select therapy?
- Basket/umbrella trial evidence: Tumor-agnostic biomarker strategies?
- Companion diagnostics: Studies validating predictive biomarkers?

**CLINICAL ENDPOINTS & EVIDENCE QUALITY**:

*Endpoint Selection*:
- Overall survival (OS) vs. progression-free survival (PFS): Which dominates?
- Pathologic complete response (pCR) in neoadjuvant studies?
- Minimal residual disease (MRD) or ctDNA clearance as endpoints?
- Quality of life (QoL) and patient-reported outcomes (PROs)?
- Novel surrogate endpoints?

*Study Design & Phase Distribution*:
- Phase 1/2 vs. Phase 3 studies: What's the balance?
- Real-world evidence (RWE) presentations?
- Long-term follow-up data from landmark trials?
- Retrospective vs. prospective designs?

**UNMET NEEDS & RESEARCH GAPS**:

Based on what IS and ISN'T being studied:
- Underserved tumor types or patient populations?
- Biomarker gaps: Important molecular alterations without targeted therapies?
- Treatment settings lacking innovation (e.g., later-line therapies, elderly patients)?
- Geographic or health equity gaps in research?

**EMD PORTFOLIO SCIENTIFIC CONTEXT**:

*Avelumab (PD-L1 checkpoint inhibitor)*:
- How does overall PD-L1/IO research momentum position avelumab?
- IO+chemotherapy vs. IO monotherapy trends: Implications for avelumab combinations?
- Maintenance therapy research: Is this paradigm growing or stable?

*Tepotinib (MET inhibitor)*:
- MET biomarker research activity: Strong momentum or niche?
- Competitive MET inhibitor landscape: How crowded is MET space?
- Lung cancer targeted therapy trends: Where does MET fit in the evolving NSCLC landscape?

*Cetuximab (anti-EGFR mAb)*:
- EGFR biomarker research: Level of activity in CRC and H&N?
- Anti-EGFR therapeutic momentum: Growing, stable, or declining?
- Biomarker refinement: RAS testing, other EGFR resistance mechanisms?

**NOTABLE SCIENTIFIC DEVELOPMENTS** (8-12 examples):
Highlight the most scientifically significant or paradigm-shifting presentations:
- For each: Abstract #, scientific theme, why it matters
- Prioritize: (1) Novel biomarkers or MOAs, (2) Paradigm-shifting data, (3) EMD portfolio relevance
- Always cite Abstract # (Identifier)

**WRITING REQUIREMENTS**:
- Natural narrative prose - flowing paragraphs, not bullet lists (use bullets only for section structure)
- Always cite Abstract # when referencing specific studies or trends
- Integrate quantitative data from biomarker/MOA table (e.g., "PD-L1 appeared in 45 abstracts, representing 30% of all IO studies...")
- Use only information from provided biomarker table and abstracts - if unavailable, state "not found in current dataset"
- Maintain scientific rigor and precision
- Descriptive analysis - avoid prescriptive clinical recommendations
- Professional vocabulary for Medical Director/VP Medical Affairs audience

**OUTPUT STRUCTURE**:
Clear section headers with analytical paragraphs. This should read as a comprehensive scientific intelligence briefing for strategic planning and portfolio positioning.""",
        "required_tables": ["biomarker_moa_hits"]
    },
    "strategy": {
        "button_label": "Strategic Recommendations",
        "ai_prompt": """You are EMD Serono's medical affairs strategic intelligence analyst. Provide indication-specific strategic analysis for ESMO 2025.

**INDICATION-SPECIFIC CONTEXT**:
- **Avelumab**: Metastatic bladder cancer (urothelial carcinoma), first-line maintenance therapy post-platinum chemotherapy
- **Tepotinib**: Metastatic NSCLC with MET exon 14 skipping mutations
- **Cetuximab (H&N)**: Locally advanced or metastatic head & neck squamous cell carcinoma
- **Cetuximab (CRC)**: Metastatic colorectal cancer (RAS wild-type)

**ANALYSIS FRAMEWORK**:

**Executive Summary**: Strategic imperatives for this specific indication

**Current Competitive Position**: Where this EMD drug sits in the treatment paradigm (line of therapy, biomarker selection, combination strategies)

**Competitive Threats & Opportunities**:
- New competitors entering this indication
- Emerging biomarker strategies that could expand/contract market
- Combination therapy trends

**Scientific & Clinical Momentum**:
- What's gaining traction in this indication (new MOAs, ADCs, biomarkers)
- Practice-changing data or consensus shifts

**White Space & Partnership Opportunities**:
- Unmet needs in this indication
- Research gaps where EMD could lead

**Medical Affairs Action Plan**:
- Priority KOLs to engage
- Key messages for medical communications
- Clinical development considerations

REQUIREMENTS:
- **Focus on the specific indication** (e.g., metastatic bladder, locally advanced H&N, etc.)
- **Line of therapy context** (1L, 2L, maintenance, etc.)
- Strategic perspective for leadership decision-making
- Cite Abstract # for all claims
- Actionable, indication-specific insights
- Use only provided data""",
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
    global df_global, csv_hash_global, chroma_client, collection

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

    print(f"[DATA] Loaded {len(df)} studies from ESMO 2025")

    # Initialize ChromaDB for semantic search
    initialize_chromadb(df)

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

def apply_bladder_cancer_filter(df: pd.DataFrame) -> pd.Series:
    """Apply bladder cancer filter with prostate exclusion."""
    keywords = ["bladder", "urothelial", "uroepithelial", "transitional cell", "genitourinary"]
    acronym = "GU"  # Case-sensitive, word boundary
    exclusions = ["prostate"]

    mask = pd.Series([False] * len(df), index=df.index)

    # Regular keywords (case-insensitive)
    for keyword in keywords:
        title_mask = df["Title"].str.contains(keyword, case=False, na=False, regex=False)
        theme_mask = df["Theme"].str.contains(keyword, case=False, na=False, regex=False)
        mask = mask | title_mask | theme_mask

    # Acronym with word boundary (case-sensitive to avoid "giant")
    pattern = r'\b' + re.escape(acronym) + r'\b'
    title_mask = df["Title"].str.contains(pattern, case=True, na=False, regex=True)
    theme_mask = df["Theme"].str.contains(pattern, case=True, na=False, regex=True)
    mask = mask | title_mask | theme_mask

    # Build theme-has-prostate mask
    theme_has_prostate = pd.Series([False] * len(df), index=df.index)
    for exclusion in exclusions:
        theme_has_prostate = theme_has_prostate | df["Theme"].str.contains(exclusion, case=False, na=False, regex=False)

    # Build title-has-bladder mask for smart exclusion
    title_has_bladder = pd.Series([False] * len(df), index=df.index)
    for keyword in keywords:
        title_has_bladder = title_has_bladder | df["Title"].str.contains(keyword, case=False, na=False, regex=False)
    pattern_gu = r'\b' + re.escape(acronym) + r'\b'
    title_has_bladder = title_has_bladder | df["Title"].str.contains(pattern_gu, case=True, na=False, regex=True)

    # Logic: (title match) OR (theme match AND no prostate in theme) OR (theme has prostate BUT title has bladder)
    mask = title_has_bladder | (mask & ~theme_has_prostate) | (theme_has_prostate & title_has_bladder)

    return mask

def apply_renal_cancer_filter(df: pd.DataFrame) -> pd.Series:
    """Apply renal cancer filter."""
    keywords = ["renal", "renal cell"]
    acronyms = ["RCC"]
    bladder_keywords = ["bladder", "urothelial", "uroepithelial"]

    mask = pd.Series([False] * len(df), index=df.index)
    title_has_renal = pd.Series([False] * len(df), index=df.index)

    # Build title and theme masks
    for keyword in keywords:
        title_has_renal = title_has_renal | df["Title"].str.contains(keyword, case=False, na=False, regex=False)

    for acronym in acronyms:
        pattern = r'\b' + re.escape(acronym) + r'\b'
        title_has_renal = title_has_renal | df["Title"].str.contains(pattern, case=False, na=False, regex=True)

    theme_has_renal = pd.Series([False] * len(df), index=df.index)
    for keyword in keywords:
        theme_has_renal = theme_has_renal | df["Theme"].str.contains(keyword, case=False, na=False, regex=False)

    for acronym in acronyms:
        pattern = r'\b' + re.escape(acronym) + r'\b'
        theme_has_renal = theme_has_renal | df["Theme"].str.contains(pattern, case=False, na=False, regex=True)

    # Check if theme contains bladder keywords
    theme_has_bladder = pd.Series([False] * len(df), index=df.index)
    for bladder_kw in bladder_keywords:
        theme_has_bladder = theme_has_bladder | df["Theme"].str.contains(bladder_kw, case=False, na=False, regex=False)

    # Logic: title match OR (theme match AND no bladder in theme)
    mask = title_has_renal | (theme_has_renal & ~theme_has_bladder)
    return mask

def apply_lung_cancer_filter(df: pd.DataFrame) -> pd.Series:
    """Apply lung cancer filter."""
    keywords = ["lung", "non-small cell lung cancer", "non-small-cell lung cancer"]
    acronyms = ["NSCLC", "MET", "ALK", "EGFR", "KRAS"]  # All with word boundaries

    mask = pd.Series([False] * len(df), index=df.index)

    for keyword in keywords:
        title_mask = df["Title"].str.contains(keyword, case=False, na=False, regex=False)
        theme_mask = df["Theme"].str.contains(keyword, case=False, na=False, regex=False)
        mask = mask | title_mask | theme_mask

    for acronym in acronyms:
        pattern = r'\b' + re.escape(acronym) + r'\b'
        title_mask = df["Title"].str.contains(pattern, case=False, na=False, regex=True)
        theme_mask = df["Theme"].str.contains(pattern, case=False, na=False, regex=True)
        mask = mask | title_mask | theme_mask

    return mask

def apply_colorectal_cancer_filter(df: pd.DataFrame) -> pd.Series:
    """Apply colorectal cancer filter."""
    keywords = ["colorectal", "colon", "rectal", "bowel"]
    acronyms = ["CRC"]
    exclusions = ["gastric", "stomach", "esophageal", "esophagus", "pancreatic", "pancreas",
                  "hepatocellular", "liver cancer", "biliary", "cholangiocarcinoma"]
    exclusion_acronyms = ["HCC", "GEJ"]

    mask = pd.Series([False] * len(df), index=df.index)

    for keyword in keywords:
        title_mask = df["Title"].str.contains(keyword, case=False, na=False, regex=False)
        theme_mask = df["Theme"].str.contains(keyword, case=False, na=False, regex=False)
        mask = mask | title_mask | theme_mask

    for acronym in acronyms:
        pattern = r'\b' + re.escape(acronym) + r'\b'
        title_mask = df["Title"].str.contains(pattern, case=False, na=False, regex=True)
        theme_mask = df["Theme"].str.contains(pattern, case=False, na=False, regex=True)
        mask = mask | title_mask | theme_mask

    # Build title-has-CRC mask for smart exclusion
    title_has_crc = pd.Series([False] * len(df), index=df.index)
    for keyword in keywords:
        title_has_crc = title_has_crc | df["Title"].str.contains(keyword, case=False, na=False, regex=False)
    for acronym in acronyms:
        pattern = r'\b' + re.escape(acronym) + r'\b'
        title_has_crc = title_has_crc | df["Title"].str.contains(pattern, case=False, na=False, regex=True)

    # Exclude other GI cancers unless title has CRC terms
    for exclusion in exclusions:
        exclusion_mask = df["Title"].str.contains(exclusion, case=False, na=False, regex=False) | \
                        df["Theme"].str.contains(exclusion, case=False, na=False, regex=False)
        mask = mask & ~(exclusion_mask & ~title_has_crc)

    for exclusion_acronym in exclusion_acronyms:
        pattern = r'\b' + re.escape(exclusion_acronym) + r'\b'
        exclusion_mask = df["Title"].str.contains(pattern, case=False, na=False, regex=True) | \
                        df["Theme"].str.contains(pattern, case=False, na=False, regex=True)
        mask = mask & ~(exclusion_mask & ~title_has_crc)

    return mask

def apply_head_neck_cancer_filter(df: pd.DataFrame) -> pd.Series:
    """Apply head and neck cancer filter."""
    keywords = ["head and neck", "head & neck", "squamous cell carcinoma of the head", "oral", "pharyngeal", "laryngeal"]
    acronyms = ["H&N", "HNSCC", "SCCHN"]

    mask = pd.Series([False] * len(df), index=df.index)

    for keyword in keywords:
        title_mask = df["Title"].str.contains(keyword, case=False, na=False, regex=False)
        theme_mask = df["Theme"].str.contains(keyword, case=False, na=False, regex=False)
        mask = mask | title_mask | theme_mask

    for acronym in acronyms:
        pattern = r'\b' + re.escape(acronym) + r'\b'
        title_mask = df["Title"].str.contains(pattern, case=False, na=False, regex=True)
        theme_mask = df["Theme"].str.contains(pattern, case=False, na=False, regex=True)
        mask = mask | title_mask | theme_mask

    return mask

def apply_tgct_filter(df: pd.DataFrame) -> pd.Series:
    """Apply TGCT filter."""
    keywords = ["tenosynovial giant cell tumor", "pigmented villonodular synovitis"]
    acronyms = ["TGCT", "PVNS"]

    mask = pd.Series([False] * len(df), index=df.index)

    for keyword in keywords:
        title_mask = df["Title"].str.contains(keyword, case=False, na=False, regex=False)
        theme_mask = df["Theme"].str.contains(keyword, case=False, na=False, regex=False)
        mask = mask | title_mask | theme_mask

    for acronym in acronyms:
        pattern = r'\b' + re.escape(acronym) + r'\b'
        title_mask = df["Title"].str.contains(pattern, case=False, na=False, regex=True)
        theme_mask = df["Theme"].str.contains(pattern, case=False, na=False, regex=True)
        mask = mask | title_mask | theme_mask

    return mask

def apply_therapeutic_area_filter(df: pd.DataFrame, ta_filter: str) -> pd.Series:
    """Apply therapeutic area filter by name."""
    if ta_filter == "All Therapeutic Areas":
        return pd.Series([True] * len(df), index=df.index)
    elif ta_filter == "Bladder Cancer":
        return apply_bladder_cancer_filter(df)
    elif ta_filter == "Renal Cancer":
        return apply_renal_cancer_filter(df)
    elif ta_filter == "Lung Cancer":
        return apply_lung_cancer_filter(df)
    elif ta_filter == "Colorectal Cancer":
        return apply_colorectal_cancer_filter(df)
    elif ta_filter == "Head and Neck Cancer":
        return apply_head_neck_cancer_filter(df)
    elif ta_filter == "TGCT":
        return apply_tgct_filter(df)
    else:
        return pd.Series([True] * len(df), index=df.index)

# ============================================================================
# MULTI-FILTER LOGIC (Main Filtering Function)
# ============================================================================

def get_filtered_dataframe_multi(drug_filters: List[str], ta_filters: List[str],
                                  session_filters: List[str], date_filters: List[str]) -> pd.DataFrame:
    """
    Apply multi-selection filters with OR logic.
    Returns filtered DataFrame combining all selected filter combinations.
    """
    if df_global is None:
        return pd.DataFrame()

    # Start with empty mask (all False)
    combined_mask = pd.Series([False] * len(df_global), index=df_global.index)

    # If no filters selected, return first 50 results to avoid overwhelming
    if not drug_filters and not ta_filters and not session_filters and not date_filters:
        return df_global.head(50)

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
    combined_mask = pd.Series([True] * len(df_global), index=df_global.index)

    # Apply drug filters (OR across multiple drug selections, AND with other filter types)
    if drug_filters and "All Drugs" not in drug_filters and "Competitive Landscape" not in drug_filters:
        drug_combined_mask = pd.Series([False] * len(df_global), index=df_global.index)
        for drug_filter in drug_filters:
            drug_config = ESMO_DRUG_FILTERS.get(drug_filter, {})
            keywords = drug_config.get("keywords", [])

            # Build drug keyword mask
            drug_mask = pd.Series([False] * len(df_global), index=df_global.index)
            if keywords:
                for keyword in keywords:
                    drug_mask = drug_mask | df_global["Title"].str.contains(keyword, case=False, na=False, regex=False)

            # If drug has indication-specific TA filter (e.g., Cetuximab H&N vs CRC), apply it
            if "ta_filter" in drug_config:
                ta_name = drug_config["ta_filter"]
                ta_mask = apply_therapeutic_area_filter(df_global, ta_name)
                drug_mask = drug_mask & ta_mask

            drug_combined_mask = drug_combined_mask | drug_mask

        combined_mask = combined_mask & drug_combined_mask

    # Apply TA filters (OR across multiple TA selections, AND with other filter types)
    if ta_filters and "All Therapeutic Areas" not in ta_filters:
        ta_combined_mask = pd.Series([False] * len(df_global), index=df_global.index)
        for ta_filter in ta_filters:
            ta_mask = apply_therapeutic_area_filter(df_global, ta_filter)
            ta_combined_mask = ta_combined_mask | ta_mask
        combined_mask = combined_mask & ta_combined_mask

    # Apply session filters (OR across multiple session selections, AND with other filter types)
    # Use EXACT matching to distinguish "Poster" from "ePoster"
    if session_filters and "All Session Types" not in session_filters:
        session_combined_mask = pd.Series([False] * len(df_global), index=df_global.index)
        for session_filter in session_filters:
            if session_filter == "Symposia":
                # Special handling: Match any session containing "Symposium" EXCEPT "Industry-Sponsored Symposium"
                symposium_mask = df_global["Session"].str.contains("Symposium", case=False, na=False, regex=False)
                industry_mask = df_global["Session"] == "Industry-Sponsored Symposium"
                session_combined_mask = session_combined_mask | (symposium_mask & ~industry_mask)
            else:
                session_types = ESMO_SESSION_TYPES.get(session_filter, [])
                if session_types:
                    for session_type in session_types:
                        session_combined_mask = session_combined_mask | (df_global["Session"] == session_type)
        combined_mask = combined_mask & session_combined_mask

    # Apply date filters (OR across multiple date selections, AND with other filter types)
    # Use EXACT matching for dates
    if date_filters and "All Dates" not in date_filters:
        date_combined_mask = pd.Series([False] * len(df_global), index=df_global.index)
        for date_filter in date_filters:
            dates = ESMO_DATES.get(date_filter, [])
            if dates:
                for date in dates:
                    date_combined_mask = date_combined_mask | (df_global["Date"] == date)
        combined_mask = combined_mask & date_combined_mask

    # Apply combined mask and deduplicate
    filtered_df = df_global[combined_mask].copy()
    filtered_df = filtered_df.drop_duplicates()

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
    """Execute smart search: partial matching for single words, exact phrase for multi-word queries."""
    # Initialize mask with same index as df to avoid index misalignment
    mask = pd.Series([False] * len(df), index=df.index)

    # Strip quotes if present (for explicit phrase search)
    keyword = keyword.strip('"').strip("'")

    # ESMO columns (using original CSV names)
    esmo_columns = ['Title', 'Speakers', 'Speaker Location', 'Affiliation', 'Identifier', 'Room', 'Date', 'Time', 'Session', 'Theme']
    actual_columns = [col for col in esmo_columns if col in df.columns]

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

def classify_user_query(user_message: str) -> dict:
    """
    Use GPT-5-mini to classify user query and extract search parameters.
    Returns structured JSON for dataset querying and table generation.
    """
    classification_prompt = f"""You are a query classifier for ESMO 2025 conference data.

Available data columns: Title, Speakers, Speaker Location, Affiliation, Identifier, Room, Date, Time, Session, Theme

Classify this user query and extract search intent:
"{user_message}"

Return ONLY valid JSON with this exact structure:
{{
  "entity_type": "drug" | "hcp" | "institution" | "session_type" | "date" | "therapeutic_area" | "general",
  "search_terms": ["term1", "term2"],
  "generate_table": true | false,
  "table_type": "author_publications" | "drug_studies" | "institution_ranking" | "session_list" | null,
  "filter_context": {{
    "drug": "drug name if mentioned" or null,
    "ta": "therapeutic area if mentioned" or null,
    "date": "Day X if mentioned" or null,
    "session": "session type if mentioned" or null
  }},
  "top_n": 10
}}

Classification examples:

"Tell me about Andrea Necchi" or "Dr. Necchi publications"
→ {{"entity_type": "hcp", "search_terms": ["Andrea Necchi", "Necchi"], "generate_table": true, "table_type": "author_publications", "filter_context": {{}}, "top_n": 20}}

"What is enfortumab vedotin?" or "Tell me about EV"
→ {{"entity_type": "drug", "search_terms": ["enfortumab vedotin", "EV", "enfortumab"], "generate_table": true, "table_type": "drug_studies", "filter_context": {{"drug": "enfortumab vedotin"}}, "top_n": 20}}

"Most active institutions in bladder cancer"
→ {{"entity_type": "institution", "search_terms": [], "generate_table": true, "table_type": "institution_ranking", "filter_context": {{"ta": "bladder cancer"}}, "top_n": 10}}

"What are all the posters on day 3 in bladder cancer?"
→ {{"entity_type": "session_type", "search_terms": ["poster"], "generate_table": true, "table_type": "session_list", "filter_context": {{"date": "Day 3", "ta": "bladder cancer"}}, "top_n": 50}}

"What are the latest trends in immunotherapy?"
→ {{"entity_type": "general", "search_terms": ["immunotherapy", "immune checkpoint"], "generate_table": false, "table_type": null, "filter_context": {{}}, "top_n": 15}}

Important drugs to recognize: avelumab, tepotinib, cetuximab (erbitux), enfortumab vedotin (EV), pembrolizumab (keytruda), nivolumab (opdivo), durvalumab (imfinzi)
Important TAs: bladder cancer, urothelial, NSCLC, lung cancer, colorectal (CRC), head & neck (H&N, HNSCC), renal (RCC)"""

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
        # Use full dataset for entity search
        filtered_df = df.copy()
    else:
        # Apply filter context for ranking/aggregation tables
        filtered_df = apply_filters_from_context(df, filter_ctx)

    if table_type == "author_publications":
        # Search for author in Speakers column
        if not search_terms:
            return "", pd.DataFrame()

        print(f"[AUTHOR SEARCH] Searching for: {search_terms} in {len(filtered_df)} records")

        mask = pd.Series([False] * len(filtered_df))
        for term in search_terms:
            term_mask = filtered_df['Speakers'].str.contains(term, case=False, na=False)
            matches = term_mask.sum()
            print(f"[AUTHOR SEARCH] Term '{term}' found {matches} matches")
            mask |= term_mask

        results = filtered_df[mask][['Identifier', 'Title', 'Speakers', 'Affiliation', 'Session', 'Date']].head(top_n)

        print(f"[AUTHOR SEARCH] Total results: {len(results)}")

        if results.empty:
            no_results_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>📊 Author Search: {search_terms[0]}</h6>
<p class='text-muted' style='margin: 0;'>No presentations found for "{search_terms[0]}" in the ESMO 2025 dataset. Try searching for the full name or last name only.</p>
</div>"""
            return no_results_html, results

        table_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>📊 Publications by {search_terms[0]} ({len(results)} found)</h6>
{results.to_html(index=False, classes='table table-sm table-striped', escape=False)}
</div>"""
        return table_html, results

    elif table_type == "drug_studies":
        # Search for drug in Title column
        if not search_terms:
            return "", pd.DataFrame()

        print(f"[DRUG SEARCH] Searching for: {search_terms} in {len(filtered_df)} records")

        mask = pd.Series([False] * len(filtered_df))
        for term in search_terms:
            term_mask = filtered_df['Title'].str.contains(term, case=False, na=False)
            matches = term_mask.sum()
            print(f"[DRUG SEARCH] Term '{term}' found {matches} matches")
            mask |= term_mask

        results = filtered_df[mask][['Identifier', 'Title', 'Speakers', 'Affiliation', 'Session']].head(top_n)

        print(f"[DRUG SEARCH] Total results: {len(results)}")

        if results.empty:
            no_results_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>💊 Drug Search: {search_terms[0]}</h6>
<p class='text-muted' style='margin: 0;'>No studies found in the ESMO 2025 dataset mentioning "{search_terms[0]}". This drug may not be featured at this conference.</p>
</div>"""
            return no_results_html, results

        table_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>💊 Studies mentioning {search_terms[0]} ({len(results)} found)</h6>
{results.to_html(index=False, classes='table table-sm table-striped', escape=False)}
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
{ranking_df.to_html(index=False, classes='table table-sm table-striped', escape=False)}
</div>"""
        return table_html, ranking_df

    elif table_type == "session_list":
        # Filter by session type
        if search_terms:
            mask = pd.Series([False] * len(filtered_df))
            for term in search_terms:
                mask |= filtered_df['Session'].str.contains(term, case=False, na=False)
            results = filtered_df[mask]
        else:
            results = filtered_df

        results = results[['Identifier', 'Title', 'Speakers', 'Room', 'Time', 'Date']].head(top_n)

        context_str = " matching criteria" if filter_ctx else ""
        table_html = f"""<div class='entity-table-container'>
<h6 class='entity-table-title'>📅 Sessions{context_str} ({len(results)} found)</h6>
{results.to_html(index=False, classes='table table-sm table-striped', escape=False)}
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

    # Comprehensive biomarker and MOA keywords
    biomarkers_moas = [
        # Checkpoint inhibitors & IO
        "PD-1", "PD-L1", "CTLA-4", "LAG-3", "TIM-3", "TIGIT",
        # ADCs and targets
        "ADC", "antibody-drug conjugate", "HER2", "TROP-2", "Nectin-4", "CEACAM5",
        # FGFR pathway
        "FGFR", "FGFR1", "FGFR2", "FGFR3", "FGFR4",
        # Lung cancer biomarkers
        "EGFR", "ALK", "ROS1", "MET", "KRAS", "BRAF", "RET", "NTRK", "HER2",
        # Mismatch repair / microsatellite
        "MSI", "MSI-H", "dMMR", "microsatellite",
        # Tumor mutational burden
        "TMB", "tumor mutational burden",
        # Circulating tumor DNA
        "ctDNA", "circulating tumor DNA",
        # Cell cycle / DNA damage
        "PARP", "ATR", "ATM", "BRCA", "HRD",
        # Angiogenesis
        "VEGF", "VEGFR",
        # PI3K/AKT/mTOR
        "PI3K", "AKT", "mTOR",
        # CDK4/6
        "CDK4", "CDK6",
        # WNT pathway
        "WNT", "beta-catenin",
        # Epigenetic
        "EZH2", "IDH",
        # Cell surface
        "CD38", "BCMA", "CD20",
        # Treatment settings
        "neoadjuvant", "adjuvant", "maintenance", "perioperative",
        # Combination approaches
        "combination", "doublet", "triplet",
        # Resistance mechanisms
        "resistance", "refractory"
    ]

    results = []
    for keyword in biomarkers_moas:
        count = df['Title'].str.contains(keyword, case=False, na=False).sum()
        if count > 0:
            results.append({'Biomarker/MOA': keyword, '# Studies': count})

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values('# Studies', ascending=False)

    return result_df

def generate_competitor_table(df: pd.DataFrame, n: int = 50) -> pd.DataFrame:
    """Generate competitor drugs table with Drug and Company columns from drug database."""
    if df.empty:
        return pd.DataFrame()

    # Load drug-company mapping from CSV
    try:
        drug_db_path = Path(__file__).parent / "Drug_Company_names.csv"
        drug_db = pd.read_csv(drug_db_path)
    except Exception as e:
        print(f"Warning: Could not load Drug_Company_names.csv: {e}")
        return pd.DataFrame()

    # Find abstracts mentioning each drug (search both commercial and generic names)
    results = []
    for _, drug_row in drug_db.iterrows():
        commercial = str(drug_row['drug_commercial']).strip() if pd.notna(drug_row['drug_commercial']) else ""
        generic = str(drug_row['drug_generic']).strip() if pd.notna(drug_row['drug_generic']) else ""
        company = str(drug_row['company']).strip() if pd.notna(drug_row['company']) else ""

        # Skip if no valid drug names
        if not commercial and not generic:
            continue

        # Build search mask for this drug (search both names)
        mask = pd.Series([False] * len(df), index=df.index)

        if commercial:
            commercial_mask = df['Title'].str.contains(commercial, case=False, na=False, regex=False)
            mask = mask | commercial_mask

        if generic:
            generic_mask = df['Title'].str.contains(generic, case=False, na=False, regex=False)
            mask = mask | generic_mask

        matching_abstracts = df[mask]

        # Add each matching abstract as a row
        # Use generic name preferentially, fall back to commercial
        drug_display_name = generic if generic else commercial

        for _, row in matching_abstracts.iterrows():
            results.append({
                'Drug': drug_display_name,
                'Company': company,
                'Identifier': row['Identifier'],
                'Title': row['Title'],
                'Speakers': row['Speakers'],
                'Affiliation': row['Affiliation']
            })

    result_df = pd.DataFrame(results)

    # Remove duplicates (same abstract might match multiple drug name variants)
    if not result_df.empty:
        result_df = result_df.drop_duplicates(subset=['Drug', 'Identifier'])
        result_df = result_df.sort_values(['Drug', 'Identifier'])
        result_df = result_df.head(n)  # Limit to n results

    return result_df

def filter_competitors_by_indication(competitor_df: pd.DataFrame, indication_keywords: list) -> pd.DataFrame:
    """Filter competitor table to only show drugs relevant to specific indication."""
    if competitor_df.empty or not indication_keywords:
        return competitor_df

    # Search Title column for indication keywords
    mask = pd.Series([False] * len(competitor_df), index=competitor_df.index)
    for keyword in indication_keywords:
        mask = mask | competitor_df['Title'].str.contains(keyword, case=False, na=False, regex=False)

    return competitor_df[mask]

def generate_emerging_threats_table(df: pd.DataFrame, indication_keywords: list, n: int = 20) -> pd.DataFrame:
    """Identify emerging threats: drugs with <5 abstracts but showing novel MOAs or combinations."""
    if df.empty:
        return pd.DataFrame()

    try:
        drug_db_path = Path(__file__).parent / "Drug_Company_names.csv"
        drug_db = pd.read_csv(drug_db_path)
    except Exception as e:
        print(f"Warning: Could not load Drug_Company_names.csv: {e}")
        return pd.DataFrame()

    # Find drugs with 2-5 mentions (emerging, not established)
    emerging = []
    for _, drug_row in drug_db.iterrows():
        commercial = str(drug_row['drug_commercial']).strip() if pd.notna(drug_row['drug_commercial']) else ""
        generic = str(drug_row['drug_generic']).strip() if pd.notna(drug_row['drug_generic']) else ""
        company = str(drug_row['company']).strip() if pd.notna(drug_row['company']) else ""

        if not commercial and not generic:
            continue

        # Build search mask
        mask = pd.Series([False] * len(df), index=df.index)
        if commercial:
            mask = mask | df['Title'].str.contains(commercial, case=False, na=False, regex=False)
        if generic:
            mask = mask | df['Title'].str.contains(generic, case=False, na=False, regex=False)

        # Filter by indication keywords
        if indication_keywords:
            indication_mask = pd.Series([False] * len(df), index=df.index)
            for keyword in indication_keywords:
                indication_mask = indication_mask | df['Title'].str.contains(keyword, case=False, na=False, regex=False)
            mask = mask & indication_mask

        matching = df[mask]
        count = len(matching)

        # Emerging: 2-5 mentions
        if 2 <= count <= 5:
            drug_name = generic if generic else commercial
            sample_title = matching.iloc[0]['Title'] if not matching.empty else ""
            emerging.append({
                'Drug': drug_name,
                'Company': company,
                '# Studies': count,
                'Sample Title': sample_title[:100] + '...' if len(sample_title) > 100 else sample_title
            })

    result_df = pd.DataFrame(emerging)
    if not result_df.empty:
        result_df = result_df.sort_values('# Studies', ascending=False).head(n)

    return result_df

# ============================================================================
# AI STREAMING FUNCTIONS
# ============================================================================

def stream_openai_response(prompt: str, model: str = "gpt-5-mini") -> str:
    """Stream response from OpenAI and return full text."""
    if not client:
        return "OpenAI API key not configured."

    try:
        response = client.responses.create(
            model=model,
            input=[{"role": "user", "content": prompt}],
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            max_output_tokens=3000,
            stream=False
        )

        return response.output_text
    except Exception as e:
        return f"Error generating AI response: {str(e)}"

def stream_openai_tokens(prompt: str, model: str = "gpt-5-mini"):
    """Stream tokens from OpenAI for SSE."""
    if not client:
        print("[OPENAI] ERROR: Client not initialized")
        yield "data: " + json.dumps({"text": "OpenAI API key not configured."}) + "\n\n"
        return

    try:
        print(f"[OPENAI] Creating streaming response with model: {model}")
        stream = client.responses.create(
            model=model,
            input=[{"role": "user", "content": prompt}],
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            max_output_tokens=6000,  # Increased for comprehensive KOL analysis
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

    # Convert to records for JSON serialization
    data_records = filtered_df[['Title', 'Speakers', 'Affiliation', 'Speaker Location', 'Identifier', 'Room',
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
        "showing": len(filtered_df),
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

    # Convert to records
    data_records = filtered_df[['Title', 'Speakers', 'Affiliation', 'Speaker Location', 'Identifier', 'Room',
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
        "showing": len(filtered_df),
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
            # Apply TA filters only, use drug filter to guide competitor search
            if playbook_key == "competitor":
                # For competitor intelligence, drug_filters guide which EMD drug's competitors to focus on
                # TA filters still apply to narrow therapeutic area scope
                if ta_filters or session_filters or date_filters:
                    filtered_df = get_filtered_dataframe_multi([], ta_filters, session_filters, date_filters)
                else:
                    filtered_df = df_global.copy()
                print(f"[PLAYBOOK] Competitor mode: Using dataset with {len(filtered_df)} studies (drug filter used for competitor focus)")
            else:
                # For other buttons, apply all filters normally
                if not drug_filters and not ta_filters and not session_filters and not date_filters:
                    filtered_df = df_global.copy()
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
                authors_table = generate_top_authors_table(filtered_df, n=15)
                tables_data["top_authors"] = authors_table.to_markdown(index=False) if not authors_table.empty else "No author data available"

                # Send table as SSE event (frontend expects: title, columns, rows as objects)
                if not authors_table.empty:
                    print(f"[PLAYBOOK] Sending authors table with {len(authors_table)} rows")
                    try:
                        table_data = {
                            "title": "Top 15 Authors",
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
                    for speaker in authors_table['Speaker'].head(15):
                        speaker_data = filtered_df[filtered_df['Speakers'] == speaker][['Identifier', 'Title', 'Affiliation', 'Session']]
                        if not speaker_data.empty:
                            kol_abstracts.append(f"\n**{speaker}** ({len(speaker_data)} abstracts):\n{speaker_data.to_markdown(index=False)}")

                    if kol_abstracts:
                        tables_data["kol_abstracts"] = "\n".join(kol_abstracts)

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
                # For competitor button, use dedicated competitor table with Drug and Company columns
                if playbook_key == "competitor":
                    # IMPORTANT: For competitor intelligence, search FULL dataset (not filtered)
                    print(f"[PLAYBOOK] Generating competitor table from FULL dataset ({len(df_global)} studies)")
                    competitor_table_full = generate_competitor_table(df_global, n=len(df_global))

                    # Filter competitors by indication if drug focus is selected
                    indication_keywords = []
                    if drug_filters and drug_filters[0] == "Avelumab Focus":
                        indication_keywords = ["bladder", "urothelial", "uroepithelial"]
                    elif drug_filters and drug_filters[0] == "Tepotinib Focus":
                        indication_keywords = ["lung", "NSCLC", "MET"]
                    elif drug_filters and drug_filters[0] == "Cetuximab Focus":
                        indication_keywords = ["colorectal", "CRC", "head and neck", "HNSCC"]

                    if indication_keywords:
                        competitor_table = filter_competitors_by_indication(competitor_table_full, indication_keywords)
                        print(f"[PLAYBOOK] Filtered to {len(competitor_table)} competitors in relevant indication")
                    else:
                        competitor_table = competitor_table_full

                    tables_data["competitor_abstracts"] = competitor_table.to_markdown(index=False) if not competitor_table.empty else "No competitor drugs found"

                    if not competitor_table.empty:
                        print(f"[PLAYBOOK] Sending main competitor table with {len(competitor_table)} studies")
                        yield "data: " + json.dumps({
                            "title": f"Competitor Drugs ({len(competitor_table)} studies)",
                            "columns": list(competitor_table.columns),
                            "rows": sanitize_data_structure(competitor_table.to_dict('records'))
                        }) + "\n\n"

                    # Generate emerging threats table
                    if indication_keywords:
                        print(f"[PLAYBOOK] Generating emerging threats table...")
                        emerging_table = generate_emerging_threats_table(df_global, indication_keywords, n=15)
                        if not emerging_table.empty:
                            print(f"[PLAYBOOK] Found {len(emerging_table)} emerging threats")
                            tables_data["emerging_threats"] = emerging_table.to_markdown(index=False)
                            yield "data: " + json.dumps({
                                "title": f"Emerging Threats (2-5 studies each)",
                                "columns": list(emerging_table.columns),
                                "rows": sanitize_data_structure(emerging_table.to_dict('records'))
                            }) + "\n\n"
                        else:
                            print(f"[PLAYBOOK] No emerging threats found")

                    if competitor_table.empty and (not indication_keywords or emerging_table.empty):
                        print(f"[PLAYBOOK] WARNING: No competitor drugs found in dataset")
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

            # For COMPETITOR button: drug_filters guide analysis focus, not dataset filtering
            if playbook_key == "competitor" and drug_filters:
                drug_context = f"**EMD Drug Focus**: {', '.join(drug_filters)} - Analyze competitors relevant to this drug's indication(s)"
            else:
                drug_context = f"Drug Filter: {', '.join(drug_filters) if drug_filters else 'Competitive Landscape'}"

            # For competitive intelligence, add specific competitor guidance based on selected EMD drug
            filter_guidance = ""
            if playbook_key == "competitor":
                if drug_filters:
                    # Map EMD drug selection to specific competitors to focus on
                    competitor_focus = {
                        "Avelumab Focus": {
                            "indication": "Metastatic Bladder Cancer (1L maintenance)",
                            "key_competitors": ["enfortumab vedotin (EV)", "EV+pembrolizumab (EV+P)", "pembrolizumab", "nivolumab", "durvalumab", "atezolizumab", "sacituzumab govitecan", "erdafitinib"],
                            "therapeutic_area": "Bladder/Urothelial Cancer"
                        },
                        "Tepotinib Focus": {
                            "indication": "NSCLC with MET exon 14 skipping mutations",
                            "key_competitors": ["capmatinib", "crizotinib", "osimertinib", "alectinib", "selpercatinib", "pralsetinib", "pembrolizumab"],
                            "therapeutic_area": "Non-Small Cell Lung Cancer (NSCLC) - MET alterations"
                        },
                        "Cetuximab Focus": {
                            "indication": "Colorectal Cancer & Head & Neck Cancer (EGFR+)",
                            "key_competitors": ["panitumumab", "bevacizumab", "pembrolizumab", "nivolumab", "regorafenib", "trifluridine/tipiracil"],
                            "therapeutic_area": "Colorectal Cancer and Head & Neck Squamous Cell Carcinoma"
                        }
                    }

                    selected_drug = drug_filters[0] if drug_filters else None
                    if selected_drug in competitor_focus:
                        focus = competitor_focus[selected_drug]
                        competitor_list = "', '".join(focus["key_competitors"])
                        filter_guidance = f"\n\n**COMPETITIVE ANALYSIS FOCUS**:\n"
                        filter_guidance += f"- **Primary EMD Asset**: {selected_drug.replace(' Focus', '')} in {focus['indication']}\n"
                        filter_guidance += f"- **Therapeutic Area**: {focus['therapeutic_area']}\n"
                        filter_guidance += f"- **Key Competitors to Analyze**: '{competitor_list}'\n"
                        filter_guidance += f"- **Analysis Scope**: Prioritize these competitors in your analysis. Search the competitor abstracts table for mentions of these drugs and provide detailed competitive positioning insights."
                elif ta_filters and "All Therapeutic Areas" not in ta_filters:
                    relevant_drugs = []
                    if any(ta in ["Bladder Cancer", "Renal Cancer"] for ta in ta_filters):
                        relevant_drugs.append("avelumab (bladder/urothelial cancer)")
                    if "Lung Cancer" in ta_filters:
                        relevant_drugs.append("tepotinib (NSCLC MET)")
                    if any(ta in ["Colorectal Cancer", "Head & Neck Cancer"] for ta in ta_filters):
                        relevant_drugs.append("cetuximab (CRC/H&N)")
                    if "TGCT" in ta_filters:
                        relevant_drugs.append("pimicotinib (TGCT)")

                    if relevant_drugs:
                        filter_guidance = f"\n\n**IMPORTANT**: This dataset is filtered to {', '.join(ta_filters)}. Focus your EMD Portfolio analysis on: {', '.join(relevant_drugs)}. You may briefly note that other EMD drugs are not relevant to this therapeutic area filter and skip their detailed analysis."

            full_prompt = f"""{prompt_template}

**CONFERENCE DATA CONTEXT**:
{drug_context}
{ta_context}
Total Studies in Filtered Dataset: {len(filtered_df)}{filter_guidance}

**DATA PROVIDED**:
{table_context}

Based on the data provided above, write a comprehensive analysis following the framework."""

            # 4. Stream AI response token by token
            for token_event in stream_openai_tokens(full_prompt):
                yield token_event

        except Exception as e:
            yield "data: " + json.dumps({"error": f"Streaming error: {str(e)}"}) + "\n\n"

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)

# ============================================================================
# CHAT ROUTE (Simplified Streaming)
# ============================================================================

@app.route('/api/chat/stream', methods=['POST'])
def stream_chat_api():
    """
    Simplified chat streaming endpoint.

    Flow: Get query → Apply filters → Semantic search → Build prompt → Stream response
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
            # 1. Classify user query to detect entity types and table needs
            classification = classify_user_query(user_query)
            print(f"[QUERY CLASSIFICATION] {classification}")

            # 2. Apply filters to get relevant dataset
            filtered_df = get_filtered_dataframe_multi(drug_filters, ta_filters, session_filters, date_filters)

            if filtered_df.empty:
                yield "data: " + json.dumps({"text": "No data matches your current filters. Please adjust filters and try again."}) + "\n\n"
                yield "data: [DONE]\n\n"
                return

            # 3. Generate entity table if needed
            table_html = ""
            table_data = pd.DataFrame()

            if classification.get('generate_table'):
                table_html, table_data = generate_entity_table(classification, df_global)

                if table_html:
                    # Send table first as a separate event
                    yield "data: " + json.dumps({"table": sanitize_unicode_for_windows(table_html)}) + "\n\n"

            # 4. Determine data context for AI response
            if not table_data.empty:
                # Use table data as primary context (reduces hallucination)
                relevant_data = table_data
                data_source = f"entity table ({len(table_data)} records)"
            elif table_html and table_data.empty:
                # Table was generated but returned no results (drug/author not found)
                # Still do semantic search to provide context for AI response
                relevant_data = filtered_df.head(20)

                if collection:
                    try:
                        results = collection.query(
                            query_texts=[user_query],
                            n_results=min(20, len(filtered_df))
                        )

                        if results and results['ids']:
                            result_indices = [int(doc_id.replace('doc_', '')) for doc_id in results['ids'][0]]
                            relevant_data = df_global.iloc[result_indices]
                            relevant_data = relevant_data[relevant_data.index.isin(filtered_df.index)]
                    except Exception as e:
                        print(f"[SEMANTIC SEARCH] Error: {e}")

                data_source = f"semantic search (no exact matches, using related studies)"
            else:
                # Fall back to semantic search
                relevant_data = filtered_df.head(20)

                if collection:
                    try:
                        results = collection.query(
                            query_texts=[user_query],
                            n_results=min(20, len(filtered_df))
                        )

                        if results and results['ids']:
                            result_indices = [int(doc_id.replace('doc_', '')) for doc_id in results['ids'][0]]
                            relevant_data = df_global.iloc[result_indices]
                            relevant_data = relevant_data[relevant_data.index.isin(filtered_df.index)]
                    except Exception as e:
                        print(f"[SEMANTIC SEARCH] Error: {e}")

                data_source = f"semantic search ({len(relevant_data)} records)"

            # 5. Build context from relevant data
            data_context = relevant_data[['Identifier', 'Title', 'Speakers', 'Affiliation']].head(15).to_markdown(index=False)

            # 6. Build prompt with scope context
            # Build human-readable scope description
            scope_parts = []
            if drug_filters:
                scope_parts.append(f"💊 {', '.join(drug_filters)}")
            if ta_filters:
                scope_parts.append(f"🎯 {', '.join(ta_filters)}")

            if scope_parts:
                active_scope = " • ".join(scope_parts)
                scope_description = f"**ACTIVE SCOPE**: {active_scope} ({len(filtered_df)} studies)"
            else:
                scope_description = f"**ACTIVE SCOPE**: All Conference Data ({len(filtered_df)} studies)"

            ta_context = f"Therapeutic Area: {', '.join(ta_filters) if ta_filters else 'All Therapeutic Areas'}"
            drug_context = f"Drug Focus: {', '.join(drug_filters) if drug_filters else 'Competitive Landscape'}"

            # Include conversation history for context
            history_context = ""
            if conversation_history:
                recent_history = conversation_history[-4:]  # Last 2 exchanges
                history_text = "\n".join([f"User: {msg['user']}\nAssistant: {msg['assistant']}" for msg in recent_history])
                history_context = f"\n\n**CONVERSATION HISTORY**:\n{history_text}"

            # Add table context if generated
            table_context = ""
            if classification.get('generate_table'):
                if not table_data.empty:
                    table_context = f"\n\n**NOTE**: A data table has been displayed to the user showing {len(table_data)} relevant records. Use this table as your primary source of truth when answering."
                else:
                    table_context = f"\n\n**NOTE**: The user asked about a specific entity that was not found in the ESMO 2025 dataset. A 'no results' message has been displayed. Explain why this might be the case and suggest alternative searches or related topics."

            prompt = f"""You are an expert medical affairs analyst for EMD Serono analyzing ESMO 2025 conference data.

**USER QUESTION**: {user_query}

{scope_description}

**DATA SOURCE**: {data_source}
{history_context}{table_context}

**RELEVANT CONFERENCE DATA**:
{data_context}

**INSTRUCTIONS**:
- **IMPORTANT**: Start your response by mentioning the active scope (e.g., "Based on {len(filtered_df)} studies in [scope]...")
- Always cite Abstract # (identifier) when referencing specific studies
- If a table was generated, reference it and provide analysis beyond what's in the table
- If the data doesn't contain information to answer the question, acknowledge this clearly
- Focus on actionable insights for medical affairs professionals
- Consider EMD Serono's portfolio: avelumab (bladder cancer), tepotinib (NSCLC MET+), cetuximab (CRC/H&N), pimicotinib (TGCT, pre-launch)
- Be concise but comprehensive

Please answer the user's question based on the conference data provided."""

            # 7. Stream AI response
            for token_event in stream_openai_tokens(prompt):
                yield token_event

        except Exception as e:
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

if df_global is None:
    print("\n[ERROR] Failed to load conference data. Application cannot start.")
    print("[ERROR] Make sure ESMO_2025_FINAL_20250929.csv is in the application directory.")
    print("[ERROR] Current directory:", Path.cwd())
    print("[ERROR] Expected location:", CSV_FILE.absolute())
else:
    print(f"\n[SUCCESS] Application ready with {len(df_global)} conference studies")
    print(f"[INFO] ChromaDB: {'Initialized' if collection else 'Not available'}")
    print(f"[INFO] OpenAI API: {'Configured' if client else 'Not configured'}")
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
        port=5000,
        debug=False,  # Changed to False for production readiness
        threaded=True
    )
