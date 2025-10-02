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
        "keywords": ["bladder", "urothelial", "uroepithelial", "transitional cell", r"\bGU\b", "genitourinary"],
        "exclusions": ["prostate"],
        "regex": True
    },
    "Renal Cancer": {
        "keywords": ["renal", "renal cell", r"\bRCC\b"],
        "regex": True
    },
    "Lung Cancer": {
        "keywords": ["lung", "non-small cell lung cancer", "non-small-cell lung cancer", "NSCLC",
                     r"\bMET\b", r"\bALK\b", r"\bEGFR\b", r"\bKRAS\b", r"\bBRAF\b", r"\bRET\b", r"\bROS1\b", r"\bNTRK\b"],
        "regex": True
    },
    "Colorectal Cancer": {
        "keywords": ["colorectal", r"\bCRC\b", "colon", "rectal", "bowel"],
        "exclusions": ["gastric", "esophageal", "pancreatic", "hepatocellular", r"\bHCC\b"],
        "regex": True
    },
    "Head and Neck Cancer": {
        "keywords": ["head and neck", "head & neck", r"\bH&N\b", r"\bHNSCC\b", r"\bSCCHN\b",
                     "squamous cell carcinoma of the head", "oral", "pharyngeal", "laryngeal"],
        "regex": True
    },
    "TGCT": {
        "keywords": [r"\bTGCT\b", r"\bPVNS\b", "tenosynovial giant cell tumor", "pigmented villonodular synovitis"],
        "regex": True
    },
    "DNA Damage Response (DDRi)": {
        "keywords": [r"\bATR\b", r"\bATRi\b", r"\bATM\b", r"\bATMi\b", r"\bPARP\b", r"\bPARPi\b", "DNA Damage Response"],
        "regex": True  # Special flag for word boundary matching
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
        "ai_prompt": """You are EMD Serono's senior competitive intelligence analyst for medical affairs. Analyze the competitive landscape at ESMO 2025 to identify strategic threats, opportunities, and positioning insights for field teams and leadership.

**CRITICAL INSTRUCTIONS**:
1. **Therapeutic Area Analysis with Indication-Specific EMD Context**:
   - You are analyzing the ENTIRE therapeutic area (e.g., all Bladder Cancer studies if "Bladder Cancer" filter selected)
   - Discuss the full competitive landscape in this therapeutic area
   - **HOWEVER**: When discussing EMD portfolio implications, be indication-specific:
     * Avelumab: Focus on **1L locally advanced/metastatic urothelial carcinoma (la/mUC) maintenance therapy** (not all bladder settings)
     * Tepotinib: Focus on **1L metastatic NSCLC with METx14 skipping mutations** (not all NSCLC or MET-driven tumors)
     * Cetuximab (H&N): Focus on **1L locally advanced/metastatic head & neck squamous cell carcinoma (la/mHNSCC)**
     * Cetuximab (CRC): Focus on **1L metastatic colorectal cancer (mCRC), RAS wild-type**
   - Example: If analyzing Bladder Cancer TA, discuss ALL bladder competitors, but flag which ones specifically threaten avelumab's 1L maintenance positioning vs other bladder settings

2. **Anti-Hallucination Safeguards**:
   - ONLY use information from provided data tables - never invent Abstract #s or presentation details
   - If data isn't in the table, write "not available in dataset" - do not speculate
   - Abstract #s must match actual Identifiers in the data
   - Presentation times/dates must come from Date/Time columns when available
   - When uncertain about any detail, omit rather than guess

3. **TGCT Clarification** (if applicable):
   - TGCT = Tenosynovial Giant Cell Tumor (PVNS), NOT testicular germ cell tumor
   - If filtering for TGCT/pimicotinib, verify joint/synovial tumor context, exclude testicular cancer

**ALERT PRIORITY SYSTEM** (Use consistently):
- 🔴 **HIGH ALERT**: Practice-changing data requiring immediate MSL response (within 7 days)
- 🟡 **MEDIUM PRIORITY**: Monitor and respond if HCPs ask (within 30 days)
- 🟢 **LOW PRIORITY**: Baseline competitor activity, no urgent action required

---

**SECTION 1: IMMEDIATE COMPETITIVE ALERTS** (Scan for tactical field intelligence)

Identify 3-5 HIGH ALERT competitive threats requiring urgent medical affairs response. For each:

🔴 **HIGH ALERT #1**: [Competitor Drug] [Data Type]
- **Abstract Details**: (Abstract #X) - [Title if showing practice-changing data]
- **Presentation**: [Date/Time from data if available, otherwise omit]
- **EMD IMPACT**: How does this threaten [specific EMD asset] in [specific indication/line of therapy]?
- **FIELD RESPONSE GUIDANCE**:
  * **Likely HCP Question**: "[What oncologists will ask based on this data]"
  * **MSL Response Framework**: "[2-3 sentence differentiation - how EMD approach differs/complements]"
  * **Supporting Evidence**: (Abstract #s from EMD research or prior studies)
- **MEDICAL AFFAIRS ESCALATION**: [If data shows X result, then Y leadership action needed]

[Repeat for additional HIGH ALERTs - limit to truly practice-changing developments]

🟡 **MEDIUM PRIORITY** Competitive Developments:
[Briefly list 2-4 items to monitor - not urgent, but notable competitive activity]

---

**SECTION 2: COMPETITIVE LANDSCAPE OVERVIEW** (Strategic context for leadership)

**Executive Summary** (2-3 paragraphs):
- **Competitive Intensity**: Quantify total competitor abstracts in filtered dataset - which drugs dominate?
- **MOA Class Distribution**: What percentage are ICIs vs ADCs vs TKIs vs bispecifics vs other?
- **Treatment Paradigm Shifts**: Are competitors moving to upfront combinations vs maintenance vs sequencing strategies?
- **Strategic Imperatives**: What are the 2-3 most significant competitive developments requiring EMD attention?

**EMD-Specific Positioning Context**:
- **Avelumab** (if filtered): How does overall checkpoint inhibitor/maintenance therapy activity position avelumab's 1L maintenance strategy in la/mUC?
- **Tepotinib** (if filtered): How does MET inhibitor landscape and NSCLC biomarker activity position tepotinib in MET-driven mNSCLC?
- **Cetuximab** (if filtered): How does anti-EGFR/RAS biomarker research activity position cetuximab in la/mHNSCC or mCRC?

---

**SECTION 3: TOP COMPETITOR DEEP-DIVE** (Focus on direct threats)

Analyze the top 5-10 competitor drugs by abstract volume. For each, provide one comprehensive paragraph:

1. **Drug Name & Company**: [From competitor table]
2. **Conference Presence**: "Drug X appears in Y abstracts" (quantify using # Studies from table)
3. **MOA Context**: [From table: e.g., "ADC targeting Nectin-4", "PD-1 checkpoint inhibitor"]
4. **Clinical Settings**: [From abstract titles: 1L vs 2L+ vs maintenance vs perioperative vs biomarker-selected]
5. **Study Types**: [Phase 3 trials? Real-world evidence? Combination studies? Biomarker work?]
6. **Strategic Threat Level**: Assess as HIGH/MEDIUM/LOW with clear justification based on:
   - Direct competition in same indication/line of therapy as EMD asset?
   - Practice-changing data vs incremental updates?
   - MOA overlap vs complementary mechanism?
7. **Citations**: Always reference specific abstracts by Identifier (Abstract #)

**Competitive Strategy Patterns**:
- *Indication Expansion*: Which competitors expanding into new tumor types or earlier disease stages?
- *Combination Development*: Most common backbones (IO+chemo, IO+ADC, doublets, triplets)? Threats to EMD monotherapy?
- *Biomarker-Driven Positioning*: Competitors fragmenting patient populations with companion diagnostics or precision medicine approaches?

---

**SECTION 4: WHITE SPACE & STRATEGIC OPPORTUNITIES**

Based on what competitors are NOT doing:
- **Underserved Patient Populations**: Which biomarker groups, age ranges, performance status, or clinical settings lack competitive research?
- **Treatment Settings**: Where are competitors not innovating? (e.g., maintenance therapy gaps if field is dominated by upfront combinations)
- **Combination Opportunities**: Which synergistic regimens are unexplored by competitors?
- **For Each Opportunity**: Rationale (why it matters) + EMD asset fit + Feasibility assessment

---

**SECTION 5: INSTITUTIONAL & KOL COMPETITIVE INTELLIGENCE**

**Leading Institutions in Competitor Research**:
- Top 5 cancer centers by competitor abstract volume
- Geographic hubs (US vs EU vs APAC concentration)
- Institutional specialization examples (e.g., "Memorial Sloan Kettering: 15 EV+P abstracts in GU oncology")

**Key Opinion Leaders Presenting Competitor Data**:
- Identify 3-5 high-profile KOLs with multiple competitor abstracts
- For each: Name, institution, competitor drugs studied, therapeutic focus
- **Engagement Consideration**: Despite competitor ties, are these KOLs accessible for EMD scientific exchange? (Based on therapeutic area overlap and research breadth)

---

**WRITING REQUIREMENTS**:
- **Audience**: Hybrid - MSLs need tactical alerts (Section 1), Medical Directors need strategic landscape (Sections 2-5)
- **Tone**: Objective, fact-based competitive intelligence - not defensive or dismissive
- **Format**: Natural narrative prose with section structure (use bullets sparingly)
- **Citations**: Always cite Abstract # when referencing specific studies
- **Quantification**: Integrate data (e.g., "Pembrolizumab: 87 abstracts, 43% of IO studies")
- **Scope**: Use only provided data - if unavailable, state "not found in current dataset"
- **Vocabulary**: Professional medical terminology appropriate for oncology medical affairs

**OUTPUT STRUCTURE**: Tactical alerts first (immediate action), then strategic context (landscape understanding).""",
        "required_tables": ["all_data"]
    },
    "kol": {
        "button_label": "KOL Analysis",
        "ai_prompt": """You are EMD Serono's medical affairs KOL intelligence analyst. Analyze the most active researchers at ESMO 2025 and provide TIER-PRIORITIZED engagement guidance for field teams and strategic planning for leadership.

**CRITICAL INSTRUCTIONS**:
1. **Strict Scope Limitation**:
   - You are analyzing a FILTERED dataset (e.g., only Bladder Cancer abstracts if TA filter applied)
   - ONLY discuss the research visible in the provided KOL abstracts list below
   - DO NOT speculate about this KOL's work in other therapeutic areas not shown
   - DO NOT assume broader research portfolio beyond what abstracts are provided
   - If a KOL has 5 bladder cancer abstracts shown, discuss ONLY those 5 - do not mention "also works in lung cancer" unless you see lung cancer abstracts in their list

2. **Anti-Hallucination Safeguards**:
   - ONLY use information from provided Top Authors table and KOL abstracts - never invent names, institutions, or Abstract #s
   - If data isn't in the table, write "not available in dataset" - do not speculate
   - Presentation times/dates must come from Date/Time columns when available
   - When uncertain about any detail, omit rather than guess

3. **TGCT Clarification** (if applicable):
   - TGCT = Tenosynovial Giant Cell Tumor (PVNS), NOT testicular germ cell tumor
   - If analyzing pimicotinib-relevant research, verify joint/synovial tumor context
   - Exclude testicular cancer KOLs from TGCT/pimicotinib analysis

4. **Formatting Consistency**:
   - Use **bold** for section headers and KOL names only (not random words)
   - Do NOT use italics unless quoting abstract titles
   - Use checkmark ✅ and warning ⚠️ symbols consistently
   - Use consistent bullet formatting (- for lists, not mix of - and •)

**TIER SYSTEM** (Use for prioritization):
- **TIER 1**: Must-meet KOLs (EMD-relevant data + high influence + accessible)
- **TIER 2**: Strategic opportunities (emerging leaders, geographic targets, adjacent therapeutic areas)
- **TIER 3**: Monitor only (heavy competitor focus, low EMD relevance)

---

**SECTION 1: TIER 1 KOL ENGAGEMENT PRIORITIES** (Top 5-8 "must-meet" KOLs)

For each Tier 1 KOL, provide tactical field guidance:

**TIER 1: Dr. [FULL NAME]** ([Institution], [City/Country])
**Abstract Count**: X presentations at ESMO 2025

**WHY TIER 1**:
- ✅ Presents EMD-relevant therapeutic area data (specify: bladder/lung/CRC/H&N)
- ✅ High productivity (X abstracts = strong thought leadership proxy)
- ✅ Portfolio alignment: [Note if presenting avelumab/tepotinib/cetuximab data - cite Abstract #s]
- ⚠️ [If applicable: Also presenting competitor data, but still accessible for engagement]

**ENGAGEMENT APPROACH**:
- **When/Where to Find**: Presenting [Day from Date column], [Time from Time column], [Room if available] (Abstract #X)
- **Discussion Topics** (based on their abstract titles):
  * [Topic 1 from their research focus - e.g., "FGFR3 biomarker testing infrastructure"]
  * [Topic 2 - e.g., "Unmet needs in cisplatin-ineligible bladder cancer"]
  * [Topic 3 - e.g., "Real-world avelumab maintenance experience"]
- **Strategic Objective**: Assess interest in [specific opportunity - e.g., "investigator-initiated RWE study" or "advisory board participation" or "scientific publication collaboration"]

**PORTFOLIO RELEVANCE**:
- Avelumab: [Yes/No - if yes, cite Abstract #s]
- Tepotinib: [Yes/No - if yes, cite Abstract #s]
- Cetuximab: [Yes/No - if yes, cite Abstract #s]
- Pimicotinib: [Yes/No - if yes, cite Abstract #s]
- [If no direct EMD work: Note therapeutic area overlap or adjacent competitive space]

**RESEARCH SPECIALIZATION SUMMARY**:
- Primary focus: [Tumor types from abstracts]
- Treatment modalities: [IO/targeted therapy/ADC/chemotherapy combinations]
- Clinical settings: [1L/2L/maintenance/perioperative/biomarker-selected]
- Key biomarkers in their work: [PD-L1, FGFR, MET, HER2, etc. - from titles]

[Repeat for 5-8 Tier 1 KOLs total]

---

**SECTION 2: TIER 2 KOL STRATEGIC OPPORTUNITIES** (Next 5-7 KOLs)

Brief profiles focusing on emerging leaders or strategic targets:

**TIER 2: Dr. [NAME]** ([Institution], [Location]) - X abstracts

**WHY TIER 2**:
- Emerging thought leader (2-5 abstracts vs 10+ for Tier 1)
- [OR] Geographic partnership target (e.g., "Italy-based, strong regional influence")
- [OR] Presents some competitor data BUT also works in EMD therapeutic areas
- [OR] Cross-indication platform researcher (relevant for multiple EMD assets)

**ENGAGEMENT CONSIDERATION**: [Brief note on when/how to engage - lower priority than Tier 1]

[Repeat for 5-7 Tier 2 KOLs]

---

**SECTION 3: TIER 3 KOL MONITORING** (Remaining top 15 KOLs)

Brief summary of lower-priority KOLs:

**WHY TIER 3**:
- Heavy competitor focus with minimal EMD portfolio relevance
- Different therapeutic areas than EMD assets
- Already established strong competitor relationships (multiple competitor abstracts)

**ACTION**: Monitor their presentations for competitive intelligence, but deprioritize engagement

[List 2-4 Tier 3 examples with brief rationale]

---

**SECTION 4: COLLECTIVE KOL LANDSCAPE ANALYSIS** (Strategic context for leadership)

**Executive Summary** (2-3 paragraphs):
- **KOL Productivity Distribution**: How many researchers with 10+ abstracts vs 5-10 vs 2-4? (Pyramid analysis)
- **Therapeutic Area Concentration**: Which tumor types have deepest KOL bench? (e.g., "8 of 15 top KOLs focus on lung cancer")
- **Geographic Distribution**: Where are top KOLs concentrated? (US vs specific European countries vs APAC)
- **EMD Portfolio Alignment**: How many work in GU cancers (bladder/renal), NSCLC, CRC, or H&N? (Quantify overlap)

**Treatment Modality Trends**:
- What percentage of top KOLs work extensively with immunotherapy? ADCs? Targeted therapy?
- Which drug classes/mechanisms dominate their research? (IO+chemo, IO+ADC, biomarker-driven approaches)

**Institutional & Geographic Patterns**:
- Do multiple top KOLs come from same institution? (Institutional hubs - e.g., "3 KOLs from Memorial Sloan Kettering")
- Geographic clusters in EMD-relevant therapeutic areas? (Helps regional MSL planning)

**Platform KOLs** (Cross-indication researchers):
- Which KOLs work across multiple tumor types? (Important for platform drug discussions)
- Breadth vs depth: Single disease-focused experts vs multi-indication thought leaders

---

**SECTION 5: NOTABLE RESEARCH HIGHLIGHTS** (6-10 key presentations)

Select most important presentations from Tier 1/2 KOLs:
- **Dr. [NAME]** ([Institution]): (Abstract #X) - [Brief description of research based on title]
- [Prioritize: (1) EMD portfolio relevance, (2) High-impact KOLs from Tier 1, (3) Novel scientific directions]
- Always cite Abstract # (Identifier)

---

**SECTION 6: ENGAGEMENT STRATEGY SUMMARY**

**For MSL Field Teams**:
- **Immediate Priorities**: 5-8 Tier 1 KOL engagements (named above with when/where/what to discuss)
- **Geographic Focus**: [Which regions have highest concentration of EMD-relevant KOLs?]
- **Therapeutic Area Focus**: [Which disease areas should drive KOL engagement resources?]

**For Medical Affairs Leadership**:
- **Advisory Board Candidates**: [Which Tier 1 KOLs are strong candidates? Why?]
- **Investigator-Initiated Trial Opportunities**: [Which KOLs presenting data suggesting interest in specific research areas?]
- **Publication Collaboration**: [Which KOLs could co-author EMD-sponsored research or real-world evidence?]
- **Competitive Consideration**: [Which KOLs have heavy competitor ties but remain strategically important to engage?]

---

**WRITING REQUIREMENTS**:
- **Audience**: Hybrid - MSLs need Tier 1 tactical guidance (Section 1), Medical Directors need landscape analysis (Sections 4-6)
- **Tone**: Professional, fact-based medical affairs intelligence with actionable engagement strategies
- **Format**: Natural narrative prose (use bullets sparingly, mainly for section structure)
- **Citations**: Always cite Abstract # when referencing specific studies
- **Quantification**: Integrate data naturally (e.g., "Five of 15 top KOLs (33%) focus on GU cancers...")
- **Scope**: Use ONLY provided Top Authors table data - if unavailable, state "not available in dataset"
- **Engagement Guidance**: Provide tactical discussion topics and strategic objectives (NOT prescriptive scripts)
- **Vocabulary**: Professional medical terminology for oncology medical affairs audience

**OUTPUT STRUCTURE**: Tactical tier-prioritized engagement first (Sections 1-3), then strategic context (Sections 4-6).""",
        "required_tables": ["top_authors"]
    },
    "institution": {
        "button_label": "Academic Partnership Opportunities",
        "ai_prompt": """You are EMD Serono's medical affairs partnership strategist. Analyze leading research institutions at ESMO 2025 to identify strategic academic partnership opportunities, assess institutional capabilities for EMD collaboration, and prioritize institutions for medical affairs engagement.

**CRITICAL INSTRUCTIONS**:
1. **Partnership Focus**: This analysis is for Medical Directors planning collaborations - focus on institutional **accessibility and partnership potential**, not just research volume

2. **Anti-Hallucination Safeguards**:
   - ONLY use information from provided Top Institutions table - never invent institution names or Abstract #s
   - If data isn't available, write "not available in dataset" - do not speculate
   - When uncertain, omit rather than guess

3. **TGCT Clarification** (if applicable):
   - TGCT = Tenosynovial Giant Cell Tumor (PVNS), NOT testicular germ cell tumor
   - Pimicotinib is for tenosynovial/joint tumor indication

**TIER SYSTEM** (Use for partnership prioritization):
- **TIER 1**: High-priority partnership targets (EMD-relevant TAs + accessible + strong infrastructure)
- **TIER 2**: Strategic opportunities (emerging centers, geographic targets, adjacent TAs)
- **TIER 3**: Monitor only (heavy competitor ties, limited EMD relevance)

---

**SECTION 1: EXECUTIVE SUMMARY** (Partnership landscape overview)

Provide strategic overview for Medical Directors (2-3 paragraphs):
- **Institutional Concentration**: How many institutions in top tier? (e.g., "Top 5 account for X% of all abstracts")
- **Geographic Distribution**: Which regions dominate? (US vs Europe vs APAC)
- **EMD Therapeutic Area Alignment**: How many top institutions focus on GU cancers, NSCLC, CRC, or H&N? (Quantify overlap)
- **Partnership Landscape**: Balance of accessible institutions vs competitor-dominated centers

---

**SECTION 2: TIER 1 PARTNERSHIP TARGETS** (Top 5-8 high-priority institutions)

For each Tier 1 institution, provide partnership assessment:

**TIER 1: [INSTITUTION NAME]** ([City], [Country])
**Abstract Volume**: X presentations at ESMO 2025

**WHY TIER 1**:
- ✅ **EMD-Relevant Therapeutic Areas**: [e.g., "Strong GU oncology program - 12 bladder/renal abstracts"]
- ✅ **Research Infrastructure**: [e.g., "High phase 3 trial volume = experienced clinical trial operations"]
- ✅ **Geographic Fit**: [e.g., "US-based = easier regulatory/contracting for EMD trials"]
- ⚠️ **Competitor Activity**: [If applicable: Note competitor presence but explain why still accessible]

**PARTNERSHIP OPPORTUNITIES**:
- **Investigator-Initiated Trials**: [Based on research focus, which EMD drug fits? Avelumab/tepotinib/cetuximab?]
- **Real-World Evidence**: [Strong patient volume in which disease areas?]
- **Biomarker Research**: [Precision medicine capabilities? Companion diagnostic infrastructure?]
- **Advisory Board Potential**: [Multiple KOLs from this institution presenting?]

**RESEARCH SPECIALIZATION**:
- **Primary TAs**: [Tumor types dominating their abstracts]
- **Treatment Modalities**: [IO/ADC/targeted therapy/chemotherapy strengths]
- **Clinical Settings**: [1L/2L/maintenance/perioperative/biomarker-selected research]

**EMD PORTFOLIO ALIGNMENT**:
- Avelumab: [Yes/No - cite Abstract #s if applicable]
- Tepotinib: [Yes/No - cite Abstract #s if applicable]
- Cetuximab: [Yes/No - cite Abstract #s if applicable]
- [If no direct EMD work: Note therapeutic area overlap = engagement opportunity]

**PARTNERSHIP FEASIBILITY**:
- **ACCESS**: [High/Medium/Low based on competitor ties and TA overlap]
- **INFRASTRUCTURE**: [Clinical trial capabilities, biomarker programs, patient volume]
- **GEOGRAPHY**: [Regulatory ease, contracting simplicity, regional partnership value]

[Repeat for 5-8 Tier 1 institutions]

---

**SECTION 3: TIER 2 STRATEGIC PARTNERSHIP OPPORTUNITIES** (Next 5-7 institutions)

Brief profiles focusing on emerging centers or strategic targets:

**TIER 2: [INSTITUTION]** ([Location]) - X abstracts

**WHY TIER 2**:
- Emerging research center (growing abstract volume year-over-year)
- [OR] Geographic partnership target (e.g., "Italy-based = European regional hub opportunity")
- [OR] Adjacent therapeutic area focus (potential platform for EMD portfolio expansion)
- [OR] Specialized capabilities (e.g., "Strong biomarker program despite lower overall volume")

**PARTNERSHIP CONSIDERATION**: [When/how to engage - lower priority than Tier 1]

[Repeat for 5-7 Tier 2 institutions]

---

**SECTION 4: TIER 3 MONITORING** (Remaining top 15 institutions)

Brief summary of lower-priority institutions:

**WHY TIER 3**:
- Heavy competitor trial activity with limited EMD access
- Different therapeutic areas than EMD portfolio focus
- Geographic/regulatory complexity outweighs potential benefit

**ACTION**: Monitor their research output for competitive intelligence, but deprioritize partnership discussions

[List 2-4 Tier 3 examples with brief rationale]

---

**SECTION 5: INSTITUTIONAL LANDSCAPE ANALYSIS** (Strategic context)

**Therapeutic Area Specialization**:
- **GU Oncology Hubs**: [Top 3-5 institutions for bladder/renal research + abstract counts]
- **Lung Cancer Centers**: [Top 3-5 for NSCLC research]
- **GI Oncology Leaders**: [Top 3-5 for CRC research]
- **H&N Cancer Expertise**: [Top 3-5 for head & neck research]

**Research Modality Strengths**:
- **IO Research Hubs**: [Institutions with high checkpoint inhibitor/immunotherapy volume]
- **ADC Centers**: [Leading antibody-drug conjugate research institutions]
- **Precision Oncology Programs**: [Biomarker-driven therapy and companion diagnostic capabilities]

**Geographic Partnership Landscape**:
- **North America**: [Leading US institutions + Canadian centers]
- **Europe**: [Dominant countries and institutions by region]
- **Asia-Pacific**: [Active centers in China, Japan, Korea, Australia]

**Collaborative Networks**:
- **Multi-Center Trial Evidence**: [Institutions frequently co-presenting = consortium members]
- **Academic Consortia**: [Cooperative group involvement - ECOG, SWOG, etc.]
- **International Partnerships**: [Cross-border collaborations visible from data]

---

**SECTION 6: PARTNERSHIP STRATEGY RECOMMENDATIONS**

**For Medical Affairs Leadership**:

**Immediate Priorities** (Next 90 Days):
- **Tier 1 Institutional Outreach**: Initiate discussions with 3-5 high-priority centers (named above)
- **KOL Mapping**: Cross-reference Tier 1 institutions with KOL Analysis to identify key investigators
- **Partnership Proposals**: Develop investigator-initiated trial concepts for top institutions

**Strategic Considerations**:
- **Geographic Diversification**: Balance US-heavy portfolio with European/APAC partnerships?
- **Therapeutic Area Clustering**: Partner with GU oncology hubs for avelumab, NSCLC centers for tepotinib?
- **Infrastructure Assessment**: Which Tier 1 institutions have strongest clinical trial infrastructure?

**Partnership Models**:
- **Investigator-Initiated Trials**: [Which institutions best fit for EMD-sponsored research?]
- **Real-World Evidence Collaborations**: [High-volume centers for RWE data collection]
- **Biomarker Development**: [Precision medicine programs for companion diagnostic validation]
- **Advisory Boards**: [Institutions with multiple KOLs = institutional advisory board opportunity]

**Resource Allocation**:
- **High-Priority**: Tier 1 institutions with EMD-relevant TAs, accessible, strong infrastructure
- **Medium-Priority**: Tier 2 emerging centers or geographic expansion targets
- **Low-Priority**: Tier 3 competitor-dominated centers (monitor only)

**Success Metrics**:
- **Partnership Initiated**: X Tier 1 institutions engaged in discussions within 90 days
- **Trial Feasibility**: At least 1 investigator-initiated trial concept developed
- **Advisory Board Recruitment**: 2-3 KOLs from Tier 1 institutions recruited
- **RWE Collaboration**: 1-2 institutions committed to real-world data collection

---

**WRITING REQUIREMENTS**:
- **Audience**: Medical Directors and VP Medical Affairs planning institutional partnerships
- **Tone**: Strategic partnership assessment - balance opportunity with feasibility
- **Format**: Natural narrative prose (use bullets for structure)
- **Citations**: Always cite Abstract # when referencing institutional research
- **Quantification**: Integrate data (e.g., "Memorial Sloan Kettering: 23 abstracts, 8% of GU oncology studies")
- **Scope**: Use ONLY Top Institutions table data - if unavailable, state "not available in dataset"
- **Prioritization**: Focus on partnership accessibility and EMD portfolio fit, not just research volume
- **Feasibility**: Assess regulatory/geographic/infrastructure considerations

**OUTPUT STRUCTURE**: Tier-prioritized partnership targets first (actionable), then landscape context (strategic understanding).""",
        "required_tables": ["top_institutions"]
    },
    "insights": {
        "button_label": "Scientific Trends",
        "ai_prompt": """You are EMD Serono's senior medical affairs scientific intelligence analyst. Conduct comprehensive trend analysis of ESMO 2025 to identify emerging scientific themes, biomarker developments, and evolving treatment paradigms that could impact EMD's oncology strategy.

**CRITICAL INSTRUCTIONS**:
1. **Anti-Hallucination Safeguards**:
   - ONLY discuss biomarkers/topics that appear in the provided biomarker/MOA table
   - Skip/omit topics with no data entirely - DO NOT mention "not found" or "not available"
   - Focus analysis on what IS present, not what's absent
   - If a section has no relevant data, skip that section completely
   - Always cite Abstract # when referencing specific studies

2. **TGCT Clarification** (if applicable):
   - TGCT = Tenosynovial Giant Cell Tumor (PVNS), NOT testicular germ cell tumor
   - Pimicotinib is for tenosynovial/joint tumor indication
   - If TGCT data appears, verify it's joint/synovial tumor context

---

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
- **CRITICAL**: Only discuss biomarkers/topics that appear in the provided table. Skip/omit topics with no data entirely - DO NOT mention "not found", "not available", "not present", or "not in dataset"
- Focus your analysis on what IS present, not what's absent
- If a section has no relevant data, skip that section completely
- Maintain scientific rigor and precision
- Descriptive analysis - avoid prescriptive clinical recommendations
- Professional vocabulary for Medical Director/VP Medical Affairs audience

**OUTPUT STRUCTURE**:
Clear section headers with analytical paragraphs. This should read as a comprehensive scientific intelligence briefing for strategic planning and portfolio positioning.""",
        "required_tables": ["biomarker_moa_hits"]
    },
    "strategy": {
        "button_label": "Strategic Recommendations",
        "ai_prompt": """You are EMD Serono's medical affairs strategic intelligence analyst. Provide indication-specific, actionable strategic analysis for ESMO 2025 with tactical 90-day priorities for field teams and leadership.

**CRITICAL INSTRUCTIONS**:
1. **Therapeutic Area Strategy with Indication-Specific EMD Focus**:
   - You are analyzing the ENTIRE therapeutic area (e.g., all Lung Cancer if "Lung Cancer" filter selected)
   - Provide strategic recommendations across the full TA landscape
   - **HOWEVER**: When providing EMD-specific tactical priorities, be indication-focused:
     * Avelumab: **1L locally advanced/metastatic urothelial carcinoma (la/mUC), maintenance therapy post-platinum** (not all bladder settings)
     * Tepotinib: **1L metastatic NSCLC (mNSCLC) with MET exon 14 skipping mutations (METx14)** (not all NSCLC)
     * Cetuximab (H&N): **1L locally advanced/metastatic head & neck squamous cell carcinoma (la/mHNSCC)**
     * Cetuximab (CRC): **1L metastatic colorectal cancer (mCRC), RAS wild-type**
   - Example: If analyzing Bladder Cancer TA, discuss TA-wide trends but tactical KOL targets and key messages should focus on avelumab's 1L maintenance positioning specifically

2. **Anti-Hallucination Safeguards**:
   - ONLY use information from provided data tables - never invent Abstract #s, KOL names, or clinical details
   - If data isn't available, write "not available in dataset" - do not speculate
   - Focus on what abstract titles CAN show (research patterns, white space) not clinical nuances requiring full abstracts
   - When uncertain, omit rather than guess

3. **TGCT Clarification** (if applicable):
   - TGCT = Tenosynovial Giant Cell Tumor (PVNS), NOT testicular germ cell tumor
   - Pimicotinib is for tenosynovial/joint tumor indication

---

**SECTION 1: EXECUTIVE SUMMARY** (Strategic imperatives for leadership)

Provide 3-5 strategic imperatives for this specific indication (2-3 paragraphs):
- **Most Critical Competitive Threat**: Which competitor development requires immediate EMD response? (Cite Abstract #s)
- **Most Promising White Space Opportunity**: Where can EMD differentiate or expand positioning?
- **Recommended 90-Day Focus**: What should medical affairs prioritize in next quarter based on ESMO intelligence?
- **Resource Allocation Guidance**: Where to invest - KOL engagement vs clinical development vs market access vs medical communications?

---

**SECTION 2: CURRENT COMPETITIVE POSITION ASSESSMENT** (Based on title analysis)

**Treatment Paradigm Context**:
- Where does EMD drug sit in treatment landscape? (Evidence from abstract volume: X abstracts on 1L vs Y on 2L vs Z on maintenance)
- Market positioning: Leader/challenger/niche in this indication? (Proxy: EMD abstract volume vs top competitors)
- Key differentiators: What makes EMD approach unique? (MOA, biomarker, patient population, treatment setting)

**Competitive Landscape Quantification**:
- Total competitor abstracts in filtered dataset: [X studies across Y drugs]
- Top 3 direct competitors: [Drug names + abstract counts + MOA class]
- Treatment paradigm distribution: Upfront combinations (X%) vs maintenance (Y%) vs sequencing (Z%)

**Utilization Context** (from research patterns):
- Research gaps visible in titles suggest: [e.g., "Low maintenance therapy activity = continued unmet need supporting avelumab positioning"]
- Biomarker selection trends: [e.g., "Increasing PD-L1 enrichment studies = precision medicine shift"]

---

**SECTION 3: COMPETITIVE THREATS** (From conference data)

For top 3-5 direct competitive threats, provide:

**THREAT 1: [Competitor Drug]** ([Company], [MOA from table])
- **Conference Presence**: X abstracts at ESMO 2025
- **Clinical Settings**: [1L/2L/maintenance/combination - from titles]
- **EMD Impact**: How does this threaten [EMD drug] positioning in [specific indication/line]?
- **Response Strategy**: [Brief guidance - e.g., "Emphasize avelumab's maintenance paradigm vs EV+P upfront combination - different patient populations"]
- **Evidence**: (Abstract #s)

[Repeat for 2-4 additional major threats]

**Emerging Competitive Patterns**:
- Indication expansion strategies: Competitors moving into adjacent tumor types or earlier disease stages?
- Combination development: Which regimen backbones threaten EMD monotherapy or current combinations?
- Biomarker-driven positioning: Competitors fragmenting patient populations with companion diagnostics?

---

**SECTION 4: WHITE SPACE & STRATEGIC OPPORTUNITIES**

Based on what competitors are NOT doing (research gaps visible from title analysis):

**Underserved Patient Populations**:
- Which biomarker groups lack competitive research? (e.g., "PD-L1 low bladder cancer - only 2 abstracts")
- Age ranges or performance status: Elderly patients? ECOG 2+ populations?
- Clinical settings: Treatment lines or settings with low competitor activity?

**Treatment Setting Gaps**:
- [Example: "Maintenance therapy gap - if most competitors focus on upfront combos, maintenance remains underserved"]
- Sequencing strategies: Optimal treatment sequences understudied?
- Consolidation approaches: Post-therapy continuation strategies missing?

**Combination Opportunities**:
- Which synergistic regimens are unexplored? (e.g., "IO+ADC in maintenance = zero abstracts, potential EMD opportunity")
- Biomarker-defined combinations: Precision medicine opportunities?

**For Each Opportunity**:
- Rationale: Why does this matter for EMD?
- EMD Asset Fit: Which drug (avelumab/tepotinib/cetuximab) fits this opportunity?
- Feasibility: Quick win vs long-term investment?

---

**SECTION 5: TACTICAL PRIORITIES - NEXT 90 DAYS**

**MSL FIELD PRIORITIES** (Tier 1 KOL Targets):

Identify 3-5 specific KOLs from conference data for priority engagement:

1. **Dr. [NAME from Top Authors]** ([Institution], [Location]) - [X abstracts]
   - **Why Priority**: [Presents EMD-relevant data/therapeutic area + high influence]
   - **Engagement Objective**: [e.g., "Assess interest in investigator-initiated RWE study on avelumab maintenance"]
   - **When/Where**: [Presenting on Date/Time if available - cite Abstract #]
   - **Discussion Topics**: [Based on their research focus from titles]

[Repeat for 2-4 additional Tier 1 KOLs]

**MEDICAL COMMUNICATIONS PRIORITIES** (Key messages for field teams):

**Key Message 1** - [EMD Differentiation Message]:
- **Message**: "[2-3 sentence positioning statement based on competitive intelligence]"
- **Supporting Evidence**: (Abstract #s from EMD research or ESMO data)
- **Target Audience**: [Oncologists/urologists/medical oncologists treating this indication]
- **Channel**: [Congress materials/post-congress webinar/publications]

**Key Message 2** - [Counter-Competitive Positioning]:
- **Competitor Claim**: "[What competitor will likely position based on ESMO data]"
- **EMD Response**: "[How EMD approach differs/complements - not dismissive, fact-based]"
- **Evidence**: (Abstract #s)

**Key Message 3** - [White Space Opportunity Message]:
- **Message**: "[Unmet need EMD addresses that competitors don't]"
- **Evidence**: (Abstract #s showing competitor gaps)

**CLINICAL DEVELOPMENT CONSIDERATIONS** (Directional recommendations):

**Trial Concept 1** - [Specific gap from conference intelligence]:
- **Rationale**: [Based on white space analysis + Abstract #s showing need]
- **Proposed Approach**: [Patient population + EMD drug + design sketch]
- **Potential Investigators**: [KOLs from Top Authors presenting relevant research]
- **Timeline**: [Directional - e.g., "6-month feasibility assessment" not detailed Gantt chart]

**Biomarker Strategy**:
- **Trend from Conference**: [e.g., "25 abstracts on ctDNA = growing momentum"]
- **EMD Application**: [e.g., "Develop ctDNA clearance endpoint for avelumab maintenance trials"]
- **Partnership**: [Companion diagnostic company or academic biomarker program]

**MARKET ACCESS CONSIDERATIONS**:
- **Anticipated Payer Questions**: [Based on competitor data, what will payers ask?]
- **Value Dossier Updates**: [Which sections need revision based on competitive developments?]
- **Real-World Evidence Gaps**: [What RWE should EMD generate to address payer concerns?]

---

**SECTION 6: ACCOUNTABILITY & NEXT STEPS**

**30-Day Deliverables** (Post-congress immediate actions):
- MSL field outreach to Tier 1 KOLs (names provided above)
- Medical communications: Finalize 3 key messages for field distribution
- Competitive intelligence: Full briefing to leadership on HIGH ALERT threats

**60-Day Deliverables**:
- Advisory board planning: Recruit 2-3 KOLs from Tier 1 list
- Clinical development: Feasibility assessment for Trial Concept 1
- Market access: Value dossier update incorporating ESMO competitive data

**90-Day Deliverables**:
- KOL engagement program: Launch investigator-initiated study discussions
- Publications: Identify RWE publication opportunities with engaged KOLs
- Strategic planning: Use ESMO intelligence for annual medical affairs plan

**Success Metrics**:
- KOL engagement: X Tier 1 KOLs met and assessed for partnership
- Field team enablement: MSLs equipped with 3 key messages, using in HCP conversations
- Competitive response: Leadership briefed on threats, mitigation strategies in place

**Note**: These are directional recommendations based on conference intelligence, not fully resourced project plans. Prioritization should account for budget, team capacity, and corporate strategy.

---

**WRITING REQUIREMENTS**:
- **Audience**: Hybrid - Medical Directors need strategic context (Sections 1-4), MSLs/Medical Communications/Clinical Dev need tactical priorities (Section 5)
- **Tone**: Actionable strategic intelligence - balance analysis with specific next steps
- **Format**: Natural narrative prose (use bullets for structure, not analysis itself)
- **Citations**: Always cite Abstract # when referencing studies
- **Scope**: Focus on what titles CAN show (research patterns, abstract volume, white space) - avoid speculation on clinical details
- **Specificity**: Name specific KOLs from Top Authors data, cite specific Abstract #s, provide concrete recommendations
- **Feasibility**: Acknowledge these are directional recommendations requiring leadership approval and resource allocation

**OUTPUT STRUCTURE**: Strategic context first (understand the landscape), then tactical 90-day priorities (what to do about it).""",
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
    acronyms = ["NSCLC", "MET", "ALK", "EGFR", "KRAS", "BRAF", "RET", "ROS1", "NTRK"]  # All with word boundaries

    mask = pd.Series([False] * len(df), index=df.index)

    for keyword in keywords:
        title_mask = df["Title"].str.contains(keyword, case=False, na=False, regex=False)
        theme_mask = df["Theme"].str.contains(keyword, case=False, na=False, regex=False)
        mask = mask | title_mask | theme_mask

    for acronym in acronyms:
        # Use word boundaries and case-sensitivity for acronyms to prevent false matches
        pattern = r'\b' + re.escape(acronym) + r'\b'
        title_mask = df["Title"].str.contains(pattern, case=True, na=False, regex=True)
        theme_mask = df["Theme"].str.contains(pattern, case=True, na=False, regex=True)
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

def apply_ddri_filter(df: pd.DataFrame) -> pd.Series:
    """Apply DNA Damage Response Inhibitor filter with strict word boundaries."""
    # Strict patterns with word boundaries to avoid false matches
    patterns = [
        r'\bATR\b',      # ATR (not "atrocious")
        r'\bATRi\b',     # ATR inhibitor
        r'\bATM\b',      # ATM (not "atmosphere")
        r'\bATMi\b',     # ATM inhibitor
        r'\bPARP\b',     # PARP
        r'\bPARPi\b'     # PARP inhibitor
    ]

    # Long-form phrase (must match full phrase)
    phrases = ["DNA Damage Response", "DNA damage response"]

    mask = pd.Series([False] * len(df), index=df.index)

    # Search patterns with word boundaries (case-sensitive for acronyms)
    for pattern in patterns:
        title_mask = df["Title"].str.contains(pattern, case=True, na=False, regex=True)
        theme_mask = df["Theme"].str.contains(pattern, case=True, na=False, regex=True)
        mask = mask | title_mask | theme_mask

    # Search phrases (case-insensitive)
    for phrase in phrases:
        title_mask = df["Title"].str.contains(phrase, case=False, na=False, regex=False)
        theme_mask = df["Theme"].str.contains(phrase, case=False, na=False, regex=False)
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
    elif ta_filter == "DNA Damage Response (DDRi)":
        return apply_ddri_filter(df)
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

    # If no filters selected, return all data (chat will use semantic search to find relevant subset)
    if not drug_filters and not ta_filters and not session_filters and not date_filters:
        return df_global

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

**4. DRUG CLASS/MOA QUERIES** (drug_class_ranking table)
"What is the most common drug class?" | "Show me drug classes" | "ADC vs ICI representation" | "Top MOA classes" | "What mechanisms are being studied?"
→ {{"entity_type": "drug_class", "search_terms": [], "generate_table": true, "table_type": "drug_class_ranking", "filter_context": {{}}, "top_n": 15}}

**5. INSTITUTION QUERIES** (institution_ranking table)
"Most active institutions" | "Top 15 hospitals" | "Leading research centers" | "Where is the research coming from?" | "Academic centers in bladder cancer"
→ {{"entity_type": "institution", "search_terms": [], "generate_table": true, "table_type": "institution_ranking", "filter_context": {{}}, "top_n": 15}}

**6. SESSION/SCHEDULE QUERIES** (session_list table)
"What posters are on day 3?" | "All presentations on Friday" | "Proffered papers in lung cancer" | "When are the oral sessions?" | "Show me symposia"
→ {{"entity_type": "session_type", "search_terms": ["poster"], "generate_table": true, "table_type": "session_list", "filter_context": {{"date": "Day 3"}}, "top_n": 50}}

**7. TREND/ANALYSIS QUERIES** (no table, just AI analysis)
"What are the latest trends?" | "Summarize immunotherapy data" | "Key takeaways" | "Emerging biomarkers" | "What's new in checkpoint inhibitors?"
→ {{"entity_type": "general", "search_terms": ["immunotherapy", "checkpoint"], "generate_table": false, "table_type": null, "filter_context": {{}}, "top_n": 15}}

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

        mask = pd.Series([False] * len(filtered_df))
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
{results.to_html(index=False, classes='table table-sm table-striped', escape=False)}
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
{ranking_df.to_html(index=False, classes='table table-sm table-striped', escape=False)}
</div>"""
        return table_html, ranking_df

    elif table_type == "drug_studies":
        # Search for drug in Title column
        if not search_terms:
            return "", pd.DataFrame()

        print(f"[DRUG SEARCH] Searching for: {search_terms} in {len(filtered_df)} records")

        # Load drug database to get MOA info
        try:
            drug_db_path = Path(__file__).parent / "Drug_Company_names.csv"
            drug_db = pd.read_csv(drug_db_path, encoding='utf-8-sig')
        except Exception as e:
            print(f"[DRUG SEARCH] Could not load Drug_Company_names.csv: {e}")
            drug_db = None

        mask = pd.Series([False] * len(filtered_df))
        for term in search_terms:
            # Use word boundaries for short acronyms (3 chars or less) to avoid false matches
            # Example: "BDC" should not match "BDC-4182"
            if len(term) <= 3 and term.isupper():
                # For short uppercase acronyms, use word boundaries
                # Also handle plural forms (e.g., "ADC" matches both "ADC" and "ADCs")
                pattern = r'\b' + re.escape(term) + r's?\b'
                term_mask = filtered_df['Title'].str.contains(pattern, case=True, na=False, regex=True)
            elif len(term) == 4 and term.endswith('s') and term[:3].isupper():
                # Handle plural acronyms like "ADCs" -> search for "ADC" or "ADCs"
                singular = term[:-1]  # Remove 's'
                pattern = r'\b' + re.escape(singular) + r's?\b'
                term_mask = filtered_df['Title'].str.contains(pattern, case=True, na=False, regex=True)
            else:
                # For longer terms or mixed case, use regular case-insensitive search
                term_mask = filtered_df['Title'].str.contains(term, case=False, na=False)
            matches = term_mask.sum()
            print(f"[DRUG SEARCH] Term '{term}' found {matches} matches")
            mask |= term_mask

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

    elif table_type == "drug_class_ranking":
        # Generate MOA class ranking from drug database
        print(f"[DRUG CLASS RANKING] Analyzing {len(filtered_df)} studies")

        try:
            drug_db_path = Path(__file__).parent / "Drug_Company_names.csv"
            drug_db = pd.read_csv(drug_db_path, encoding='utf-8-sig')
        except Exception as e:
            print(f"[DRUG CLASS RANKING] Could not load Drug_Company_names.csv: {e}")
            return "", pd.DataFrame()

        # Count MOA classes by matching drugs in titles
        moa_counts = {}
        for idx, row in filtered_df.iterrows():
            title = str(row['Title']).lower()
            # Check each drug in database
            for _, drug_row in drug_db.iterrows():
                commercial = str(drug_row['drug_commercial']).lower() if pd.notna(drug_row['drug_commercial']) else ""
                generic = str(drug_row['drug_generic']).lower() if pd.notna(drug_row['drug_generic']) else ""
                moa_class = str(drug_row['moa_class']) if pd.notna(drug_row['moa_class']) else "Unknown"

                if moa_class == "Unknown":
                    continue

                # Check if drug is in title
                if (commercial and commercial in title) or (generic and generic in title):
                    moa_counts[moa_class] = moa_counts.get(moa_class, 0) + 1

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

def generate_competitor_table(df: pd.DataFrame, indication_keywords: list = None, focus_moa_classes: list = None, n: int = 200) -> pd.DataFrame:
    """
    Generate competitor drugs table using CSV with MOA/target data.

    Args:
        df: Dataframe to search
        indication_keywords: Keywords to filter by indication (e.g., ["bladder", "urothelial"])
        focus_moa_classes: MOA classes to focus on (e.g., ["ICI", "ADC", "Targeted Therapy"])
        n: Max results
    """
    if df.empty:
        return pd.DataFrame()

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

    results = []
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

        # Filter by indication keywords if specified
        if indication_keywords and mask.any():
            indication_mask = pd.Series([False] * len(df), index=df.index)
            for keyword in indication_keywords:
                indication_mask = indication_mask | df['Title'].str.contains(keyword, case=False, na=False, regex=False)
            mask = mask & indication_mask

        matching_abstracts = df[mask]

        if len(matching_abstracts) == 0:
            continue

        drug_display_name = generic if generic else commercial

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

def generate_emerging_threats_table(df: pd.DataFrame, indication_keywords: list, n: int = 20) -> pd.DataFrame:
    """
    Identify emerging threats: drugs with 3-5 abstracts showing novel MOAs or combinations.

    Args:
        df: Dataframe to search
        indication_keywords: Keywords to filter by indication (e.g., ["bladder", "urothelial"])
        n: Max results to return
    """
    if df.empty:
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
                # For competitor button, use CSV-driven MOA-aware competitor detection
                if playbook_key == "competitor":
                    # IMPORTANT: For competitor intelligence, search FULL dataset (not filtered)
                    print(f"[PLAYBOOK] Generating CSV-driven competitor table from FULL dataset ({len(df_global)} studies)")

                    # Define indication keywords and MOA classes based on drug focus
                    indication_keywords = []
                    focus_moa_classes = None

                    if drug_filters and drug_filters[0] == "Avelumab Focus":
                        indication_keywords = ["bladder", "urothelial", "uroepithelial"]
                        focus_moa_classes = ["ICI", "ADC", "Targeted Therapy", "Bispecific Antibody"]
                    elif drug_filters and drug_filters[0] == "Tepotinib Focus":
                        indication_keywords = ["lung", "NSCLC", "MET"]
                        focus_moa_classes = ["TKI", "ADC", "ICI", "Targeted Therapy"]
                    elif drug_filters and drug_filters[0] == "Cetuximab CRC":
                        indication_keywords = ["colorectal", "CRC", "colon", "rectal"]
                        focus_moa_classes = ["Targeted Therapy", "ICI", "ADC", "Bispecific Antibody"]
                    elif drug_filters and drug_filters[0] == "Cetuximab H&N":
                        indication_keywords = ["head and neck", "head & neck", "H&N", "HNSCC", "SCCHN", "oral", "pharyngeal", "laryngeal"]
                        focus_moa_classes = ["Targeted Therapy", "ICI", "ADC", "Bispecific Antibody"]

                    # Generate competitor table with MOA filtering
                    competitor_table = generate_competitor_table(
                        df_global,
                        indication_keywords=indication_keywords,
                        focus_moa_classes=focus_moa_classes,
                        n=200
                    )

                    print(f"[PLAYBOOK] CSV approach found {len(competitor_table)} competitor studies")
                    tables_data["competitor_abstracts"] = competitor_table.to_markdown(index=False) if not competitor_table.empty else "No competitor drugs found"

                    if not competitor_table.empty:
                        # Table 1: Drug/MOA Ranking Summary
                        ranking_table = generate_drug_moa_ranking(competitor_table, n=15)
                        if not ranking_table.empty:
                            print(f"[PLAYBOOK] Sending drug ranking table with {len(ranking_table)} drugs")
                            yield "data: " + json.dumps({
                                "title": f"Competitor Drug Ranking ({len(ranking_table)} drugs)",
                                "subtitle": "Summary of # studies per drug and MOA class",
                                "columns": list(ranking_table.columns),
                                "rows": sanitize_data_structure(ranking_table.to_dict('records'))
                            }) + "\n\n"
                            tables_data["drug_ranking"] = ranking_table.to_markdown(index=False)

                        # Table 2: Full competitor studies list
                        print(f"[PLAYBOOK] Sending competitor table with {len(competitor_table)} studies")
                        yield "data: " + json.dumps({
                            "title": f"Competitor Studies ({len(competitor_table)} abstracts)",
                            "subtitle": "Filtered by indication keywords and MOA classes from Drug_Company_names.csv",
                            "columns": list(competitor_table.columns),
                            "rows": sanitize_data_structure(competitor_table.to_dict('records'))
                        }) + "\n\n"

                    # Table 3: Generate emerging threats table (drugs with 3-5 studies)
                    if indication_keywords:
                        print(f"[PLAYBOOK] Generating emerging threats table...")
                        emerging_table = generate_emerging_threats_table(df_global, indication_keywords, n=15)
                        if not emerging_table.empty:
                            print(f"[PLAYBOOK] Found {len(emerging_table)} emerging threats")
                            tables_data["emerging_threats"] = emerging_table.to_markdown(index=False)
                            yield "data: " + json.dumps({
                                "title": f"Emerging Threats ({len(emerging_table)} drugs with 3-5 studies each)",
                                "subtitle": "Novel or early-stage drugs showing limited but emerging presence",
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
                        "Cetuximab CRC": {
                            "indication": "Metastatic Colorectal Cancer (EGFR+, RAS wild-type)",
                            "key_competitors": ["panitumumab", "bevacizumab", "pembrolizumab", "nivolumab", "regorafenib", "trifluridine/tipiracil", "fruquintinib", "encorafenib+cetuximab"],
                            "therapeutic_area": "Metastatic Colorectal Cancer"
                        },
                        "Cetuximab H&N": {
                            "indication": "Locally Advanced or Metastatic Head & Neck Cancer (EGFR+)",
                            "key_competitors": ["pembrolizumab", "nivolumab", "durvalumab", "panitumumab", "toripalimab"],
                            "therapeutic_area": "Head & Neck Squamous Cell Carcinoma"
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
            # 1. Classify user query to detect entity types and table needs (with conversation context)
            classification = classify_user_query(user_query, conversation_history)
            print(f"[QUERY CLASSIFICATION] {classification}")

            # 1.5. Handle clarification requests (vague queries)
            if classification.get('entity_type') == 'clarification_needed':
                clarification_text = classification.get('clarification_question',
                    "Could you please be more specific? For example, you could ask about:\n\n" +
                    "• Specific researchers (e.g., 'Who is Andrea Necchi?')\n" +
                    "• Drugs or therapies (e.g., 'Tell me about enfortumab vedotin')\n" +
                    "• Top rankings (e.g., 'Most active institutions')\n" +
                    "• Trends or analyses (e.g., 'Latest immunotherapy trends')")

                yield "data: " + json.dumps({"text": clarification_text}) + "\n\n"
                yield "data: [DONE]\n\n"
                return

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

            prompt = f"""You are an AI assistant for COSMIC, the Conference Intelligence App for EMD Serono medical affairs. You help analyze ESMO 2025 conference abstracts.

**YOUR ROLE**:
- Respond naturally and conversationally to user queries
- For greetings like "Hi" or "Hello", be friendly and briefly introduce your capabilities
- For data questions, provide insights based on the conference abstracts
- You have access to {len(filtered_df)} conference studies in the current scope

**USER QUESTION**: {user_query}

{scope_description}

**DATA SOURCE**: {data_source}
{history_context}{table_context}

**SAMPLE CONFERENCE DATA** (showing {len(relevant_data)} most relevant of {len(filtered_df)} total studies):
{data_context}

**INSTRUCTIONS**:
- Respond naturally to the user's question (whether greeting, casual query, or data request)
- When analyzing conference data, mention the scope size: "Looking at {len(filtered_df)} studies in [scope]..."
- Always cite Abstract # (Identifier) when referencing specific studies
- If data doesn't answer the question, acknowledge this and suggest alternatives
- Consider EMD Serono's portfolio context: avelumab (bladder), tepotinib (NSCLC MET+), cetuximab (CRC/H&N), pimicotinib (TGCT)
- Be conversational, helpful, and concise

Please respond naturally to the user."""

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
