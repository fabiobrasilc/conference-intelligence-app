# app.py (Consolidated, Advanced, and Corrected Version)

from flask import Flask, render_template, request, jsonify, Response
import pandas as pd
import chromadb  # Vector DB
from chromadb.utils import embedding_functions
from openai import OpenAI
from pathlib import Path
import re
import json
from typing import List, Tuple, Dict, Any, Optional
from collections import Counter
from datetime import datetime
from dataclasses import dataclass
import os
import time
from dotenv import load_dotenv
import hashlib  # <-- Added (used by file_md5 / df_sig)

# --- Heartbeat wrapper for SSE streaming ---
def stream_with_heartbeat(inner_gen, interval=10):
    """
    Wrap an iterator (SSE token generator) and ensure we emit a ping
    at least every `interval` seconds so the connection never goes idle.
    """
    last = time.monotonic()

    for chunk in inner_gen:
        yield chunk
        last = time.monotonic()

        # Non-blocking: while there are long gaps before the next chunk, drip pings
        now = time.monotonic()
        if now - last >= interval:
            yield f": ping {int(now)}\n\n"
            last = now

    # one last ping for good measure
    yield f": ping {int(time.monotonic())}\n\n"

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",       # ignored if not applicable, safe to send
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Cache-Control",
}

# --- Initialization ---
load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_strong_fallback_secret_key_change_me")

from pathlib import Path
CSV_FILE = Path(__file__).parent / "ASCO GU 2025 Poster Author Affiliations info.csv"

CHROMA_DB_PATH = "./chroma_conference_db"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Configure OpenAI client with controlled connection pooling for Railway deployment
if OPENAI_API_KEY:
    import httpx

    # Create custom httpx client with controlled connection pooling
    custom_http_client = httpx.Client(
        timeout=httpx.Timeout(300.0, connect=30.0),  # 5-minute timeout, 30s connect
        limits=httpx.Limits(
            max_connections=3,          # Reduced from default 100
            max_keepalive_connections=1  # Reduced from default 20
        ),
        transport=httpx.HTTPTransport(retries=2)
    )

    client = OpenAI(
        api_key=OPENAI_API_KEY,
        timeout=60.0,   # More realistic timeout per request
        max_retries=2,
        http_client=custom_http_client
    )
else:
    client = None

# --- Global variables ---
chroma_client = None
collection = None
csv_hash_global = None
df_global = None
bladder_keywords_global = None
renal_keywords_global = None

# =========================
# Global Helpers
# =========================
def file_md5(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def df_sig(df: pd.DataFrame) -> str:
    return hashlib.md5(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()[:8]

def table_for_prompt(df: pd.DataFrame, max_rows: int = 30, cols: Optional[List[str]] = None) -> str:
    """Return a compact CSV string (<= max_rows) for inclusion in prompts."""
    if df is None or len(df) == 0:
        return "No rows."
    slim = df
    if cols:
        keep = [c for c in cols if c in slim.columns]
        if keep:
            slim = slim.loc[:, keep]
    return slim.head(max_rows).to_csv(index=False)

def safe_contains(series: pd.Series, pattern: str, regex: bool = True) -> pd.Series:
    return series.fillna("").str.contains(pattern, case=False, na=False, regex=regex)

def clean_filename(s: str) -> str:
    return s.lower().replace(' ', '_').replace('/', '_').replace('\\', '_')

def extract_number_default(q: str, default_n: int = 20) -> int:
    nums = re.findall(r"\b(\d{1,3})\b", q)
    if not nums:
        return default_n
    try:
        n = int(nums[0])
        return max(1, min(200, n))
    except Exception:
        return default_n

def normalize_txt(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()

# =========================
# Load / Prepare Data
# =========================
def load_and_prepare_data():
    data_path = Path(CSV_FILE)
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {CSV_FILE}")

    df = pd.read_csv(data_path, encoding="utf-8-sig").fillna("")

    # TA tagging (title-based)
    bladder_keywords = ["bladder", "urothelial", r"\buc\b", r"\bmuc\b"]
    renal_keywords = [
        "renal", "kidney", "rcc", "ccrcc", "nccrcc", "prcc", "chrcc",
        "renal cell", "clear cell", "papillary", "chromophobe"
    ]
    is_bladder = safe_contains(df["Title"], "|".join(bladder_keywords), regex=True)
    is_renal   = safe_contains(df["Title"], "|".join(renal_keywords), regex=True)
    df["ta"] = "other"
    df.loc[is_bladder, "ta"] = "bladder"
    df.loc[is_renal,   "ta"] = "renal"

    # Combined text for embeddings
    df["combined_text"] = (
        "Title: " + df["Title"].astype(str)
        + " | Authors: " + df["Authors"].astype(str)
        + " | Institutions: " + df["Institutions"].astype(str)
        + " | Abstract #: " + df["Abstract #"].astype(str)
        + " | Poster #: " + df["Poster #"].astype(str)
    )

    # Normalize delimiters
    for col in ["Authors", "Institutions"]:
        df[col] = df[col].astype(str).str.replace(r"\s*[,/]\s*", "; ", regex=True)

    return df, bladder_keywords, renal_keywords, file_md5(data_path)

# =========================
# Vector DB
# =========================
def setup_vector_db(csv_hash: str):
    global collection
    if client is None:
        print("Warning: OpenAI client not initialized. Cannot set up vector DB.")
        return None

    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    openai_ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY,
        model_name="text-embedding-3-small",
    )
    collection_name = f"conference_abstracts_{csv_hash[:8]}"

    try:
        collection = chroma_client.get_collection(name=collection_name, embedding_function=openai_ef)
        print(f"Chroma collection '{collection_name}' loaded.")
        return collection
    except Exception:
        print(f"Collection '{collection_name}' not found, creating and populating...")
        # Garbage-collect older collections quietly
        try:
            for old_collection in chroma_client.list_collections():
                if old_collection.name.startswith("conference_abstracts_"):
                    print(f"Deleting old collection: {old_collection.name}")
                    chroma_client.delete_collection(name=old_collection.name)
        except Exception as e:
            print(f"Error cleaning old collections: {e}")

        collection = chroma_client.create_collection(name=collection_name, embedding_function=openai_ef)
        df, _, _, _ = load_and_prepare_data()
        texts = df["combined_text"].tolist()

        ids, seen = [], set()
        for i, (a, p) in enumerate(zip(df["Abstract #"].astype(str), df["Poster #"].astype(str))):
            base = f"{a}_{p}".strip("_")
            if base in seen or base == "":
                base = f"{a}_{p}_row_{i}"  # Fallback for duplicate/empty identifiers
            ids.append(f"abstract_{base}")
            seen.add(base)

        metadatas = df[["Abstract #", "Title", "Authors", "Institutions", "Poster #", "ta"]].to_dict("records")

        batch_size = 300
        print(f"Adding {len(texts)} documents to ChromaDB...")
        for i in range(0, len(texts), batch_size):
            collection.add(
                documents=texts[i:i + batch_size],
                ids=ids[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
            )
        print("ChromaDB population complete.")
        return collection

def semantic_search(query: str, ta_filter: str, n_results: int = 10):
    """Uses the global `collection`."""
    if collection is None:
        print("Error: Vector database not initialized for semantic search.")
        return {"error": "Vector database not initialized."}

    where = {}
    if ta_filter == "Bladder Cancer":
        where = {"ta": "bladder"}
    elif ta_filter == "Renal Cell Carcinoma":
        where = {"ta": "renal"}

    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where if where else None,
            include=["documents", "metadatas", "distances"],
        )
        return results
    except Exception as e:
        print(f"Error during semantic search: {e}")
        return {"error": f"Search failed: {str(e)}"}

def format_search_results(results) -> pd.DataFrame:
    if not results or "metadatas" not in results or not results["metadatas"] or not results["metadatas"][0]:
        return pd.DataFrame()
    rows = []
    for i, md in enumerate(results["metadatas"][0]):
        rows.append({
            "Abstract #": md.get("Abstract #", ""),
            "Poster #": md.get("Poster #", ""),
            "Title": md.get("Title", ""),
            "Authors": md.get("Authors", ""),
            "Institutions": md.get("Institutions", ""),
            "Relevance Score": f"{1 - results['distances'][0][i]:.3f}",
        })
    return pd.DataFrame(rows)

# =========================
# Playbooks Spec
# =========================
PLAYBOOKS: Dict[str, Dict[str, Any]] = {
    "competitor": {
        "button_label": "🏆 Competitor Intelligence",
        "subtitle": "Conference Landscape",
        "sections": [
            "Executive Summary",
            "Current Landscape & Standard of Care (TA Scoped)",
            "Avelumab Presence at This Conference",
            "Conference Activity by Competitor",
            "Notable Signals & Examples (by Line/Setting)"
        ],
        "required_tables": ["competitor_abstracts", "emerging_threats"],
        "buckets": {
            "competitors": [
                "enfortumab vedotin", "disitamab vedotin", "zelenectide pevedotin",
                "pembrolizumab", "nivolumab", "atezolizumab", "durvalumab",
                "sacituzumab govitecan", "erdafitinib", r"ev.*pembrolizumab",
                r"keytruda.*padcev", r"EV\+P", "padcev", "trodelvy"
            ],
            "lines": ["maintenance", "neoadjuvant", "adjuvant", "1L", "2L"],
            "avelumab_terms": ["avelumab", "bavencio"]
        },
        "must_cover": [
            "Explicitly state whether Avelumab/Bavencio appears in this conference CSV and cite Abstract # if present.",
            "Describe volume and thematic focus by named competitors; cite Abstract # examples.",
            "Use Abstract # when referencing items; do not invent counts—use counts only if present in the compact slices or context.",
            "If a competitor/theme is not present in the CSV, state that explicitly."
        ],
        "allow_soc": True,
        "allow_strategic_implications": False,
        "ai_prompt": """You are a senior competitive intelligence analyst for EMD Serono's medical affairs team. Your mission is to deliver a comprehensive strategic analysis of the competitive landscape at ASCO GU 2025, focusing on threats and opportunities for avelumab (Bavencio) in the bladder cancer space.

STRATEGIC CONTEXT:
- EMD Serono's avelumab is positioned as maintenance therapy in bladder cancer post-platinum chemotherapy
- EV+P (enfortumab vedotin + pembrolizumab) has dominated first-line treatment for ~2 years, fundamentally reshaping the treatment paradigm
- Medical affairs needs actionable intelligence to defend market position and identify expansion opportunities
- Conference presence often predicts future competitive moves and clinical development priorities

COMPETITIVE INTELLIGENCE FRAMEWORK:

**1. EXECUTIVE SUMMARY & COMPETITIVE INTENSITY**
Provide a strategic overview of the competitive landscape intensity. Assess the overall level of competitive activity, dominant themes, and whether this conference signals intensifying or stable competition in our therapeutic areas.

**2. AVELUMAB COMPETITIVE POSITIONING ANALYSIS**
- Conduct thorough search for avelumab/Bavencio presence (cite specific Abstract # if found)
- If absent: analyze what this gap means for our competitive visibility and strategic positioning
- Compare our conference footprint to key competitors quantitatively
- Assess whether absence creates defensive vulnerabilities or missed engagement opportunities

**3. COMPETITOR ACTIVITY DEEP DIVE**
Analyze each major competitor's conference strategy and volume:
- **EV+P Ecosystem**: Volume, expansion studies, combination strategies, institutional leadership
- **Pembrolizumab**: Standalone studies, new combinations, competitive positioning moves
- **Other ADCs** (Sacituzumab govitecan, Disitamab vedotin): Development stage, target populations, competitive threats
- **Checkpoint Inhibitors** (Nivolumab, Atezolizumab, Durvalumab): Combination strategies, new indications
- Identify which competitors are most aggressive in expanding their footprint

**4. INSTITUTIONAL & GEOGRAPHIC COMPETITIVE INTELLIGENCE**
- Which leading cancer centers are driving competitor research agendas?
- Are there institutional partnerships we should be aware of or potentially disrupt?
- Geographic patterns that suggest regional competitive strongholds

**5. EMERGING COMPETITIVE THREATS & WHITE SPACE OPPORTUNITIES**
- New players or unexpected competitive moves we haven't been tracking
- Treatment settings/patient populations where competitors are notably absent
- Gaps in the competitive landscape that represent expansion opportunities for avelumab

**6. STRATEGIC IMPLICATIONS & MEDICAL AFFAIRS PRIORITIES**
- Most immediate competitive threats requiring defensive action
- Partnership or combination opportunities suggested by competitor activity patterns
- Key opinion leader engagement priorities based on who's leading competitor research
- Recommended monitoring priorities for upcoming conferences/data readouts

ANALYSIS REQUIREMENTS:
- Write as a flowing, strategic narrative - avoid bullet points or rigid formatting
- Always cite specific Abstract # when referencing studies or claims
- Only use data/counts that appear in the provided tables - never invent numbers
- If competitors/themes aren't present in the data, explicitly acknowledge the absence
- Focus on actionable insights that inform medical affairs strategy and tactical decisions
- Maintain the perspective of a senior strategist advising executive leadership

Deliver a comprehensive intelligence brief that provides clear strategic direction for EMD Serono's competitive response."""
    },
    "kol": {
        "button_label": "👥 KOL Analysis",
        "subtitle": "People & Themes",
        "sections": [
            "Executive Summary",
            "Ranked Authors (Conference Presence)",
            "Thematic Focus by KOL",
            "Collaboration Footprint",
            "Representative Abstract Mentions"
        ],
        "required_tables": ["top_authors"],
        "buckets": {
            "topics": ["ADC", "Nectin", "HER2", "TROP-2", "FGFR", "checkpoint", "ctDNA", "utDNA", "PD-L1", "FGFR3", "TMB"]
        },
        "must_cover": [
            "Describe top authors by unique abstracts (counts supported by the attached table).",
            "No engagement advice; descriptive only.",
            "Use Abstract # to ground claims.",
            "If an author/theme is not present in data, indicate that explicitly."
        ],
        "allow_soc": False,
        "allow_strategic_implications": False,
        "ai_prompt": """You are a medical affairs KOL (Key Opinion Leader) analyst for EMD Serono. Write a comprehensive KOL analysis based on the ASCO GU 2025 conference data.

Context:
- Medical affairs teams need to identify and understand key researchers and thought leaders
- Focus on identifying potential collaboration opportunities and research partnerships
- Analyze research themes, institutional networks, and collaboration patterns
- This is descriptive analysis only - no engagement recommendations

Based on the conference data and author activity tables provided, write a natural, flowing analysis that covers:

**Executive Summary**: Brief overview of the most influential researchers and key themes at this conference

**Leading Researchers & Conference Presence**: Analysis of the most active authors based on unique abstracts presented, highlighting their research volume and areas of focus

**Research Themes & Expertise Areas**: Examination of what the top researchers are working on, including biomarkers, mechanisms of action, and therapeutic approaches they're advancing

**Institutional Networks & Collaboration Patterns**: Analysis of where these researchers are based and how they collaborate across institutions, identifying key research centers and partnerships

**Representative Research Examples**: Specific examples of notable research from key authors, citing Abstract # to ground the analysis

CRITICAL REQUIREMENTS:
- Write as a natural, flowing narrative - NOT bullet points or rigid sections
- Always cite Abstract # when referencing specific studies
- Only use author counts and data that are present in the provided tables
- If specific researchers/themes are not present in the data, explicitly state that
- Focus on descriptive analysis - avoid engagement advice or recommendations
- Maintain a professional, analytical tone focused on research insights
- Include specific research themes like ADCs, checkpoint inhibitors, biomarkers (PD-L1, FGFR3, TMB), etc.

Write a comprehensive research intelligence report that reads naturally and provides strategic insights for medical affairs professionals."""
    },
    "institution": {
        "button_label": "🏥 Institution Analysis",
        "subtitle": "Centers & Capabilities",
        "sections": [
            "Executive Summary",
            "Ranked Institutions (Conference Presence)",
            "Focus Areas by Institution",
            "Representative Abstract Mentions"
        ],
        "required_tables": ["top_institutions"],
        "buckets": {
            "topics": ["ADC", "Nectin", "HER2", "TROP-2", "FGFR", "checkpoint", "ctDNA", "utDNA", "PD-L1"]
        },
        "must_cover": [
            "Narrative guided by counts in attached table (unique abstracts).",
            "Focus strictly on conference data; no extrapolation.",
            "Use Abstract # to ground claims.",
            "Trial names must come from titles in the CSV, if present; otherwise indicate not found."
        ],
        "allow_soc": False,
        "allow_strategic_implications": False,
        "ai_prompt": """You are a medical affairs institutional analysis specialist for EMD Serono. Write a comprehensive institution analysis based on the ASCO GU 2025 conference data.

Context:
- Medical affairs teams need to understand key research institutions and their capabilities
- Focus on identifying institutional research strengths and partnership opportunities
- Analyze research focus areas, collaborative patterns, and institutional leadership
- This is descriptive analysis focused on research landscape intelligence

Based on the conference data and institutional activity tables provided, write a natural, flowing analysis that covers:

**Executive Summary**: Brief overview of the most active research institutions and their collective impact at this conference

**Leading Research Centers & Conference Presence**: Analysis of the most active institutions based on unique abstracts presented, highlighting their research volume and areas of specialization

**Institutional Research Focus Areas**: Examination of what top institutions are working on, including therapeutic approaches, biomarkers, and clinical development programs

**Collaborative Networks & Geographic Distribution**: Analysis of how institutions collaborate and their geographic distribution, identifying key research hubs and partnerships

**Representative Research Examples**: Specific examples of notable research from key institutions, citing Abstract # to ground the analysis

CRITICAL REQUIREMENTS:
- Write as a natural, flowing narrative - NOT bullet points or rigid sections
- Always cite Abstract # when referencing specific studies
- Only use institutional counts and data that are present in the provided tables
- If specific institutions/themes are not present in the data, explicitly state that
- Focus on descriptive analysis of research capabilities and focus areas
- Maintain a professional, analytical tone focused on institutional intelligence
- Include specific research themes like ADCs, checkpoint inhibitors, biomarkers (PD-L1, FGFR3, TMB), etc.

Write a comprehensive institutional intelligence report that reads naturally and provides strategic insights for medical affairs professionals."""
    },
    "insights": {
        "button_label": "🧭 Insights & Scientific Trends",
        "subtitle": "Comprehensive Evidence Synthesis",
        "sections": [
            "Executive Summary",
            "Trend Map (MOA & Biomarkers)",
            "Signal & Study Quality",
            "Treatment Paradigm Shifts (Descriptive)",
            "Endpoints & Evidence Patterns",
            "Unmet Needs & Evidence Gaps",
            "Potential Clinical Translation"
        ],
        "required_tables": ["biomarker_moa_hits"],
        "buckets": {
            "topics": [
                "ADCs", "ICIs", "FGFR", "DNA damage response", "HER2", "TROP-2",
                "ctDNA", "utDNA", "PD-L1", "FGFR3", "molecular subtypes", "TMB"
            ],
        },
        "must_cover": [
            "Cite representative Abstract #s for trend claims.",
            "Stay descriptive; no prescriptive recommendations.",
            "If signals are not found for a bucket, state that it does not appear in the CSV slice."
        ],
        "allow_soc": False,
        "allow_strategic_implications": False,
        "ai_prompt": """You are a medical affairs strategic intelligence analyst for EMD Serono. Write a comprehensive insights and trends analysis based on the ASCO GU 2025 conference data.

Context:
- Medical affairs teams need to understand emerging scientific trends and their strategic implications
- Focus on identifying patterns in research themes, biomarkers, mechanisms of action, and treatment approaches
- Analyze the overall scientific landscape and emerging paradigms in genitourinary oncology
- This analysis should provide strategic insights for portfolio positioning and development priorities

Based on the conference data and biomarker/MOA analysis tables provided, write a natural, flowing analysis that covers:

**Executive Summary**: Brief overview of the most significant scientific trends and research themes emerging from this conference

**Research Theme Landscape**: Analysis of the dominant research areas including ADCs, checkpoint inhibitors, FGFR targeting, DNA damage response, and other emerging mechanisms

**Biomarker Strategy Evolution**: Examination of biomarker research patterns including PD-L1, FGFR3, TMB, HER2, TROP-2, and ctDNA/utDNA approaches

**Treatment Paradigm Signals**: Analysis of emerging treatment approaches, combination strategies, and shifts in therapeutic focus areas

**Clinical Development Patterns**: Assessment of endpoint strategies, patient population focus, and evidence generation approaches

**Emerging Scientific Opportunities**: Identification of under-explored areas, novel mechanisms, and potential white space opportunities

**Strategic Intelligence for Portfolio Planning**: Analysis of how these trends might impact future development strategies and competitive positioning

CRITICAL REQUIREMENTS:
- Write as a natural, flowing narrative - NOT bullet points or rigid sections
- Always cite Abstract # when referencing specific studies or trends
- Only use data and patterns that are present in the provided tables and conference data
- If specific themes/biomarkers are not present in the data, explicitly state that
- Focus on strategic trend analysis while remaining grounded in the actual data
- Maintain a forward-looking perspective on scientific and clinical implications
- Include quantitative insights where supported by the data

Write a comprehensive scientific intelligence report that reads naturally and provides actionable insights for medical affairs strategy."""
    },
    "strategy": {
        "button_label": "📋 Medical Affairs Strategy",
        "subtitle": "Portfolio Implications",
        "sections": [
            "Executive Summary",
            "Strategic Implications for Avelumab & Portfolio"
        ],
        "required_tables": [],
        "buckets": {},
        "must_cover": [
            "Organize Strategic Implications as: Positioning vs Standard of Care; Evidence Themes to Amplify; Differentiating Messages; Portfolio Adjacencies.",
            "No action items/risks/12-month outlook.",
            "If CSV lacks evidence to support a point, say so plainly."
        ],
        "allow_soc": False,
        "allow_strategic_implications": True,
        "ai_prompt": """You are a senior medical affairs strategist for EMD Serono. Write a comprehensive strategic analysis based on the ASCO GU 2025 conference data, focusing on implications for avelumab (Bavencio) and the broader EMD Serono portfolio.

Context:
- EMD Serono's avelumab is positioned as maintenance therapy in bladder cancer post-platinum chemotherapy
- EV+P has dominated first-line treatment for ~2 years, fundamentally reshaping the treatment landscape
- Medical affairs needs strategic direction for portfolio positioning, competitive response, and market access
- This analysis should provide actionable strategic recommendations based on conference intelligence

Based on all available conference data and analysis, write a natural, flowing strategic assessment that covers:

**Executive Summary**: High-level strategic implications of the conference findings for EMD Serono's position in the genitourinary oncology market

**Portfolio Positioning Strategy**: Assessment of how avelumab and potential future assets should be positioned given the competitive landscape revealed at this conference

**Competitive Response Framework**: Strategic implications of competitor activity and how EMD Serono should respond to maintain and expand market position

**Evidence Strategy & Medical Affairs Priorities**: Identification of key evidence gaps, research priorities, and medical affairs focus areas based on competitive intelligence

**Market Access & Differentiation Opportunities**: Analysis of positioning opportunities and potential differentiation strategies informed by conference trends

**Strategic Recommendations for Portfolio Development**: Forward-looking recommendations for clinical development, partnership opportunities, and portfolio expansion based on conference insights

CRITICAL REQUIREMENTS:
- Write as a natural, flowing narrative - NOT bullet points or rigid sections
- Ground all strategic recommendations in specific conference data and cite Abstract # when relevant
- Only make recommendations supported by the conference evidence provided
- If specific strategic implications cannot be supported by the data, explicitly state that limitation
- Maintain focus on actionable medical affairs and portfolio strategy
- Consider both defensive positioning (protecting current market) and offensive opportunities (expansion)
- Balance strategic ambition with evidence-based realism

Write a comprehensive strategic intelligence report that provides clear direction for EMD Serono's medical affairs strategy and portfolio positioning."""
    }
}

# =========================
# Quantifications & Tables
# =========================
def count_top_authors(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    df_unique = df.drop_duplicates(subset=["Abstract #"]).copy()
    authors_series = df_unique["Authors"].fillna("").str.split(";").explode().str.strip()
    counts = (
        authors_series[authors_series != ""]
        .value_counts()
        .head(n)
        .rename_axis("Authors")
        .reset_index(name="Unique Abstracts")
    )

    # Common institutions per top author
    common_insts = []
    for _, row in counts.iterrows():
        author = row["Authors"]
        pat = r"\b" + re.escape(author) + r"\b"
        sub_abs = df_unique[safe_contains(df_unique["Authors"], pat, regex=True)]
        all_insts = []
        for inst_str in sub_abs["Institutions"]:
            for inst in str(inst_str).split(";"):
                s = inst.strip()
                if len(s) > 4:
                    all_insts.append(s)
        if all_insts:
            top2 = Counter(all_insts).most_common(2)
            common_insts.append("; ".join(inst for inst, _ in top2))
        else:
            common_insts.append("")
    counts["Institutions"] = common_insts
    counts = counts[["Unique Abstracts", "Authors", "Institutions"]]
    return counts

def count_top_institutions(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    df_unique = df.drop_duplicates(subset=["Abstract #"]).copy()
    institutions_list = []
    institution_keywords = [
        "university","hospital","cancer","center","centre","institute",
        "medical","clinic","college","health system","health service","foundation","consortium"
    ]
    for _, row in df_unique.iterrows():
        inst_text = str(row.get("Institutions", ""))
        parts = re.split(r"[;,\|]", inst_text)
        for part in parts:
            s = part.strip()
            if len(s) > 6 and any(k in s.lower() for k in institution_keywords):
                institutions_list.append({"Abstract #": row["Abstract #"], "Institution": s, "Title": row["Title"]})

    if not institutions_list:
        return pd.DataFrame(columns=["#Unique Abstracts", "Institutions", "Main focus area"])

    inst_df = pd.DataFrame(institutions_list)
    counts = (
        inst_df.drop_duplicates(subset=["Abstract #", "Institution"])
        .groupby("Institution")["Abstract #"]
        .nunique()
        .reset_index(name="#Unique Abstracts")
    )

    focus_keywords = {
        "ADCs": ["adc", "enfortumab", "sacituzumab", "deruxtecan", "nectin"],
        "ICIs": ["avelumab", "pembrolizumab", "nivolumab", "atezolizumab", "durvalumab", "checkpoint"],
        "FGFR": ["fgfr", "erdafitinib"],
        "HER2": ["her2"],
        "TROP-2": ["trop-2", "trop2"],
        "ctDNA/utDNA": ["ctdna", "utdna"],
        "Perioperative": ["neoadjuvant", "adjuvant"],
        "Maintenance": ["maintenance"],
    }
    inst_titles = (
        inst_df.drop_duplicates(subset=["Abstract #", "Institution"])[["Institution", "Title"]]
        .groupby("Institution")["Title"].apply(list).to_dict()
    )
    main_focus = []
    for inst in counts["Institution"]:
        titles = " ".join(inst_titles.get(inst, [])).lower()
        score = {area: sum(titles.count(k) for k in keys) for area, keys in focus_keywords.items()}
        best = max(score, key=score.get) if score else None
        main_focus.append(best if best and score[best] > 0 else "")
    counts["Main focus area"] = main_focus
    counts = counts.sort_values("#Unique Abstracts", ascending=False).head(n)
    counts = counts[["#Unique Abstracts", "Institution", "Main focus area"]].rename(columns={"Institution": "Institutions"})
    return counts

def get_drug_company_mapping_ai(drug_names: List[str]) -> Dict[str, str]:
    """Use AI to map drug names to pharmaceutical companies."""
    if not client:
        return {}

    drugs_text = ", ".join(drug_names)
    prompt = f"""You are a pharmaceutical industry expert. For each drug listed below, provide the primary pharmaceutical company that manufactures/markets it. Respond in this exact format:

Drug Name: Company Name

Only include drugs you're confident about. For combination drugs, list both companies separated by '/'.

Drugs to map: {drugs_text}"""

    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=500
        )

        # Parse the response into a dictionary
        drug_company_map = {}
        for line in response.choices[0].message.content.split('\n'):
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    drug = parts[0].strip()
                    company = parts[1].strip()
                    drug_company_map[drug] = company

        return drug_company_map
    except Exception as e:
        print(f"Error in AI drug-company mapping: {str(e)}")
        return {}

def create_competitor_abstracts_table(filtered_df: pd.DataFrame, competitors_to_check: List[Tuple[str, List[str]]]) -> pd.DataFrame:
    competitor_abstracts = []

    # Base company map with known mappings
    base_company_map = {
        "Avelumab": "EMD Serono",  # Our own drug!
        "Enfortumab vedotin": "Astellas/Seagen",
        "Pembrolizumab": "Merck",
        "Nivolumab": "Bristol Myers Squibb",
        "Atezolizumab": "Roche/Genentech",
        "Durvalumab": "AstraZeneca",
        "Sacituzumab govitecan": "Gilead",
        "Erdafitinib": "Johnson & Johnson",
        "EV + Pembrolizumab": "Astellas/Seagen + Merck",
        "Disitamab vedotin": "RemeGen",
        "Zelenectide pevedotin": "Mersana Therapeutics",
    }

    # Get list of drugs that aren't in base map for AI enhancement
    all_drugs = [canonical for canonical, _ in competitors_to_check]
    unmapped_drugs = [drug for drug in all_drugs if drug not in base_company_map]

    # Use AI to map unmapped drugs
    ai_company_map = {}
    if unmapped_drugs:
        ai_company_map = get_drug_company_mapping_ai(unmapped_drugs)

    # Combine base map with AI enhancements
    company_map = {**base_company_map, **ai_company_map}

    def extract_company_from_institutions(institutions_text: str) -> str:
        """Extract pharmaceutical company names from institution affiliations."""
        if not institutions_text:
            return ""

        # Common pharmaceutical company patterns in institution names
        pharma_patterns = [
            r'Astellas', r'Seagen', r'Merck', r'Bristol.?Myers.?Squibb', r'BMS',
            r'Roche', r'Genentech', r'AstraZeneca', r'Gilead', r'Johnson.?&.?Johnson',
            r'J&J', r'EMD.?Serono', r'Pfizer', r'Novartis', r'GSK', r'GlaxoSmithKline',
            r'Sanofi', r'Bayer', r'Amgen', r'Regeneron', r'Biogen', r'Moderna'
        ]

        institutions_lower = institutions_text.lower()
        found_companies = []

        for pattern in pharma_patterns:
            matches = re.findall(pattern, institutions_text, re.IGNORECASE)
            if matches:
                found_companies.extend(matches)

        # Return first found company or empty string
        return found_companies[0] if found_companies else ""

    dfu = filtered_df.drop_duplicates(subset=["Abstract #"]).copy()
    for canonical, aliases in competitors_to_check:
        for alias in aliases:
            use_regex = bool(re.search(r'[.*+?^${}()|[\]\\]', alias))
            mask = (
                safe_contains(dfu["Title"], alias, regex=use_regex) |
                safe_contains(dfu["Authors"], alias, regex=use_regex) |
                safe_contains(dfu["Institutions"], alias, regex=use_regex)
            )
            hits = dfu[mask]
            if not hits.empty:
                for _, row in hits.iterrows():
                    # Intelligent company detection: try drug mapping first, then extract from institutions
                    mapped_company = company_map.get(canonical, "")
                    if not mapped_company:
                        # Try to extract company from institution affiliations
                        institution_company = extract_company_from_institutions(row["Institutions"])
                        mapped_company = institution_company if institution_company else "Unknown"

                    competitor_abstracts.append({
                        "Competitor": canonical,
                        "Company": mapped_company,
                        "Abstract #": row["Abstract #"],
                        "Poster #": row["Poster #"],
                        "Title": row["Title"],
                        "Authors": row["Authors"],
                        "Institutions": row["Institutions"],
                    })
    if competitor_abstracts:
        df_out = pd.DataFrame(competitor_abstracts).drop_duplicates(subset=["Abstract #", "Title"])
        df_out = df_out[["Competitor", "Company", "Abstract #", "Poster #", "Title", "Authors", "Institutions"]]
        return df_out.sort_values(["Competitor", "Abstract #"])
    return pd.DataFrame(columns=["Competitor","Company","Abstract #","Poster #","Title","Authors","Institutions"])

def create_emerging_threats_table(filtered_df: pd.DataFrame) -> pd.DataFrame:
    emerging_keywords = [
        "nectin-4","nectin 4","NECTIN4","HER2","HER2-low","trastuzumab deruxtecan","DS-8201",
        "CAR-T","car t","bispecific","novel","investigational","phase i","phase 1","first-in-human","TROP-2","trop2"
    ]
    dfu = filtered_df.drop_duplicates(subset=["Abstract #"]).copy()
    rows = []
    for kw in emerging_keywords:
        mask = safe_contains(dfu["Title"], kw) | safe_contains(dfu["Authors"], kw)
        for _, r in dfu[mask].iterrows():
            rows.append({
                "Threat Type": kw.upper(),
                "Abstract #": r["Abstract #"],
                "Poster #": r["Poster #"],
                "Title": r["Title"]
            })
    if rows:
        return pd.DataFrame(rows).drop_duplicates(subset=["Abstract #", "Threat Type"])
    return pd.DataFrame(columns=["Threat Type","Abstract #","Poster #","Title"])

def build_biomarker_moa_hits_table(filtered_df: pd.DataFrame) -> pd.DataFrame:
    dfu = filtered_df.drop_duplicates(subset=["Abstract #"]).copy()
    topics = {
        "ADCs": ["adc", "enfortumab", "sacituzumab", "deruxtecan", "nectin", "trop-2", "trop2"],
        "ICIs": ["avelumab", "pembrolizumab", "nivolumab", "atezolizumab", "durvalumab", "checkpoint"],
        "FGFR": ["fgfr", "erdafitinib"],
        "HER2": ["her2"],
        "TMB": ["tmb"],
        "ctDNA": ["ctdna"],
        "utDNA": ["utdna"],
        "PD-L1": ["pd-l1", "pdl1", "pd l1"],
        "FGFR3": ["fgfr3"],
        "DDR": ["dna damage response", "atr", "atm", "parp"]
    }
    rows = []
    for _, r in dfu.iterrows():
        title_l = str(r["Title"]).lower()
        tags = [label for label, keys in topics.items() if any(k in title_l for k in keys)]
        for tag in tags:
            rows.append({"Biomarker / MOA": tag, "Abstract #": r["Abstract #"], "Title": r["Title"]})
    if rows:
        return pd.DataFrame(rows).drop_duplicates(subset=["Biomarker / MOA", "Abstract #"])
    return pd.DataFrame(columns=["Biomarker / MOA", "Abstract #", "Title"])

# Cached-like helpers
def get_top_authors(filtered_sig: str, filtered_df: pd.DataFrame, n: int = 20):
    return count_top_authors(filtered_df, n)

def get_top_institutions(filtered_sig: str, filtered_df: pd.DataFrame, n: int = 20):
    return count_top_institutions(filtered_df, n)

def build_competitor_tables(filtered_sig: str, filtered_df: pd.DataFrame, competitors_to_check: List[Tuple[str, List[str]]]):
    comp = create_competitor_abstracts_table(filtered_df, competitors_to_check)
    emerg = create_emerging_threats_table(filtered_df)
    return comp, emerg

def get_biomarker_moa_hits(filtered_sig: str, filtered_df: pd.DataFrame):
    return build_biomarker_moa_hits_table(filtered_df)

def get_unique_authors(filtered_sig: str, filtered_df: pd.DataFrame) -> List[str]:
    dfu = filtered_df.drop_duplicates(subset=["Abstract #"]).copy()
    authors = (
        dfu["Authors"].fillna("").str.split(";").explode().str.strip()
    )
    authors = authors[authors != ""].drop_duplicates().tolist()
    return sorted(authors)

def extract_author_from_query(query: str, authors_list: List[str]) -> Optional[str]:
    qn = normalize_txt(query)
    best_match = None
    best_len = 0
    for a in authors_list:
        an = normalize_txt(a)
        if len(an) < 3:
            continue
        if an in qn:
            if len(an) > best_len:
                best_len = len(an)
                best_match = a
    if best_match:
        return best_match
    m = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", query)
    for cand in m:
        for a in authors_list:
            if cand.lower().strip() == a.lower().strip():
                return a
    return None

# =========================
# RAG Snippet Builder
# =========================
def build_rag_snippets(filtered_df: pd.DataFrame, playbook_key: str, buckets: Dict[str, List[str]], limit: int = 10) -> List[str]:
    dfu = filtered_df.drop_duplicates(subset=["Abstract #"]).copy()
    snippets: List[str] = []
    used = set()

    def add_snip(row):
        a = str(row["Abstract #"])
        if a in used:
            return
        title = str(row["Title"])
        authors = str(row["Authors"])
        snippets.append(f"Abstract #{a}: {title} | Authors: {authors}")
        used.add(a)

    priority_terms: List[str] = []
    if playbook_key == "competitor":
        priority_terms += (buckets or {}).get("avelumab_terms", [])
        priority_terms += (buckets or {}).get("competitors", [])
        priority_terms += (buckets or {}).get("lines", [])
    else:
        for _, terms in (buckets or {}).items():
            priority_terms += terms

    if not priority_terms:
        for _, r in dfu.head(limit).iterrows():
            add_snip(r)
            if len(snippets) >= limit:
                break
        return snippets

    idx = 0
    while len(snippets) < limit and idx < len(priority_terms) * 10:
        term = priority_terms[idx % len(priority_terms)]
        idx += 1
        term_regex = True if re.search(r"[.*+?^${}()|[\]\\]", term) else False
        mask = safe_contains(dfu["Title"], term, regex=term_regex) | safe_contains(dfu["Authors"], term, regex=term_regex)
        for _, r in dfu[mask].iterrows():
            if len(snippets) >= limit:
                break
            add_snip(r)

    if len(snippets) < limit:
        for _, r in dfu.iterrows():
            if len(snippets) >= limit:
                break
            add_snip(r)

    return snippets[:limit]

# =========================
# AI-First Query Analysis (New Architecture)
# =========================

@dataclass
class QueryPlan:
    """Data structure for AI query analysis plan - now flexible and context-aware"""
    user_intent: str  # What the user actually wants
    response_type: str  # data_table, specific_lookup, strategic_analysis, informational_narrative
    primary_entities: Dict[str, List[str]]  # drugs, authors, institutions, topics
    search_strategy: Dict[str, Any]  # How to gather the data
    response_approach: str  # How to respond helpfully
    confidence: float

    # Legacy fields for compatibility
    @property
    def intent_type(self) -> str:
        return self.response_type

    @property
    def mentioned_entities(self) -> Dict[str, List[str]]:
        return self.primary_entities

    @property
    def requires_semantic_search(self) -> bool:
        return self.search_strategy.get("use_semantic_search", True)

    @property
    def semantic_search_terms(self) -> List[str]:
        return self.search_strategy.get("search_terms", [])

    @property
    def needs_competitor_analysis(self) -> bool:
        return self.search_strategy.get("get_competitor_data", False)

    @property
    def needs_author_analysis(self) -> bool:
        return self.search_strategy.get("get_author_data", False)

    @property
    def needs_institution_analysis(self) -> bool:
        return self.search_strategy.get("get_institution_data", False)

def analyze_user_query_ai(query: str, ta_filter: str, conversation_history: list = None) -> QueryPlan:
    """
    True AI-powered query understanding that determines what the user wants
    without forcing rigid categories. Flexible and context-aware.
    """
    if client is None:
        print("Error: OpenAI client not initialized for AI query analysis.")
        return QueryPlan(
            user_intent="Fallback - no AI available",
            response_type="informational_narrative",
            primary_entities={},
            search_strategy={
                "use_semantic_search": True,
                "search_terms": [query],
                "get_author_data": False,
                "get_institution_data": False,
                "get_competitor_data": False
            },
            response_approach="Provide basic information",
            confidence=0.0
        )

    # Build conversation context if available
    conversation_context = ""
    if conversation_history:
        conversation_context = "\n\nConversation History (for understanding pronouns and references):\n"
        for msg in conversation_history:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')[:300] + ('...' if len(msg.get('content', '')) > 300 else '')
            conversation_context += f"{role.title()}: {content}\n"
        conversation_context += "\n"

    system_prompt = """You are an intelligent assistant helping analyze user requests for medical conference data. Your job is to understand what the user actually wants and determine the best way to help them.
""" + conversation_context + """
Available conference data includes:
- Abstract titles, authors, institutions, poster numbers
- Semantic search across all text
- Author activity summaries
- Institution activity summaries
- Drug/competitor mentions

YOUR GOAL: Understand the user's real intent and determine the most helpful response approach.

**CRITICAL: AUTHOR NAME DETECTION**
When users mention specific people (e.g., "Petros Grivas", "John Smith", "Dr. Anderson"), this is almost always a lookup request wanting:
- Their specific research activity
- Collaboration patterns and institutional affiliations
- Strategic analysis of their work
→ Set response_type: "specific_lookup", get_author_data: true, and extract the name in "authors" field

**IMPORTANT: PRONOUN RESOLUTION**
If the user uses pronouns (he, she, they, him, her) or refers to "the author", "this person", look at the conversation history to identify who they're referring to. Extract the actual name from the previous context.

EXAMPLES OF USER INTENT PATTERNS:

**Author/Researcher Lookups** (MOST IMPORTANT):
- "Does Petros Grivas have any pharmaceutical industry involvement?"
- "Show me John Smith's work" / "what has researcher X published"
- "Tell me about Dr. Anderson's research"
→ These want SPECIFIC AUTHOR DATA with KOL analysis framework

**Quantitative Requests** (want tables/lists):
- "top 20 authors" / "most active scientists" / "leading researchers"
- "list avelumab studies" / "show me all research on drug X"
- "top institutions" / "most active centers"
→ These want DATA TABLES with brief context, not strategic analysis

**Institution Lookups**:
- "abstracts from Memorial Sloan Kettering"
- "what is Mayo Clinic working on"
→ These want SPECIFIC INSTITUTION DATA with explanation

**Analytical Requests** (want strategic insights):
- "what risks does drug X pose to drug Y"
- "competitive landscape analysis"
- "treatment paradigm implications"
→ These want STRATEGIC ANALYSIS with medical context

**General Questions** (want informational answers):
- "what are the main trends in bladder cancer"
- "tell me about biomarker research"
→ These want COMPREHENSIVE NARRATIVE with supporting data

Return JSON determining the optimal response approach:
{
  "user_intent": "brief description of what user actually wants",
  "response_type": "data_table|specific_lookup|strategic_analysis|informational_narrative",
  "primary_entities": {
    "drugs": ["mentioned drugs"],
    "authors": ["mentioned authors"],
    "institutions": ["mentioned institutions"],
    "topics": ["key topics/concepts"]
  },
  "search_strategy": {
    "use_semantic_search": true/false,
    "search_terms": ["optimized terms"],
    "get_author_data": true/false,
    "get_institution_data": true/false,
    "get_competitor_data": true/false
  },
  "response_approach": "concise description of how to respond helpfully",
  "confidence": 0.0-1.0
}"""

    user_prompt = f"""
Analyze this query for a medical affairs conference intelligence system:

Query: "{query}"
Therapeutic Area Filter: {ta_filter}

Context: This system analyzes oncology conference abstracts (ASCO GU 2025) with focus on bladder cancer and renal cell carcinoma. The user is likely a medical affairs professional seeking competitive intelligence, clinical insights, or strategic analysis.

Determine the optimal execution strategy and return ONLY valid JSON format matching the schema exactly. Do not include any explanatory text before or after the JSON.
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_completion_tokens=400,
        )

        txt = resp.choices[0].message.content.strip()
        print(f"🔍 RAW AI RESPONSE: {txt[:200]}...")  # Debug output

        if txt.startswith("```"):
            txt = re.sub(r"^```(json)?", "", txt).strip()
            if txt.endswith("```"):
                txt = txt[:-3].strip()

        # Additional cleanup for GPT-5-mini
        if not txt:
            raise ValueError("Empty response from AI")

        # Try to extract JSON if it's wrapped in text
        import re
        json_match = re.search(r'\{.*\}', txt, re.DOTALL)
        if json_match:
            txt = json_match.group()

        data = json.loads(txt)

        return QueryPlan(
            user_intent=data.get("user_intent", "General inquiry"),
            response_type=data.get("response_type", "informational_narrative"),
            primary_entities=data.get("primary_entities", {}),
            search_strategy=data.get("search_strategy", {
                "use_semantic_search": True,
                "search_terms": [query],
                "get_author_data": False,
                "get_institution_data": False,
                "get_competitor_data": False
            }),
            response_approach=data.get("response_approach", "Provide helpful information based on available data"),
            confidence=data.get("confidence", 0.7)
        )

    except Exception as e:
        print(f"Error in AI query analysis: {e}")
        # Fallback to semantic search approach
        return QueryPlan(
            user_intent="General inquiry (fallback)",
            response_type="informational_narrative",
            primary_entities={},
            search_strategy={
                "use_semantic_search": True,
                "search_terms": [query],
                "get_author_data": False,
                "get_institution_data": False,
                "get_competitor_data": False
            },
            response_approach="Provide helpful information using semantic search",
            confidence=0.5
        )

@dataclass
class ContextPackage:
    """Structured container for all gathered context"""
    semantic_results: Optional[pd.DataFrame] = None
    competitor_data: Optional[pd.DataFrame] = None
    author_data: Optional[pd.DataFrame] = None
    institution_data: Optional[pd.DataFrame] = None
    medical_context: Optional[Dict[str, str]] = None
    quantitative_summaries: Optional[Dict[str, pd.DataFrame]] = None

def gather_intelligent_context(plan: QueryPlan, ta_filter: str, filtered_df: pd.DataFrame) -> ContextPackage:
    """
    Intelligently gather exactly the context needed based on AI's analysis plan
    """
    context = ContextPackage()

    # Semantic search for complex queries
    if plan.requires_semantic_search and plan.semantic_search_terms:
        search_query = " ".join(plan.semantic_search_terms)
        try:
            semantic_results = semantic_search(search_query, ta_filter, n_results=15)
            context.semantic_results = format_search_results(semantic_results)
        except Exception as e:
            print(f"Error in semantic search: {e}")
            context.semantic_results = pd.DataFrame()

    # Competitor analysis if needed
    if plan.needs_competitor_analysis and plan.mentioned_entities.get("drugs"):
        # Build competitor search terms
        competitors_to_check = []
        for drug in plan.mentioned_entities["drugs"]:
            drug_lower = drug.lower()
            if "enfortumab vedotin" in drug_lower or "enfortumab" in drug_lower:
                competitors_to_check.append(("Enfortumab vedotin", ["enfortumab vedotin", "enfortumab", r"\bEV\b", "Padcev"]))
            elif "disitamab vedotin" in drug_lower or "disitamab" in drug_lower:
                competitors_to_check.append(("Disitamab vedotin", ["disitamab vedotin", "disitamab", "RC48"]))
            elif "zelenectide pevedotin" in drug_lower or "zelenectide" in drug_lower:
                competitors_to_check.append(("Zelenectide pevedotin", ["zelenectide pevedotin", "zelenectide"]))
            elif "pembrolizumab" in drug_lower:
                competitors_to_check.append(("Pembrolizumab", ["pembrolizumab", "keytruda"]))
            elif "avelumab" in drug_lower:
                competitors_to_check.append(("Avelumab", ["avelumab", "bavencio"]))
            elif "sacituzumab govitecan" in drug_lower or ("sacituzumab" in drug_lower and "govitecan" in drug_lower):
                competitors_to_check.append(("Sacituzumab govitecan", ["sacituzumab govitecan", "sacituzumab", "govitecan", "trodelvy"]))
            # Add more as needed

        if competitors_to_check:
            comp_table, _ = build_competitor_tables(df_sig(filtered_df), filtered_df, competitors_to_check)
            context.competitor_data = comp_table

    # Author analysis if needed (enhanced to detect authors from query text)
    if plan.needs_author_analysis:
        author_results = []

        # First try explicit authors mentioned by AI
        if plan.mentioned_entities.get("authors"):
            for author in plan.mentioned_entities["authors"]:
                pat = r"\b" + re.escape(author) + r"\b"
                mask = safe_contains(filtered_df["Authors"], pat, regex=True)
                author_abstracts = filtered_df.loc[mask, ["Abstract #","Poster #","Title","Authors","Institutions"]].drop_duplicates(subset=["Abstract #"])
                if not author_abstracts.empty:
                    author_results.append(author_abstracts)

        # Also try to extract author names from query using the existing function
        if not author_results:
            authors_list = get_unique_authors(df_sig(df_global), df_global)
            # Use search terms from plan since query is not available in this scope
            query_text = " ".join(plan.semantic_search_terms) if plan.semantic_search_terms else ""
            detected_author = extract_author_from_query(query_text, authors_list)
            if detected_author:
                pat = r"\b" + re.escape(detected_author) + r"\b"
                mask = safe_contains(filtered_df["Authors"], pat, regex=True)
                author_abstracts = filtered_df.loc[mask, ["Abstract #","Poster #","Title","Authors","Institutions"]].drop_duplicates(subset=["Abstract #"])
                if not author_abstracts.empty:
                    author_results.append(author_abstracts)

        if author_results:
            context.author_data = pd.concat(author_results, ignore_index=True).drop_duplicates(subset=["Abstract #"])

    # Add medical context based on mentioned drugs/entities
    context.medical_context = get_enhanced_medical_context(plan.mentioned_entities, ta_filter)

    return context

def get_enhanced_medical_context(mentioned_entities: Dict[str, List[str]], ta_filter: str) -> Dict[str, str]:
    """
    Provide rich medical context based on entities mentioned in the query
    """
    context = {}

    drugs = mentioned_entities.get("drugs", [])

    if any("enfortumab" in drug.lower() for drug in drugs):
        context["enfortumab_vedotin"] = """
        Enfortumab vedotin (EV, Padcev) is an ADC targeting Nectin-4. EV+pembrolizumab (EV+P) is the new 1L standard of care for locally advanced/metastatic urothelial carcinoma per EV-302 trial results. This fundamentally changes the treatment landscape and competitive positioning for all other therapies.
        """

    if any("avelumab" in drug.lower() for drug in drugs):
        context["avelumab"] = """
        Avelumab (Bavencio) is established as standard 1L maintenance therapy post-platinum chemotherapy for non-progressive advanced urothelial carcinoma (JAVELIN Bladder 100). With EV+P becoming 1L SOC, avelumab's role is shifting and requires redefinition of optimal patient populations.
        """

    # Add therapeutic area context
    if ta_filter == "Bladder Cancer":
        context["ta_landscape"] = """
        Bladder cancer landscape dominated by ADCs (EV, sacituzumab govitecan) and checkpoint inhibitors. EV+P is new 1L SOC. Key resistance mechanisms and post-EV+P sequencing are active areas of investigation.
        """
    elif ta_filter == "Renal Cell Carcinoma":
        context["ta_landscape"] = """
        RCC dominated by IO+TKI combinations in 1L (pembrolizumab+axitinib, nivolumab+cabozantinib). VEGF pathway central to treatment resistance. Non-clear cell histologies remain challenging.
        """

    return context

# =========================
# LLM Router (Legacy - Kept for Fallback)
# =========================
def llm_route_query(query: str) -> Tuple[str, float, Dict[str, Any]]:
    """
    Returns (intent, confidence, slots) from an LLM JSON response.
    Falls back to lightweight rules if parsing fails.
    """
    if client is None:
        print("Error: OpenAI client not initialized for LLM routing.")
        return "out_of_scope", 0.0, {}

    system = "You are a routing assistant. Return STRICT JSON with keys: intent, confidence (0-1), slots (object). No prose."
    user = f"""
Route the user query to one of these intents:
- competitor_playbook, kol_playbook, institution_playbook, insights_playbook, strategy_playbook
- top_authors, top_institutions, list_avelumab, search, author_abstracts, institution_abstracts
- smalltalk, help, general_conference_question, out_of_scope

Extract slots where relevant:
- n (int)
- term (string) for generic search
- author (string) for author_abstracts
- institution (string) for institution_abstracts

User query: {query}
Return only JSON.
"""
    try:
        resp = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            max_completion_tokens=180,
        )
        txt = resp.choices[0].message.content.strip()
        if txt.startswith("```"):
            txt = re.sub(r"^```(json)?", "", txt).strip()
            if txt.endswith("```"):
                txt = txt[:-3].strip()
        data = json.loads(txt)
        intent = str(data.get("intent", "out_of_scope"))
        conf = float(data.get("confidence", 0.0))
        slots = data.get("slots", {}) or {}
        return intent, conf, slots
    except Exception as e:
        print(f"Error in LLM routing: {e}. Falling back to rule-based intent detection.")
        return detect_chat_intent_fallback(query)

def detect_chat_intent_fallback(q: str) -> Tuple[str, float, Dict[str, Any]]:
    ql = q.lower().strip()
    if re.fullmatch(r"(hi|hello|hey|yo|good\s*(morning|afternoon|evening)|how are you\??)", ql):
        return "smalltalk", 0.9, {}
    if "help" in ql or "how to" in ql or "what can you do" in ql:
        return "help", 0.8, {}
    if any(p in ql for p in ["involvement from", "by author", "by ", "authored by", "from author"]):
        return "author_abstracts", 0.6, {}
    if "top" in ql and ("author" in ql or "kol" in ql):
        return "top_authors", 0.7, {"n": extract_number_default(ql, 20)}
    if "top" in ql and "institution" in ql:
        return "top_institutions", 0.7, {"n": extract_number_default(ql, 20)}
    if ("avelumab" in ql or "bavencio" in ql) and any(x in ql for x in ["table", "studies", "abstracts", "list", "show"]):
        return "list_avelumab", 0.7, {}
    if "find " in ql or "search " in ql:
        m = re.search(r"['\"]([^'\"]+)['\"]", ql)
        if m:
            term = m.group(1).strip()
        else:
            m2 = re.search(r"(?:find|search)\s+([a-z0-9\-\+\.\s]{2,})", ql)
            term = m2.group(1).strip() if m2 else ""
        return ("search", 0.6, {"term": term}) if term else ("search", 0.5, {})
    if "competitor" in ql or "landscape" in ql or "standard of care" in ql:
        return "competitor_playbook", 0.6, {}
    if "kol" in ql and ("analysis" in ql or "people" in ql or "authors" in ql):
        return "kol_playbook", 0.6, {}
    if "institution" in ql and ("analysis" in ql or "centers" in ql):
        return "institution_playbook", 0.6, {}
    if any(x in ql for x in ["trend", "insight", "biomarker", "paradigm"]):
        return "insights_playbook", 0.6, {}
    if "strategy" in ql or "implications" in ql:
        return "strategy_playbook", 0.6, {}
    return "general_conference_question", 0.4, {}

# =========================
# AI: Multi-Pass Analysis Engine
# =========================
def generate_kol_analysis(
    filtered_df: pd.DataFrame,
    top_authors_table: pd.DataFrame,
    ta_filter: str = "All"
) -> str:
    """
    Multi-pass comprehensive KOL analysis with surgical prompts.

    Args:
        filtered_df: The filtered conference data
        top_authors_table: Pre-built top authors table
        ta_filter: Therapeutic area filter

    Returns:
        Comprehensive KOL analysis narrative
    """
    print(f"[DEBUG] Starting multi-pass KOL analysis for {ta_filter}")

    if client is None:
        print("[ERROR] OpenAI client not initialized")
        return "Error: OpenAI client not initialized. Please ensure OPENAI_API_KEY is set."

    try:
        # Prepare data summaries
        total_abstracts = len(filtered_df)
        top_15_authors = top_authors_table.head(15)['Authors'].tolist()

        print(f"[PASS1] Extracting targeted data for {len(top_15_authors)} top KOLs...")

        # Extract specific abstracts for each top KOL for targeted analysis
        kol_specific_data = {}
        for author in top_15_authors:
            # Find all abstracts where this author appears
            author_mask = filtered_df['Authors'].str.contains(re.escape(author), case=False, na=False)
            author_abstracts = filtered_df[author_mask]
            if not author_abstracts.empty:
                kol_specific_data[author] = author_abstracts.to_csv(index=False)

        # Pass 1: Systematic KOL Analysis with Framework
        print("[PASS1] Systematic analysis of individual KOLs using targeted data...")

        all_profiles = []

        # Process KOLs in batches of 4 to reduce API calls from 15 to 3-4
        batch_size = 4
        authors_with_data = [author for author in top_15_authors if author in kol_specific_data]

        for batch_start in range(0, len(authors_with_data), batch_size):
            batch_end = min(batch_start + batch_size, len(authors_with_data))
            batch_authors = authors_with_data[batch_start:batch_end]

            print(f"[PASS1] Analyzing batch {batch_start//batch_size + 1} with {len(batch_authors)} KOLs: {', '.join(batch_authors)}")

            # Prepare batch data for all KOLs in this batch
            batch_data_sections = []
            for author in batch_authors:
                batch_data_sections.append(f"""
=== KOL: {author} ===
ALL ABSTRACTS FOR {author}:
{kol_specific_data[author]}
""")

            batch_prompt = f"""Analyze these {len(batch_authors)} KOLs using the conference data and systematic framework. Provide separate analysis for each KOL.

{('').join(batch_data_sections)}

SYSTEMATIC ANALYSIS FRAMEWORK (apply to each KOL):
a) WHO: Name, primary institution(s), geographic location (from Institutions column)
b) RESEARCH INTERESTS: What therapeutic areas, drugs, mechanisms they focus on (from Title column + your knowledge)
c) HCP COLLABORATIONS: Which other top authors they co-author with (from Authors column)
d) PHARMA COLLABORATIONS: Which pharmaceutical/biotech companies appear in their Institutions column

For each KOL, write ONE comprehensive paragraph that flows naturally covering all four framework elements. Use ONLY the actual data provided above. Cite specific Abstract # examples. Be systematic and thorough.

Format your response as:
**[KOL Name 1]**: [Analysis paragraph]

**[KOL Name 2]**: [Analysis paragraph]

etc."""

            try:
                batch_response = client.chat.completions.create(
                    model="gpt-5-mini",
                    reasoning_effort="minimal",
                    verbosity="low",
                    messages=[{"role": "user", "content": batch_prompt}],
                            max_completion_tokens=1600  # Increased for batch processing
                )
                batch_profiles = batch_response.choices[0].message.content

                # Split the batch response and add individual profiles
                # The response should already be formatted correctly
                all_profiles.append(batch_profiles)

            except Exception as e:
                print(f"Error analyzing batch {batch_start//batch_size + 1}: {e}")
                # Add error messages for each author in the failed batch
                for author in batch_authors:
                    all_profiles.append(f"**{author}**: Analysis unavailable due to processing error.")

        combined_profiles = "\n\n".join(all_profiles)

        # Pass 2: Brief Strategic Summary
        print("[PASS2] Brief strategic summary...")

        summary_prompt = f"""Based on these KOL profiles, provide a brief strategic summary for EMD Serono in 2 short paragraphs:

{combined_profiles}

Paragraph 1: Top 5 priority KOLs for engagement and why (based on research alignment and influence).
Paragraph 2: Key strategic opportunities and geographic considerations.

Keep it concise and actionable."""

        summary_response = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[{"role": "user", "content": summary_prompt}],
            max_completion_tokens=500
        )
        strategic_summary = summary_response.choices[0].message.content

        # Combine analyses
        final_analysis = f"""# 👥 KOL Analysis — Data-Driven Intelligence Report

## Strategic Summary
{strategic_summary}

## Individual KOL Profiles (Top 15 Most Prolific)
{combined_profiles}
"""

        print(f"[DEBUG] Multi-pass KOL analysis complete, total length: {len(final_analysis)} chars")
        return final_analysis

    except Exception as e:
        print(f"[ERROR] in generate_kol_analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Error generating KOL analysis: {str(e)}"

def sse_event(event_name: str, payload: dict) -> str:
    """Helper function to create structured SSE events"""
    import json
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

def extract_author_name_from_query(query: str) -> str:
    """Extract author name from chat query"""
    import re
    # Look for patterns like "tell me about John Smith" or "who is Jane Doe"
    patterns = [
        r'\b(?:tell me about|more about|info about|who is|what about)\s+([a-z]+\s+[a-z]+)',
        r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1).title()

    return "Author"

def yield_hybrid_stream(prompt: str, section: str):
    """Helper function to yield hybrid streaming events"""
    try:
        stream = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=2000,
            stream=True
        )

        current_content = ""
        last_boundary_pos = 0

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                token = chunk.choices[0].delta.content
                current_content += token

                # Stream the token immediately
                yield sse_event("token", {"text": token, "section": section})

                # Check for NEW paragraph boundaries (double newlines)
                boundary_pos = current_content.find('\n\n', last_boundary_pos)
                if boundary_pos != -1:
                    yield sse_event("paragraph_boundary", {"section": section})
                    last_boundary_pos = boundary_pos + 2

        # Send completion signal
        yield sse_event("done", {})

    except Exception as e:
        print(f"🚨 ERROR in yield_hybrid_stream: {str(e)}")
        import traceback
        traceback.print_exc()
        yield sse_event("error", {"message": f"Streaming error: {str(e)}"})

def generate_kol_analysis_streaming(
    filtered_df: pd.DataFrame,
    top_authors_table: pd.DataFrame,
    ta_filter: str = "All"
):
    """
    Multi-pass streaming KOL analysis using the working backup approach.
    Uses multiple small API calls instead of one massive call to stay under token limits.
    """
    if client is None:
        yield "data: Error: OpenAI client not initialized\n\n"
        return

    try:
        # Send immediate heartbeat to prevent proxy timeout
        yield sse_event("status", {"message": "⏳ Starting KOL analysis..."})

        # Prepare data summaries
        top_15_authors = top_authors_table.head(15)['Authors'].tolist()
        total_authors = len(top_15_authors)
        ta_context = f" in {ta_filter}" if ta_filter != "All" else " across all therapeutic areas"
        abstracts_count = len(filtered_df)

        # Extract actual research themes from abstract titles
        sample_titles = filtered_df['Title'].head(20).tolist()
        top_institutions = filtered_df['Institutions'].str.split(';').explode().value_counts().head(10).index.tolist()

        # Emit report title
        yield sse_event("heading", {"level": 1, "text": "👥 KOL Analysis — Data-Driven Intelligence Report"})

        # Emit the top authors table FIRST (so users see data immediately)
        authors_table_data = top_authors_table.head(15).to_dict('records')
        yield sse_event("table", {
            "title": "Top Authors by Abstract Count",
            "rows": authors_table_data
        })

        # Emit executive summary heading
        yield sse_event("heading", {"level": 2, "text": "Executive Summary"})

        # Generate executive summary paragraphs
        executive_summary_prompt = f"""Provide a comprehensive executive summary of KOL activity at this conference{ta_context}.

Conference Data Overview:
- {total_authors} top authors identified across {abstracts_count} abstracts
- Leading authors: {', '.join(top_15_authors[:5])}
- Top institutions: {', '.join(top_institutions[:5])}

Sample Research Themes (from abstract titles):
{chr(10).join([f"• {title}" for title in sample_titles[:10]])}

Write ONE comprehensive paragraph (4-6 sentences) that covers:
- Overall KOL activity level, research volume, and key therapeutic focus areas
- Dominant research themes, biomarker patterns, and institutional leadership
- Strategic engagement opportunities for EMD Serono medical affairs

Make it flow naturally as a single, well-structured paragraph without internal breaks."""

        # Stream executive summary tokens in real-time
        summary_stream = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[
                {"role": "system", "content": "You are a medical affairs analyst. Provide comprehensive analysis immediately without delay. Start your response right away."},
                {"role": "user", "content": executive_summary_prompt}
            ],
            max_completion_tokens=500,  # Increased for executive summary
            stream=True
        )

        # Stream tokens and detect paragraph boundaries
        current_content = ""
        last_boundary_pos = 0
        for chunk in summary_stream:
            if chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                current_content += token

                # Stream the token immediately
                yield sse_event("token", {"text": token, "section": "executive_summary"})

                # Check for NEW paragraph boundaries (double newlines) after last detected position
                boundary_pos = current_content.find('\n\n', last_boundary_pos)
                if boundary_pos != -1:
                    # Send paragraph boundary signal only once
                    yield sse_event("paragraph_boundary", {"section": "executive_summary"})
                    last_boundary_pos = boundary_pos + 2  # Move past the boundary

        # Final boundary for executive summary completion
        yield sse_event("section_boundary", {"section": "executive_summary"})

        # Emit KOL profiles heading
        yield sse_event("heading", {"level": 2, "text": "Individual KOL Profiles (Top 15 Most Prolific)"})

        # Extract specific abstracts for each top KOL
        kol_specific_data = {}
        for author in top_15_authors:
            author_mask = filtered_df['Authors'].str.contains(re.escape(author), case=False, na=False)
            author_abstracts = filtered_df[author_mask]
            if not author_abstracts.empty:
                kol_specific_data[author] = author_abstracts.to_csv(index=False)

        print(f"🔧 Starting KOL analysis for {len(top_15_authors)} authors")
        print(f"🔧 KOL data available for: {len(kol_specific_data)} authors")

        # Process each KOL
        for i, author in enumerate(top_15_authors, 1):
            if author in kol_specific_data:
                individual_prompt = f"""Analyze this specific KOL using the conference data and systematic framework.

KOL NAME: {author}

ALL ABSTRACTS FOR THIS KOL:
{kol_specific_data[author]}

SYSTEMATIC ANALYSIS FRAMEWORK:
a) WHO: Name, primary institution(s), geographic location (from Institutions column)
b) RESEARCH INTERESTS: What therapeutic areas, drugs, mechanisms they focus on (from Title column + your knowledge)
c) HCP COLLABORATIONS: Which other top authors they co-author with (from Authors column)
d) PHARMA COLLABORATIONS: Which pharmaceutical/biotech companies appear in their Institutions column

Write ONE comprehensive paragraph that flows naturally covering all four framework elements. Use ONLY the actual data provided above. Cite specific Abstract # examples. Be systematic and thorough."""

                try:
                    print(f"🔧 Starting streaming for KOL {i}/{len(top_15_authors)}: {author}")

                    # Send progress update to keep connection alive
                    yield sse_event("progress", {
                        "message": f"Processing KOL {i}/{len(top_15_authors)}: {author}",
                        "current": i,
                        "total": len(top_15_authors)
                    })

                    # Signal start of new KOL profile
                    yield sse_event("kol_start", {"author": author})

                    # Stream the analysis token by token
                    print(f"🔧 Prompt length: {len(individual_prompt)} chars")
                    stream = client.chat.completions.create(
                        model="gpt-5-mini",
                        reasoning_effort="minimal",
                        verbosity="low",
                        messages=[
                            {"role": "system", "content": "You are a medical affairs analyst. Provide comprehensive analysis immediately without delay. Start your response right away."},
                            {"role": "user", "content": individual_prompt}
                        ],
                                    max_completion_tokens=600,  # Increased for more complete responses
                        stream=True
                    )

                    profile_content = ""
                    token_count = 0
                    last_token_time = time.time()

                    for chunk in stream:
                        if chunk.choices[0].delta.content is not None:
                            token = chunk.choices[0].delta.content
                            profile_content += token
                            token_count += 1
                            last_token_time = time.time()

                            # Stream each token with author context
                            yield sse_event("token", {
                                "text": token,
                                "section": "kol_profile",
                                "author": author
                            })

                        # Send keep-alive ping every 5 seconds during streaming
                        elif time.time() - last_token_time > 5:
                            yield sse_event("ping", {"timestamp": int(time.time())})
                            last_token_time = time.time()

                    print(f"🔧 Completed streaming for {author}: {token_count} tokens, {len(profile_content)} chars")

                    # Signal end of this KOL profile
                    yield sse_event("kol_end", {"author": author})

                except Exception as e:
                    print(f"🚨 ERROR analyzing {author}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    error_msg = f"Analysis unavailable: {str(e)[:100]}..."

                    # Signal start and stream error message
                    yield sse_event("kol_start", {"author": author})
                    yield sse_event("token", {
                        "text": error_msg,
                        "section": "kol_profile",
                        "author": author
                    })
                    yield sse_event("kol_end", {"author": author})
            else:
                # Handle authors with no abstract data
                print(f"⚠️ No abstract data found for {author}")
                no_data_msg = f"No abstracts found for this author in the filtered dataset."

                # Signal start and stream no data message
                yield sse_event("kol_start", {"author": author})
                yield sse_event("token", {
                    "text": no_data_msg,
                    "section": "kol_profile",
                    "author": author
                })
                yield sse_event("kol_end", {"author": author})

        # Send completion signal
        yield sse_event("done", {})

    except Exception as e:
        yield sse_event("error", {"message": f"Error generating KOL analysis: {str(e)}"})

def generate_competitor_analysis_streaming(
    filtered_df: pd.DataFrame,
    comp_table: pd.DataFrame,
    emerg_table: pd.DataFrame,
    ta_filter: str = "All"
):
    """
    Token-by-token streaming competitor analysis using AI-first approach.
    """
    if client is None:
        yield "data: Error: OpenAI client not initialized\n\n"
        return

    try:
        # Prepare context data
        ta_context = f" in {ta_filter}" if ta_filter != "All" else " across all therapeutic areas"
        abstracts_count = len(filtered_df)

        # Emit report title
        yield sse_event("heading", {"level": 1, "text": "🏆 Competitor Intelligence — Strategic Analysis Report"})

        # Emit tables FIRST (so users see data immediately)
        if not comp_table.empty:
            comp_table_data = comp_table.to_dict('records')
            yield sse_event("table", {
                "title": "Competitor Abstracts",
                "rows": comp_table_data
            })

        if not emerg_table.empty:
            emerg_table_data = emerg_table.to_dict('records')
            yield sse_event("table", {
                "title": "Emerging Threats",
                "rows": emerg_table_data
            })

        # Build context for AI analysis
        tables_context = ""
        if not comp_table.empty:
            tables_context += f"\n\n=== Competitor Abstracts ===\n{comp_table.to_csv(index=False)}"
        if not emerg_table.empty:
            tables_context += f"\n\n=== Emerging Threats ===\n{emerg_table.to_csv(index=False)}"

        # Use the AI prompt from PLAYBOOKS
        competitor_prompt = f"""{PLAYBOOKS["competitor"]["ai_prompt"]}

CONFERENCE DATA TABLES:{tables_context}

Therapeutic Area Filter: {ta_filter}

Write a comprehensive, natural intelligence report based on this data."""

        # Stream the analysis in real-time
        stream = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[{"role": "user", "content": competitor_prompt}],
            max_completion_tokens=3000,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                token = chunk.choices[0].delta.content

                # Stream each token
                yield sse_event("token", {
                    "text": token,
                    "section": "competitor_analysis"
                })

        # Signal end of stream
        yield sse_event("end", {"message": "Competitor analysis complete"})

    except Exception as e:
        print(f"🚨 ERROR in competitor streaming: {str(e)}")
        import traceback
        traceback.print_exc()
        yield f"data: Error generating competitor analysis: {str(e)}\n\n"

def generate_institution_analysis_streaming(
    filtered_df: pd.DataFrame,
    top_institutions_table: pd.DataFrame,
    ta_filter: str = "All"
):
    """
    Token-by-token streaming institution analysis using AI-first approach.
    """
    if client is None:
        yield "data: Error: OpenAI client not initialized\n\n"
        return

    try:
        # Prepare context data
        ta_context = f" in {ta_filter}" if ta_filter != "All" else " across all therapeutic areas"
        abstracts_count = len(filtered_df)

        # Emit report title
        yield sse_event("heading", {"level": 1, "text": "🏥 Institution Analysis — Research Landscape Report"})

        # Emit tables FIRST (so users see data immediately)
        if not top_institutions_table.empty:
            institutions_table_data = top_institutions_table.to_dict('records')
            yield sse_event("table", {
                "title": "Top Institutions",
                "rows": institutions_table_data
            })

        # Build context for AI analysis
        tables_context = ""
        if not top_institutions_table.empty:
            tables_context += f"\n\n=== Top Institutions ===\n{top_institutions_table.to_csv(index=False)}"

        # Use the AI prompt from PLAYBOOKS
        institution_prompt = f"""{PLAYBOOKS["institution"]["ai_prompt"]}

CONFERENCE DATA TABLES:{tables_context}

Therapeutic Area Filter: {ta_filter}

Write a comprehensive, natural intelligence report based on this data."""

        # Stream the analysis in real-time
        stream = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[{"role": "user", "content": institution_prompt}],
            max_completion_tokens=3000,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                token = chunk.choices[0].delta.content

                # Stream each token
                yield sse_event("token", {
                    "text": token,
                    "section": "institution_analysis"
                })

        # Signal end of stream
        yield sse_event("end", {"message": "Institution analysis complete"})

    except Exception as e:
        print(f"🚨 ERROR in institution streaming: {str(e)}")
        import traceback
        traceback.print_exc()
        yield f"data: Error generating institution analysis: {str(e)}\n\n"

def generate_insights_analysis_streaming(
    filtered_df: pd.DataFrame,
    biomarker_moa_table: pd.DataFrame,
    ta_filter: str = "All"
):
    """
    Token-by-token streaming insights analysis using AI-first approach.
    """
    if client is None:
        yield "data: Error: OpenAI client not initialized\n\n"
        return

    try:
        # Prepare context data
        ta_context = f" in {ta_filter}" if ta_filter != "All" else " across all therapeutic areas"
        abstracts_count = len(filtered_df)

        # Emit report title
        yield sse_event("heading", {"level": 1, "text": "🧭 Insights & Trends — Strategic Intelligence Report"})

        # Emit tables FIRST (so users see data immediately)
        if not biomarker_moa_table.empty:
            biomarker_table_data = biomarker_moa_table.to_dict('records')
            yield sse_event("table", {
                "title": "Biomarker & MOA Analysis",
                "rows": biomarker_table_data
            })

        # Build context for AI analysis
        tables_context = ""
        if not biomarker_moa_table.empty:
            tables_context += f"\n\n=== Biomarker & MOA Analysis ===\n{biomarker_moa_table.to_csv(index=False)}"

        # Use the AI prompt from PLAYBOOKS
        insights_prompt = f"""{PLAYBOOKS["insights"]["ai_prompt"]}

CONFERENCE DATA TABLES:{tables_context}

Therapeutic Area Filter: {ta_filter}

Write a comprehensive, natural intelligence report based on this data."""

        # Stream the analysis in real-time
        stream = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[{"role": "user", "content": insights_prompt}],
            max_completion_tokens=3000,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                token = chunk.choices[0].delta.content

                # Stream each token
                yield sse_event("token", {
                    "text": token,
                    "section": "insights_analysis"
                })

        # Signal end of stream
        yield sse_event("end", {"message": "Insights analysis complete"})

    except Exception as e:
        print(f"🚨 ERROR in insights streaming: {str(e)}")
        import traceback
        traceback.print_exc()
        yield f"data: Error generating insights analysis: {str(e)}\n\n"

def generate_strategy_analysis_streaming(
    filtered_df: pd.DataFrame,
    ta_filter: str = "All"
):
    """
    Token-by-token streaming strategy analysis using AI-first approach.
    """
    if client is None:
        yield "data: Error: OpenAI client not initialized\n\n"
        return

    try:
        # Prepare context data
        ta_context = f" in {ta_filter}" if ta_filter != "All" else " across all therapeutic areas"
        abstracts_count = len(filtered_df)

        # Emit report title
        yield sse_event("heading", {"level": 1, "text": "📋 Strategic Recommendations — Medical Affairs Action Plan"})

        # Build basic context from the dataset
        sample_abstracts = filtered_df.head(10)[["Abstract #", "Title"]].to_csv(index=False)
        tables_context = f"\n\n=== Sample Conference Data ({abstracts_count} total abstracts) ===\n{sample_abstracts}"

        # Use the AI prompt from PLAYBOOKS
        strategy_prompt = f"""{PLAYBOOKS["strategy"]["ai_prompt"]}

CONFERENCE DATA TABLES:{tables_context}

Therapeutic Area Filter: {ta_filter}

Write a comprehensive, natural intelligence report based on this data."""

        # Stream the analysis in real-time
        stream = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[{"role": "user", "content": strategy_prompt}],
            max_completion_tokens=3000,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                token = chunk.choices[0].delta.content

                # Stream each token
                yield sse_event("token", {
                    "text": token,
                    "section": "strategy_analysis"
                })

        # Signal end of stream
        yield sse_event("end", {"message": "Strategy analysis complete"})

    except Exception as e:
        print(f"🚨 ERROR in strategy streaming: {str(e)}")
        import traceback
        traceback.print_exc()
        yield f"data: Error generating strategy analysis: {str(e)}\n\n"

def format_evidence_for_prompt(evidence_pack: Dict[str, Any]) -> str:
    """Format evidence pack for inclusion in prompts."""
    formatted_evidence = []

    for key, data in evidence_pack.items():
        if hasattr(data, 'to_csv'):
            # It's a DataFrame
            csv_data = data.head(30).to_csv(index=False)
            formatted_evidence.append(f"**{key.upper()} TABLE:**\n{csv_data}")
        elif isinstance(data, list) and len(data) > 0:
            # It's a list of records
            formatted_evidence.append(f"**{key.upper()}:**\n{json.dumps(data[:20], indent=2)}")
        else:
            formatted_evidence.append(f"**{key.upper()}:** {str(data)}")

    return "\n\n".join(formatted_evidence)

# =========================
# AI: Strict Playbook Runner
# =========================
def run_playbook_ai(
    playbook_key: str,
    ta_filter: str,
    user_query: str,
    filtered_df: pd.DataFrame,
    tables_for_prompt: Dict[str, pd.DataFrame],
    rag_snippets: List[str]
) -> str:
    if client is None:
        return "Error: OpenAI client not initialized. Please ensure OPENAI_API_KEY is set."

    pb = PLAYBOOKS[playbook_key]

    # AI-FIRST APPROACH: Check if this playbook has an ai_prompt (Phase 2 implementation)
    if "ai_prompt" in pb and pb["ai_prompt"]:
        # Build table data context for the AI
        tables_context = ""
        for table_name, table_df in tables_for_prompt.items():
            if not table_df.empty:
                tables_context += f"\n\n=== {table_name} ===\n{table_df.to_csv(index=False)}"

        # Build RAG context if available
        rag_context = ""
        if rag_snippets:
            rag_context = f"\n\nRelevant conference context:\n" + "\n".join(rag_snippets)

        # Create the AI prompt with all context
        ai_prompt = f"""{pb["ai_prompt"]}

CONFERENCE DATA TABLES:{tables_context}

{rag_context}

Therapeutic Area Filter: {ta_filter}

Write a comprehensive, natural intelligence report based on this data."""

        try:
            response = client.chat.completions.create(
                model="gpt-5-mini",
                reasoning_effort="minimal",
                verbosity="low",
                messages=[{"role": "user", "content": ai_prompt}],
                    max_completion_tokens=3000
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error generating AI response: {str(e)}"

    # AI-Enhanced Framework Approach: Intelligent adaptation based on available data
    ai_enhanced_frameworks = {
        "competitor": {
            "focus": "competitive intelligence and market dynamics",
            "core_elements": [
                "Executive Summary (competitive focus)",
                "Avelumab presence and positioning at this conference",
                "Competitor activity analysis with specific examples",
                "Strategic implications for competitive positioning"
            ],
            "data_requirements": "competitor mentions, drug activity, positioning insights"
        },
        "kol": {
            "focus": "key opinion leader identification and activity analysis",
            "core_elements": [
                "Executive Summary (KOL and author activity focus)",
                "Most active authors and their research themes",
                "Collaboration patterns and institutional networks",
                "Notable research areas and trending topics among KOLs"
            ],
            "data_requirements": "author activity data, research focus areas, institutional affiliations"
        },
        "institution": {
            "focus": "institutional research activity and capabilities analysis",
            "core_elements": [
                "Executive Summary (institutional research focus)",
                "Most active institutions and their research volume",
                "Research focus areas by institution",
                "Geographic distribution and collaboration patterns"
            ],
            "data_requirements": "institutional activity data, research themes, geographic insights"
        },
        "insights": {
            "focus": "scientific trends and emerging patterns analysis",
            "core_elements": [
                "Executive Summary (scientific trends focus)",
                "Emerging biomarker and mechanism of action patterns",
                "Treatment paradigm evolution signals",
                "Evidence quality and clinical translation potential"
            ],
            "data_requirements": "biomarker mentions, MOA patterns, clinical trial phases"
        },
        "strategy": {
            "focus": "strategic implications for medical affairs and portfolio",
            "core_elements": [
                "Executive Summary (strategic implications focus)",
                "Positioning opportunities versus standard of care",
                "Evidence themes to amplify",
                "Portfolio adjacency opportunities"
            ],
            "data_requirements": "competitive landscape insights, clinical evidence themes"
        }
    }

    framework = ai_enhanced_frameworks[playbook_key]

    # Core guidelines that apply to all playbooks
    core_guidelines = [
        "Focus specifically on the stated analysis focus",
        "Adapt the framework intelligently based on available data",
        "Always cite Abstract # when referencing specific studies",
        "Do NOT invent statistics - only use data from provided context",
        "If insufficient data exists for a framework element, acknowledge this and focus on what is available",
        "Keep responses relevant to the specific analytical focus",
        "Avoid generic therapeutic landscape discussions unless directly relevant to the analysis type"
    ]

    # Build context for AI-Enhanced Analysis
    context_data = []
    rag_context = "\n".join(f"- {s}" for s in rag_snippets) if rag_snippets else "No specific context snippets available."

    # Intelligently gather relevant data based on analysis type
    if playbook_key == "competitor":
        # For competitor analysis, focus on competitive activity
        avelu_mask = safe_contains(filtered_df["Title"], r"avelumab|bavencio", regex=True) | \
                     safe_contains(filtered_df["Authors"], r"avelumab|bavencio", regex=True)
        avelu_df = filtered_df.loc[avelu_mask, ["Abstract #", "Title"]].drop_duplicates(subset=["Abstract #"])

        if not avelu_df.empty:
            context_data.append(f"Avelumab Presence: {len(avelu_df)} abstracts found")
            for _, row in avelu_df.head(5).iterrows():
                context_data.append(f"- Abstract #{row['Abstract #']}: {row['Title']}")
        else:
            context_data.append("Avelumab Presence: No direct mentions found in conference abstracts")

        comp_df = tables_for_prompt.get("competitor_abstracts", pd.DataFrame())
        if comp_df is not None and not comp_df.empty:
            comp_summary = comp_df.groupby("Competitor")["Abstract #"].nunique().head(8)
            context_data.append("Competitor Activity:")
            for comp, count in comp_summary.items():
                context_data.append(f"- {comp}: {count} abstracts")

    elif playbook_key in ["kol", "institution"]:
        # For KOL/Institution analysis, focus on activity data
        if playbook_key == "kol":
            table_key = "top_authors"
            activity_type = "Author"
        else:
            table_key = "top_institutions"
            activity_type = "Institution"

        activity_df = tables_for_prompt.get(table_key, pd.DataFrame())
        if activity_df is not None and not activity_df.empty:
            context_data.append(f"Top {activity_type} Activity:")
            for _, row in activity_df.head(10).iterrows():
                if playbook_key == "kol":
                    context_data.append(f"- {row['Authors']}: {row['Unique Abstracts']} abstracts ({row['Institutions']})")
                else:
                    context_data.append(f"- {row['Institutions']}: {row['#Unique Abstracts']} abstracts (Focus: {row['Main focus area']})")
        else:
            context_data.append(f"No {activity_type.lower()} activity data available in current dataset")

    else:
        # For insights/strategy, use available tables
        for key, df_tbl in tables_for_prompt.items():
            if df_tbl is not None and not df_tbl.empty:
                context_data.append(f"{key.replace('_', ' ').title()}: {len(df_tbl)} entries available")

    available_data = "\n".join(context_data) if context_data else "Limited conference data available for this analysis type."

    # Medical context (keep the good stuff)
    ta_context = {
        "Bladder Cancer": {
            "key_trends": "EV+P as new 1L SOC, ADC dominance, avelumab maintenance positioning, ctDNA/biomarker evolution",
            "competitive_landscape": "EV+P disruption, sacituzumab govitecan combinations, HER2-targeted strategies",
            "avelumab_context": "Established 1L maintenance standard, evolving role post-EV+P era"
        },
        "Renal Cell Carcinoma": {
            "key_trends": "IO+TKI combinations dominance, VEGF pathway evolution, biomarker development",
            "competitive_landscape": "Established IO+TKI standards, cabozantinib strength, novel combinations",
            "avelumab_context": "Investigational in combinations, not yet standard therapy"
        }
    }

    current_context = ta_context.get(ta_filter, {
        "key_trends": "Context-dependent trends",
        "competitive_landscape": "Multiple therapeutic approaches",
        "avelumab_context": "Variable positioning by indication"
    })

    # AI-Enhanced Prompt: Intelligent and Adaptive
    prompt = f"""
You are an expert medical affairs analyst for EMD Serono providing {framework['focus']} for the {ta_filter} therapeutic area.

## Analysis Focus: {framework['focus']}

## Core Framework Elements (adapt intelligently based on available data):
{chr(10).join(f"- {element}" for element in framework['core_elements'])}

## Available Conference Data:
{available_data}

## Relevant Conference Context:
{rag_context}

## Therapeutic Area Context for {ta_filter}:
- Key Trends: {current_context['key_trends']}
- Competitive Landscape: {current_context['competitive_landscape']}
- Avelumab Context: {current_context['avelumab_context']}

## Instructions:
{chr(10).join(f"- {guideline}" for guideline in core_guidelines)}

## Data Requirements for This Analysis:
{framework['data_requirements']}

Generate a comprehensive {framework['focus']} analysis that intelligently adapts the framework based on the available data. If certain framework elements cannot be addressed due to insufficient data, acknowledge this and focus on what insights can be provided from the available conference information.

## Response Requirements:
- Structure your response using the framework elements as guidance, but adapt intelligently
- Always cite Abstract # when referencing specific conference presentations
- Be specific about what data is available vs. what is missing
- Focus on actionable insights relevant to the stated analysis focus
- Maintain medical affairs professionalism while being conversational and helpful
- Do NOT invent statistics or data not present in the provided context
"""
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[
                {"role": "system", "content": f"You are an expert medical affairs analyst providing {framework['focus']} for EMD Serono. Focus on delivering relevant, data-driven insights that directly address the analysis objectives."},
                {"role": "user", "content": prompt}
            ],
            max_completion_tokens=1600,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error generating AI-enhanced analysis: {e}")
        return f"Error generating analysis: {str(e)}"

# =========================
# Enhanced AI Response Generation (New Architecture)
# =========================

def generate_intelligent_response(query: str, plan: QueryPlan, context: ContextPackage, ta_filter: str) -> Tuple[str, List[Tuple[str, pd.DataFrame, str]]]:
    """
    Generate truly flexible AI response based on user intent and available context.
    No rigid frameworks - just intelligent, helpful responses.
    """
    if client is None:
        return "Error: OpenAI client not initialized. Cannot generate intelligent response.", []

    # Build context information
    context_info = []
    tables_to_attach = []

    # Handle specific response types differently
    if plan.response_type == "data_table":
        # For quantitative requests like "top 20 authors" - prioritize tables with brief context
        return handle_data_table_request(query, plan, context, ta_filter)

    elif plan.response_type == "specific_lookup":
        # For specific lookups like "show me John Smith's work" - focused data with explanation
        return handle_specific_lookup_request(query, plan, context, ta_filter)

    # For strategic_analysis or informational_narrative - build comprehensive context
    if context.semantic_results is not None and not context.semantic_results.empty:
        abstracts_summary = []
        for _, row in context.semantic_results.head(8).iterrows():
            abstracts_summary.append(f"Abstract #{row['Abstract #']}: {row['Title']}")
        context_info.append("Relevant abstracts:\n" + "\n".join(f"- {a}" for a in abstracts_summary))
        tables_to_attach.append(("🔎 Relevant Abstracts", context.semantic_results.head(15), "data"))

    if context.competitor_data is not None and not context.competitor_data.empty:
        comp_summary = []
        for _, row in context.competitor_data.head(6).iterrows():
            comp_summary.append(f"{row['Competitor']}: {row['Title']} (Abstract #{row['Abstract #']})")
        context_info.append("Competitor activity:\n" + "\n".join(f"- {c}" for c in comp_summary))
        tables_to_attach.append(("🏆 Competitor Analysis", context.competitor_data, "data"))

    if context.author_data is not None and not context.author_data.empty:
        tables_to_attach.append(("👤 Author Analysis", context.author_data, "data"))

    # Build flexible AI prompt based on what user actually wants
    system_prompt = f"""You are a helpful medical affairs assistant providing information about conference data. Your goal is to directly answer the user's question in the most helpful way possible.

User Intent: {plan.user_intent}
Response Approach: {plan.response_approach}

Guidelines:
- Answer the user's question directly and helpfully
- Use a conversational, informative tone
- Cite Abstract # when referencing specific studies
- If you have quantitative data tables, mention them but don't repeat the data in text
- Be concise but thorough
- Don't force rigid analytical frameworks unless the user specifically asks for strategic analysis
- If data is limited, say so clearly and explain what you can provide instead"""

    # Build medical context if available
    medical_context = ""
    if context.medical_context:
        medical_context = "\n".join([f"{key}: {value.strip()}" for key, value in context.medical_context.items()])

    user_prompt = f"""
User Question: "{query}"
Therapeutic Area Filter: {ta_filter}

{f"Medical Context: {medical_context}" if medical_context else ""}

Available Conference Data:
{chr(10).join(context_info) if context_info else "No specific conference data found for this query in the current filter."}

Please provide a helpful, direct response to the user's question. Focus on being informative and useful rather than following a rigid analytical framework.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_completion_tokens=800,
        )

        response_text = response.choices[0].message.content
        return response_text, tables_to_attach

    except Exception as e:
        error_msg = f"Error generating response: {str(e)}"
        print(error_msg)
        return error_msg, tables_to_attach

def handle_data_table_request(query: str, plan: QueryPlan, context: ContextPackage, ta_filter: str) -> Tuple[str, List[Tuple[str, pd.DataFrame, str]]]:
    """
    Handle requests for quantitative data tables like "top 20 authors", "most active scientists"
    Returns brief context + the actual data table
    """
    tables_to_attach = []

    # Determine what type of table the user wants
    entities = plan.primary_entities
    query_lower = query.lower()

    # Author-related requests
    if (any(term in query_lower for term in ["author", "scientist", "researcher", "investigator", "people"]) or
        entities.get("authors")):

        # Extract number from query (default 20)
        n = extract_number_default(query, 20)

        # Get the current filtered data
        if ta_filter == "Bladder Cancer":
            current_df = df_global[df_global["ta"] == "bladder"].copy()
        elif ta_filter == "Renal Cell Carcinoma":
            current_df = df_global[df_global["ta"] == "renal"].copy()
        else:
            current_df = df_global.copy()

        # For data table requests, users might want individual abstracts OR summary stats
        # Let's provide both: summary stats + recent individual abstracts from top authors
        top_authors_summary = get_top_authors(df_sig(current_df), current_df, min(n, 15))

        if not top_authors_summary.empty:
            # Add summary table
            tables_to_attach.append((f"👥 Top {len(top_authors_summary)} Authors (Summary)", top_authors_summary, "data"))

            # Also add individual abstracts from these top authors
            top_author_names = top_authors_summary['Authors'].head(10).tolist()
            individual_abstracts = []

            for author in top_author_names:
                pat = r"\b" + re.escape(author) + r"\b"
                mask = safe_contains(current_df["Authors"], pat, regex=True)
                author_abstracts = current_df.loc[mask, ["Abstract #", "Poster #", "Title", "Authors", "Institutions"]].drop_duplicates(subset=["Abstract #"])
                if not author_abstracts.empty:
                    individual_abstracts.append(author_abstracts.head(2))  # Max 2 per author

            if individual_abstracts:
                combined_abstracts = pd.concat(individual_abstracts, ignore_index=True).drop_duplicates(subset=["Abstract #"])
                # Ensure correct column order
                combined_abstracts = combined_abstracts[["Abstract #", "Poster #", "Title", "Authors", "Institutions"]]
                tables_to_attach.append((f"📄 Individual Abstracts from Top Authors", combined_abstracts, "data"))

            response = f"Here are the **top {len(top_authors_summary)} most active authors** in {ta_filter} based on unique abstracts at this conference. The first table shows summary statistics, and the second shows individual abstracts from these top authors."
        else:
            response = f"No author data found for {ta_filter} in the current dataset."

    # Institution-related requests
    elif (any(term in query_lower for term in ["institution", "center", "hospital", "university", "organization"]) or
          entities.get("institutions")):

        n = extract_number_default(query, 20)

        if ta_filter == "Bladder Cancer":
            current_df = df_global[df_global["ta"] == "bladder"].copy()
        elif ta_filter == "Renal Cell Carcinoma":
            current_df = df_global[df_global["ta"] == "renal"].copy()
        else:
            current_df = df_global.copy()

        # Similar approach for institutions - summary + individual abstracts
        top_institutions_summary = get_top_institutions(df_sig(current_df), current_df, min(n, 15))

        if not top_institutions_summary.empty:
            # Add summary table
            tables_to_attach.append((f"🏥 Top {len(top_institutions_summary)} Institutions (Summary)", top_institutions_summary, "data"))

            # Also add individual abstracts from these top institutions
            top_institution_names = top_institutions_summary['Institutions'].head(8).tolist()
            institutional_abstracts = []

            for institution in top_institution_names:
                mask = safe_contains(current_df["Institutions"], institution, regex=False)
                inst_abstracts = current_df.loc[mask, ["Abstract #", "Poster #", "Title", "Authors", "Institutions"]].drop_duplicates(subset=["Abstract #"])
                if not inst_abstracts.empty:
                    institutional_abstracts.append(inst_abstracts.head(3))  # Max 3 per institution

            if institutional_abstracts:
                combined_inst_abstracts = pd.concat(institutional_abstracts, ignore_index=True).drop_duplicates(subset=["Abstract #"])
                # Ensure correct column order
                combined_inst_abstracts = combined_inst_abstracts[["Abstract #", "Poster #", "Title", "Authors", "Institutions"]]
                tables_to_attach.append((f"📄 Individual Abstracts from Top Institutions", combined_inst_abstracts, "data"))

            response = f"Here are the **top {len(top_institutions_summary)} most active institutions** in {ta_filter} based on unique abstracts at this conference. The first table shows summary statistics, and the second shows individual abstracts from these institutions."
        else:
            response = f"No institution data found for {ta_filter} in the current dataset."

    # Drug/study-related requests
    elif any(term in query_lower for term in ["studies", "research", "abstracts", "work", "projects"]):
        # Use semantic search results if available
        if context.semantic_results is not None and not context.semantic_results.empty:
            # Ensure correct column order for semantic results
            studies_data = context.semantic_results.head(20).copy()
            if "Abstract #" in studies_data.columns:
                column_order = ["Abstract #", "Poster #", "Title", "Authors", "Institutions"]
                available_columns = [col for col in column_order if col in studies_data.columns]
                if len(available_columns) > 0:
                    studies_data = studies_data[available_columns]

            tables_to_attach.append(("🔬 Relevant Studies", studies_data, "data"))
            response = f"Found **{len(context.semantic_results)} relevant studies** matching your query in {ta_filter}. The table below shows the most relevant abstracts based on semantic similarity."
        else:
            response = f"No specific studies found matching your query in {ta_filter}."

    else:
        # Generic response - try to provide the best available data
        if context.semantic_results is not None and not context.semantic_results.empty:
            tables_to_attach.append(("🔎 Relevant Data", context.semantic_results.head(15), "data"))
            response = f"Here's the most relevant data I found for your query in {ta_filter}."
        else:
            response = f"I couldn't find specific data matching your request in {ta_filter}. Try refining your query or using different search terms."

    return response, tables_to_attach

def handle_specific_lookup_request(query: str, plan: QueryPlan, context: ContextPackage, ta_filter: str) -> Tuple[str, List[Tuple[str, pd.DataFrame, str]]]:
    """
    Handle specific lookup requests like "show me John Smith's work" or "tell me about Neil Milloy"
    Provides KOL analysis framework for authors and relevant tables.
    """
    tables_to_attach = []

    # Extract author name from query if possible
    author_name = None
    for entity_list in plan.primary_entities.values():
        for entity in entity_list:
            if len(entity.split()) >= 2:  # Likely a person's name (First Last)
                author_name = entity
                break
        if author_name:
            break

    # Use available context data - prioritize author data
    if context.author_data is not None and not context.author_data.empty:
        tables_to_attach.append(("📄 Author Studies", context.author_data, "data"))

        # Generate KOL analysis for the specific author
        if client and author_name:
            author_context = f"""Analyze {author_name} based on their conference research:

Conference data ({ta_filter}):
{context.author_data.to_csv(index=False)}

Provide a comprehensive analysis covering:
1. Research Profile & Expertise (focus areas, biomarkers, methodologies)
2. Collaboration Network & Industry Involvement (institutions, partnerships, alliances)
3. Strategic Value & Influence (leadership indicators, medical affairs opportunities)

Write natural, detailed paragraphs for each section. Be specific about their research contributions and strategic value for medical affairs."""

            try:
                author_analysis = client.chat.completions.create(
                    model="gpt-5-mini",
                    reasoning_effort="minimal",
                    verbosity="low",
                    messages=[{"role": "user", "content": author_context}],
                            max_completion_tokens=800
                )

                author_profile = author_analysis.choices[0].message.content
                response = f"## KOL Profile: {author_name}\n\n{author_profile}\n\n**Research Activity**: Found **{len(context.author_data)} abstracts** by this author in {ta_filter}. See detailed studies in the table below."

            except Exception as e:
                print(f"Error generating author analysis: {e}")
                response = f"## {author_name}\n\nFound **{len(context.author_data)} abstracts** by this author in {ta_filter}. The table below shows their research work at this conference."
        else:
            response = f"Found **{len(context.author_data)} abstracts** related to your lookup in {ta_filter}. The table below shows the relevant work."

    else:
        # NO AUTHOR DATA FOUND - simple, direct response
        if author_name:
            if ta_filter != "All":
                response = f"No studies found for {author_name} in {ta_filter}. Try changing the filter to 'All GU Cancers' to see if other studies are available."
            else:
                response = f"No studies found for {author_name} in the ASCO GU 2025 conference data."
        else:
            response = f"No specific results found for your lookup in {ta_filter}."

    return response, tables_to_attach

# =========================
# General (ad-hoc) answer (Legacy - Kept for Fallback)
# =========================
def run_general_ai(query: str, ta_filter: str, filtered_df: pd.DataFrame):
    if client is None:
        return "Error: OpenAI client not initialized. Cannot run general AI query.", pd.DataFrame()
    if collection is None:
        return "Error: Vector database not initialized. Cannot run general AI query.", pd.DataFrame()

    try:
        sr = semantic_search(query, ta_filter, n_results=12)
        ctx_df = format_search_results(sr)
        if ctx_df.empty:
            return ("I couldn’t find relevant abstracts for that query in the current TA filter. "
                    "Try refining your terms or using the sidebar playbooks."), pd.DataFrame()
        snippets = []
        for _, r in ctx_df.head(8).iterrows():
            snippets.append(f"Abstract #{r['Abstract #']}: {r['Title']}")
        rag = "\n".join(f"- {s}" for s in snippets)

        # Enhanced context for comprehensive responses
        ta_context = {
            "Bladder Cancer": {
                "avelumab_context": "Avelumab is established as standard 1L maintenance therapy post-platinum chemotherapy for non-progressive advanced urothelial carcinoma (JAVELIN Bladder 100). JAVELIN Bladder Medley shows avelumab+sacituzumab govitecan improves PFS vs avelumab monotherapy. Real-world data from Japan and Brazil confirm effectiveness.",
                "competitive_landscape": "EV+P is new 1L SOC. Other key players: sacituzumab govitecan, disitamab vedotin (HER2-targeted), nivolumab combinations.",
                "biomarkers": "Inflammatory markers (NLR, SII) predict avelumab maintenance outcomes. ctDNA emerging for monitoring."
            }
        }

        current_context = ta_context.get(ta_filter, {})
        context_info = ""
        if "avelumab" in query.lower() and ta_filter == "Bladder Cancer":
            context_info = f"\n\nBackground Context: {current_context.get('avelumab_context', '')}"

        prompt = f"""
You are a medical affairs expert providing comprehensive analysis for EMD Serono. Generate a substantive narrative response (3-4 paragraphs) that thoroughly addresses the user's question.

## Requirements:
- Provide detailed narrative analysis, not just data summaries
- Cite specific Abstract # when referencing conference presentations
- Include relevant background context about treatment landscape when appropriate
- Analyze implications and significance of the findings
- Do NOT invent counts; only cite numbers from the provided context
- If information is not available in the conference data, explicitly state so

User question: {query}
TA scope: {ta_filter}

Context from conference abstracts:
{rag}{context_info}

Generate a comprehensive narrative response that includes analysis, context, and implications of the conference data related to this question.
"""
        resp = client.chat.completions.create(
            model="gpt-5-mini",
            reasoning_effort="minimal",
            verbosity="low",
            messages=[
                {"role":"system","content":"You are a world-class medical affairs strategist providing comprehensive, analytical responses for EMD Serono."},
                {"role":"user","content":prompt}
            ],
            max_completion_tokens=800,
        )
        narrative = resp.choices[0].message.content
        hits = ctx_df[["Abstract #","Poster #","Title","Authors","Institutions"]].head(20)
        return narrative, hits
    except Exception as e:
        print(f"Error generating general AI answer: {e}")
        return f"Error generating answer: {str(e)}", pd.DataFrame()

# --- Global Initialization ---
def initialize_app_globals():
    global df_global, bladder_keywords_global, renal_keywords_global, csv_hash_global, collection

    if df_global is None:
        print("Initializing application globals (data and vector DB)...")
        try:
            df_global, bladder_keywords_global, renal_keywords_global, csv_hash_global = load_and_prepare_data()
            print(f"Data loaded successfully. CSV hash: {csv_hash_global[:8]}")
            collection = setup_vector_db(csv_hash_global)
            if collection is None:
                print("Warning: Vector database could not be fully set up. AI features may be limited.")
            return True
        except FileNotFoundError as e:
            print(f"FATAL ERROR: Data file not found: {e}")
            return False
        except Exception as e:
            print(f"FATAL ERROR during data/vector DB initialization: {e}")
            return False
    return True

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data_api():
    if not initialize_app_globals():
        return jsonify({"error": "Application data could not be loaded. Check server logs for details."}), 500

    ta_filter = request.args.get('ta', 'All')
    if ta_filter == "Bladder Cancer":
        filtered_df = df_global[df_global["ta"] == "bladder"].copy()
    elif ta_filter == "Renal Cell Carcinoma":
        filtered_df = df_global[df_global["ta"] == "renal"].copy()
    else:
        filtered_df = df_global.copy()

    display_columns = ["Abstract #", "Poster #", "Title", "Authors", "Institutions"]
    valid_columns = [col for col in display_columns if col in filtered_df.columns]
    return jsonify(filtered_df[valid_columns].to_dict('records'))

@app.route('/api/search')
def search_data_api():
    if not initialize_app_globals():
        return jsonify({"error": "Application data could not be loaded. Check server logs for details."}), 500

    ta_filter = request.args.get('ta', 'All')
    keyword = request.args.get('keyword', '').strip()
    search_field = request.args.get('field', 'All')

    if not keyword:
        return jsonify([])

    if ta_filter == "Bladder Cancer":
        current_df = df_global[df_global["ta"] == "bladder"].copy()
    elif ta_filter == "Renal Cell Carcinoma":
        current_df = df_global[df_global["ta"] == "renal"].copy()
    else:
        current_df = df_global.copy()

    if search_field == "All":
        mask = (
            safe_contains(current_df["Title"], keyword, regex=False) |
            safe_contains(current_df["Authors"], keyword, regex=False) |
            safe_contains(current_df["Institutions"], keyword, regex=False) |
            current_df["Abstract #"].astype(str).str.contains(keyword, case=False, na=False, regex=False) |
            current_df["Poster #"].astype(str).str.contains(keyword, case=False, na=False, regex=False)
        )
    elif search_field in ["Abstract #", "Poster #"]:
        mask = current_df[search_field].astype(str).str.contains(keyword, case=False, na=False, regex=False)
    elif search_field in current_df.columns:
        mask = safe_contains(current_df[search_field], keyword, regex=False)
    else:
        mask = pd.Series(False, index=current_df.index)

    display_columns = ["Abstract #", "Poster #", "Title", "Authors", "Institutions"]
    valid_columns = [col for col in display_columns if col in current_df.columns]
    search_results_df = current_df.loc[mask, valid_columns]
    return jsonify(search_results_df.to_dict('records'))

# API Endpoint to run a specific playbook
@app.route('/api/playbook/kol/stream', methods=['GET'])
def stream_kol_analysis():
    """
    Token-by-token streaming endpoint for KOL analysis.
    Returns Server-Sent Events with each token as it's generated.
    """
    if not initialize_app_globals():
        return "data: Error: Application data could not be loaded\n\n", 500, {'Content-Type': 'text/event-stream'}

    ta_filter = request.args.get('ta', 'All')

    if ta_filter == "Bladder Cancer":
        filtered_df_for_playbook = df_global[df_global["ta"] == "bladder"].copy()
    elif ta_filter == "Renal Cell Carcinoma":
        filtered_df_for_playbook = df_global[df_global["ta"] == "renal"].copy()
    else:
        filtered_df_for_playbook = df_global.copy()

    # Generate top authors table
    top_authors_table = get_top_authors(df_sig(filtered_df_for_playbook), filtered_df_for_playbook, 20)

    def generate():
        try:
            for token in generate_kol_analysis_streaming(filtered_df_for_playbook, top_authors_table, ta_filter):
                yield token
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)

@app.route('/api/playbook/kol/single', methods=['GET'])
def stream_single_kol():
    """
    Stream analysis for a single KOL. Returns quickly (under 30 seconds).
    Parameters: ta (therapeutic area), author (KOL name), index (position in list)
    """
    if not initialize_app_globals():
        return jsonify({"error": "Application data could not be loaded"}), 500

    ta_filter = request.args.get('ta', 'All')
    author_name = request.args.get('author', '')
    kol_index = request.args.get('index', '0')

    if not author_name:
        return jsonify({"error": "Author name required"}), 400

    # Filter data based on therapeutic area
    if ta_filter == "Bladder Cancer":
        filtered_df = df_global[df_global["ta"] == "bladder"].copy()
    elif ta_filter == "Renal Cell Carcinoma":
        filtered_df = df_global[df_global["ta"] == "renal"].copy()
    else:
        filtered_df = df_global.copy()

    def generate():
        try:
            # Send immediate heartbeat
            yield sse_event("status", {"message": f"⏳ Analyzing {author_name}..."})

            # Get author's publications
            author_data = filtered_df[filtered_df['Authors'].str.contains(author_name, case=False, na=False)]

            if author_data.empty:
                yield sse_event("kol_complete", {
                    "author": author_name,
                    "index": kol_index,
                    "content": f"No publications found for {author_name} in {ta_filter}."
                })
                return

            # Build analysis prompt
            abstracts_list = []
            for _, row in author_data.iterrows():
                abstract_entry = f"• {row['Title']}"
                if pd.notna(row['Institutions']):
                    institutions = row['Institutions'].split(';')[0]  # First institution
                    abstract_entry += f" ({institutions})"
                abstracts_list.append(abstract_entry)

            abstracts_text = "\n".join(abstracts_list[:10])  # Limit to 10 abstracts

            individual_prompt = f"""Analyze this KOL's research profile at ASCO GU 2025:

**KOL**: {author_name}
**Therapeutic Area**: {ta_filter}
**Publications** ({len(author_data)}):
{abstracts_text}

Provide a comprehensive analysis covering:
1. **Research Focus**: Primary areas of investigation
2. **Clinical Impact**: Significance of their work
3. **Collaboration Patterns**: Key institutional partnerships
4. **EMD Serono Relevance**: Potential for avelumab-related collaborations

Deliver insights in paragraph form, 150-200 words."""

            # Stream the AI response
            stream = client.chat.completions.create(
                model="gpt-5-mini",
                reasoning_effort="minimal",
                verbosity="low",
                messages=[
                    {"role": "system", "content": "You are a medical affairs analyst. Provide strategic insights immediately without delay."},
                    {"role": "user", "content": individual_prompt}
                ],
                max_completion_tokens=300,
                stream=True
            )

            profile_content = ""

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    profile_content += token
                    yield sse_event("token", {"token": token})

            # Send completion event
            yield sse_event("kol_complete", {
                "author": author_name,
                "index": kol_index,
                "content": profile_content
            })

        except Exception as e:
            yield sse_event("error", {"message": f"Error analyzing {author_name}: {str(e)}"})

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)

@app.route('/api/playbook/kol/list', methods=['GET'])
def get_kol_list():
    """Get the list of top 15 KOLs for progressive loading"""
    if not initialize_app_globals():
        return jsonify({"error": "Application data could not be loaded"}), 500

    ta_filter = request.args.get('ta', 'All')

    # Filter data based on therapeutic area
    if ta_filter == "Bladder Cancer":
        filtered_df = df_global[df_global["ta"] == "bladder"].copy()
    elif ta_filter == "Renal Cell Carcinoma":
        filtered_df = df_global[df_global["ta"] == "renal"].copy()
    else:
        filtered_df = df_global.copy()

    # Get top authors table
    top_authors_table = get_top_authors(df_sig(filtered_df), filtered_df, 20)
    top_15_authors = top_authors_table.head(15)['Authors'].tolist()

    # Return list with table data
    authors_table_data = top_authors_table.head(15).to_dict('records')

    return jsonify({
        "authors": top_15_authors,
        "table_data": authors_table_data,
        "total_count": len(top_15_authors)
    })

@app.route('/api/playbook/competitor/stream', methods=['GET'])
def stream_competitor_analysis():
    """
    Token-by-token streaming endpoint for competitor analysis.
    Returns Server-Sent Events with each token as it's generated.
    """
    if not initialize_app_globals():
        return "data: Error: Application data could not be loaded\n\n", 500, {'Content-Type': 'text/event-stream'}

    ta_filter = request.args.get('ta', 'All')

    if ta_filter == "Bladder Cancer":
        filtered_df_for_playbook = df_global[df_global["ta"] == "bladder"].copy()
    elif ta_filter == "Renal Cell Carcinoma":
        filtered_df_for_playbook = df_global[df_global["ta"] == "renal"].copy()
    else:
        filtered_df_for_playbook = df_global.copy()

    # Generate competitor tables (same logic as regular competitor endpoint)
    competitors_to_check = [
        ("Avelumab", ["avelumab", "bavencio"]),  # ADD OUR OWN DRUG FIRST!
        ("Enfortumab vedotin", ["enfortumab vedotin", "enfortumab", r"\bEV\b", "EV-302", "EV 302", "EV+P", "Padcev"]),
        ("Disitamab vedotin", ["disitamab vedotin", "disitamab", "RC48"]),
        ("Zelenectide pevedotin", ["zelenectide pevedotin", "zelenectide"]),
        ("Pembrolizumab", ["pembrolizumab", "keytruda"]),
        ("Nivolumab", ["nivolumab", "opdivo"]),
        ("Atezolizumab", ["atezolizumab", "tecentriq"]),
        ("Durvalumab", ["durvalumab", "imfinzi"]),
        ("Sacituzumab govitecan", ["sacituzumab govitecan", "sacituzumab", "govitecan", "trodelvy"]),
        ("Erdafitinib", ["erdafitinib", "balversa"]),
        ("EV + Pembrolizumab", [r"ev.*pembrolizumab", r"enfortumab.*pembrolizumab", "evp", r"EV\+P", r"EV.*\+.*P"]),
    ]
    comp_table, emerg_table = build_competitor_tables(
        df_sig(filtered_df_for_playbook), filtered_df_for_playbook, competitors_to_check
    )

    def generate():
        try:
            for token in generate_competitor_analysis_streaming(filtered_df_for_playbook, comp_table, emerg_table, ta_filter):
                yield token
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)

@app.route('/api/playbook/institution/stream', methods=['GET'])
def stream_institution_analysis():
    """
    Token-by-token streaming endpoint for institution analysis.
    Returns Server-Sent Events with each token as it's generated.
    """
    if not initialize_app_globals():
        return "data: Error: Application data could not be loaded\n\n", 500, {'Content-Type': 'text/event-stream'}

    ta_filter = request.args.get('ta', 'All')

    if ta_filter == "Bladder Cancer":
        filtered_df_for_playbook = df_global[df_global["ta"] == "bladder"].copy()
    elif ta_filter == "Renal Cell Carcinoma":
        filtered_df_for_playbook = df_global[df_global["ta"] == "renal"].copy()
    else:
        filtered_df_for_playbook = df_global.copy()

    # Generate top institutions table
    top_institutions_table = get_top_institutions(df_sig(filtered_df_for_playbook), filtered_df_for_playbook, 20)

    def generate():
        try:
            for token in generate_institution_analysis_streaming(filtered_df_for_playbook, top_institutions_table, ta_filter):
                yield token
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)

@app.route('/api/playbook/insights/stream', methods=['GET'])
def stream_insights_analysis():
    """
    Token-by-token streaming endpoint for insights analysis.
    Returns Server-Sent Events with each token as it's generated.
    """
    if not initialize_app_globals():
        return "data: Error: Application data could not be loaded\n\n", 500, {'Content-Type': 'text/event-stream'}

    ta_filter = request.args.get('ta', 'All')

    if ta_filter == "Bladder Cancer":
        filtered_df_for_playbook = df_global[df_global["ta"] == "bladder"].copy()
    elif ta_filter == "Renal Cell Carcinoma":
        filtered_df_for_playbook = df_global[df_global["ta"] == "renal"].copy()
    else:
        filtered_df_for_playbook = df_global.copy()

    # Generate biomarker MOA hits table
    biomarker_moa_table = get_biomarker_moa_hits(df_sig(filtered_df_for_playbook), filtered_df_for_playbook)

    def generate():
        try:
            for token in generate_insights_analysis_streaming(filtered_df_for_playbook, biomarker_moa_table, ta_filter):
                yield token
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)

@app.route('/api/playbook/strategy/stream', methods=['GET'])
def stream_strategy_analysis():
    """
    Token-by-token streaming endpoint for strategy analysis.
    Returns Server-Sent Events with each token as it's generated.
    """
    if not initialize_app_globals():
        return "data: Error: Application data could not be loaded\n\n", 500, {'Content-Type': 'text/event-stream'}

    ta_filter = request.args.get('ta', 'All')

    if ta_filter == "Bladder Cancer":
        filtered_df_for_playbook = df_global[df_global["ta"] == "bladder"].copy()
    elif ta_filter == "Renal Cell Carcinoma":
        filtered_df_for_playbook = df_global[df_global["ta"] == "renal"].copy()
    else:
        filtered_df_for_playbook = df_global.copy()

    # For strategy analysis, we use basic context data from the filtered dataset
    # No additional table preparation needed beyond the filtered dataframe

    def generate():
        try:
            for token in generate_strategy_analysis_streaming(filtered_df_for_playbook, ta_filter):
                yield token
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)

@app.route('/api/playbook/<playbook_key>', methods=['GET'])
def run_playbook_api_route(playbook_key):
    if not initialize_app_globals():
        return jsonify({"error": "Application data could not be loaded. Check server logs for details."}), 500

    ta_filter = request.args.get('ta', 'All')
    if playbook_key not in PLAYBOOKS:
        return jsonify({"error": "Invalid playbook key"}), 400

    if ta_filter == "Bladder Cancer":
        filtered_df_for_playbook = df_global[df_global["ta"] == "bladder"].copy()
    elif ta_filter == "Renal Cell Carcinoma":
        filtered_df_for_playbook = df_global[df_global["ta"] == "renal"].copy()
    else:
        filtered_df_for_playbook = df_global.copy()

    pb = PLAYBOOKS.get(playbook_key)
    tables_for_prompt: Dict[str, pd.DataFrame] = {}

    if playbook_key == "competitor":
        competitors_to_check = [
            ("Avelumab", ["avelumab", "bavencio"]),  # ADD OUR OWN DRUG FIRST!
            ("Enfortumab vedotin", ["enfortumab vedotin", "enfortumab", r"\bEV\b", "EV-302", "EV 302", "EV+P", "Padcev"]),
            ("Disitamab vedotin", ["disitamab vedotin", "disitamab", "RC48"]),
            ("Zelenectide pevedotin", ["zelenectide pevedotin", "zelenectide"]),
            ("Pembrolizumab", ["pembrolizumab", "keytruda"]),
            ("Nivolumab", ["nivolumab", "opdivo"]),
            ("Atezolizumab", ["atezolizumab", "tecentriq"]),
            ("Durvalumab", ["durvalumab", "imfinzi"]),
            ("Sacituzumab govitecan", ["sacituzumab govitecan", "sacituzumab", "govitecan", "trodelvy"]),
            ("Erdafitinib", ["erdafitinib", "balversa"]),
            ("EV + Pembrolizumab", [r"ev.*pembrolizumab", r"enfortumab.*pembrolizumab", "evp", r"EV\+P", r"EV.*\+.*P"]),
        ]
        comp_table, emerg_table = build_competitor_tables(
            df_sig(filtered_df_for_playbook), filtered_df_for_playbook, competitors_to_check
        )
        tables_for_prompt["competitor_abstracts"] = comp_table
        tables_for_prompt["emerging_threats"] = emerg_table

    elif playbook_key == "kol":
        tables_for_prompt["top_authors"] = get_top_authors(df_sig(filtered_df_for_playbook), filtered_df_for_playbook, 20)

    elif playbook_key == "institution":
        tables_for_prompt["top_institutions"] = get_top_institutions(df_sig(filtered_df_for_playbook), filtered_df_for_playbook, 20)

    elif playbook_key == "insights":
        tables_for_prompt["biomarker_moa_hits"] = get_biomarker_moa_hits(df_sig(filtered_df_for_playbook), filtered_df_for_playbook)

    rag_snippets = build_rag_snippets(
        filtered_df_for_playbook,
        playbook_key,
        PLAYBOOKS[playbook_key].get("buckets", {}),
        limit=10
    )

    user_query = f"Run the '{pb['button_label']} — {pb['subtitle']}' playbook for {ta_filter}."

    # Use multi-pass analysis for KOL button, fallback to framework for others
    if playbook_key == "kol":
        print(f"[DEBUG] USING MULTI-PASS ANALYSIS for KOL button - TA filter: {ta_filter}")
        narrative = generate_kol_analysis(
            filtered_df=filtered_df_for_playbook,
            top_authors_table=tables_for_prompt.get("top_authors", pd.DataFrame()),
            ta_filter=ta_filter
        )
        print(f"[DEBUG] Multi-pass KOL analysis complete, length: {len(narrative) if narrative else 0} chars")
    else:
        # Use existing framework approach for other buttons
        narrative = run_playbook_ai(
            playbook_key=playbook_key,
            ta_filter=ta_filter,
            user_query=user_query,
            filtered_df=filtered_df_for_playbook,
            tables_for_prompt=tables_for_prompt,
            rag_snippets=rag_snippets
        )

    response_tables = {}
    for key, df_tbl in tables_for_prompt.items():
        if df_tbl is not None and not df_tbl.empty:
            response_tables[key] = df_tbl.to_dict('records')
        else:
            response_tables[key] = []

    return jsonify({
        "narrative": narrative,
        "tables": response_tables,
        "playbook_title": f"{pb['button_label']} — {pb['subtitle']}",
        "sections": pb["sections"]
    })

# API Endpoint for chat messages (NEW AI-FIRST ARCHITECTURE)
@app.route('/api/chat/stream', methods=['POST'])
def stream_chat_api():
    """
    Token-by-token streaming endpoint for all chat responses with conversation memory.
    Accepts: {"message": "user question", "ta_filter": "All", "conversation_history": []}
    """
    if not initialize_app_globals():
        return "data: Error: Application data could not be loaded\n\n", 500, {'Content-Type': 'text/event-stream'}

    try:
        data = request.get_json()
        if not data:
            return "data: Error: No JSON data provided\n\n", 400, {'Content-Type': 'text/event-stream'}

        user_query = data.get('message', '').strip()
        ta_filter = data.get('ta_filter', 'All')
        conversation_history = data.get('conversation_history', [])  # List of {"role": "user/assistant", "content": "text"}

        # Limit conversation history to last 10 exchanges (20 messages)
        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]

    except Exception as e:
        return f"data: Error parsing request: {str(e)}\n\n", 400, {'Content-Type': 'text/event-stream'}

    if not user_query:
        return "data: Error: No message provided\n\n", 400, {'Content-Type': 'text/event-stream'}

    def generate():
        try:
            # Use the existing AI query analysis and response generation logic
            if ta_filter == "Bladder Cancer":
                filtered_df = df_global[df_global["ta"] == "bladder"].copy()
            elif ta_filter == "Renal Cell Carcinoma":
                filtered_df = df_global[df_global["ta"] == "renal"].copy()
            else:
                filtered_df = df_global.copy()

            # Analyze the query and generate intelligent response using existing logic
            plan = analyze_user_query_ai(user_query, ta_filter, conversation_history)
            print(f"🔍 CHAT STREAMING DEBUG - Query: '{user_query}' | Plan: {plan.response_type} | Entities: {plan.primary_entities}")
            context = gather_intelligent_context(plan, ta_filter, filtered_df)

            # Check if this should use sophisticated author analysis
            if plan.response_type == "specific_lookup":
                # TRUE STREAMING: Stream directly from sophisticated prompt without pre-generation

                # Extract author name or institution from query - prioritize institutions
                author_name = None
                institution_name = None

                # First check if institutions are mentioned
                if plan.primary_entities.get("institutions"):
                    institution_name = plan.primary_entities["institutions"][0]

                # If no institutions, then check for authors
                if not institution_name and plan.primary_entities.get("authors"):
                    author_name = plan.primary_entities["authors"][0]

                # Fallback: look for any entity with 2+ words (could be author or institution)
                if not author_name and not institution_name:
                    for entity_list in plan.primary_entities.values():
                        for entity in entity_list:
                            if len(entity.split()) >= 2:  # Likely a person's name (First Last)
                                author_name = entity
                                break
                        if author_name:
                            break

                # AI-FIRST APPROACH: Handle institutions vs authors appropriately
                if institution_name:
                    # Handle institution lookup - ALWAYS do direct institution search first
                    mask = safe_contains(filtered_df["Institutions"], institution_name, regex=True)
                    institution_results = filtered_df.loc[mask, ["Abstract #","Poster #","Title","Authors","Institutions"]].drop_duplicates(subset=["Abstract #"])

                    if not institution_results.empty:
                        # EMIT TABLE FIRST - showing all institution's studies
                        institution_table_data = institution_results.to_dict('records')
                        table_title = f"🏥 {institution_name} - Conference Studies ({len(institution_results)} abstracts)"
                        yield sse_event("table", {
                            "title": table_title,
                            "rows": institution_table_data
                        })

                        # Include ALL results, but provide summary in prompt
                        total_count = len(institution_results)
                        institution_data = f"Total abstracts found: {total_count}\n\n" + institution_results.to_csv(index=False)
                    else:
                        # Fallback to semantic search if direct search finds nothing
                        if context.semantic_results is not None and not context.semantic_results.empty:
                            institution_data = context.semantic_results.head(20).to_csv(index=False)
                        else:
                            institution_data = "No data found"

                    # Build conversation context
                    conversation_context = ""
                    if conversation_history:
                        conversation_context = "\n\nConversation History (for context only):\n"
                        for msg in conversation_history:
                            role = msg.get('role', 'unknown')
                            content = msg.get('content', '')[:200] + ('...' if len(msg.get('content', '')) > 200 else '')
                            conversation_context += f"{role.title()}: {content}\n"
                        conversation_context += "\n"

                    streaming_prompt = f"""You are an AI medical affairs analyst. Respond to the user's request about institutional activity.
{conversation_context}
Current User Request: "{user_query}"
Therapeutic Area Filter: {ta_filter}

Conference Data for {institution_name}:
{institution_data}

Based on the user's specific request, provide an appropriate response that:
- Analyzes the institution's research activity and focus areas
- Uses natural language that flows well
- Includes specific evidence from the conference data (Abstract #s)
- Focuses on medical affairs insights relevant to EMD Serono/avelumab
- Mentions the number of abstracts/studies from this institution

Respond naturally to exactly what the user asked about this institution."""

                elif context.author_data is not None and not context.author_data.empty:
                    # EMIT TABLE FIRST - showing all author's studies
                    author_table_data = context.author_data.to_dict('records')
                    table_title = f"📄 {author_name} - Conference Studies ({len(context.author_data)} abstracts)"
                    yield sse_event("table", {
                        "title": table_title,
                        "rows": author_table_data
                    })

                    # Build conversation context
                    conversation_context = ""
                    if conversation_history:
                        conversation_context = "\n\nConversation History (for context only):\n"
                        for msg in conversation_history:
                            role = msg.get('role', 'unknown')
                            content = msg.get('content', '')[:200] + ('...' if len(msg.get('content', '')) > 200 else '')
                            conversation_context += f"{role.title()}: {content}\n"
                        conversation_context += "\n"

                    streaming_prompt = f"""You are an AI medical affairs analyst. Respond to the user's request naturally and appropriately.
{conversation_context}
Current User Request: "{user_query}"
Therapeutic Area Filter: {ta_filter}

Conference Data for {author_name}:
{context.author_data.to_csv(index=False)}

Based on the user's specific request, provide an appropriate response that:
- Matches the level of detail they're asking for (brief, detailed, comprehensive, etc.)
- Uses natural language that flows well
- Includes specific evidence from the conference data
- Focuses on medical affairs insights relevant to EMD Serono/avelumab
- Always includes the participation count: "{author_name} participated in [X] studies at the conference"

Respond naturally to exactly what the user asked - don't follow rigid frameworks or bullet points unless they specifically request that format."""

                else:
                    # NO AUTHOR/INSTITUTION DATA - return simple response immediately (no AI needed)
                    entity_name = institution_name or author_name
                    entity_type = "institution" if institution_name else "author"

                    if ta_filter != "All":
                        simple_response = f"No studies found for {entity_name} in {ta_filter}. Try changing the filter to 'All GU Cancers' to see if other studies are available."
                    else:
                        simple_response = f"No studies found for {entity_name} in the ASCO GU 2025 conference data."

                    # Stream the simple response immediately
                    for char in simple_response:
                        yield f"data: {char}\n\n"
                    yield f"data: [DONE]\n\n"
                    return
            else:
                # Use generic response for other query types
                if context.semantic_results is not None and not context.semantic_results.empty:
                    semantic_data = context.semantic_results.head(20).to_csv(index=False)
                else:
                    semantic_data = "No relevant data found."

                # Build conversation context
                conversation_context = ""
                if conversation_history:
                    conversation_context = "\n\nConversation History (for context only):\n"
                    for msg in conversation_history:
                        role = msg.get('role', 'unknown')
                        content = msg.get('content', '')[:200] + ('...' if len(msg.get('content', '')) > 200 else '')
                        conversation_context += f"{role.title()}: {content}\n"
                    conversation_context += "\n"

                streaming_prompt = f"""You are a medical affairs AI assistant analyzing conference data from ASCO GU 2025.
{conversation_context}
Current User Query: "{user_query}"
Therapeutic Area Filter: {ta_filter}

Relevant Conference Data:
{semantic_data}

Based on the user's query and the relevant conference data above, provide a comprehensive and helpful response. Be specific, cite abstract numbers when relevant, and focus on actionable insights for medical affairs professionals.

Write a natural, conversational response that directly answers the user's question."""

            # Enhanced streaming with paragraph boundary detection
            stream = client.chat.completions.create(
                model="gpt-5-mini",
                reasoning_effort="minimal",
                verbosity="low",
                messages=[{"role": "user", "content": streaming_prompt}],
                    max_completion_tokens=2000,
                stream=True
            )

            # Track content for paragraph detection
            accumulated_content = ""
            last_boundary_pos = 0

            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    token = chunk.choices[0].delta.content
                    accumulated_content += token

                    # Send the token (legacy format for compatibility)
                    yield f"data: {token}\n\n"

                    # Check for NEW paragraph boundaries
                    boundary_pos = accumulated_content.find('\n\n', last_boundary_pos)
                    if boundary_pos != -1:
                        # Send a special boundary signal
                        yield f"data: |||PARAGRAPH_BREAK|||\n\n"
                        last_boundary_pos = boundary_pos + 2

            # Send completion signal
            yield "data: [DONE]\n\n"

        except Exception as e:
            print(f"🚨 ERROR in chat streaming: {str(e)}")
            import traceback
            traceback.print_exc()
            yield sse_event("error", {"message": f"Error generating response: {str(e)}"})

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)

@app.route('/api/chat', methods=['POST'])
def chat_api():
    if not initialize_app_globals():
        return jsonify({"error": "Application data could not be loaded. Check server logs for details."}), 500

    data = request.get_json()
    user_message = data.get('message')
    ta_filter = data.get('ta_filter', 'All')
    conversation_history = data.get('conversation_history', [])
    use_legacy = data.get('use_legacy', False)  # Allow fallback to old system if needed

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    # Limit conversation history to last 20 messages (10 exchanges)
    if len(conversation_history) > 20:
        conversation_history = conversation_history[-20:]

    # Filter data based on TA
    if ta_filter == "Bladder Cancer":
        current_df = df_global[df_global["ta"] == "bladder"].copy()
    elif ta_filter == "Renal Cell Carcinoma":
        current_df = df_global[df_global["ta"] == "renal"].copy()
    else:
        current_df = df_global.copy()

    # Use legacy system if explicitly requested or for simple queries
    simple_queries = ["hi", "hello", "help", "top authors", "top institutions"]
    if use_legacy or any(simple in user_message.lower() for simple in simple_queries):
        return legacy_chat_handler(user_message, ta_filter, current_df)

    try:
        # NEW AI-FIRST FLOW
        print(f"AI-First: Analyzing query: {user_message}")

        # Step 1: AI analyzes the query and creates execution plan
        plan = analyze_user_query_ai(user_message, ta_filter, conversation_history)
        print(f"AI-First: Plan created - Intent: {plan.intent_type}, Confidence: {plan.confidence}")

        # Step 2: Gather intelligent context based on plan
        context = gather_intelligent_context(plan, ta_filter, current_df)
        print(f"AI-First: Context gathered - Semantic results: {context.semantic_results is not None and not context.semantic_results.empty}")

        # Step 3: Generate comprehensive AI response
        response_text, tables_to_attach = generate_intelligent_response(user_message, plan, context, ta_filter)
        print(f"AI-First: Response generated with {len(tables_to_attach)} tables")

        # Format response for frontend
        response_tables = {}
        for title, df_tbl, ttype in tables_to_attach:
            if not df_tbl.empty:
                response_tables[title] = df_tbl.to_dict('records')
            else:
                response_tables[title] = []

        return jsonify({
            "action": "display_message",
            "message": response_text,
            "tables": response_tables,
            "ai_analysis": {
                "intent_type": plan.intent_type,
                "confidence": plan.confidence,
                "mentioned_entities": plan.mentioned_entities
            }
        })

    except Exception as e:
        print(f"Error in AI-first chat handler: {e}")
        # Fallback to legacy system on error
        return legacy_chat_handler(user_message, ta_filter, current_df)

# Legacy chat handler (kept for fallback and simple queries)
def legacy_chat_handler(user_message: str, ta_filter: str, current_df: pd.DataFrame):
    """Original chat handler kept for simple queries and fallback"""
    original_query = user_message
    intent, conf, slots = llm_route_query(user_message)
    slots["original_query"] = original_query

    msg, tbls_to_attach, trigger_playbook = handle_chat_intent(intent, slots, ta_filter, current_df)

    response_tables = {}
    for title, df_tbl, ttype in tbls_to_attach:
        if not df_tbl.empty:
            response_tables[title] = df_tbl.to_dict('records')
        else:
            response_tables[title] = []

    if trigger_playbook:
        return jsonify({"action": "trigger_playbook", "playbook_key": trigger_playbook, "message": msg, "tables": response_tables})
    else:
        return jsonify({"action": "display_message", "message": msg, "tables": response_tables})

def handle_chat_intent(intent: str, slots: Dict[str, Any], ta_filter: str, filtered_df: pd.DataFrame) -> Tuple[str, List[Tuple[str, pd.DataFrame, str]], Optional[str]]:
    """
    Returns: (assistant_message, list_of_tables_to_attach, trigger_playbook_key|None)
    Each table tuple: (title, df, type)
    """
    tables: List[Tuple[str, pd.DataFrame, str]] = []
    trigger_playbook = None

    if intent in {"smalltalk", "help"}:
        if intent == "smalltalk":
            msg = ("Hi! 👋 This workspace is for **conference intelligence**.\n\n"
                   "You can:\n"
                   "- Run a playbook from the sidebar (Competitor, KOLs, Institutions, Trends, Strategy)\n"
                   "- Ask quick questions like **“top 20 authors”**, **“top 15 institutions”**, or **“list avelumab studies”**\n"
                   "- Just say things like **“all abstracts with involvement from Shilpa Gupta”** — I’ll detect the author and show the table.\n\n"
                   "What would you like to explore?")
        else:
            msg = ("Here’s how to use this:\n"
                   "• **Pick a playbook** for a structured narrative; tables attach below the analysis.\n"
                   "• **Quick queries**: “top 20 authors”, “top 20 institutions”, “list avelumab studies”.\n"
                   "• **Natural author lookups**: “all abstracts with involvement from Shilpa Gupta”.\n"
                   "Rules: no invented counts; cite **Abstract #**; if not in CSV, I’ll say so.")
        return msg, tables, None

    if intent == "top_authors":
        n = int(slots.get("n", 20))
        top_auth = get_top_authors(df_sig(filtered_df), filtered_df, n)
        msg = ("No authors found in the current TA filter."
               if top_auth.empty else
               f"Here are the **top {len(top_auth)} authors** by unique abstracts within **{ta_filter}**. Counts come from the table below.")
        if not top_auth.empty:
            tables.append((f"👥 Top {len(top_auth)} Authors by Unique Abstracts", top_auth, "data"))
        return msg, tables, None

    if intent == "top_institutions":
        n = int(slots.get("n", 20))
        top_inst = get_top_institutions(df_sig(filtered_df), filtered_df, n)
        msg = ("No institutions found in the current TA filter."
               if top_inst.empty else
               f"Here are the **top {len(top_inst)} institutions** by unique abstracts within **{ta_filter}**.")
        if not top_inst.empty:
            tables.append((f"🏥 Top {len(top_inst)} Institutions by Unique Abstracts", top_inst, "data"))
        return msg, tables, None

    if intent == "list_avelumab":
        mask = safe_contains(filtered_df["Title"], r"avelumab|bavencio", regex=True) | \
               safe_contains(filtered_df["Authors"], r"avelumab|bavencio", regex=True)
        av_df = filtered_df.loc[mask, ["Abstract #","Poster #","Title","Authors","Institutions"]].drop_duplicates(subset=["Abstract #"])
        msg = (f"No Avelumab/Bavencio abstracts found under **{ta_filter}** in the CSV."
               if av_df.empty else
               f"Listed **Avelumab/Bavencio** abstracts detected in the CSV for **{ta_filter}**. Reference **Abstract #** in the table below.")
        if not av_df.empty:
            tables.append((f"🧪 Avelumab/Bavencio Studies ({len(av_df)})", av_df, "data"))
        return msg, tables, None

    if intent == "author_abstracts":
        author = (slots.get("author") or "").strip()
        if not author:
            authors_list = get_unique_authors(df_sig(df_global), df_global)
            author = extract_author_from_query(slots.get("original_query",""), authors_list) or ""
        if not author:
            return "I couldn’t detect which author you meant. Try e.g., **all abstracts with involvement from Shilpa Gupta**.", tables, None
        pat = r"\b" + re.escape(author) + r"\b"
        mask = safe_contains(filtered_df["Authors"], pat, regex=True)
        res = filtered_df.loc[mask, ["Abstract #","Poster #","Title","Authors","Institutions"]].drop_duplicates(subset=["Abstract #"])
        if res.empty:
            return f"No abstracts with involvement from **{author}** were found under **{ta_filter}** in the CSV.", tables, None
        msg = f"Here are the abstracts with involvement from **{author}** (TA scope: **{ta_filter}**)."
        tables.append((f"👤 Abstracts with {author} ({len(res)})", res, "data"))
        return msg, tables, None

    if intent == "institution_abstracts":
        institution = (slots.get("institution") or "").strip()
        if not institution:
            return "Please specify the institution, e.g., **all abstracts from Memorial Sloan Kettering**.", tables, None
        mask = safe_contains(filtered_df["Institutions"], institution, regex=True)
        res = filtered_df.loc[mask, ["Abstract #","Poster #","Title","Authors","Institutions"]].drop_duplicates(subset=["Abstract #"])
        if res.empty:
            return f"No abstracts found for **{institution}** under **{ta_filter}** in the CSV.", tables, None
        msg = f"Here are the abstracts associated with **{institution}** (TA scope: **{ta_filter}**)."
        tables.append((f"🏥 Abstracts from {institution} ({len(res)})", res, "data"))
        return msg, tables, None

    if intent == "search":
        term = str(slots.get("term", "")).strip()
        if not term:
            authors_list = get_unique_authors(df_sig(df_global), df_global)
            author = extract_author_from_query(slots.get("original_query",""), authors_list)
            if author:
                pat = r"\b" + re.escape(author) + r"\b"
                mask = safe_contains(filtered_df["Authors"], pat, regex=True)
                res = filtered_df.loc[mask, ["Abstract #","Poster #","Title","Authors","Institutions"]].drop_duplicates(subset=["Abstract #"])
                if res.empty:
                    return f"No abstracts with involvement from **{author}** were found under **{ta_filter}** in the CSV.", tables, None
                msg = f"Detected author **{author}**. Showing involved abstracts (TA: **{ta_filter}**)."
                tables.append((f"👤 Abstracts with {author} ({len(res)})", res, "data"))
                return msg, tables, None
            narrative, hits = run_general_ai(slots.get("original_query",""), ta_filter, filtered_df)
            if hits is not None and not hits.empty:
                tables.append(("🔎 Relevant Abstracts (Top Matches)", hits, "data"))
            return narrative, tables, None

        mask = (
            safe_contains(filtered_df["Title"], term, regex=False) |
            safe_contains(filtered_df["Authors"], term, regex=False) |
            safe_contains(filtered_df["Institutions"], term, regex=False) |
            filtered_df["Abstract #"].astype(str).str.contains(term, case=False, na=False, regex=False) |
            filtered_df["Poster #"].astype(str).str.contains(term, case=False, na=False, regex=False)
        )
        res = filtered_df.loc[mask, ["Abstract #","Poster #","Title","Authors","Institutions"]]
        msg = (f"No results containing **{term}** found in **{ta_filter}**."
               if res.empty else
               f"Found **{len(res)}** abstracts containing **{term}** in **{ta_filter}**. See table below.")
        if not res.empty:
            tables.append((f"🔎 Search Results: {term} ({len(res)})", res, "data"))
        return msg, tables, None

    if intent in {"competitor_playbook","kol_playbook","institution_playbook","insights_playbook","strategy_playbook"}:
        mapping = {
            "competitor_playbook": "competitor",
            "kol_playbook": "kol",
            "institution_playbook": "institution",
            "insights_playbook": "insights",
            "strategy_playbook": "strategy",
        }
        trigger_playbook = mapping[intent]
        return "Launching requested analysis…", tables, trigger_playbook

    if intent == "general_conference_question":
        narrative, hits = run_general_ai(slots.get("original_query", ""), ta_filter, filtered_df)
        tables_out = []
        if hits is not None and not hits.empty:
            tables_out.append(("🔎 Relevant Abstracts (Top Matches)", hits, "data"))
        return narrative, tables_out, None

    msg = ("This workspace focuses on **conference intelligence**. "
           "Try a playbook from the left, or ask quick questions like **“top 20 authors”**, "
           "**“top institutions”**, or **`all abstracts with involvement from <Author>`**.")
    return msg, tables, None

@app.route('/__healthz')
def healthz():
    here = Path(__file__).resolve()
    idx = (Path(__file__).parent / "templates" / "index.html").resolve()
    return jsonify({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "app_file": str(here),
        "app_md5": file_md5(here),
        "index_html": str(idx),
        "index_md5": file_md5(idx) if idx.exists() else None,
        "cwd": str(Path.cwd()),
        "title_check": "vTEST-A — FIXED VERSION — Data Explorer",
        "port_note": "You can pin a unique PORT when launching to avoid ghosts."
    })

# --- Export Endpoint ---
@app.route('/api/export', methods=['POST'])
def export_data():
    from flask import make_response
    import io

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        export_format = data.get('format', '').lower()
        ta_filter = data.get('ta_filter', 'All')

        if export_format not in ['csv', 'excel']:
            return jsonify({"error": "Unsupported format. Use 'csv' or 'excel'"}), 400

        # Fix 1: Use df_global and apply proper filtering
        if ta_filter == "Bladder Cancer":
            filtered_df = df_global[df_global["ta"] == "bladder"].copy()
        elif ta_filter == "Renal Cell Carcinoma":
            filtered_df = df_global[df_global["ta"] == "renal"].copy()
        else:
            filtered_df = df_global.copy()

        # Fix 3: Sanitize data to prevent CSV injection
        for col in filtered_df.select_dtypes(include=['object']).columns:
            filtered_df[col] = filtered_df[col].astype(str).str.replace(r'^[=+\-@]', '', regex=True)

        # Fix 4: Generate proper response with headers
        if export_format == 'csv':
            output = io.StringIO()
            filtered_df.to_csv(output, index=False)

            response = make_response(output.getvalue())
            response.headers["Content-Type"] = "text/csv"
            response.headers["Content-Disposition"] = f"attachment; filename=asco_gu_2025_{ta_filter.lower().replace(' ', '_')}.csv"
            return response

        else:  # excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                filtered_df.to_excel(writer, sheet_name='ASCO GU 2025 Data', index=False)

            output.seek(0)
            response = make_response(output.getvalue())
            response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            response.headers["Content-Disposition"] = f"attachment; filename=asco_gu_2025_{ta_filter.lower().replace(' ', '_')}.xlsx"
            return response

    except Exception as e:
        print(f"Export error: {str(e)}")
        return jsonify({"error": "Export failed. Please try again."}), 500

# --- Running the App ---
if __name__ == '__main__':
    if not initialize_app_globals():
        print("Application failed to initialize and will not start. Please check your data file and configuration.")
    else:
        print("Starting Flask server...")
        app.run(debug=True)
