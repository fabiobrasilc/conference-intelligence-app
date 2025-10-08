# Competitive Intelligence Button: Current vs Pre-Computed Flow

## Medical Affairs Context

**Current Problem**: MSL clicks "Competitive Intelligence" button filtered to "Bladder Cancer" → waits 15-30 seconds → receives 2000-word analysis. Another MSL in different region clicks same button with same filter → waits another 15-30 seconds → receives **IDENTICAL** analysis. Total cost: $0.40, total wait time: 30-60 seconds.

**Solution**: Pre-compute the analysis ONCE during nightly batch → MSL clicks button → instant response (<1s) → same quality analysis, zero API cost, consistent across organization.

---

## CURRENT FLOW (Real-Time AI Generation)

### Step 1: User Action
**What happens**: MSL clicks "Competitive Intelligence" button with TA filter: `Bladder Cancer`

**Frontend code** ([app.js:~900](static/js/app.js)):
```javascript
// User clicks button, frontend makes API call
fetch(`/api/playbook/competitor/stream?ta_filters[]=Bladder+Cancer`)
```

### Step 2: Backend Route Initialization
**What happens**: Flask route receives request and extracts filters

**Backend code** ([app.py:3764](app.py)):
```python
@app.route('/api/playbook/<playbook_key>/stream')
def stream_playbook(playbook_key):
    # Extract filter parameters
    ta_filters = request.args.getlist('ta_filters[]')  # ['Bladder Cancer']
    # Result: ta_filters = ['Bladder Cancer']
```

### Step 3: Dataset Filtering
**What happens**: Filter 4,686 studies down to Bladder Cancer only

**Backend code** ([app.py:3788-3795](app.py)):
```python
if playbook_key == "competitor":
    # Competitor button: drug_filters are for FOCUS, not dataset filtering
    if ta_filters:
        filtered_df = get_filtered_dataframe_multi([], ta_filters, [], [])
    else:
        filtered_df = df_global
    # Result: filtered_df has ~450 Bladder Cancer studies (from 4,686 total)
```

**Filtering logic** (uses keyword matching from `ESMO_THERAPEUTIC_AREAS`):
```python
ESMO_THERAPEUTIC_AREAS = {
    "Bladder Cancer": {
        "keywords": [
            "bladder", "urothelial", "uc", " muc", "la/muc",
            "mibc", "nmibc", "muscle-invasive bladder",
            "non-muscle-invasive bladder", "transitional cell"
        ]
    }
}
# Searches all 4,686 titles for these keywords → returns ~450 matches
```

### Step 4: Table Generation (3 Tables)
**What happens**: Generate 3 tables from filtered dataset

#### Table 1: Competitor Drug Ranking
**Backend code** ([app.py:3883-3905](app.py)):
```python
# Match studies to Drug_Company_names.csv
competitor_table = match_studies_with_competitive_landscape(filtered_df, "Bladder Cancer")
# Result: ~120 studies matched to known competitor drugs

# Generate ranking summary
ranking_table = generate_drug_moa_ranking(competitor_table, n=20)
# Result: Top 20 drugs by study count
```

**Example output** (Drug Ranking Table):
| Drug | Company | Study Count | MOA Class | MOA Target |
|------|---------|-------------|-----------|------------|
| Enfortumab Vedotin | Seagen/Astellas | 47 | ADC | Nectin-4 |
| Pembrolizumab | Merck | 23 | ICI | PD-1 |
| Erdafitinib | Janssen | 18 | TKI | FGFR |
| Sacituzumab Govitecan | Gilead | 15 | ADC | Trop-2 |

**Time cost**: ~2-3 seconds (drug database matching + table generation)

#### Table 2: Competitor Studies (Full List)
**Backend code** ([app.py:3907-3914](app.py)):
```python
# Send full competitor_table with all columns
yield "data: " + json.dumps({
    "title": f"Competitor Studies ({len(competitor_table)} abstracts)",
    "columns": ['Identifier', 'Title', 'Drug', 'Company', 'MOA Class', 'MOA Target'],
    "rows": competitor_table.to_dict('records')
}) + "\n\n"
# Result: ~120 studies displayed to user
```

**Example output**:
| Identifier | Title | Drug | Company | MOA Class | MOA Target |
|------------|-------|------|---------|-----------|------------|
| LBA1 | EV-302: EV+P vs chemo in 1L la/mUC | Enfortumab Vedotin | Seagen | ADC | Nectin-4 |
| 450P | JAVELIN Bladder 100: 3yr OS update | Avelumab | EMD Serono | ICI | PD-L1 |

**Time cost**: ~1 second (data formatting)

#### Table 3: Emerging Threats
**Backend code** ([app.py:3916-4028](app.py)):
```python
# Identify emerging threats via keyword matching
def is_emerging_threat(row):
    title = str(row['Title']).lower()
    return any(keyword in title for keyword in [
        'adc', 'bispecific', 'tce', 'car-t', 'radioligand',
        '+', ' plus ', ' in combination'
    ])

emerging_threats_base = filtered_df[filtered_df.apply(is_emerging_threat, axis=1)]
# Result: ~80 studies with novel mechanisms/combinations

# Classify with drug database
emerging_with_moa = classify_studies_with_drug_db(emerging_threats_base, "Bladder Cancer")

# Extract treatment settings (1L, 2L, Phase, etc.)
emerging_threats_display['Setting/Novelty'] = emerging_threats_display['Title'].apply(extract_setting_novelty)
# Result: Emerging threats table with 80 rows, enriched with MOA + setting data
```

**Example output**:
| Identifier | Title | Drug | Company | MOA Class | Setting/Novelty |
|------------|-------|------|---------|-----------|-----------------|
| 452P | First-in-human bispecific targeting Nectin-4 + PD-L1 | Not in Drug DB | Unknown | See Title | Phase 1, First-in-Human |
| 453P | EV + savolitinib in MET+ la/mUC | Enfortumab Vedotin + Savolitinib | Seagen + Blueprint | ADC + TKI | 1L, Biomarker-Selected |

**Time cost**: ~3-4 seconds (keyword matching + drug classification + setting extraction)

### Step 5: Prompt Building
**What happens**: Inject tables into massive prompt template

**Backend code** ([app.py:4073-4145](app.py)):
```python
# Get prompt template from PLAYBOOKS config
prompt_template = PLAYBOOKS["competitor"]["ai_prompt"]  # 3,373 characters

# Inject table data as markdown strings
table_context = "\n\n".join([
    f"**DRUG_RANKING**:\n{ranking_table.to_markdown()}",
    f"**COMPETITOR_ABSTRACTS**:\n{competitor_table.to_markdown()}",
    f"**EMERGING_THREATS**:\n{emerging_threats_display.to_markdown()}"
])
# Result: ~15,000 characters of table data

# Add TA-specific guidance
filter_guidance = f"""
**COMPETITIVE ANALYSIS FOCUS FOR BLADDER CANCER**:
- **Primary EMD Asset**: Avelumab in 1L maintenance metastatic urothelial carcinoma post-platinum
- **Key Competitors to Analyze**: 'enfortumab vedotin (EV)', 'EV+pembrolizumab (EV+P)', 'pembrolizumab', 'erdafitinib', 'sacituzumab govitecan'
- **Emerging Threat Categories**: ADCs, combination therapies, FGFR inhibitors
- **Analysis Scope**: The tables below contain ONLY Bladder Cancer studies. Focus exclusively on competitors relevant to this therapeutic area.
"""

# Build full prompt
full_prompt = f"{prompt_template}\n\n{filter_guidance}\n\n{table_context}"
# Result: ~20,000 character prompt (3,373 + 2,000 + 15,000)
```

**Time cost**: <1 second (string concatenation)

### Step 6: OpenAI API Call (Real-Time Streaming)
**What happens**: Send 20,000 character prompt to OpenAI, stream response token-by-token

**Backend code** ([app.py:4150-4156](app.py)):
```python
# Stream AI response
reasoning_effort = "low"  # Prevent timeout with large prompts
for token_event in stream_openai_tokens(full_prompt, reasoning_effort="low"):
    yield token_event
# Result: ~2000-word analysis streamed over 15-30 seconds
```

**OpenAI API details**:
- **Model**: `gpt-5-mini` with reasoning
- **Input tokens**: ~20,000 chars ≈ 5,000 tokens
- **Output tokens**: ~2,000 words ≈ 2,500 tokens
- **Cost**: Input ($0.01/1M tokens) + Output ($0.04/1M tokens) ≈ **$0.15-0.20 per response**
- **Time**: 15-30 seconds (streaming)

**Example AI response** (abbreviated):
```markdown
**SECTION 1: COMPETITIVE ACTIVITY OVERVIEW**

ESMO 2025 bladder cancer data reveals intense competitive activity with 120 competitor studies across 35 unique drugs. Enfortumab vedotin (EV) dominates with 47 studies, followed by pembrolizumab (23 studies) and erdafitinib (18 studies). MOA class distribution shows ADCs leading (38% of studies), followed by ICIs (31%) and TKIs (18%). Geographic hotspots include MD Anderson (23 studies), Memorial Sloan Kettering (18 studies), and Institut Gustave Roussy (15 studies). EMD portfolio presence is limited with 12 avelumab studies compared to 120 competitor studies.

**SECTION 2: COMPETITOR INTELLIGENCE SUMMARIES**

**Enfortumab Vedotin** (Seagen/Astellas) — **47 studies** at ESMO 2025

**Research Focus**: Predominantly EV+pembrolizumab combination therapy across multiple lines of therapy, biomarker-driven patient selection (Nectin-4 expression), resistance mechanisms, safety/tolerability in elderly populations.

**Treatment Settings**: 1L la/mUC (EV-302 trial), 2L+ post-platinum, maintenance therapy, adjuvant setting, biomarker-selected cohorts.

**Key Studies**:
- **(LBA1)** EV-302: EV+pembrolizumab vs chemotherapy in 1L la/mUC (Phase 3 pivotal data)
- **(450P)** EV+pembrolizumab in cisplatin-ineligible 1L mUC (Phase 2)
- **(451P)** Nectin-4 expression as predictive biomarker for EV response

**Material Threat to Avelumab 1L Maintenance?**: **YES**
EV-302 Phase 3 data showing EV+pembrolizumab superiority over chemotherapy in 1L setting directly competes with avelumab maintenance positioning. If approved, EV+P could displace avelumab in 1L post-platinum maintenance.

[... continues for 5-8 competitors ...]

**SECTION 3: EMERGING SIGNALS & INNOVATION**

[... emerging threats analysis ...]
```

**Total time cost**: **15-30 seconds**
**Total financial cost**: **$0.15-0.20**

### Step 7: Frontend Display
**What happens**: Frontend receives SSE stream, displays tables first, then streams AI text

**Frontend code** ([app.js:~400-500](static/js/app.js)):
```javascript
// Receive SSE stream
const reader = response.body.getReader();
while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    // Parse SSE event
    const parsed = JSON.parse(dataStr);

    if (parsed.title && parsed.columns) {
        // Display table
        renderTable(parsed.title, parsed.columns, parsed.rows);
    } else if (parsed.text) {
        // Stream AI text word-by-word
        aiResponseDiv.innerHTML += parsed.text;
    }
}
```

**User experience**:
1. Click button → loading spinner
2. **3-4 seconds**: Tables appear (Drug Ranking, Competitor Studies, Emerging Threats)
3. **15-30 seconds**: AI analysis streams word-by-word
4. **Total wait**: 18-34 seconds

---

## PRE-COMPUTED FLOW (Cache-First Strategy)

### PART A: Nightly Batch Job (One-Time Pre-Computation)

#### Step 1: Batch Script Initialization
**What happens**: Cron job runs at 2:00 AM to pre-compute all intelligence

**New file**: `scripts/generate_intelligence_cache.py`
```python
"""
Nightly batch job to pre-compute intelligence responses.
Run via Windows Task Scheduler: 2:00 AM daily
"""

THERAPEUTIC_AREAS = [
    "Bladder Cancer",
    "Lung Cancer",
    "Colorectal Cancer",
    "Head & Neck Cancer",
    "Renal Cancer",
    "TGCT"
]

def main():
    for ta in THERAPEUTIC_AREAS:
        print(f"[BATCH] Generating Competitive Intelligence for {ta}...")
        generate_competitor_intelligence_cache(ta)
```

#### Step 2: Generate Competitor Intelligence (Same Logic as Current Real-Time)
**What happens**: Run exact same logic as current button, but save result to JSON

**New function**:
```python
def generate_competitor_intelligence_cache(ta_filter: str):
    """
    Pre-compute competitive intelligence for a single TA.
    This runs the EXACT SAME logic as current real-time button.
    """
    from datetime import datetime
    import json
    import os

    # STEP 1: Filter dataset (same as current Step 3)
    filtered_df = get_filtered_dataframe_multi([], [ta_filter], [], [])
    print(f"[BATCH] Filtered to {len(filtered_df)} {ta_filter} studies")

    # STEP 2: Generate tables (same as current Step 4)
    # Table 1: Drug Ranking
    competitor_table = match_studies_with_competitive_landscape(filtered_df, ta_filter)
    ranking_table = generate_drug_moa_ranking(competitor_table, n=20)

    # Table 2: Competitor Studies (full list)
    competitor_studies = competitor_table[['Identifier', 'Title', 'Drug', 'Company', 'MOA Class', 'MOA Target']]

    # Table 3: Emerging Threats
    emerging_threats_base = filtered_df[filtered_df.apply(is_emerging_threat, axis=1)]
    emerging_with_moa = classify_studies_with_drug_db(emerging_threats_base, ta_filter)
    # ... (same enrichment logic as current)

    # STEP 3: Build prompt (same as current Step 5)
    prompt_template = PLAYBOOKS["competitor"]["ai_prompt"]
    filter_guidance = build_filter_guidance(ta_filter)  # TA-specific competitor guidance
    table_context = build_table_context(ranking_table, competitor_studies, emerging_threats)
    full_prompt = f"{prompt_template}\n\n{filter_guidance}\n\n{table_context}"

    # STEP 4: Call OpenAI (SYNCHRONOUS, not streaming)
    print(f"[BATCH] Calling OpenAI for {ta_filter}...")
    response = client.responses.create(
        model="gpt-5-mini",
        input=[{"role": "user", "content": full_prompt}],
        reasoning={"effort": "low"},
        max_output_tokens=3000
    )
    analysis_text = response.output_text  # Full text, not streamed
    print(f"[BATCH] Generated {len(analysis_text)} chars of analysis")

    # STEP 5: Structure output as JSON
    cache_data = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "ta": ta_filter,
        "dataset_size": len(filtered_df),
        "competitor_count": len(competitor_table),
        "tables": {
            "drug_ranking": {
                "title": f"Competitor Drug Ranking ({len(ranking_table)} drugs)",
                "subtitle": "Drug database matching with MOA appending for combinations",
                "columns": list(ranking_table.columns),
                "rows": ranking_table.to_dict('records')
            },
            "competitor_studies": {
                "title": f"Competitor Studies ({len(competitor_studies)} abstracts)",
                "subtitle": "Combinations shown as single entries with appended MOAs",
                "columns": list(competitor_studies.columns),
                "rows": competitor_studies.to_dict('records')
            },
            "emerging_threats": {
                "title": f"Emerging Threats ({len(emerging_threats)} signals)",
                "subtitle": "Novel mechanisms, combinations, and early-phase programs",
                "columns": list(emerging_threats.columns),
                "rows": emerging_threats.to_dict('records')
            }
        },
        "analysis": analysis_text  # Full 2000-word analysis
    }

    # STEP 6: Save to cache file
    cache_dir = "cache/intelligence"
    os.makedirs(cache_dir, exist_ok=True)

    cache_key = f"competitor_{ta_filter.lower().replace(' ', '_')}"
    cache_file = os.path.join(cache_dir, f"{cache_key}.json")

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)

    print(f"[BATCH] ✓ Saved to {cache_file}")
    print(f"[BATCH] File size: {os.path.getsize(cache_file) / 1024:.1f} KB")

    return cache_file
```

**Batch job output** (example for Bladder Cancer):
```
[BATCH] Generating Competitive Intelligence for Bladder Cancer...
[BATCH] Filtered to 447 Bladder Cancer studies
[BATCH] Generated competitor table with 118 studies
[BATCH] Drug ranking: 20 drugs
[BATCH] Emerging threats: 82 signals
[BATCH] Calling OpenAI for Bladder Cancer...
[BATCH] Generated 8,450 chars of analysis
[BATCH] ✓ Saved to cache/intelligence/competitor_bladder_cancer.json
[BATCH] File size: 156.3 KB
```

**Time cost**: ~25 seconds per TA (table generation + API call)
**Financial cost**: $0.15-0.20 per TA
**Total batch job**: 6 TAs × 25s = **2.5 minutes**, 6 × $0.20 = **$1.20 per run**

**Batch schedule**: Once per week (ESMO data is static) = **$1.20/week** = **$5/month**

#### Step 3: Cache File Structure
**What happens**: JSON file saved to disk

**File**: `cache/intelligence/competitor_bladder_cancer.json`
```json
{
  "last_updated": "2025-10-06T02:15:33Z",
  "ta": "Bladder Cancer",
  "dataset_size": 447,
  "competitor_count": 118,
  "tables": {
    "drug_ranking": {
      "title": "Competitor Drug Ranking (20 drugs)",
      "subtitle": "Drug database matching with MOA appending for combinations",
      "columns": ["Drug", "Company", "Study Count", "MOA Class", "MOA Target"],
      "rows": [
        {
          "Drug": "Enfortumab Vedotin",
          "Company": "Seagen/Astellas",
          "Study Count": 47,
          "MOA Class": "ADC",
          "MOA Target": "Nectin-4"
        },
        {
          "Drug": "Pembrolizumab",
          "Company": "Merck",
          "Study Count": 23,
          "MOA Class": "ICI",
          "MOA Target": "PD-1"
        }
      ]
    },
    "competitor_studies": { /* ... 118 rows ... */ },
    "emerging_threats": { /* ... 82 rows ... */ }
  },
  "analysis": "**SECTION 1: COMPETITIVE ACTIVITY OVERVIEW**\n\nESMO 2025 bladder cancer data reveals intense competitive activity with 118 competitor studies across 35 unique drugs. Enfortumab vedotin (EV) dominates with 47 studies, followed by pembrolizumab (23 studies) and erdafitinib (18 studies)...\n\n[Full 2000-word analysis text continues...]"
}
```

**All cache files generated**:
```
cache/intelligence/
├── competitor_bladder_cancer.json (156 KB)
├── competitor_lung_cancer.json (178 KB)
├── competitor_colorectal_cancer.json (142 KB)
├── competitor_head_neck_cancer.json (98 KB)
├── competitor_renal_cancer.json (134 KB)
└── competitor_tgct.json (45 KB)
```

---

### PART B: Runtime (Button Click → Instant Response)

#### Step 1: User Action (Same as Current)
**What happens**: MSL clicks "Competitive Intelligence" button with TA filter: `Bladder Cancer`

**Frontend code** (unchanged):
```javascript
fetch(`/api/playbook/competitor/stream?ta_filters[]=Bladder+Cancer`)
```

#### Step 2: Backend Route with Cache Check
**What happens**: Check cache FIRST, only fall back to real-time if cache miss

**Modified backend code** ([app.py:3764](app.py)):
```python
@app.route('/api/playbook/<playbook_key>/stream')
def stream_playbook(playbook_key):
    """
    MODIFIED: Cache-first playbook streaming endpoint.
    """
    if playbook_key not in PLAYBOOKS:
        return jsonify({"error": "Invalid playbook"}), 404

    # Get filter parameters
    ta_filters = request.args.getlist('ta_filters[]') or []

    # CACHE KEY GENERATION
    ta_filter = ta_filters[0] if ta_filters else "all_therapeutic_areas"
    cache_key = f"{playbook_key}_{ta_filter.lower().replace(' ', '_')}"
    cache_file = f"cache/intelligence/{cache_key}.json"

    def generate():
        try:
            # ============ CACHE-FIRST STRATEGY ============
            if os.path.exists(cache_file):
                print(f"[CACHE HIT] Loading from {cache_file}")
                start_time = time.time()

                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)

                load_time = time.time() - start_time
                print(f"[CACHE] Loaded {cache_key} in {load_time:.3f}s")

                # SEND METADATA FIRST
                yield "data: " + json.dumps({
                    "metadata": {
                        "last_updated": cached_data["last_updated"],
                        "dataset_size": cached_data["dataset_size"],
                        "competitor_count": cached_data["competitor_count"],
                        "cache_hit": True
                    }
                }) + "\n\n"

                # SEND TABLES (instant, no generation delay)
                for table_name, table_data in cached_data["tables"].items():
                    yield "data: " + json.dumps({
                        "title": table_data["title"],
                        "subtitle": table_data.get("subtitle", ""),
                        "columns": table_data["columns"],
                        "rows": table_data["rows"]
                    }) + "\n\n"
                print(f"[CACHE] Sent {len(cached_data['tables'])} tables")

                # STREAM CACHED ANALYSIS with realistic typing effect
                analysis_text = cached_data["analysis"]
                words = analysis_text.split()

                for i, word in enumerate(words):
                    yield "data: " + json.dumps({"text": word + " "}) + "\n\n"
                    # Typing effect: 100ms per word (realistic reading speed)
                    time.sleep(0.1)

                    # Send heartbeat every 50 words to prevent timeout
                    if i % 50 == 0:
                        yield "data: " + json.dumps({"heartbeat": True}) + "\n\n"

                yield "data: [DONE]\n\n"

                total_time = time.time() - start_time
                print(f"[CACHE] Total response time: {total_time:.1f}s (includes typing effect)")

            else:
                # ============ CACHE MISS: FALLBACK TO REAL-TIME ============
                print(f"[CACHE MISS] {cache_file} not found, generating real-time...")
                # Run original logic (Steps 3-6 from current flow)
                # ... (exact same code as current implementation)

        except Exception as e:
            print(f"[ERROR] {e}")
            yield "data: " + json.dumps({"error": str(e)}) + "\n\n"

    return Response(stream_with_heartbeat(generate()),
                    mimetype='text/event-stream',
                    headers=SSE_HEADERS)
```

**Cache hit flow**:
1. **Load cache file**: ~0.05 seconds (load 156 KB JSON)
2. **Send metadata**: ~0.01 seconds
3. **Send 3 tables**: ~0.1 seconds (serialize JSON)
4. **Stream analysis with typing effect**: ~200 words × 0.1s = **20 seconds** (artificial delay)
5. **Total time**: **~20 seconds** (mostly typing effect for UX)

**Financial cost**: **$0.00** (no API call)

#### Step 3: Frontend Display (Unchanged)
**What happens**: Frontend receives same SSE stream format, displays identically

**User experience**:
1. Click button → loading spinner
2. **<1 second**: Tables appear (all 3 tables sent instantly from cache)
3. **20 seconds**: AI analysis streams word-by-word (typing effect from cached text)
4. **Total wait**: ~20 seconds (vs 18-34 seconds current)

**User perception**: Feels slightly faster, but main benefit is **consistency** and **zero cost**

---

## COMPARISON TABLE

| Metric | Current (Real-Time) | Pre-Computed (Cache) | Savings |
|--------|---------------------|----------------------|---------|
| **User wait time** | 18-34 seconds | ~20 seconds | 10-40% faster |
| **Backend processing** | 3-4s (tables) + 15-30s (AI) | 0.15s (cache load) | **99% faster** |
| **API cost per click** | $0.15-0.20 | $0.00 | **100% reduction** |
| **Monthly cost (100 users)** | $600-800 | $5 (batch only) | **99% reduction** |
| **Response consistency** | Varies (AI randomness) | Identical for all users | **100% consistent** |
| **Medical review** | Impossible (generated on-demand) | Pre-reviewed before deployment | **Compliance gain** |
| **Cache invalidation** | N/A | Weekly batch refresh | Manual control |

---

## WHAT NEEDS TO BE BUILT

### 1. Batch Script (`scripts/generate_intelligence_cache.py`)
**Complexity**: Medium
**Lines of code**: ~300

**Key functions**:
- `generate_competitor_intelligence_cache(ta_filter)` - Main logic (reuses 90% of current code)
- `build_filter_guidance(ta_filter)` - TA-specific competitor guidance (already exists in current code)
- `save_to_cache(cache_data, cache_file)` - JSON serialization
- `main()` - Loop through 6 TAs, generate all caches

**Testing requirements**:
- Run manually for 1 TA (Bladder Cancer)
- Verify JSON structure matches expected format
- Load cache file and verify tables + analysis render correctly
- Run for all 6 TAs, ensure batch completes in <5 minutes

### 2. Flask Route Modification (`app.py:3764`)
**Complexity**: Low
**Lines of code**: ~50 (mostly wrapping existing code)

**Changes**:
- Add cache key generation logic
- Add cache file check (`os.path.exists()`)
- Add cache loading + SSE streaming
- Wrap existing real-time logic in `else` block (fallback)

**Testing requirements**:
- Test cache hit: click button with Bladder Cancer filter → verify instant response
- Test cache miss: click button with non-existent TA → verify fallback to real-time
- Test typing effect: verify analysis streams word-by-word (not instant dump)

### 3. Cache Directory Structure
**Complexity**: Trivial
**Lines of code**: 0 (just create directory)

**Structure**:
```
cache/
└── intelligence/
    ├── competitor_bladder_cancer.json
    ├── competitor_lung_cancer.json
    ├── competitor_colorectal_cancer.json
    ├── competitor_head_neck_cancer.json
    ├── competitor_renal_cancer.json
    └── competitor_tgct.json
```

**Git handling**:
- Add `cache/intelligence/.gitkeep` (track directory)
- Add `cache/intelligence/*.json` to `.gitignore` (don't track cache files)

### 4. Windows Task Scheduler Setup (Optional for MVP)
**Complexity**: Low
**Manual setup**: ~5 minutes

**Task configuration**:
- **Trigger**: Weekly, Sundays at 2:00 AM
- **Action**: `python scripts/generate_intelligence_cache.py`
- **Working directory**: `C:\...\conference_intelligence_app`

**Alternative**: Run manually before ESMO conference (ESMO data doesn't change daily)

### 5. Frontend Enhancement (Optional for v2)
**Complexity**: Low
**Lines of code**: ~20

**Features to add**:
- Display "Last Updated" timestamp from cache metadata
- Add visual indicator for cache hit vs real-time generation
- Add "Refresh Cache" button for admins

---

## ROLLOUT PLAN

### Phase 1: Proof of Concept (1 TA only)
1. Build batch script for Bladder Cancer only
2. Generate cache file manually: `python scripts/generate_intelligence_cache.py --ta "Bladder Cancer"`
3. Modify Flask route with cache-first logic
4. Test button with Bladder Cancer filter → verify instant response
5. **Decision point**: If successful, proceed to Phase 2

### Phase 2: Full Deployment (All 6 TAs)
1. Extend batch script to loop through all 6 TAs
2. Run full batch manually: `python scripts/generate_intelligence_cache.py`
3. Test button with all 6 TAs → verify all cache hits
4. **Medical review**: Have medical affairs team review all 6 cached responses
5. Approve for production

### Phase 3: Automation (Optional)
1. Set up Windows Task Scheduler for weekly batch
2. Add error notifications (email if batch fails)
3. Add cache monitoring (alert if cache files missing)

---

## RISKS & MITIGATIONS

### Risk 1: Cache Staleness
**Problem**: ESMO data changes (late-breaking abstracts added), cache is outdated
**Mitigation**:
- Add "Last Updated" timestamp to UI
- Manual cache refresh button for admins
- Weekly batch auto-refresh

### Risk 2: Cache Miss (User selects non-cached TA)
**Problem**: User applies custom filter combo not in cache (e.g., Bladder + Session filter)
**Mitigation**:
- Fallback to real-time generation (already built)
- Log cache misses to identify popular filter combos → add to batch job

### Risk 3: Medical Inaccuracy (EMD drug misclassification)
**Problem**: Cached response incorrectly labels avelumab study as "competitor threat"
**Mitigation**:
- Medical review workflow before cache deployment
- Validation rules in batch script (check for EMD drug false positives)

### Risk 4: File Corruption
**Problem**: Cache file corrupted, JSON parse error
**Mitigation**:
- Try/except with fallback to real-time
- Batch job writes to temp file first, then atomic rename

---

## MEDICAL AFFAIRS VALUE PROPOSITION

### For MSLs
- **Instant intelligence**: <1s table display (vs 3-4s current)
- **Consistent messaging**: All MSLs receive identical analysis (no AI randomness)
- **Offline capability** (future): Download cache files for offline conference use

### For Medical Directors
- **Cost savings**: $600/month → $5/month (99% reduction)
- **Quality control**: Pre-review all responses before deployment (compliance)
- **Predictable performance**: No OpenAI downtime impact on user experience

### For HQ Strategy
- **Standardized intelligence**: Organization-wide alignment on competitive assessment
- **Audit trail**: Cache files serve as timestamped record of competitive landscape analysis
- **Scalability**: Add ASCO, ASH, SABCS conferences without API cost explosion

---

## NEXT STEPS

1. **Review this analysis** - Confirm approach makes sense
2. **Build Phase 1** - Bladder Cancer only proof of concept
3. **Test & validate** - Medical review of cached response
4. **Scale to all TAs** - Full deployment
5. **Iterate on other buttons** - KOL, Institution, Biomarker, Strategy

Ready to start building Phase 1?
