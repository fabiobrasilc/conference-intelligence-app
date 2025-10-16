# COSMIC Mobile - Clean PWA Version

This is a **clean clone** of the COSMIC conference intelligence app, prepared for mobile/PWA enhancements.

## What's Included (Essential Files Only)

### Core Application
- `app.py` - Main Flask application (221 KB)
- `requirements.txt` - Python dependencies
- `runtime.txt` - Python version specification

### Data Files
- `ESMO_2025_FINAL_20251013.csv` - Conference data (7.6 MB)
- `Drug_Company_names_with_MOA.csv` - Drug database (32 KB)
- `nsclc-json.json` - NSCLC landscape data
- `erbi-crc-json.json` - CRC landscape data
- `erbi-HN-json.json` - H&N landscape data
- `bladder-json.json` - Bladder cancer landscape data

### Application Structure
- `templates/` - HTML templates for Flask
- `static/` - CSS, JavaScript, images
- `ai_first_refactor/` - Simplified AI assistant module

## What's NOT Included (Cleaned Out)

- ❌ Backup files (`*_backup_*.py`, `*_BACKUP_*`)
- ❌ Test scripts (`test_*.py`)
- ❌ Archive folders (`_cleanup_archive_*`, `backup_v18_*`)
- ❌ Markdown documentation (`*.md` - except this README)
- ❌ Log files (`*.log`)
- ❌ Cache directories
- ❌ Old/deprecated code files

## Next Steps - PWA Enhancement

### Phase 1: Mobile-Responsive Design
- [ ] Add viewport meta tags
- [ ] Responsive CSS (card layouts for mobile)
- [ ] Touch-friendly buttons (44px minimum)
- [ ] Collapsible filters

### Phase 2: PWA Files
- [ ] Create `manifest.json` (app metadata)
- [ ] Create `service-worker.js` (offline support)
- [ ] Add app icons (192x192, 512x512)
- [ ] Test "Add to Home Screen" prompt

### Phase 3: Mobile UX
- [ ] Study card design for mobile
- [ ] Bottom navigation bar
- [ ] Swipe gestures
- [ ] Share functionality

## Running the App

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python app.py

# Access at http://localhost:5001
```

## File Size Summary

Total: ~8 MB (compared to ~100+ MB in original folder with backups/archives)

**This is the clean working base for mobile development!**
