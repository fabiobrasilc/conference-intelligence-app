# Legacy Modules - Archived October 2025

These modules were replaced by the AI-first architecture on October 8, 2025.

## Replaced By
`ai_first_refactor/ai_assistant.py` - Two-step AI flow (200 lines)

## Archived Modules

### 1. entity_resolver.py (~415 lines)
**Purpose:** Drug name expansion and abbreviation resolution using hardcoded dictionaries

**Replaced with:** GPT-5's pharmaceutical knowledge - AI naturally understands "EV" = enfortumab vedotin, "P" = pembrolizumab, etc. without dictionaries

**Example:**
- **Old:** Dictionary maps "EV" → ["enfortumab vedotin", "enfortumab"]
- **New:** AI extracts `{"drugs": ["enfortumab vedotin"]}` from query understanding

---

### 2. query_intelligence.py (~200 lines)
**Purpose:** Intent classification and query type detection

**Replaced with:** GPT-5 natural query interpretation - AI understands intent without classification

**Example:**
- **Old:** Classify query as "drug_search" vs "institution_search" vs "landscape_query"
- **New:** AI generates appropriate keywords: drugs, institutions, TAs, dates, etc.

---

### 3. enhanced_search.py (~400 lines)
**Purpose:** Complex multi-stage search pipeline with entity resolution

**Replaced with:** Simple pandas/regex filtering after AI keyword extraction

**Example:**
- **Old:** `complete_search_pipeline()` - entity resolution → search → deduplication → ranking
- **New:** AI keywords → `df[df['column'].str.contains(pattern)]` → done

---

### 4. lean_synthesis.py (~300 lines)
**Purpose:** Token optimization and manual data truncation for AI prompts

**Replaced with:** GPT-5 handles token management; we send only filtered results (e.g., 11 studies, not 4,686)

**Example:**
- **Old:** `build_lean_synthesis_prompt()` - manually truncate titles, estimate tokens
- **New:** Two-step flow filters 4,686 → 11 studies; AI analyzes only 11

---

## Why These Were Removed

### 1. Overengineering
- **6 modules, ~1,500 lines** of hardcoded logic
- Complex interdependencies
- Difficult to maintain and extend

### 2. AI Can Do It Better
- GPT-5 has pharmaceutical knowledge built-in
- Understands abbreviations, drug classes, therapeutic areas
- No need for dictionaries that become outdated

### 3. The Bible's Vision
From `ARCHITECTURE_PLAN.md`:
> "LET THE AI BE THE INTELLIGENCE"
> "NO drug expansion (AI knows drugs naturally via GPT-5 training)"
> "NO intent classification (AI understands naturally)"

---

## Migration Path

### Old Flow (6 Steps):
1. `entity_resolver` expands "EV" → ["enfortumab vedotin"]
2. `query_intelligence` classifies intent → "drug_search"
3. `enhanced_search` runs multi-stage pipeline
4. Search returns 500+ studies
5. `lean_synthesis` truncates data to fit prompt
6. AI analyzes truncated data

**Problem:** AI never saw full data, hardcoded logic was brittle

### New Flow (2 Steps):
1. **AI Step 1:** Interprets "EV + P" → `{"drugs": ["enfortumab vedotin", "pembrolizumab"]}`
2. **DataFrame Filter:** Pandas filters 4,686 → 11 studies
3. **AI Step 2:** Analyzes 11 studies (full data, not truncated)

**Benefits:** Accurate filtering, AI sees complete data, no hardcoding

---

## Code Reduction

| Component | Lines (Old) | Lines (New) | Reduction |
|-----------|-------------|-------------|-----------|
| entity_resolver.py | 415 | 0 | -415 |
| query_intelligence.py | 200 | 0 | -200 |
| enhanced_search.py | 400 | 0 | -400 |
| lean_synthesis.py | 300 | 0 | -300 |
| **Total Archived** | **1,315** | **0** | **-1,315** |
| ai_assistant.py | 0 | 200 | +200 |
| **Net Reduction** | | | **-1,115 lines (85% reduction)** |

Plus:
- app.py: -327 lines (removed old endpoints)
- **Total cleanup: ~1,442 lines removed**

---

## If You Need to Restore

1. Copy files back from `legacy_modules_archived/` to project root
2. Restore app.py from `app_backup_pre_cleanup_20251008.py`
3. Restore imports in app.py (lines 32-36)
4. Change frontend to use `/api/chat/enhanced` endpoint

**Not recommended** - the AI-first flow is more accurate and maintainable.

---

## Test Results

Validated that AI-first flow produces identical or better results:

### Test 1: "EV + P"
- **Expected:** 11 studies
- **Old system:** 13 studies (WRONG - included germ cell tumors, gastric cancer)
- **New system:** 11 studies (CORRECT - exact match with ground truth) ✅

### Test 2: "nivolumab renal cancer 10/18"
- **Expected:** 6 studies
- **Old system:** Not tested (would likely over-retrieve)
- **New system:** 6 studies (CORRECT - exact match with manual verification) ✅

### Test 3: "MD Anderson"
- **Expected:** 73 studies
- **Old system:** 89 studies (WRONG - over-retrieved)
- **New system:** 73 studies (CORRECT) ✅

---

## Archived Date
October 8, 2025

## Restored By
If these files have been moved back to the project root, the AI-first refactor was rolled back.
