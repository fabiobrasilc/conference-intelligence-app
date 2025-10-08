# Project Folder Cleanup Plan

## Files to KEEP

### Essential Application Files
- ✅ app.py - Main application
- ✅ improved_search.py - Search functionality
- ✅ .env - Environment variables
- ✅ .gitignore - Git configuration
- ✅ requirements.txt - Dependencies
- ✅ Procfile - Railway deployment
- ✅ railway.toml - Railway configuration
- ✅ runtime.txt - Python version

### Data Files (CSV, Excel, TXT - User Requested)
- ✅ ESMO_2025_FINAL_20250929.csv - Main conference data
- ✅ ASCO GU 2025 Poster Author Affiliations info.csv - Additional data
- ✅ Drug_Company_names_with_MOA.csv - Drug database (keep latest)
- ✅ *.txt files - Various text files (user wants to keep)

### JSON Configuration Files (Active)
- ✅ bladder-json.json - Competitive landscape
- ✅ nsclc-json.json - Competitive landscape
- ✅ erbi-crc-json.json - Competitive landscape
- ✅ erbi-HN-json.json - Competitive landscape

### Folders
- ✅ static/ - Frontend assets
- ✅ templates/ - HTML templates
- ✅ ai_first_refactor/ - New AI architecture
- ✅ legacy_modules_archived/ - Archived legacy code
- ✅ __pycache__/ - Python cache (auto-generated)
- ✅ .git/ - Git repository
- ✅ chroma_conference_db/ - Vector database

### Latest Backups ONLY
- ✅ app_backup_pre_cleanup_20251008.py - LATEST backup (Oct 8)

### Documentation (Recent/Relevant)
- ✅ CLEANUP_COMPLETED.md (created today)
- ✅ INTEGRATION_COMPLETE.md
- ✅ README_TIER1_TIER2.md
- ✅ CLAUDE.md

---

## Files to REMOVE

### 1. Old App Backups (Keep only latest: app_backup_pre_cleanup_20251008.py)
❌ app copy.py
❌ app copy 2.py
❌ app copy 3.py
❌ app copy 4.py
❌ app_backup_20251001_143119.py
❌ app_backup_before_prompt_redesign_20251001_235349.py
❌ app_backup_before_tier1_tier2_integration_20251007.py
❌ app_backup_pre_cleanup_.py (duplicate)
❌ app_enhanced_chat_endpoint.py
❌ app_v17_backup_column_toggles_drug_search_fix_20251001_203440.py
❌ app_v19_backup_pre_esmo_integration.py
❌ app_v20_backup_multi_conference_architecture.py
❌ app_v21_backup_search_fixes_complete.py
❌ app_v22.py
❌ app_v23_working chat.py
❌ app_v24.py
❌ app_v25_backup_before_refactor_20250930.py

**Total:** 17 old app backup files

### 2. Test Scripts (All debug/test files)
❌ test.py
❌ test_*.py (all 39 test files)
❌ debug_*.py (all debug files)
❌ check_*.py
❌ inspect_*.py
❌ cleanup_app.py (one-time script, already used)

**Pattern:** `test_*.py`, `debug_*.py`, `check_*.py`, `inspect_*.py`

**Total:** ~50 test/debug scripts

### 3. Duplicate Drug Database Files
❌ Drug_Company_names.csv (old)
❌ Drug_Company_names_with_MOA-LTUS0226388.csv (duplicate)
Keep: Drug_Company_names_with_MOA.csv (latest)

### 4. Unused JSON Files
❌ development_chat_history.json (old development data)

### 5. Log Files (Temporary)
❌ debug_server.log
❌ server.log
❌ server_test.log
❌ ev_p_debug.log
❌ test_results.txt

### 6. Outdated Documentation
❌ ACTIVE_SCRIPTS.md (outdated after cleanup)
❌ AI_ASSISTANT_VALUE_ANALYSIS.md (pre-refactor analysis)
❌ BEFORE_AFTER_COMPARISON.md (old comparison)
❌ CLEANUP_PLAN.md (duplicate in ai_first_refactor/)
❌ COMPETITOR_BUTTON_DETAILED_ANALYSIS.md (old analysis)
❌ CONSOLIDATION_OPTION.md (outdated)
❌ DESIGN_IMPLEMENTATION_GUIDE.md (old)
❌ ESMO_INTEGRATION_BACKUP_README.md (old backup notes)
❌ MULTI_FIELD_SEARCH_FIX.md (implemented already)
❌ PHASE_1_IMPLEMENTATION_SUMMARY.md (old phase)
❌ POSTGRES_SETUP.md (not using Postgres)
❌ PRECOMPUTED_INTELLIGENCE_PLAN.md (archived approach)
❌ PROMPT_REDESIGN_PLAN.md (old redesign)
❌ PROMPT_REDESIGN_SUMMARY.md (old summary)
❌ SEARCH_LOGIC_ANALYSIS.md (old analysis)
❌ TIER1_IMPLEMENTATION_SUMMARY.md (old tier system)
❌ TIER2_IMPLEMENTATION_COMPLETE.md (old tier system)
❌ TEST_RESULTS_SUMMARY.md (old test results)

### 7. Backup Folders
❌ backup_v18_before_esmo_integration_20250925/ (old)
❌ static_backup/ (old)
❌ templates_backup/ (old)

### 8. Miscellaneous
❌ bg.txt (unknown)
❌ code.txt (code dump)
❌ app java.txt (code dump)
❌ index html.txt (code dump)
❌ style css.txt (code dump)
❌ structured output doc.txt (doc)
❌ reddit timeout issue.txt (old issue)
❌ requirements copy.txt (duplicate)
❌ requirements_v18_backup.txt (old)
❌ Gemini_Generated_Image_*.png (image file)
❌ COSMIC_driven by innovation submission*.docx (Word docs - not code)

---

## Summary

### Keep
- 1 latest app backup
- Active application files (app.py, improved_search.py, etc.)
- All CSV/Excel files
- All active JSON configs (4 competitive landscapes)
- All TXT files
- Current folders (static, templates, ai_first_refactor, legacy_modules_archived)
- Essential deployment files
- 3-4 relevant documentation files

### Remove
- 17 old app backups
- ~50 test/debug scripts
- 3 backup folders
- ~15 outdated documentation files
- 5 log files
- 2 duplicate CSV files
- ~10 miscellaneous text dumps and old files

**Total files to remove: ~100+ files**

**Estimated space savings: ~3-4 MB**
