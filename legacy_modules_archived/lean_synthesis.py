"""
Lean AI Synthesis Module
=========================
Streamlined prompt generation using "prompt diet" principle:
- Feed AI only IDs + Titles (+ 1-2 key fields), not full rows
- Keep full data table for UI display
- Slash token count by ~80%
- Maintain output quality

Key Design:
- Compact representation for AI input
- Clear synthesis instructions
- Role-specific insights
- Assumption transparency
"""

import pandas as pd
from typing import Dict, List, Optional


# ============================================================================
# COMPACT DATA REPRESENTATION
# ============================================================================

def format_compact_study_list(
    df: pd.DataFrame,
    include_speakers: bool = True,
    include_affiliation: bool = False,
    max_title_length: Optional[int] = None
) -> str:
    """
    Format study data in compact form for AI synthesis.

    Instead of full markdown table with all columns, provide:
    - Identifier | Title | Speakers (optional)

    This reduces token count by ~60-80% while maintaining enough context.

    Args:
        df: Results DataFrame
        include_speakers: Include speaker names
        include_affiliation: Include affiliations (increases token count)
        max_title_length: Truncate titles longer than this (None = no truncation)

    Returns:
        Compact string representation
    """
    if df.empty:
        return "No studies found."

    lines = []

    for idx, row in df.iterrows():
        identifier = row.get('Identifier', 'N/A')
        title = row.get('Title', 'Untitled')

        # Optional title truncation
        if max_title_length and len(title) > max_title_length:
            title = title[:max_title_length] + "..."

        # Build compact line
        parts = [f"{identifier}", title]

        if include_speakers and 'Speakers' in row and pd.notna(row['Speakers']):
            parts.append(f"({row['Speakers']})")

        if include_affiliation and 'Affiliation' in row and pd.notna(row['Affiliation']):
            # Shorten affiliation (just first institution)
            aff = str(row['Affiliation']).split(',')[0]
            parts.append(f"[{aff}]")

        lines.append(" | ".join(parts))

    return "\n".join(lines)


def get_study_statistics(df: pd.DataFrame) -> Dict[str, any]:
    """
    Calculate summary statistics for synthesis context.

    Returns:
        Dict with counts, session distribution, date range, etc.
    """
    stats = {
        "total_count": len(df),
        "session_distribution": {},
        "dates": [],
        "top_institutions": []
    }

    if df.empty:
        return stats

    # Session distribution
    if 'Session' in df.columns:
        session_counts = df['Session'].value_counts().to_dict()
        stats["session_distribution"] = {k: v for k, v in list(session_counts.items())[:5]}

    # Date range
    if 'Date' in df.columns:
        unique_dates = df['Date'].dropna().unique().tolist()
        stats["dates"] = unique_dates[:5]  # Limit to first 5 dates

    # Top institutions (top 5)
    if 'Affiliation' in df.columns:
        # Extract first institution from affiliation string
        affiliations = df['Affiliation'].dropna().apply(lambda x: str(x).split(',')[0])
        top_aff = affiliations.value_counts().head(5).to_dict()
        stats["top_institutions"] = list(top_aff.keys())

    return stats


# ============================================================================
# LEAN SYNTHESIS PROMPTS
# ============================================================================

def build_lean_synthesis_prompt(
    user_query: str,
    results_df: pd.DataFrame,
    search_metadata: Dict,
    verbosity: str = "medium"
) -> str:
    """
    Build lean synthesis prompt using compact study representation.

    Args:
        user_query: Original user query
        results_df: Filtered results (full data for table, but AI sees compact version)
        search_metadata: Metadata from search (logic used, drugs found, etc.)
        verbosity: "quick" or "medium" or "detailed"

    Returns:
        Compact synthesis prompt string
    """
    # Get statistics
    stats = get_study_statistics(results_df)
    result_count = len(results_df)

    # ========================================================================
    # BREVITY GUARD: Override verbosity for sparse results (token efficiency)
    # ========================================================================
    if result_count == 1:
        verbosity = "minimal"  # Force brief response for single result
    elif result_count <= 3:
        verbosity = "quick"  # Force concise response for 2-3 results

    # Format compact study list
    compact_studies = format_compact_study_list(
        results_df,
        include_speakers=True,
        include_affiliation=False  # Omit to save tokens
    )

    # Build assumption statement
    assumptions = []
    if search_metadata.get('logic'):
        logic = search_metadata['logic']
        drugs = search_metadata.get('drugs_found', [])
        if logic == "OR" and len(drugs) > 1:
            assumptions.append(f"Assuming **either drug** (OR logic) for: {', '.join(drugs)}")
        elif logic == "AND" and len(drugs) > 1:
            assumptions.append(f"Assuming **combination/co-mention** (AND logic) for: {', '.join(drugs)}")

    if search_metadata.get('ta_keywords_applied'):
        ta_kw = search_metadata['ta_keywords_applied']
        assumptions.append(f"Therapeutic area filtered by: {', '.join(ta_kw)}")

    assumption_text = "\n".join(f"- {a}" for a in assumptions) if assumptions else "None"

    # Verbosity-specific instructions (including new "minimal" tier)
    if verbosity == "minimal":
        synthesis_instructions = """Provide a MINIMAL response (2-4 sentences max):
- What is this drug/study? (1 sentence)
- Who's presenting and why it matters (1 sentence)
- Strategic relevance if any (1 sentence, optional)

CRITICAL: Keep response under 100 words. No speculation, just factual."""
    elif verbosity == "quick":
        synthesis_instructions = """Provide a CONCISE synthesis (3-5 bullet points):
- Main research themes from titles
- Notable studies or patterns
- Key takeaways for medical affairs"""
    elif verbosity == "detailed":
        synthesis_instructions = """Provide a COMPREHENSIVE synthesis:

**1. Research Landscape**:
- Dominant themes and mechanisms from study titles
- Treatment settings and patient populations
- Drug/therapy distribution

**2. Notable Studies**:
- Highlight top 5 most decision-relevant presentations
- Explain why each matters for medical affairs strategy

**3. Strategic Implications**:
- Competitive landscape insights
- KOL engagement opportunities
- Portfolio positioning considerations"""
    else:  # medium
        synthesis_instructions = """Provide a BALANCED synthesis:

**1. Key Themes**: Identify 3-4 major research themes from titles

**2. Notable Studies**: Highlight 3-5 most strategically relevant presentations

**3. Strategic Takeaways**: Concise implications for medical affairs"""

    # Build prompt
    prompt = f"""You are a medical affairs intelligence analyst for a pharmaceutical company.

**USER QUERY**: {user_query}

**SEARCH RESULTS**: {stats['total_count']} studies found

**ASSUMPTIONS USED**:
{assumption_text}

**SESSION DISTRIBUTION**: {stats['session_distribution']}

**TOP INSTITUTIONS**: {', '.join(stats['top_institutions'][:5]) if stats['top_institutions'] else 'N/A'}

{synthesis_instructions}

**STUDY LIST** (Identifier | Title | Speakers):
```
{compact_studies}
```

**INSTRUCTIONS**:
- Focus on TITLES to identify research themes
- Be specific: cite Identifier when mentioning studies
- Keep output concise and actionable
- DO NOT speculate about efficacy/safety (abstracts not yet available)
- DO provide strategic context and thematic analysis"""

    return prompt


def build_lean_synthesis_prompt_with_abstracts(
    user_query: str,
    results_df: pd.DataFrame,
    search_metadata: Dict,
    verbosity: str = "medium"
) -> str:
    """
    Build lean synthesis prompt for POST-ABSTRACT state.

    When abstracts are available, include them but still keep prompt compact.

    Args:
        user_query: Original user query
        results_df: Filtered results with Abstract column
        search_metadata: Metadata from search
        verbosity: Synthesis depth

    Returns:
        Synthesis prompt with abstracts
    """
    # Check if abstracts available
    has_abstracts = 'Abstract' in results_df.columns and results_df['Abstract'].notna().any()

    if not has_abstracts:
        # Fall back to pre-abstract version
        return build_lean_synthesis_prompt(user_query, results_df, search_metadata, verbosity)

    # Filter to studies with abstracts
    with_abstracts = results_df[results_df['Abstract'].notna() & (results_df['Abstract'].str.strip() != '')]

    stats = get_study_statistics(with_abstracts)

    # Format studies with abstracts (more detail since we have full data now)
    study_blocks = []
    for idx, row in with_abstracts.iterrows():
        identifier = row.get('Identifier', 'N/A')
        title = row.get('Title', 'Untitled')
        abstract = row.get('Abstract', '')
        speakers = row.get('Speakers', 'N/A')

        # Truncate abstract if too long (keep first 500 chars)
        if len(abstract) > 500:
            abstract = abstract[:500] + "..."

        block = f"""**{identifier}**: {title}
Speakers: {speakers}
Abstract: {abstract}
"""
        study_blocks.append(block)

    studies_text = "\n\n".join(study_blocks)

    # Build assumptions
    assumptions = []
    if search_metadata.get('logic'):
        logic = search_metadata['logic']
        drugs = search_metadata.get('drugs_found', [])
        if logic == "OR" and len(drugs) > 1:
            assumptions.append(f"Assuming **either drug** (OR logic) for: {', '.join(drugs)}")
        elif logic == "AND" and len(drugs) > 1:
            assumptions.append(f"Assuming **combination** (AND logic) for: {', '.join(drugs)}")

    assumption_text = "\n".join(f"- {a}" for a in assumptions) if assumptions else "None"

    # Verbosity instructions
    if verbosity == "quick":
        synthesis_instructions = "Provide a concise synthesis (5-7 bullet points) of key efficacy/safety signals and strategic implications."
    else:
        synthesis_instructions = """Provide a comprehensive synthesis:

**1. Efficacy Signals**: Key outcomes across studies (response rates, survival data, etc.)

**2. Safety Patterns**: Notable toxicity trends or safety insights

**3. Biomarker Insights**: Predictive/prognostic biomarker findings

**4. Strategic Implications**: Competitive landscape and portfolio positioning"""

    prompt = f"""You are a medical affairs intelligence analyst.

**USER QUERY**: {user_query}

**RESULTS**: {len(with_abstracts)} studies with abstracts

**ASSUMPTIONS**:
{assumption_text}

{synthesis_instructions}

**STUDIES**:
{studies_text}

**INSTRUCTIONS**:
- Synthesize efficacy and safety data from abstracts
- Be specific: cite study Identifiers
- Highlight competitive intelligence and strategic insights
- Keep output actionable for medical affairs"""

    return prompt


# ============================================================================
# TOKEN ESTIMATION
# ============================================================================

def estimate_prompt_tokens(prompt: str) -> int:
    """
    Rough token estimate (4 chars ≈ 1 token for English).

    Args:
        prompt: Prompt string

    Returns:
        Estimated token count
    """
    return len(prompt) // 4


def compare_prompt_sizes(old_prompt: str, new_prompt: str) -> Dict[str, any]:
    """
    Compare old vs new prompt token counts.

    Returns:
        Dict with old/new counts and % reduction
    """
    old_tokens = estimate_prompt_tokens(old_prompt)
    new_tokens = estimate_prompt_tokens(new_prompt)
    reduction_pct = ((old_tokens - new_tokens) / old_tokens * 100) if old_tokens > 0 else 0

    return {
        "old_tokens": old_tokens,
        "new_tokens": new_tokens,
        "reduction_pct": round(reduction_pct, 1),
        "tokens_saved": old_tokens - new_tokens
    }


# ============================================================================
# MODULE SELF-TEST
# ============================================================================

if __name__ == "__main__":
    # Test data
    test_df = pd.DataFrame({
        'Identifier': ['LBA1', 'P123', 'O456'],
        'Title': [
            'Pembrolizumab + enfortumab vedotin in advanced bladder cancer: Phase 3 results',
            'Biomarker analysis of FGFR3 mutations in urothelial carcinoma',
            'Real-world outcomes with atezolizumab maintenance in bladder cancer'
        ],
        'Speakers': ['Smith J', 'Johnson A', 'Lee K'],
        'Affiliation': ['MD Anderson, USA', 'Memorial Sloan Kettering, USA', 'Dana Farber, USA'],
        'Session': ['LBA', 'Poster', 'Oral']
    })

    test_metadata = {
        "logic": "OR",
        "drugs_found": ["pembrolizumab", "enfortumab vedotin"],
        "ta_keywords_applied": ["bladder", "urothelial"],
        "result_count": 3
    }

    print("Lean Synthesis Module Self-Test")
    print("=" * 60)

    # Test compact formatting
    print("\n1. Compact Study List:")
    print(format_compact_study_list(test_df, include_speakers=True))

    # Test statistics
    print("\n2. Study Statistics:")
    stats = get_study_statistics(test_df)
    print(f"   Total: {stats['total_count']}")
    print(f"   Sessions: {stats['session_distribution']}")
    print(f"   Top institutions: {stats['top_institutions']}")

    # Test prompt generation
    print("\n3. Lean Synthesis Prompt (token estimate):")
    prompt = build_lean_synthesis_prompt(
        "What are the latest pembrolizumab and EV studies in bladder cancer?",
        test_df,
        test_metadata,
        verbosity="medium"
    )
    tokens = estimate_prompt_tokens(prompt)
    print(f"   Estimated tokens: {tokens}")
    print(f"   Prompt length (chars): {len(prompt)}")
    print(f"\n   First 500 chars of prompt:")
    print(f"   {prompt[:500]}...")
