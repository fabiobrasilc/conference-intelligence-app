# Active Scripts in Conference Intelligence App

## Core Application Files (ACTIVE)

### Main Application
- **`app.py`** - Main Flask application
  - Routes: `/`, `/api/chat/enhanced`, `/api/data`, `/health`
  - System prompt, meta-query detection, competitor intelligence
  - Drug database caching (444 drugs)
  - Smart TA filtering

### Supporting Modules (Imported by app.py)
1. **`entity_resolver.py`** - Drug/institution entity extraction
   - Functions: `expand_query_entities()`, `resolve_drug_name()`
   - Extracts drugs, institutions, TA keywords from queries

2. **`improved_search.py`** - Search text precomputation
   - Functions: `precompute_search_text()`, `smart_search()`
   - TIER1 enhancement: normalized search across all fields

3. **`query_intelligence.py`** - Intent classification
   - Functions: `analyze_query()`
   - Detects intent (factual, list, synthesis, comparison)
   - User verbosity control (concise/comprehensive)

4. **`enhanced_search.py`** - Complete search pipeline
   - Functions: `complete_search_pipeline()`
   - Integrates entity resolution + query intelligence + multi-field search
   - Vague query guard

5. **`lean_synthesis.py`** - AI prompt generation
   - Functions: `build_lean_synthesis_prompt()`, `estimate_prompt_tokens()`
   - Token-efficient prompts (80% reduction)
   - Brevity guard (1 result = minimal verbosity)

## Frontend
- **`templates/index.html`** - Main UI
- **`static/js/app.js`** - JavaScript (calls `/api/chat/enhanced`)
- **`static/css/styles.css`** - Styling

## Configuration
- **`railway.toml`** - Railway deployment config
- **`.env`** - Environment variables (OpenAI API key)
- **`requirements.txt`** - Python dependencies

## Data Files (ACTIVE)
- **`ESMO_2025_FINAL_20250929.csv`** - Conference data (4,686 studies)
- **`Drug_Company_names_with_MOA.csv`** - Drug database (444 drugs)
- **`bladder-json.json`** - Bladder cancer competitive landscape
- **`nsclc-json.json`** - Lung cancer competitive landscape
- **`erbi-crc-json.json`** - Colorectal cancer competitive landscape
- **`erbi-HN-json.json`** - Head & neck cancer competitive landscape

---

## Inactive Files (Can be deleted or archived)

### Backup Files
- `app copy*.py` (4 files)
- `app_backup_*.py` (3 files)
- `app_v*.py` (10 versions)
- `app_enhanced_chat_endpoint.py` (merged into main app)

### Debug Scripts (70+ files)
- `debug_*.py` (13 files)
- `test_*.py` (40+ files)
- `check_*.py` (2 files)
- `inspect_*.py` (2 files)

**Note:** Test scripts are useful for validation but not required for production.

---

## Architecture Flow

```
User Query
    ↓
Frontend (app.js) → /api/chat/enhanced
    ↓
app.py (enhanced endpoint)
    ↓
detect_meta_query() → If meta, return natural response
    ↓
complete_search_pipeline() (enhanced_search.py)
    ├→ expand_query_entities() (entity_resolver.py)
    ├→ analyze_query() (query_intelligence.py)
    ├→ Vague query guard
    ├→ smart_search() (improved_search.py)
    └→ build_lean_synthesis_prompt() (lean_synthesis.py)
    ↓
stream_openai_tokens() → AI synthesis with system prompt
    ↓
Response to frontend
```

---

## Key Features Implemented

1. **Drug Database Integration** (444 drugs, MOA/target caching)
2. **Smart TA Filtering** (multi-field + title-based exclusions)
3. **AI Competitor Intelligence** (auto-detects competitors)
4. **System Prompt** (brevity rules, professional tone)
5. **Meta-Query Detection** (conversational responses)
6. **User Verbosity Control** (concise/comprehensive)
7. **Brevity Guard** (1 result = minimal response)
8. **Vague Query Guard** (prevents 4,686-study dumps)

---

**Last Updated:** October 8, 2025
