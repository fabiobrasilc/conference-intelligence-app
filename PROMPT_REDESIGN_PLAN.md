# COSMIC Playbook Prompt Redesign Plan
**Date**: October 1, 2025
**Purpose**: Transform prompts from academic summaries to actionable field intelligence

---

## 🎯 CORE PHILOSOPHY CHANGE

### BEFORE (Current State):
- **Audience**: Medical Directors/VP Medical Affairs
- **Output Style**: Comprehensive academic briefing
- **Use Case**: Post-conference strategic planning
- **Example**: "Pembrolizumab appeared in 87 abstracts (43% of all IO studies)..."

### AFTER (Target State):
- **Audience**: MSLs + Medical Directors (dual-purpose outputs)
- **Output Style**: Tactical field intelligence with strategic context
- **Use Case**: Pre/during/post-conference execution
- **Example**: "🔴 HIGH ALERT: EV+P Phase 3 data Friday 10am (Abstract #1847) threatens avelumab positioning. MSL response: 'Different paradigms - EV+P is upfront combo for cisplatin-eligible, avelumab maintenance is for post-chemo responders.'"

---

## 📋 PLAYBOOK-BY-PLAYBOOK REDESIGN

### 1. COMPETITOR INTELLIGENCE 🏆

#### CURRENT ISSUES:
- ✅ Good: Instructs AI to quantify presence, cite Abstract #, assess threat levels
- ❌ Problem: Produces 20-paragraph academic landscape analysis
- ❌ Problem: No distinction between practice-changing vs incremental data
- ❌ Problem: No field team response guidance

#### REDESIGNED PROMPT STRUCTURE:

```
Section 1: IMMEDIATE COMPETITIVE THREATS (Action-Oriented)
- 🔴 HIGH ALERT items requiring MSL response within 7 days
- 🟡 MEDIUM PRIORITY items to monitor
- 🟢 LOW PRIORITY baseline competitor activity

For each HIGH ALERT:
1. Threat Description: What data? Which abstract? When presenting?
2. EMD Impact: How does this threaten our positioning?
3. Field Response Script: Exact talking points for MSLs when HCPs ask
4. Escalation Trigger: When to involve medical affairs leadership

Section 2: COMPETITIVE LANDSCAPE OVERVIEW (Strategic Context)
- Quantify total competitive activity (X abstracts for Y competitors)
- MOA class distribution (ADCs: X%, IO: Y%, TKI: Z%)
- Treatment paradigm shifts (upfront combos vs maintenance vs sequencing)

Section 3: TOP 5 COMPETITOR DEEP-DIVE
- Focus on direct threats (same indication/line as EMD asset)
- Quantify presence, assess strategic threat level
- Identify white space (what competitors AREN'T doing)

Section 4: KOL & INSTITUTIONAL COMPETITIVE INTELLIGENCE
- Which thought leaders are driving competitor research?
- Which institutions have high competitor trial activity?
- Engagement implications (can we still work with these KOLs?)
```

#### KEY MEDICAL AFFAIRS ADDITIONS:
- **Alert Priority System** (🔴🟡🟢): MSLs scan for HIGH items first
- **Field Response Scripts**: Pre-written talking points for HCP conversations
- **Escalation Triggers**: Clear guidance on when medical director involvement needed
- **White Space Analysis**: Not just threats, but opportunities

---

### 2. KOL ANALYSIS 👥

#### CURRENT ISSUES:
- ✅ Good: Comprehensive KOL profiling framework
- ✅ Good: Portfolio relevance assessment
- ❌ **CRITICAL BUG** (line 414): "Avoid tactical engagement recommendations" - THIS MUST GO
- ❌ Problem: Ranks by abstract count (productivity) not engagement priority
- ❌ Problem: No tier stratification (all KOLs treated equally)
- ❌ Problem: No competitive intelligence (KOL on competitor advisory board?)

#### REDESIGNED PROMPT STRUCTURE:

```
Section 1: TIER 1 KOL ENGAGEMENT PRIORITIES (MSL Action Items)
For top 5-8 "must-meet" KOLs:
- NAME & INSTITUTION: Dr. [Name] ([Institution], [City/Country])
- ABSTRACT COUNT: X presentations at ESMO 2025
- WHY TIER 1:
  * Presents EMD-relevant data (Abstract #s)
  * High influence in therapeutic area
  * No major competitor advisory board ties (or note if applicable)
- ENGAGEMENT STRATEGY:
  * Where/when to find them: "Presenting Friday 2pm (Abstract #1847)"
  * Talking points: "Discuss real-world avelumab experience in cisplatin-ineligible patients"
  * Ask: "Would you participate in investigator-initiated trial?"
- PORTFOLIO ALIGNMENT:
  * Avelumab: [Yes/No + Abstract #s]
  * Tepotinib: [Yes/No + Abstract #s]
  * Cetuximab: [Yes/No + Abstract #s]

Section 2: TIER 2 KOL OPPORTUNITIES (Strategic Engagement)
For next 5-10 "strong potential" KOLs:
- NAME & INSTITUTION
- WHY TIER 2:
  * Presents some competitor data BUT also works in EMD therapeutic areas
  * Emerging thought leader (2-5 abstracts vs 10+)
  * Geographic/institutional partnership potential
- ENGAGEMENT APPROACH: Focus on scientific collaboration, not current competitor ties

Section 3: TIER 3 KOL MONITORING (Low Priority)
For remaining KOLs in top 15:
- WHY TIER 3:
  * Heavy competitor focus with minimal EMD relevance
  * Different therapeutic areas than EMD portfolio
  * Already established strong competitor relationships
- ACTION: Monitor their presentations for competitive intelligence, but deprioritize engagement

Section 4: COLLECTIVE KOL LANDSCAPE ANALYSIS
- Therapeutic area concentration
- Geographic distribution (identify US/EU/APAC clusters)
- Institutional hubs (multiple KOLs from same center)
- Platform KOLs (work across multiple indications)

Section 5: NOTABLE RESEARCH HIGHLIGHTS
- 6-10 key presentations from Tier 1/2 KOLs
- Prioritize: EMD portfolio relevance > Novel science > Competitive intelligence
- Cite Abstract # for each
```

#### KEY MEDICAL AFFAIRS ADDITIONS:
- **REMOVE** line 414 ("avoid tactical engagement recommendations") - COMPLETE REVERSAL
- **Tier 1/2/3 System**: Clear prioritization for MSL time allocation
- **Engagement Strategy**: Where to find KOL, what to discuss, what to ask
- **Competitor Intelligence**: Flag KOLs with advisory board ties (use cautiously)
- **Geographic Context**: Help MSLs find KOLs in their territories

---

### 3. STRATEGIC RECOMMENDATIONS 📋

#### CURRENT ISSUES:
- ✅ Good: Indication-specific framework
- ✅ Good: Line of therapy context
- ❌ **CRITICAL**: Only 38 lines (vs 187 for Competitor, 171 for KOL) - SEVERELY UNDERSPECIFIED
- ❌ Problem: Vague "Medical Affairs Action Plan" - no concrete outputs
- ❌ Problem: Says "Priority KOLs to engage" but doesn't name them
- ❌ Problem: Says "Key messages for medical communications" but doesn't write them

#### REDESIGNED PROMPT STRUCTURE:

```
Section 1: EXECUTIVE SUMMARY (For Medical Directors)
- 3-5 strategic imperatives for this specific indication
- Most critical competitive threat requiring immediate response
- Most promising white space opportunity for EMD differentiation
- Recommended resource allocation (KOL engagement vs clinical development vs market access)

Section 2: CURRENT COMPETITIVE POSITION ASSESSMENT
- Treatment paradigm: Where does EMD drug sit? (1L/2L/maintenance/combination)
- Market share context: Leader/challenger/niche? (based on abstract volume as proxy)
- Differentiation: What makes EMD drug unique vs top 3 competitors?
- Utilization barriers: What prevents HCPs from using our drug? (based on research gaps)

Section 3: IMMEDIATE COMPETITIVE THREATS (90-Day Horizon)
For each major threat:
- THREAT: [Drug name] [Data type] (Abstract #, Session date/time)
- EMD IMPACT: How this affects our positioning/market share/messaging
- FIELD RESPONSE: Exact talking points for MSLs
- MEDICAL AFFAIRS ESCALATION: When/how to involve leadership

Section 4: WHITE SPACE OPPORTUNITIES (6-12 Month Horizon)
- Biomarker populations underserved by competitors
- Treatment settings where competitors not innovating (e.g., maintenance)
- Combination strategies unexplored
- Patient populations excluded from trials (elderly, poor performance status, etc.)
- For each opportunity: Rationale + Proposed action + Feasibility

Section 5: 90-DAY MEDICAL AFFAIRS ACTION PLAN

**FIELD TEAM PRIORITIES (MSLs):**
TIER 1 KOL ENGAGEMENTS (Must Complete):
1. Dr. [NAME] ([Institution]) - [X abstracts on EMD-relevant topics]
   - WHEN/WHERE: [Session date/time, Abstract #]
   - TALKING POINTS: [3-5 bullet points]
   - ASK: "Would you participate in investigator-initiated trial on [specific topic]?"
   - EXPECTED OUTCOME: Potential advisory board member OR trial investigator OR publication co-author

2. [Repeat for 3-5 Tier 1 KOLs with names and specifics]

TIER 2 KOL ENGAGEMENTS (If Time Permits):
[2-3 additional KOLs with brief guidance]

**MEDICAL COMMUNICATIONS PRIORITIES:**
KEY MESSAGE 1: [Exact message for HCP communications]
- Supporting Data: Abstract #s that reinforce this message
- Target Audience: [Oncologists/urologists/medical oncologists/etc.]
- Channel: [Congress booth materials/post-congress webinar/publications/etc.]

KEY MESSAGE 2: [Exact counter-message to competitor positioning]
- Competitor Claim: "[Competitor X says...]"
- EMD Response: "[Here's why EMD approach is different/better...]"
- Evidence: Abstract #s supporting our response

KEY MESSAGE 3: [White space opportunity message]

**CLINICAL DEVELOPMENT PRIORITIES:**
PROPOSAL 1: [Specific trial concept]
- Rationale: [Based on Abstract #s showing gap]
- Design: [Patient population, treatment, endpoints]
- Proposed Investigators: Dr. [NAME], Dr. [NAME] (both presenting relevant data at ESMO)
- Timeline: Feasibility assessment by [date], protocol by [date]

PROPOSAL 2: [Biomarker strategy]
- Rationale: [Based on biomarker trends at congress]
- Approach: [Companion diagnostic development vs retrospective analysis]
- Partnership: [Dx company or academic institution]

**MARKET ACCESS PRIORITIES:**
- Anticipated Payer Questions: "[Based on competitor data, payers will ask...]"
- Value Dossier Updates: [Which sections need revision based on new competitive data]
- Real-World Evidence Gaps: [What RWE do we need to generate?]

Section 6: MEASUREMENT & ACCOUNTABILITY
- 30-Day Checkpoint: [Specific deliverables]
- 60-Day Checkpoint: [Specific deliverables]
- 90-Day Checkpoint: [Specific deliverables]
- Success Metrics: [How do we know this plan worked?]
```

#### KEY MEDICAL AFFAIRS ADDITIONS:
- **EXPAND** from 38 lines to ~150 lines with specific tactical outputs
- **NAME SPECIFIC KOLs** with session times, talking points, expected outcomes
- **WRITE EXACT KEY MESSAGES** - not "develop key messages"
- **PROPOSE SPECIFIC TRIALS** with investigators, rationale, design sketch
- **Include Market Access lens** (payer objections, value dossier updates)
- **Add Accountability** (30/60/90-day checkpoints with deliverables)

---

### 4. INSTITUTION ANALYSIS 🏥

#### DECISION POINT: KEEP, REDESIGN, OR REMOVE?

**CURRENT ISSUES:**
- ✅ Good: Comprehensive institutional profiling
- ❌ Problem: More relevant for Clinical Development (trial site selection) than MSLs
- ❌ Problem: Overlaps with KOL Analysis (institutional clustering emerges from KOL data)
- ❌ Problem: MSLs engage individuals, not institutions

**OPTION A: REMOVE PLAYBOOK**
- Merge institutional insights into KOL Analysis
- Add note: "Dr. X is one of 5 bladder cancer KOLs from Memorial Sloan Kettering (institutional hub)"
- Simplifies UI (4 playbooks instead of 5)

**OPTION B: REDESIGN FOR PARTNERSHIP INTELLIGENCE**
- Reframe as "Academic Partnership Opportunities"
- Target audience: Medical Directors planning collaborations
- Focus: Which institutions are accessible? What's their trial infrastructure?
- Output: Tier 1/2/3 partnership targets with engagement rationale

**OPTION C: KEEP AS-IS (NOT RECOMMENDED)**
- Current prompt is well-structured but serves wrong audience
- Low value for MSL field work

**RECOMMENDATION**: **Option A** - Remove and merge into KOL Analysis. If medical directors need institutional partnership analysis, they can use Strategic Recommendations playbook.

---

### 5. SCIENTIFIC INSIGHTS 📈

#### CURRENT ISSUES:
- ✅ Good: Comprehensive biomarker/MOA coverage
- ✅ Good: EMD portfolio context section
- ✅ Good: Instruction to skip topics with no data (prevents hallucination)
- ❌ Problem: Too academic - reads like "ESMO scientific summary"
- ❌ Problem: Describes trends but doesn't link to business action
- ❌ Problem: Missing "so what for EMD?" in most sections

#### REDESIGNED PROMPT STRUCTURE:

```
Section 1: EXECUTIVE SUMMARY (3-5 Dominant Scientific Themes)
For each theme:
- THEME: [e.g., "ADC Expansion Beyond Breast/Bladder"]
- CONFERENCE MOMENTUM: [X abstracts, Y% of total studies]
- EMD RELEVANCE: How does this impact our portfolio positioning?
- STRATEGIC IMPLICATION: Should EMD invest in this area? Partner? Monitor?

Section 2: BIOMARKER & MOA LANDSCAPE WITH EMD CONTEXT

For each biomarker/MOA category:
- CONFERENCE ACTIVITY: [Quantify from table]
- TREND DIRECTION: Growing/Stable/Declining momentum
- **EMD PORTFOLIO IMPLICATIONS**:
  * Avelumab: [How does this trend affect PD-L1 checkpoint inhibitor strategy?]
  * Tepotinib: [How does MET biomarker research position tepotinib?]
  * Cetuximab: [How does EGFR/RAS testing evolution impact cetuximab use?]
- **MEDICAL AFFAIRS RESPONSE**:
  * Medical Communications: [Which trends should we amplify/counter?]
  * Clinical Development: [Should we invest in biomarker X based on momentum?]
  * KOL Engagement: [Which biomarker experts should we target?]

Section 3: TREATMENT PARADIGM EVOLUTION & WHITE SPACE

*Maintenance Therapy Trends*:
- Conference Activity: [X abstracts on maintenance strategies]
- AVELUMAB CONTEXT: Is maintenance paradigm growing? Which competitors entering?
- WHITE SPACE: [What maintenance settings are unexplored?]
- RECOMMENDATION: [Expand/defend/pivot maintenance strategy?]

*Combination Regimen Trends*:
- IO+Chemo vs IO+IO vs IO+ADC vs IO+TKI: [Volume breakdown]
- EMD RELEVANCE: [Which combinations threaten our monotherapy positioning?]
- OPPORTUNITY: [Which combination backbones should EMD explore?]

*Biomarker-Driven Selection*:
- Conference Activity: [X% of studies use biomarker selection]
- EMD CONTEXT: [Are we behind/ahead of competitors in precision medicine?]
- RECOMMENDATION: [Invest in companion diagnostics vs basket trials vs retrospective analyses?]

Section 4: CLINICAL DEVELOPMENT INTELLIGENCE

**HIGH-PRIORITY DEVELOPMENT AREAS** (Based on conference trends):

OPPORTUNITY 1: [Specific gap in research landscape]
- EVIDENCE: [Abstract #s showing this gap]
- EMD FIT: [Which EMD asset could address this?]
- PROPOSED TRIAL: [Patient population, design, endpoints]
- FEASIBILITY: [Which KOLs presenting relevant work could be investigators?]
- TIMELINE: [6 months to protocol vs 12-18 months to first patient?]

OPPORTUNITY 2: [Biomarker strategy]
[Similar structure]

**AVOID AREAS** (Crowded competitive space):
- [Which research areas are saturated with competitors?]
- [Where should EMD NOT invest resources?]

Section 5: COMPETITIVE POSITIONING SUMMARY

*Avelumab Positioning*:
- Current Science: [How do PD-L1/IO trends support or challenge avelumab?]
- Recommendation: [Emphasize maintenance story vs pivot to combinations?]

*Tepotinib Positioning*:
- Current Science: [How does MET research momentum position tepotinib?]
- Recommendation: [Expand to MET amp/overexpression vs stay METex14-focused?]

*Cetuximab Positioning*:
- Current Science: [How do EGFR/anti-EGFR trends affect cetuximab?]
- Recommendation: [Invest in RAS biomarker refinement vs new indications?]

Section 6: NOTABLE SCIENTIFIC DEVELOPMENTS
- 8-12 paradigm-shifting abstracts
- For each: Abstract #, Scientific significance, EMD relevance
- Prioritize: (1) Practice-changing data, (2) Novel biomarkers/MOAs, (3) EMD competitive threats
```

#### KEY MEDICAL AFFAIRS ADDITIONS:
- **EMD Portfolio Implications** for every major trend (not just summary at end)
- **Medical Affairs Response** guidance (communications, clinical dev, KOL engagement)
- **White Space Analysis** (what's NOT being studied = opportunity)
- **Clinical Development Intelligence** (specific trial proposals with investigators)
- **Competitive Positioning Summary** (actionable recommendations for each asset)
- **Link Science to Business** (don't just describe trends, prescribe actions)

---

## 🔧 CROSS-CUTTING IMPROVEMENTS (ALL PLAYBOOKS)

### 1. TGCT DISAMBIGUATION FIX
**Problem**: AI picks up "testicular germ cell tumor" when filtering for TGCT (tenosynovial giant cell tumor)

**Solution**: Add this instruction to ALL playbooks that mention TGCT/pimicotinib:
```
**CRITICAL TGCT CLARIFICATION**:
- TGCT = Tenosynovial Giant Cell Tumor (also called PVNS - Pigmented Villonodular Synovitis)
- DO NOT confuse with testicular germ cell tumor (different disease)
- Pimicotinib is being developed for tenosynovial giant cell tumor only
- If you see "TGCT" in an abstract title, verify context - if it's testicular cancer, EXCLUDE from analysis
```

Add to prompts at lines:
- Competitor: Line 256 (after CRITICAL INSTRUCTION)
- KOL: Line 373 (in Portfolio Relevance section)
- Strategy: Line 646 (in INDICATION-SPECIFIC CONTEXT)
- Insights: Line 616 (in EMD PORTFOLIO SCIENTIFIC CONTEXT)

### 2. CITATION FORMATTING CONSISTENCY
Change from: "Abstract #2847" or "(Abstract #2847)"
To: **"(Abstract #2847)"** - consistent parenthetical format

### 3. ALERT PRIORITY EMOJI SYSTEM
Use consistently across all playbooks:
- 🔴 **HIGH ALERT**: Requires immediate MSL/medical affairs response (within 7 days)
- 🟡 **MEDIUM PRIORITY**: Important to monitor, respond if HCPs ask (within 30 days)
- 🟢 **LOW PRIORITY**: Baseline competitive activity, no action required
- 📋 **STRATEGIC**: Important for medical directors, not urgent field action

### 4. FIELD RESPONSE SCRIPT FORMAT
When providing MSL talking points, use this structure:
```
**HCP Question**: "[What competitor might say/ask]"
**MSL Response**: "[Exact 2-3 sentence talking point]"
**Supporting Evidence**: (Abstract #s)
**Escalation**: [If HCP pushes back, refer to medical director? Clinical data? Publications?]
```

### 5. TIMELINE HORIZONS
- **Immediate** (0-7 days): MSL field actions during/right after congress
- **Short-term** (30 days): Medical communications, rapid response publications
- **Medium-term** (90 days): KOL engagement programs, advisory boards
- **Long-term** (6-12 months): Clinical development, partnership discussions

---

## 📊 BEFORE/AFTER COMPARISON

### EXAMPLE: Competitor Intelligence Prompt

**BEFORE (Current - Academic Style)**:
```
**MAJOR COMPETITOR DEEP-DIVE ANALYSIS**:
For each major competitor drug shown in the data tables, provide a dedicated paragraph
analyzing its conference presence and strategic threat. Pembrolizumab appeared in 87
abstracts (43% of all IO studies). This checkpoint inhibitor targeting PD-1 shows
strong momentum in lung cancer with 34 studies in NSCLC settings including first-line,
second-line, and perioperative approaches. Key KOLs presenting pembrolizumab data
include Dr. X (Memorial Sloan Kettering) and Dr. Y (Dana-Farber)...
```

**AFTER (Redesigned - Tactical Field Intelligence)**:
```
🔴 **HIGH ALERT - IMMEDIATE COMPETITIVE THREATS**

**THREAT 1**: Enfortumab Vedotin + Pembrolizumab (EV+P) in First-Line Metastatic Urothelial Carcinoma
- **Data**: Phase 3 overall survival results (Abstract #1847, Friday Oct 18, 10:00am, Hall A)
- **Presenter**: Dr. Thomas Powles (Barts Cancer Institute, UK)
- **EMD Impact**: DIRECT THREAT to avelumab 1L maintenance positioning
  * If OS benefit shown, could establish EV+P as new 1L standard in cisplatin-eligible patients
  * May shift treatment paradigm from "maintenance after chemo" to "upfront combination"
  * Payer impact: Formularies may prioritize EV+P over avelumab maintenance

**Field Response Script**:
- **HCP Question**: "Should I use EV+P instead of avelumab maintenance?"
- **MSL Response**: "EV+P and avelumab serve different patient populations and treatment paradigms. EV+P is an upfront combination for cisplatin-eligible patients who can tolerate intensive therapy. Avelumab maintenance is for patients who've responded to initial platinum chemotherapy and need continued disease control. Many of our maintenance patients are cisplatin-ineligible or prefer less intensive treatment. Different approaches for different clinical scenarios."
- **Supporting Evidence**: JAVELIN Bladder 100 trial (avelumab maintenance), EV-302 trial (EV+P upfront)
- **Escalation**: If HCP wants head-to-head comparison, refer to medical director for detailed clinical discussion

**MSL Action Items**:
1. ATTEND Friday 10am session (Abstract #1847) - take detailed notes on OS data, subgroup analyses
2. CONTACT medical affairs lead within 24 hours post-presentation with summary
3. EXPECT increased HCP questions Monday-Friday following congress - use response script above
4. IDENTIFY which of your HCPs are likely EV+P investigators (check ClinicalTrials.gov) - proactive outreach

**Medical Affairs Escalation**:
- If OS HR <0.70 (strong benefit): Prepare rapid response publication within 2 weeks
- If cisplatin-ineligible subgroup shows benefit: Emergency advisory board to discuss positioning
- If payer questions arise: Engage health economics team for value dossier update
```

---

## ✅ IMPLEMENTATION CHECKLIST

### Step 1: Review & Approval (30 minutes)
- [ ] Review this redesign plan with MSL who built COSMIC
- [ ] Confirm medical affairs strategy alignment
- [ ] Decide on Institution Analysis playbook (remove vs redesign)
- [ ] Confirm TGCT disambiguation approach

### Step 2: Implement Prompt Changes (3 hours)
- [ ] Update Competitor Intelligence prompt (1 hr)
- [ ] Update KOL Analysis prompt + remove line 414 (1 hr)
- [ ] Expand Strategic Recommendations prompt (1 hr)
- [ ] Update Scientific Insights prompt (30 min)
- [ ] Add TGCT clarification to all prompts (15 min)
- [ ] Test each playbook with sample filters (15 min)

### Step 3: Validation Testing (1 hour)
- [ ] Run Competitor Intelligence with "Avelumab Focus" + "Bladder Cancer"
- [ ] Run KOL Analysis with "All Therapeutic Areas"
- [ ] Run Strategic Recommendations with drug-specific filter
- [ ] Run Scientific Insights with "Bladder Cancer"
- [ ] Verify TGCT outputs don't include testicular cancer
- [ ] Check output quality: Tactical vs Academic?

### Step 4: User Testing (External)
- [ ] Share outputs with 2-3 MSL colleagues
- [ ] Ask: "Is this more useful than before?"
- [ ] Ask: "Would you use these outputs in the field?"
- [ ] Collect feedback on missing elements
- [ ] Iterate based on feedback

---

## 🎯 SUCCESS CRITERIA

**We'll know the redesign worked if:**

1. **MSL Reaction**: "This just saved me 5 hours of prep work for ESMO"
2. **Medical Director Reaction**: "These are the exact action items I needed for the team meeting"
3. **Output Quality**: Prompts generate <5 paragraphs of setup, then jump straight to tactical recommendations
4. **Actionability**: Every output includes specific KOL names, session times, talking points, next steps
5. **TGCT Accuracy**: Zero testicular cancer abstracts in TGCT-filtered analyses

---

## 📝 NOTES FOR IMPLEMENTATION

1. **Don't Lose Good Stuff**: Current prompts have excellent citation requirements, quantification, and professional tone - preserve these
2. **Test Incrementally**: Implement one playbook at a time, test output quality before moving to next
3. **Expect AI Variance**: GPT responses will vary - may need to run same prompt 2-3 times to find best phrasing
4. **Token Limits**: Redesigned prompts are longer - monitor OpenAI max_output_tokens (currently 3000) - may need adjustment
5. **Backup Current Prompts**: Already done (app_backup_before_prompt_redesign_*.py)

---

**Ready to proceed with implementation?**
**Next Step**: Review this plan, confirm strategy, then implement prompt changes in app.py
