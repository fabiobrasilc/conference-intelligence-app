# Pre-Computed Intelligence Button Replacement Plan

## Medical Affairs Strategic Overview

Replace real-time AI API calls with pre-computed intelligence modules that provide instant, validated insights. Each button becomes a **strategic intelligence package** rather than a theatrical streaming effect.

---

## BUTTON 1: Competitive Intelligence

### Current Flow ❌

1. User clicks button → 15-30s wait
2. Backend filters dataset by TA
3. Generates 3 tables (Drug Ranking, Studies, Emerging Threats)
4. Injects 4000+ chars into prompt
5. Streams OpenAI response describing tables user can already see
6. **Result**: $0.20 API cost, identical output for all users

### New Flow ✅

1. User clicks button → **Instant response (<1s)**
2. Load pre-computed analysis from cache: `PRECOMPUTED['competitor_bladder_cancer.json']`
3. Stream cached response with typing effect (psychological engagement)
4. Display pre-validated tables generated during nightly batch
5. **Result**: $0 API cost, QC'd medical accuracy, consistent messaging

### Medical Affairs Value

**MSL Use Case**: Quick prep before KOL meeting - "What are the 3 biggest competitive threats in Bladder?"

**Medical Director**: Portfolio defense brief - "Where is EV+P outcompeting avelumab?"

**Pre-computation Logic**:
- Generate 6 analyses (one per TA: Bladder, Lung, CRC, H&N, Renal, TGCT)
- Include EMD positioning guidance per TA
- Flag material threats (Phase 3 data, FDA submissions)

### Stepwise Technical Flow (Button Click → Output)

#### Step 1: User Action
- User clicks "Competitive Intelligence" button with filters: `TA = Bladder Cancer`

#### Step 2: Cache Key Generation
```python
cache_key = f"competitor_{ta_filter.lower().replace(' ', '_')}"
# Example: "competitor_bladder_cancer"
```

#### Step 3: Cache Lookup
```python
cache_file = f"cache/intelligence/{cache_key}.json"
if os.path.exists(cache_file):
    cached_data = json.load(open(cache_file))
else:
    # Fallback to real-time generation (rare)
    cached_data = generate_realtime_competitor_intel(ta_filter)
```

#### Step 4: Data Structure Loaded
```json
{
  "last_updated": "2025-10-05T12:00:00Z",
  "ta": "Bladder Cancer",
  "tables": {
    "drug_ranking": [...],
    "competitor_studies": [...],
    "emerging_threats": [...]
  },
  "analysis": {
    "overview": "ESMO 2025 bladder cancer data reveals...",
    "top_threats": [
      {
        "drug": "Enfortumab Vedotin + Pembrolizumab",
        "risk_level": "HIGH",
        "rationale": "EV-302 Phase 3 data in 1L directly competes with avelumab maintenance",
        "abstracts": ["LBA1", "450P", "451P"]
      }
    ],
    "competitive_summary": "Full narrative analysis text here..."
  }
}
```

#### Step 5: Frontend Display
- **Tables**: Render pre-computed tables instantly (no generation delay)
- **Analysis Text**: Stream with 150ms/word typing effect (psychological engagement)
- **Metadata**: Show "Last Updated: Oct 5, 2025" timestamp

#### Step 6: User Actions
- Read analysis
- Click "Export to PowerPoint" (future enhancement)
- Filter to specific drug within results

---

## BUTTON 2: KOL Analysis

### Current Flow ❌

1. Button click → filter dataset → generate top 10 authors table
2. Retrieve all abstracts per KOL (50-200 rows)
3. 4890-char prompt asking AI to "identify engagement priorities"
4. AI response essentially paraphrases the table
5. No session times, no competitive context, no talk tracks

### New Flow ✅

1. Button click → Load `KOL_INTELLIGENCE['bladder_cancer_kols.json']`
2. Display **pre-ranked engagement priority list**:
   - **Tier 1 KOLs**: EMD drug presenters (avelumab, tepotinib) + discussion time/room
   - **Tier 2 KOLs**: Competitive data presenters (EV+P, erdafitinib) + strategic interest
   - **Tier 3 KOLs**: Emerging biomarker leaders (FGFR3, Nectin-4)
3. One-click export to PowerPoint with KOL profiles
4. Include institutional affiliations for partnership targeting

### Medical Affairs Value

**MSL Use Case**: "Who should I prioritize in my 2-day ESMO schedule?"

**Answer**: Dr. Andrea Necchi (IEO Milano) - Avelumab maintenance 3yr update, Session: Presidential Symposium 1, Friday 13th Sept, 4:30pm, Hall A

**Pre-computation Logic**:
- Rank by: EMD drug relevance > presentation type (oral > poster) > institutional prestige
- Cross-reference with competitive studies (flag KOLs comparing us to competitors)
- Add "Last Interaction Date" field (requires CRM integration in future)

### Stepwise Technical Flow (Button Click → Output)

#### Step 1: User Action
- User clicks "KOL Analysis" button with filters: `TA = Bladder Cancer`

#### Step 2: Cache Lookup
```python
cache_key = f"kol_{ta_filter.lower().replace(' ', '_')}"
cached_data = load_from_cache(cache_key)
```

#### Step 3: Data Structure Loaded
```json
{
  "last_updated": "2025-10-05T12:00:00Z",
  "ta": "Bladder Cancer",
  "kol_tiers": {
    "tier1_emd_presenters": [
      {
        "name": "Dr. Andrea Necchi",
        "institution": "Istituto Europeo di Oncologia, Milano",
        "abstracts": [
          {
            "id": "LBA5",
            "title": "JAVELIN Bladder 100: 3-year survival update",
            "session": "Presidential Symposium 1",
            "date": "Friday, Sept 13",
            "time": "16:30-18:00",
            "room": "Hall A",
            "presentation_type": "Oral"
          }
        ],
        "engagement_priority": 1,
        "rationale": "Lead investigator for avelumab maintenance - critical for 1L positioning",
        "competitive_context": "Also presenting erdafitinib data (Abstract 452P) - dual engagement opportunity"
      }
    ],
    "tier2_competitive": [...],
    "tier3_emerging": [...]
  },
  "analysis": "Full narrative text ranking KOLs with rationale..."
}
```

#### Step 4: Frontend Display
- **Interactive KOL Cards**: Click to expand, show session schedule
- **Calendar View**: Map KOLs to ESMO conference schedule (visual timeline)
- **Engagement Checklist**: "Dr. Necchi - LBA5 Discussion (4:30pm) ☐ Attended ☐ Notes Added"

#### Step 5: MSL Workflow
1. Review Tier 1 KOLs (5-7 names)
2. Add to calendar with room/time
3. Prepare talk tracks based on "rationale" field
4. Export KOL profiles to PDF for offline reference

---

## BUTTON 3: Institution Analysis

### Current Flow ❌

1. Generate top 15 institutions table
2. Ask AI to "identify partnership opportunities"
3. AI lists institutions from table with generic rationale
4. No geographic analysis, no contact info, no partnership history

### New Flow ✅

1. Load `INSTITUTION_INTEL['bladder_cancer_institutions.json']`
2. Display **partnership-ready intelligence**:
   - **Tier 1**: Institutions with EMD collaborations (highlight existing partnerships)
   - **Tier 2**: High-volume institutions with NO EMD presence (white space opportunities)
   - **Tier 3**: Emerging research centers (China, Asia-Pacific growth hotspots)
3. Include: # abstracts, top investigators, MOA expertise, contact leads (if available)
4. Map view: Geographic distribution of institutional activity

### Medical Affairs Value

**Medical Director**: "Where should we invest in investigator-initiated trials?"

**Answer**: MD Anderson - 23 bladder abstracts, 0 avelumab studies → **Partnership Gap**

**Pre-computation Logic**:
- Cross-reference institutions against EMD clinical trial database
- Flag "competitive strongholds" (institutions loyal to Seagen, Janssen)
- Identify "rising stars" (institutions with 5+ abstracts, <5yr track record)

### Stepwise Technical Flow (Button Click → Output)

#### Step 1: User Action
- User clicks "Institution Analysis" button with filters: `TA = Bladder Cancer`

#### Step 2: Cache Lookup & Data Load
```python
cache_key = f"institution_{ta_filter.lower().replace(' ', '_')}"
cached_data = load_from_cache(cache_key)
```

#### Step 3: Data Structure Loaded
```json
{
  "last_updated": "2025-10-05T12:00:00Z",
  "ta": "Bladder Cancer",
  "institution_tiers": {
    "tier1_emd_partners": [
      {
        "name": "Dana-Farber Cancer Institute",
        "location": "Boston, MA, USA",
        "abstract_count": 12,
        "emd_collaboration": "JAVELIN Bladder 100 site investigator",
        "top_investigators": ["Dr. Guru Sonpavde", "Dr. Toni Choueiri"],
        "moa_expertise": ["ICIs", "ADCs", "FGFR inhibitors"],
        "partnership_status": "Active - Avelumab trials ongoing"
      }
    ],
    "tier2_white_space": [
      {
        "name": "MD Anderson Cancer Center",
        "location": "Houston, TX, USA",
        "abstract_count": 23,
        "emd_collaboration": "None",
        "top_investigators": ["Dr. Arlene Siefker-Radtke", "Dr. Matthew Campbell"],
        "moa_expertise": ["ADCs", "FGFR inhibitors", "Immunotherapy"],
        "partnership_status": "OPPORTUNITY - High volume, no EMD presence",
        "competitive_focus": "Seagen (EV), Janssen (erdafitinib)"
      }
    ],
    "tier3_emerging": [...]
  },
  "geographic_distribution": {
    "North America": 45,
    "Europe": 38,
    "Asia-Pacific": 12,
    "Other": 5
  },
  "analysis": "Full narrative identifying partnership opportunities..."
}
```

#### Step 4: Frontend Display
- **Interactive Map**: Plot institutions geographically with color-coding
  - Green = EMD partners
  - Yellow = White space opportunities
  - Blue = Emerging centers
- **Institution Cards**: Click to expand, show investigators + abstracts
- **Partnership Action Items**: "Contact Dr. Siefker-Radtke (MD Anderson) re: IIT collaboration"

#### Step 5: Medical Director Workflow
1. Review Tier 2 white space institutions
2. Identify top 3 partnership targets
3. Export to Excel with investigator contact info (if available)
4. Route to Clinical Development team for IIT discussions

---

## BUTTON 4: Biomarker/MOA Insights

### Current Flow ❌

1. Keyword search for biomarkers in titles (FGFR, Nectin-4, PD-L1)
2. Generate table of hits
3. Ask AI to "identify emerging trends"
4. Generic response: "FGFR3 mutations show promise..."

### New Flow ✅

1. Load `BIOMARKER_TRENDS['bladder_cancer_biomarkers.json']`
2. Display **actionable biomarker intelligence**:
   - **Validated Biomarkers**: PD-L1, FGFR3, HER2 (with EMD positioning)
   - **Emerging Signals**: Nectin-4, Trop-2, CLDN18.2 (competitive threats)
   - **Investment Opportunities**: Under-researched biomarkers with clinical potential
3. Include: # studies per biomarker, development stage distribution, competitor focus
4. **Predictive Alert**: "FGFR3 inhibitors show 300% YoY growth → potential avelumab displacement in 1L"

### Medical Affairs Value

**HQ Strategy**: "Should we invest in Nectin-4 biomarker companion diagnostics?"

**Answer**: 18 Nectin-4 studies at ESMO (vs 5 at ASCO), all Seagen/Astellas → **Competitive Threat**

**Pre-computation Logic**:
- Track biomarker mentions YoY across conferences
- Map biomarkers to EMD pipeline relevance
- Flag biomarkers appearing in Phase 3 but absent in EMD trials (data gaps)

### Stepwise Technical Flow (Button Click → Output)

#### Step 1: User Action
- User clicks "Biomarker/MOA Insights" button with filters: `TA = Bladder Cancer`

#### Step 2: Cache Lookup
```python
cache_key = f"biomarker_{ta_filter.lower().replace(' ', '_')}"
cached_data = load_from_cache(cache_key)
```

#### Step 3: Data Structure Loaded
```json
{
  "last_updated": "2025-10-05T12:00:00Z",
  "ta": "Bladder Cancer",
  "biomarker_categories": {
    "validated": [
      {
        "biomarker": "PD-L1",
        "study_count": 34,
        "emd_relevance": "HIGH - Avelumab approved in PD-L1+ patients",
        "phase_distribution": {"Phase 1": 5, "Phase 2": 12, "Phase 3": 17},
        "competitive_focus": ["Pembrolizumab", "Atezolizumab", "Durvalumab"],
        "abstracts": ["LBA1", "450P", "451P", ...]
      }
    ],
    "emerging_threats": [
      {
        "biomarker": "Nectin-4",
        "study_count": 18,
        "yoy_growth": "+260%",
        "emd_relevance": "LOW - No EMD assets targeting Nectin-4",
        "competitive_focus": ["Enfortumab Vedotin (Seagen/Astellas)"],
        "risk_assessment": "HIGH - EV+P dominance in 1L threatens avelumab positioning",
        "abstracts": ["LBA1", "LBA2", "452P", ...]
      }
    ],
    "investment_opportunities": [
      {
        "biomarker": "CLDN18.2",
        "study_count": 4,
        "emd_relevance": "MEDIUM - Emerging in gastric/bladder cancers",
        "competitive_activity": "LOW - Early-stage programs only",
        "opportunity": "White space for EMD antibody-drug conjugate development"
      }
    ]
  },
  "trend_analysis": {
    "rising_stars": ["Nectin-4", "Trop-2", "FGFR3"],
    "declining_interest": ["CTLA-4", "VEGF"],
    "stable_leaders": ["PD-L1", "HER2"]
  },
  "analysis": "Full narrative on biomarker landscape with strategic implications..."
}
```

#### Step 4: Frontend Display
- **Biomarker Trend Chart**: Bar chart showing YoY growth per biomarker
- **Risk Dashboard**: Color-coded alerts (RED = high threat, YELLOW = monitor, GREEN = opportunity)
- **Interactive Cards**: Click biomarker to see all associated abstracts + phase distribution

#### Step 5: HQ Strategy Workflow
1. Review "Emerging Threats" section (Nectin-4, Trop-2)
2. Assess EMD pipeline gaps
3. Initiate business development discussions (license Nectin-4 ADC?)
4. Brief R&D on competitive biomarker activity

---

## BUTTON 5: Strategic Recommendations

### Current Flow ❌

1. Sample 50 abstracts
2. 3000-char prompt asking for "strategic insights"
3. AI generates generic strategy: "Monitor ADCs, engage KOLs, watch FDA approvals"
4. No prioritization, no quantification, no risk assessment

### New Flow ✅

1. Load `STRATEGY_BRIEF['bladder_cancer_strategy.json']`
2. Display **executive-ready strategic intelligence**:
   - **Top 3 Material Threats**: Ranked by clinical stage + market impact
     - Example: *EV+P Phase 3 data in 1L → Direct avelumab competition (RISK: HIGH)*
   - **Top 3 Partnership Opportunities**: Institutions + scientific rationale
   - **Top 3 Data Gaps**: Areas where EMD has no presence but competitors dominate
3. Include: Investment priority scoring, competitive response playbooks, FDA timeline predictions
4. One-click export to PowerPoint for executive briefings

### Medical Affairs Value

**VP Medical Affairs**: "What's the 30-second ESMO strategic readout?"

**Answer**: "EV+P dominates 1L, FGFR3 inhibitors rising in 2L, Asia-Pacific institutions underrepresented in EMD partnerships"

**Pre-computation Logic**:
- Aggregate insights from other 4 buttons
- Weight threats by: Phase (3 > 2 > 1), indication overlap, time-to-market
- Cross-reference with EMD pipeline to identify defensive vs offensive opportunities

### Stepwise Technical Flow (Button Click → Output)

#### Step 1: User Action
- User clicks "Strategic Recommendations" button with filters: `TA = Bladder Cancer`

#### Step 2: Cache Lookup
```python
cache_key = f"strategy_{ta_filter.lower().replace(' ', '_')}"
cached_data = load_from_cache(cache_key)
```

#### Step 3: Data Structure Loaded
```json
{
  "last_updated": "2025-10-05T12:00:00Z",
  "ta": "Bladder Cancer",
  "strategic_pillars": {
    "material_threats": [
      {
        "rank": 1,
        "threat": "Enfortumab Vedotin + Pembrolizumab (EV+P)",
        "risk_level": "HIGH",
        "rationale": "EV-302 Phase 3 data shows superiority over chemo in 1L la/mUC - direct competition to avelumab maintenance positioning",
        "abstracts": ["LBA1", "450P"],
        "competitive_response": "Emphasize avelumab safety profile and maintenance setting differentiation",
        "timeline": "FDA approval expected Q4 2025"
      },
      {
        "rank": 2,
        "threat": "Erdafitinib (FGFR inhibitor)",
        "risk_level": "MEDIUM",
        "rationale": "Janssen expanding erdafitinib into earlier lines (adjuvant, 1L combo with ICI)",
        "abstracts": ["452P", "453P", "LBA3"],
        "competitive_response": "Monitor biomarker-driven patient segmentation - limited overlap with avelumab",
        "timeline": "Adjuvant FDA filing expected 2026"
      },
      {
        "rank": 3,
        "threat": "Sacituzumab Govitecan (Trop-2 ADC)",
        "risk_level": "MEDIUM",
        "rationale": "Expanding into earlier lines, potential combo with avelumab (opportunity?)",
        "abstracts": ["454P", "455P"],
        "competitive_response": "Explore EMD-Gilead partnership for sacituzumab + avelumab combo",
        "timeline": "1L combinations in Phase 2 currently"
      }
    ],
    "partnership_opportunities": [
      {
        "rank": 1,
        "institution": "MD Anderson Cancer Center",
        "rationale": "23 bladder abstracts, 0 EMD collaborations - high-volume white space",
        "action": "Initiate IIT discussions with Dr. Arlene Siefker-Radtke (ADC expertise)",
        "priority": "HIGH"
      },
      {
        "rank": 2,
        "institution": "Chinese Academy of Medical Sciences",
        "rationale": "12 abstracts, rising Asia-Pacific presence, government funding support",
        "action": "Explore regional partnership for avelumab registration studies",
        "priority": "MEDIUM"
      }
    ],
    "data_gaps": [
      {
        "rank": 1,
        "gap": "Nectin-4 targeting",
        "competitor_activity": "18 studies (all Seagen/Astellas)",
        "emd_presence": "None",
        "recommendation": "Evaluate in-licensing Nectin-4 ADC for bladder cancer portfolio"
      },
      {
        "rank": 2,
        "gap": "Biomarker-driven patient selection beyond PD-L1",
        "competitor_activity": "FGFR3, HER2, TMB-based trials increasing",
        "emd_presence": "Avelumab trials focus on PD-L1 only",
        "recommendation": "Initiate post-hoc biomarker analyses (TMB, HER2) from JAVELIN trials"
      }
    ]
  },
  "executive_summary": "ESMO 2025 bladder cancer data reveals intensifying competitive pressure in 1L setting with EV+P combination demonstrating superiority to chemotherapy. Avelumab maintenance positioning remains differentiated but threatened by earlier-line ADC+ICI combos. Key strategic priorities: (1) Emphasize safety/tolerability advantage, (2) Explore combo opportunities with sacituzumab, (3) Expand biomarker-driven patient selection beyond PD-L1.",
  "investment_priorities": [
    {"priority": 1, "action": "Defensive: Fund head-to-head trials (avelumab vs EV+P)", "budget": "$$$$"},
    {"priority": 2, "action": "Offensive: License Nectin-4 or Trop-2 ADC", "budget": "$$$"},
    {"priority": 3, "action": "Partnership: MD Anderson IIT collaborations", "budget": "$$"}
  ]
}
```

#### Step 4: Frontend Display
- **Executive Dashboard**: 3-column layout (Threats | Opportunities | Gaps)
- **Risk Heatmap**: Visual matrix of threats by risk level + timeline
- **Action Items**: Checklist format with responsible owners (Medical Affairs, BD, R&D)
- **Export to PowerPoint**: One-click generation of executive slide deck

#### Step 5: VP Medical Affairs Workflow
1. Review executive summary (30-second readout)
2. Drill into Top 3 Threats for competitive response planning
3. Share Partnership Opportunities with Clinical Development VP
4. Export to PowerPoint for upcoming Board meeting
5. Assign action items to functional leads

---

## Implementation Roadmap

### Phase 1: Pre-Computation Infrastructure (Week 1)

#### Task 1.1: Create Cache Generation Script
**File**: `scripts/generate_intelligence_cache.py`

```python
"""
Nightly batch job to pre-compute intelligence responses.
Run via cron: 0 2 * * * python scripts/generate_intelligence_cache.py
"""

import json
import os
from datetime import datetime
from app import (
    df_global,
    get_filtered_dataframe_multi,
    generate_top_authors_table,
    match_studies_with_competitive_landscape,
    # ... import all helper functions
)

THERAPEUTIC_AREAS = [
    "Bladder Cancer",
    "Lung Cancer",
    "Colorectal Cancer",
    "Head & Neck Cancer",
    "Renal Cancer",
    "TGCT"
]

PLAYBOOK_KEYS = [
    "competitor",
    "kol",
    "institution",
    "biomarker",
    "strategy"
]

def generate_competitor_intelligence(ta_filter):
    """Generate pre-computed competitive intelligence for given TA"""
    filtered_df = get_filtered_dataframe_multi([], [ta_filter], [], [])

    # Generate tables
    competitor_table = match_studies_with_competitive_landscape(filtered_df, ta_filter)
    drug_ranking = generate_drug_moa_ranking(competitor_table, n=20)
    emerging_threats = identify_emerging_threats(filtered_df, ta_filter)

    # Generate AI analysis (ONE-TIME cost)
    prompt = build_competitor_prompt(ta_filter, competitor_table, drug_ranking, emerging_threats)
    analysis_text = call_openai_sync(prompt)  # Synchronous call for batch job

    # Structure output
    output = {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "ta": ta_filter,
        "tables": {
            "drug_ranking": drug_ranking.to_dict('records'),
            "competitor_studies": competitor_table.to_dict('records'),
            "emerging_threats": emerging_threats.to_dict('records')
        },
        "analysis": analysis_text
    }

    return output

def main():
    """Generate all intelligence cache files"""
    cache_dir = "cache/intelligence"
    os.makedirs(cache_dir, exist_ok=True)

    for ta in THERAPEUTIC_AREAS:
        for playbook in PLAYBOOK_KEYS:
            print(f"Generating {playbook} for {ta}...")

            if playbook == "competitor":
                data = generate_competitor_intelligence(ta)
            elif playbook == "kol":
                data = generate_kol_intelligence(ta)
            elif playbook == "institution":
                data = generate_institution_intelligence(ta)
            elif playbook == "biomarker":
                data = generate_biomarker_intelligence(ta)
            elif playbook == "strategy":
                data = generate_strategy_intelligence(ta)

            # Save to cache
            cache_key = f"{playbook}_{ta.lower().replace(' ', '_')}"
            cache_file = os.path.join(cache_dir, f"{cache_key}.json")

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"  ✓ Saved to {cache_file}")

    print(f"\n✓ Generated {len(THERAPEUTIC_AREAS) * len(PLAYBOOK_KEYS)} cache files")

if __name__ == "__main__":
    main()
```

#### Task 1.2: Modify Flask Routes to Use Cache

**File**: `app.py` (modifications to `@app.route('/api/playbook/<playbook_key>/stream')`)

```python
@app.route('/api/playbook/<playbook_key>/stream')
def stream_playbook(playbook_key):
    """
    Pre-computed playbook streaming endpoint with cache-first strategy.
    """
    if playbook_key not in PLAYBOOKS:
        return jsonify({"error": "Invalid playbook"}), 404

    # Get filter parameters
    ta_filters = request.args.getlist('ta_filters[]') or request.args.getlist('ta_filters') or []

    # Generate cache key
    ta_filter = ta_filters[0] if ta_filters else "all_therapeutic_areas"
    cache_key = f"{playbook_key}_{ta_filter.lower().replace(' ', '_')}"
    cache_file = f"cache/intelligence/{cache_key}.json"

    def generate():
        try:
            # CACHE-FIRST STRATEGY
            if os.path.exists(cache_file):
                print(f"[CACHE HIT] Loading pre-computed response from {cache_file}")
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)

                # Send tables first
                for table_name, table_data in cached_data.get("tables", {}).items():
                    yield "data: " + json.dumps({
                        "title": table_name.replace('_', ' ').title(),
                        "columns": list(table_data[0].keys()) if table_data else [],
                        "rows": table_data
                    }) + "\n\n"

                # Stream cached analysis with typing effect
                analysis_text = cached_data.get("analysis", "")
                for word in analysis_text.split():
                    yield "data: " + json.dumps({"text": word + " "}) + "\n\n"
                    time.sleep(0.15)  # 150ms delay for realistic typing effect

                yield "data: [DONE]\n\n"

            else:
                # FALLBACK: Real-time generation for cache misses
                print(f"[CACHE MISS] Generating real-time response for {cache_key}")
                # ... existing real-time generation logic ...

        except Exception as e:
            print(f"[ERROR] {e}")
            yield "data: " + json.dumps({"error": str(e)}) + "\n\n"

    return Response(stream_with_heartbeat(generate()), mimetype='text/event-stream', headers=SSE_HEADERS)
```

### Phase 2: Quality Control Workflow (Week 2)

#### Task 2.1: Medical Review Interface
**File**: `templates/admin/review_cache.html`

- Display all 30 cached responses (5 buttons × 6 TAs)
- Allow medical reviewers to:
  - Flag EMD drug misclassifications
  - Edit analysis text for regulatory compliance
  - Approve/reject before production deployment
- Track review status (Pending, Approved, Rejected)

#### Task 2.2: Validation Rules
**File**: `scripts/validate_intelligence.py`

```python
def validate_competitor_intelligence(data, ta):
    """Validate competitive intelligence for medical accuracy"""
    errors = []

    # Rule 1: EMD drugs should not appear in "competitor threats"
    emd_drugs = ["avelumab", "bavencio", "tepotinib", "cetuximab", "pimicotinib"]
    analysis_lower = data["analysis"].lower()

    for emd_drug in emd_drugs:
        if emd_drug in analysis_lower and "threat" in analysis_lower:
            # Check if it's a false positive (e.g., "EV threatens avelumab" is OK)
            if f"{emd_drug} threat" in analysis_lower:
                errors.append(f"EMD drug '{emd_drug}' incorrectly labeled as threat")

    # Rule 2: All abstract IDs must exist in dataset
    abstract_pattern = r'\b\d{1,4}[A-Z]?\b'  # Matches "450P", "LBA1", etc.
    cited_abstracts = re.findall(abstract_pattern, data["analysis"])
    valid_abstracts = set(df_global['Identifier'].values)

    for abstract_id in cited_abstracts:
        if abstract_id not in valid_abstracts:
            errors.append(f"Invalid abstract ID cited: {abstract_id}")

    # Rule 3: Therapeutic area consistency
    if ta.lower() not in analysis_lower:
        errors.append(f"Analysis does not mention therapeutic area '{ta}'")

    return errors
```

### Phase 3: Frontend Enhancements (Week 3)

#### Task 3.1: Add "Last Updated" Timestamp
**File**: `templates/index.html` (modify button response display)

```html
<div class="intelligence-response">
    <div class="metadata">
        <span class="last-updated">Last Updated: {{ cached_data.last_updated }}</span>
        <button class="export-btn">Export to PowerPoint</button>
    </div>
    <div class="analysis-content">
        <!-- Streamed analysis text -->
    </div>
</div>
```

#### Task 3.2: Export to PowerPoint Feature
**File**: `app.py` (new route)

```python
from pptx import Presentation
from pptx.util import Inches, Pt

@app.route('/api/export/pptx/<playbook_key>/<ta_filter>')
def export_to_powerpoint(playbook_key, ta_filter):
    """Generate PowerPoint slide deck from cached intelligence"""

    cache_key = f"{playbook_key}_{ta_filter.lower().replace(' ', '_')}"
    cache_file = f"cache/intelligence/{cache_key}.json"

    if not os.path.exists(cache_file):
        return jsonify({"error": "No cached data found"}), 404

    with open(cache_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Create presentation
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(7.5)

    # Slide 1: Title
    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = f"{playbook_key.title()} Intelligence: {ta_filter}"

    # Slide 2-4: Tables
    for table_name, table_data in data["tables"].items():
        slide = prs.slides.add_slide(prs.slide_layouts[5])  # Blank layout
        # Add table with data...

    # Slide 5: Analysis Summary
    analysis_slide = prs.slides.add_slide(prs.slide_layouts[1])
    analysis_slide.shapes.title.text = "Strategic Analysis"
    # Add analysis text...

    # Save to temp file
    temp_file = f"/tmp/{cache_key}.pptx"
    prs.save(temp_file)

    return send_file(temp_file, as_attachment=True, download_name=f"{cache_key}.pptx")
```

#### Task 3.3: Visual Charts (Competitive Heatmap, KOL Network)
**File**: `static/js/charts.js`

- Use D3.js or Chart.js to render:
  - Competitive landscape heatmap (drugs × MOA classes)
  - KOL network graph (force-directed layout)
  - Biomarker trend chart (time series)

---

## Cost-Benefit Analysis

### Current State (Real-Time AI)
- **API Calls**: 5 buttons × 6 TAs × 100 users/month = 3,000 calls/month
- **Cost per Call**: $0.20 (average for GPT-4 with 4000-char prompts)
- **Monthly Cost**: 3,000 × $0.20 = **$600/month**
- **Annual Cost**: $7,200/year

### New State (Pre-Computed)
- **Pre-Computation**: 5 buttons × 6 TAs × 1 run/week = 30 calls/week
- **Weekly Cost**: 30 × $0.20 = $6/week
- **Monthly Cost**: $6 × 4 = **$24/month**
- **Annual Cost**: $288/year

### Savings
- **Monthly Savings**: $600 - $24 = **$576/month**
- **Annual Savings**: $7,200 - $288 = **$6,912/year**
- **Cost Reduction**: 96% reduction in API costs

### Additional Benefits (Non-Monetary)
- **Speed**: 15-30s → <1s (30× faster)
- **Consistency**: QC'd responses across all users
- **Reliability**: No OpenAI downtime impact on user experience
- **Medical Accuracy**: Human review before deployment
- **Regulatory Compliance**: Pre-approved language

---

## Success Metrics

### Technical KPIs
- ✅ Response time: <1s (vs 15-30s currently)
- ✅ Cache hit rate: >95% (only 5% fallback to real-time)
- ✅ API cost reduction: >95%
- ✅ Zero EMD drug misclassifications

### Medical Affairs KPIs
- ✅ MSL adoption: Track button usage before/during conferences
- ✅ Engagement effectiveness: Survey MSLs on KOL interaction success
- ✅ Strategic impact: # of executive briefings using exported intelligence
- ✅ Time-to-insight: Measure time from "ESMO data released" to "Medical Affairs briefed"

### User Satisfaction
- ✅ NPS score for intelligence quality
- ✅ Feature request tracking (what additional buttons/analyses do users want?)
- ✅ Export usage: # of PowerPoint exports (indicates actionability)

---

## Rollout Plan

### Week 1: Button 1 (Competitive Intelligence)
- Generate cache for all 6 TAs
- Deploy cache-first route
- Medical review & approval
- A/B test with 10 users

### Week 2: Button 2 (KOL Analysis)
- Generate KOL intelligence cache
- Add calendar integration
- Medical review
- Expand to 50 users

### Week 3: Buttons 3-5 (Institution, Biomarker, Strategy)
- Complete remaining cache generation
- Add visual charts (heatmaps, networks)
- Full medical review
- Production rollout to all users

### Week 4: Enhancements
- PowerPoint export feature
- User feedback collection
- Performance monitoring
- Iteration based on user requests

---

## Future Enhancements (Post-MVP)

### Multi-Conference Intelligence
- Import ASCO, ASH, SABCS data
- Track competitive momentum across conferences
- YoY trend analysis (ESMO 2024 → ESMO 2025)

### Predictive Analytics
- "Based on abstract trends, predict FDA approvals"
- "Forecast next year's dominant MOA classes"
- "Identify tomorrow's KOLs from today's junior authors"

### Personalization Layer
- Track user preferences (which TAs they focus on)
- Role-based views (MSL vs Medical Director vs VP)
- Regional customization (EU vs US vs Asia-Pacific)

### Integration with CRM
- Link KOLs to Veeva CRM profiles
- Track engagement history
- Suggest follow-up actions based on past interactions

---

## Appendix: Technical Architecture

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     NIGHTLY BATCH JOB                        │
│  (generate_intelligence_cache.py)                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │  Load ESMO 2025 Data   │
         │  (4,686 abstracts)     │
         └────────┬───────────────┘
                  │
                  ▼
    ┌─────────────────────────────┐
    │  For each TA (6 total):     │
    │  - Filter dataset           │
    │  - Generate tables          │
    │  - Call OpenAI (1× per TA)  │
    │  - Save to cache/           │
    └────────┬────────────────────┘
             │
             ▼
┌────────────────────────────────────┐
│  CACHE FILES (30 total)            │
│  - competitor_bladder_cancer.json  │
│  - kol_lung_cancer.json            │
│  - institution_crc.json            │
│  - ...                             │
└────────┬───────────────────────────┘
         │
         ▼
┌────────────────────────────────────┐
│  USER CLICKS BUTTON (Runtime)      │
│  1. Check cache                    │
│  2. If hit: stream cached response │
│  3. If miss: fallback to real-time │
└────────────────────────────────────┘
```

### File Structure

```
conference_intelligence_app/
├── app.py                          # Main Flask app
├── cache/
│   └── intelligence/               # Pre-computed responses
│       ├── competitor_bladder_cancer.json
│       ├── kol_bladder_cancer.json
│       ├── institution_bladder_cancer.json
│       ├── biomarker_bladder_cancer.json
│       ├── strategy_bladder_cancer.json
│       └── ... (25 more files for other TAs)
├── scripts/
│   ├── generate_intelligence_cache.py   # Nightly batch job
│   └── validate_intelligence.py         # QC validation rules
├── templates/
│   ├── index.html                       # Main UI
│   └── admin/
│       └── review_cache.html            # Medical review interface
└── static/
    ├── js/
    │   └── charts.js                    # D3.js visualizations
    └── css/
        └── intelligence.css             # Styling
```

---

## Conclusion

This plan transforms the COSMIC AI Assistant from a **theatrical streaming effect** into a **strategic medical affairs intelligence platform**. By pre-computing deterministic analyses, we achieve:

1. **96% cost reduction** ($7,200/year → $288/year)
2. **30× speed improvement** (15-30s → <1s)
3. **Zero EMD drug misclassifications** (human QC before deployment)
4. **Actionable outputs** (PowerPoint exports, calendar integration)
5. **Scalability** (add ASCO, ASH data without API cost explosion)

The key insight: **Stop trying to make the AI seem smart. Start making it actually useful.**

Medical affairs professionals don't need GPT-4 to describe a table they can already see. They need **instant, validated, actionable intelligence** that helps them engage KOLs, assess competitive threats, and defend portfolio positioning.

This plan delivers exactly that.
