"""
Entity Resolver Module
======================
Lightweight, deterministic resolver for drug names, abbreviations, MOA classes, and institutions.
Runs BEFORE any AI classification to normalize queries and expand acronyms.

Design Principles:
- No AI needed - pure dictionary lookups
- Fast: O(1) lookup per term
- Protects against AI classification failures
- Caches on module load
"""

import re
from typing import List, Dict, Set, Tuple
from functools import lru_cache

# ============================================================================
# DRUG RESOLUTION DATABASE
# ============================================================================

DRUG_ALIASES = {
    # PD-1 / PD-L1 Inhibitors
    "pembro": "pembrolizumab",
    "p": "pembrolizumab",  # Common abbreviation in combinations (EV+P)
    "keytruda": "pembrolizumab",
    "nivo": "nivolumab",
    "n": "nivolumab",  # Common abbreviation in combinations
    "opdivo": "nivolumab",
    "atezo": "atezolizumab",
    "tecentriq": "atezolizumab",
    "durva": "durvalumab",
    "imfinzi": "durvalumab",
    "avel": "avelumab",
    "bavencio": "avelumab",
    "cemiplimab": "cemiplimab",
    "libtayo": "cemiplimab",

    # ADCs
    "ev": "enfortumab vedotin",
    "padcev": "enfortumab vedotin",
    "enfortumab": "enfortumab vedotin",
    "sg": "sacituzumab govitecan",
    "trodelvy": "sacituzumab govitecan",
    "sacituzumab": "sacituzumab govitecan",
    "t-dxd": "trastuzumab deruxtecan",
    "enhertu": "trastuzumab deruxtecan",
    "ds-8201": "trastuzumab deruxtecan",

    # CTLA-4 Inhibitors
    "ipi": "ipilimumab",
    "yervoy": "ipilimumab",
    "tremelimumab": "tremelimumab",

    # FGFR Inhibitors
    "erda": "erdafitinib",
    "erdafitinib": "erdafitinib",
    "balversa": "erdafitinib",

    # Other targeted therapies
    "cabozantinib": "cabozantinib",
    "cabo": "cabozantinib",
    "cabometyx": "cabozantinib",
    "lenvatinib": "lenvatinib",
    "lenvima": "lenvatinib",
    "axitinib": "axitinib",
    "inlyta": "axitinib",

    # Chemotherapy
    "cis": "cisplatin",
    "carbo": "carboplatin",
    "gem": "gemcitabine",
    "gemzar": "gemcitabine",
}

# MOA class expansions (e.g., "show me ADCs" → list of ADC drugs)
MOA_EXPANSIONS = {
    "adc": ["enfortumab vedotin", "sacituzumab govitecan", "trastuzumab deruxtecan"],
    "adcs": ["enfortumab vedotin", "sacituzumab govitecan", "trastuzumab deruxtecan"],
    "antibody drug conjugate": ["enfortumab vedotin", "sacituzumab govitecan", "trastuzumab deruxtecan"],

    "ici": ["pembrolizumab", "nivolumab", "atezolizumab", "durvalumab", "avelumab", "cemiplimab"],
    "icis": ["pembrolizumab", "nivolumab", "atezolizumab", "durvalumab", "avelumab", "cemiplimab"],
    "immune checkpoint inhibitor": ["pembrolizumab", "nivolumab", "atezolizumab", "durvalumab", "avelumab", "cemiplimab"],

    "pd-1": ["pembrolizumab", "nivolumab", "cemiplimab"],
    "pd1": ["pembrolizumab", "nivolumab", "cemiplimab"],
    "pd-l1": ["atezolizumab", "durvalumab", "avelumab"],
    "pdl1": ["atezolizumab", "durvalumab", "avelumab"],

    "ctla-4": ["ipilimumab", "tremelimumab"],
    "ctla4": ["ipilimumab", "tremelimumab"],

    "fgfr inhibitor": ["erdafitinib"],
    "fgfri": ["erdafitinib"],

    "vegf inhibitor": ["cabozantinib", "lenvatinib", "axitinib"],
    "vegfi": ["cabozantinib", "lenvatinib", "axitinib"],
    "tki": ["cabozantinib", "lenvatinib", "axitinib", "erdafitinib"],
}

# Suffix patterns for drug variations (e.g., "enfortumab vedotin-ejfv")
DRUG_SUFFIX_PATTERNS = {
    "enfortumab vedotin": r"enfortumab[\s\-]vedotin(?:\-[a-z0-9]+)?",
    "sacituzumab govitecan": r"sacituzumab[\s\-]govitecan(?:\-[a-z0-9]+)?",
    "trastuzumab deruxtecan": r"trastuzumab[\s\-]deruxtecan(?:\-[a-z0-9]+)?",
}

# ============================================================================
# INSTITUTION / AFFILIATION ALIASES
# ============================================================================

INSTITUTION_ALIASES = {
    # Major cancer centers (short → full name)
    "msk": "memorial sloan kettering",
    "mskcc": "memorial sloan kettering",
    "md anderson": "md anderson cancer center",
    "mda": "md anderson cancer center",
    "mdacc": "md anderson cancer center",
    "dana farber": "dana-farber cancer institute",
    "dana-farber": "dana-farber cancer institute",
    "dfci": "dana-farber cancer institute",
    "hopkins": "johns hopkins",
    "jhu": "johns hopkins",
    "mayo": "mayo clinic",
}

# ============================================================================
# THERAPEUTIC AREA ACRONYMS
# ============================================================================

TA_ACRONYMS = {
    "gu": ["bladder", "urothelial", "renal", "kidney", "prostate"],
    "nsclc": ["non-small cell lung", "nsclc"],
    "sclc": ["small cell lung", "sclc"],
    "crc": ["colorectal", "colon", "rectal"],
    "hn": ["head and neck", "hnsc", "hnscc"],
    "gi": ["gastrointestinal", "gastric", "esophageal"],
}

# ============================================================================
# COMBINATION OPERATORS
# ============================================================================

# Explicit AND operators (combination therapy)
EXPLICIT_AND_OPERATORS = ["+", "plus", "with", "combo", "combined with", "in combination with"]

# Ambiguous operators (need clarification)
AMBIGUOUS_OPERATORS = [" and ", " & "]


# ============================================================================
# CORE RESOLVER FUNCTIONS
# ============================================================================

def normalize_term(term: str) -> str:
    """Normalize a search term: lowercase, strip whitespace."""
    return term.lower().strip()


def resolve_drug_name(query_term: str) -> List[str]:
    """
    Resolve a drug term to canonical generic name(s).

    Args:
        query_term: User input (e.g., "pembro", "Keytruda", "ADC")

    Returns:
        List of canonical drug names (usually 1, but can be multiple for MOA classes)

    Examples:
        resolve_drug_name("pembro") → ["pembrolizumab"]
        resolve_drug_name("ADC") → ["enfortumab vedotin", "sacituzumab govitecan", "trastuzumab deruxtecan"]
        resolve_drug_name("pembrolizumab") → ["pembrolizumab"] (passthrough)
    """
    normalized = normalize_term(query_term)

    # Check if it's a MOA class expansion
    if normalized in MOA_EXPANSIONS:
        return MOA_EXPANSIONS[normalized]

    # Check if it's a known alias/abbreviation/brand name
    if normalized in DRUG_ALIASES:
        return [DRUG_ALIASES[normalized]]

    # Otherwise, use as-is (might already be generic name)
    return [query_term]


def resolve_institution(query_term: str) -> str:
    """
    Resolve institution abbreviation to full name.

    Examples:
        resolve_institution("MSK") → "memorial sloan kettering"
        resolve_institution("MD Anderson") → "md anderson cancer center"
    """
    normalized = normalize_term(query_term)
    return INSTITUTION_ALIASES.get(normalized, query_term)


def resolve_ta_acronym(query_term: str) -> List[str]:
    """
    Expand therapeutic area acronym to keywords.

    Examples:
        resolve_ta_acronym("GU") → ["bladder", "urothelial", "renal", "kidney", "prostate"]
        resolve_ta_acronym("NSCLC") → ["non-small cell lung", "nsclc"]
    """
    normalized = normalize_term(query_term)
    return TA_ACRONYMS.get(normalized, [query_term])


def detect_combination_logic(query: str) -> Tuple[str, List[str]]:
    """
    Detect if query implies AND (combination) or OR (separate) logic.

    Returns:
        Tuple of (logic, matched_operators)
        - logic: "AND", "OR", or "unclear"
        - matched_operators: list of operators found in query

    Examples:
        detect_combination_logic("pembro + nivo") → ("AND", ["+"])
        detect_combination_logic("pembro and nivo") → ("unclear", [" and "])
        detect_combination_logic("pembro or nivo") → ("OR", [" or "])
    """
    query_lower = query.lower()

    # Check for explicit AND operators
    explicit_and_found = [op for op in EXPLICIT_AND_OPERATORS if op in query_lower]
    if explicit_and_found:
        return ("AND", explicit_and_found)

    # Check for explicit OR operators
    if " or " in query_lower:
        return ("OR", [" or "])

    # Check for ambiguous operators
    ambiguous_found = [op for op in AMBIGUOUS_OPERATORS if op in query_lower]
    if ambiguous_found:
        return ("unclear", ambiguous_found)

    # Default to OR if multiple drugs but no explicit operator
    return ("OR", [])


def build_drug_regex(drug_name: str, case_insensitive: bool = True) -> re.Pattern:
    """
    Build a regex pattern for a drug name with word boundaries and suffix awareness.

    Args:
        drug_name: Canonical drug name (e.g., "pembrolizumab", "enfortumab vedotin")
        case_insensitive: Whether to make regex case-insensitive

    Returns:
        Compiled regex pattern

    Examples:
        build_drug_regex("pembrolizumab") → matches "pembrolizumab" but not "pembrolizumabs"
        build_drug_regex("enfortumab vedotin") → matches "enfortumab vedotin-ejfv"
    """
    # Check if drug has a special suffix pattern
    if drug_name in DRUG_SUFFIX_PATTERNS:
        pattern = DRUG_SUFFIX_PATTERNS[drug_name]
    else:
        # Standard word boundary pattern
        pattern = r'\b' + re.escape(drug_name) + r'\b'

    flags = re.IGNORECASE if case_insensitive else 0
    return re.compile(pattern, flags)


def expand_query_entities(query: str) -> Dict[str, any]:
    """
    Main resolver function: Extract and expand all entities from a query.

    This runs BEFORE AI classification to normalize terms.

    Args:
        query: Raw user query

    Returns:
        Dict with expanded entities:
        {
            "original_query": str,
            "drugs": List[str],  # Canonical drug names
            "institutions": List[str],  # Full institution names
            "ta_keywords": List[str],  # TA keywords
            "logic": str,  # "AND", "OR", or "unclear"
            "operators_found": List[str],
            "needs_clarification": bool
        }

    Example:
        Input: "Show me pembro + nivo at MSK"
        Output: {
            "original_query": "Show me pembro + nivo at MSK",
            "drugs": ["pembrolizumab", "nivolumab"],
            "institutions": ["memorial sloan kettering"],
            "ta_keywords": [],
            "logic": "AND",
            "operators_found": ["+"],
            "needs_clarification": False
        }
    """
    # Detect combination logic
    logic, operators = detect_combination_logic(query)

    result = {
        "original_query": query,
        "drugs": [],
        "institutions": [],
        "ta_keywords": [],
        "logic": logic,
        "operators_found": operators,
        "needs_clarification": (logic == "unclear")
    }

    # Extract potential drug terms (simple heuristic: look for known patterns)
    # This is a fallback - typically AI classification will provide structured terms
    query_lower = query.lower()

    # Check for known drug aliases
    for alias, canonical in DRUG_ALIASES.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', query_lower):
            if canonical not in result["drugs"]:
                result["drugs"].append(canonical)

    # ALSO check for canonical drug names directly (e.g., "pembrolizumab", "nivolumab")
    # Get all canonical drug names from DRUG_ALIASES values
    canonical_drug_names = set(DRUG_ALIASES.values())
    for canonical_name in canonical_drug_names:
        if re.search(r'\b' + re.escape(canonical_name) + r'\b', query_lower):
            if canonical_name not in result["drugs"]:
                result["drugs"].append(canonical_name)

    # Check for MOA class terms
    for moa_term, drug_list in MOA_EXPANSIONS.items():
        if re.search(r'\b' + re.escape(moa_term) + r'\b', query_lower):
            result["drugs"].extend([d for d in drug_list if d not in result["drugs"]])

    # Check for institution aliases
    for alias, full_name in INSTITUTION_ALIASES.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', query_lower):
            if full_name not in result["institutions"]:
                result["institutions"].append(full_name)

    # Check for TA acronyms
    for acronym, keywords in TA_ACRONYMS.items():
        if re.search(r'\b' + re.escape(acronym) + r'\b', query_lower):
            result["ta_keywords"].extend([k for k in keywords if k not in result["ta_keywords"]])

    return result


# ============================================================================
# UTILITY FUNCTIONS FOR SEARCH
# ============================================================================

@lru_cache(maxsize=256)
def get_drug_search_patterns(drug_name: str) -> List[re.Pattern]:
    """
    Get all regex patterns for searching a drug (cached for performance).

    Returns patterns for:
    - Canonical name
    - Known aliases
    - Brand names
    - Suffix variations
    """
    patterns = [build_drug_regex(drug_name)]

    # Add patterns for aliases that map to this drug
    for alias, canonical in DRUG_ALIASES.items():
        if canonical == drug_name:
            patterns.append(build_drug_regex(alias))

    return patterns


def get_all_drug_names() -> Set[str]:
    """Get set of all canonical drug names in the resolver."""
    all_drugs = set(DRUG_ALIASES.values())
    for drug_list in MOA_EXPANSIONS.values():
        all_drugs.update(drug_list)
    return all_drugs


# ============================================================================
# MODULE SELF-TEST
# ============================================================================

if __name__ == "__main__":
    # Test cases
    test_cases = [
        "Show me pembro studies",
        "Keytruda + nivo combination",
        "What about ADC in bladder cancer?",
        "Studies at MSK with EV",
        "pembro and atezo trials",  # Ambiguous
        "enfortumab vedotin-ejfv results",
    ]

    print("Entity Resolver Self-Test")
    print("=" * 60)

    for query in test_cases:
        print(f"\nQuery: {query}")
        result = expand_query_entities(query)
        print(f"  Drugs: {result['drugs']}")
        print(f"  Institutions: {result['institutions']}")
        print(f"  Logic: {result['logic']}")
        print(f"  Needs clarification: {result['needs_clarification']}")
