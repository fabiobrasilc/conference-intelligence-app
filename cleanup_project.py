"""
Project Folder Cleanup Script
==============================

Removes old backups, test scripts, and unused files.
Keeps: Latest backup, CSV/Excel/TXT files, active configs.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

def cleanup_project():
    """Clean up project folder."""

    # Create archive folder for removed files (just in case)
    archive_dir = Path("_cleanup_archive_20251008")
    archive_dir.mkdir(exist_ok=True)

    print(f"Created archive folder: {archive_dir}")
    print(f"Files will be moved here (not deleted) for safety\n")

    removed_count = 0

    # 1. Old app backups (keep only app_backup_pre_cleanup_20251008.py)
    old_app_backups = [
        "app copy.py",
        "app copy 2.py",
        "app copy 3.py",
        "app copy 4.py",
        "app_backup_20251001_143119.py",
        "app_backup_before_prompt_redesign_20251001_235349.py",
        "app_backup_before_tier1_tier2_integration_20251007.py",
        "app_backup_pre_cleanup_.py",  # duplicate
        "app_enhanced_chat_endpoint.py",
        "app_v17_backup_column_toggles_drug_search_fix_20251001_203440.py",
        "app_v19_backup_pre_esmo_integration.py",
        "app_v20_backup_multi_conference_architecture.py",
        "app_v21_backup_search_fixes_complete.py",
        "app_v22.py",
        "app_v23_working chat.py",
        "app_v24.py",
        "app_v25_backup_before_refactor_20250930.py",
    ]

    print("=" * 70)
    print("REMOVING OLD APP BACKUPS")
    print("=" * 70)
    for filename in old_app_backups:
        if os.path.exists(filename):
            shutil.move(filename, archive_dir / filename)
            print(f"[OK] Archived: {filename}")
            removed_count += 1

    # 2. Test scripts
    print("\n" + "=" * 70)
    print("REMOVING TEST/DEBUG SCRIPTS")
    print("=" * 70)
    test_patterns = ["test_*.py", "debug_*.py", "check_*.py", "inspect_*.py"]
    for pattern in test_patterns:
        for filepath in Path(".").glob(pattern):
            if filepath.name != "test.py":  # Keep generic test.py for now
                shutil.move(str(filepath), archive_dir / filepath.name)
                print(f"[OK] Archived: {filepath.name}")
                removed_count += 1

    # Also remove test.py and cleanup_app.py
    for filename in ["test.py", "cleanup_app.py"]:
        if os.path.exists(filename):
            shutil.move(filename, archive_dir / filename)
            print(f"[OK] Archived: {filename}")
            removed_count += 1

    # 3. Duplicate CSV files
    print("\n" + "=" * 70)
    print("REMOVING DUPLICATE CSV FILES")
    print("=" * 70)
    duplicate_csvs = [
        "Drug_Company_names.csv",
        "Drug_Company_names_with_MOA-LTUS0226388.csv"
    ]
    for filename in duplicate_csvs:
        if os.path.exists(filename):
            shutil.move(filename, archive_dir / filename)
            print(f"[OK] Archived: {filename}")
            removed_count += 1

    # 4. Log files
    print("\n" + "=" * 70)
    print("REMOVING LOG FILES")
    print("=" * 70)
    log_files = [
        "debug_server.log",
        "server.log",
        "server_test.log",
        "ev_p_debug.log",
        "test_results.txt"
    ]
    for filename in log_files:
        if os.path.exists(filename):
            shutil.move(filename, archive_dir / filename)
            print(f"[OK] Archived: {filename}")
            removed_count += 1

    # 5. Unused JSON
    print("\n" + "=" * 70)
    print("REMOVING UNUSED JSON FILES")
    print("=" * 70)
    unused_json = ["development_chat_history.json"]
    for filename in unused_json:
        if os.path.exists(filename):
            shutil.move(filename, archive_dir / filename)
            print(f"[OK] Archived: {filename}")
            removed_count += 1

    # 6. Outdated documentation
    print("\n" + "=" * 70)
    print("REMOVING OUTDATED DOCUMENTATION")
    print("=" * 70)
    outdated_docs = [
        "ACTIVE_SCRIPTS.md",
        "AI_ASSISTANT_VALUE_ANALYSIS.md",
        "BEFORE_AFTER_COMPARISON.md",
        "CLEANUP_PLAN.md",  # duplicate in ai_first_refactor/
        "COMPETITOR_BUTTON_DETAILED_ANALYSIS.md",
        "CONSOLIDATION_OPTION.md",
        "DESIGN_IMPLEMENTATION_GUIDE.md",
        "ESMO_INTEGRATION_BACKUP_README.md",
        "MULTI_FIELD_SEARCH_FIX.md",
        "PHASE_1_IMPLEMENTATION_SUMMARY.md",
        "POSTGRES_SETUP.md",
        "PRECOMPUTED_INTELLIGENCE_PLAN.md",
        "PROMPT_REDESIGN_PLAN.md",
        "PROMPT_REDESIGN_SUMMARY.md",
        "SEARCH_LOGIC_ANALYSIS.md",
        "TIER1_IMPLEMENTATION_SUMMARY.md",
        "TIER2_IMPLEMENTATION_COMPLETE.md",
        "TEST_RESULTS_SUMMARY.md"
    ]
    for filename in outdated_docs:
        if os.path.exists(filename):
            shutil.move(filename, archive_dir / filename)
            print(f"[OK] Archived: {filename}")
            removed_count += 1

    # 7. Miscellaneous text dumps and old files
    print("\n" + "=" * 70)
    print("REMOVING MISCELLANEOUS FILES")
    print("=" * 70)
    misc_files = [
        "bg.txt",
        "code.txt",
        "app java.txt",
        "index html.txt",
        "style css.txt",
        "structured output doc.txt",
        "reddit timeout issue.txt",
        "requirements copy.txt",
        "requirements_v18_backup.txt",
        "Gemini_Generated_Image_nwuxa6nwuxa6nwux.png"
    ]
    # Add Word docs
    for filepath in Path(".").glob("*.docx"):
        misc_files.append(filepath.name)

    for filename in misc_files:
        if os.path.exists(filename):
            shutil.move(filename, archive_dir / filename)
            print(f"[OK] Archived: {filename}")
            removed_count += 1

    # 8. Backup folders
    print("\n" + "=" * 70)
    print("REMOVING OLD BACKUP FOLDERS")
    print("=" * 70)
    backup_folders = [
        "backup_v18_before_esmo_integration_20250925",
        "static_backup",
        "templates_backup"
    ]
    for foldername in backup_folders:
        if os.path.exists(foldername):
            shutil.move(foldername, archive_dir / foldername)
            print(f"[OK] Archived folder: {foldername}")
            removed_count += 1

    # Summary
    print("\n" + "=" * 70)
    print("CLEANUP SUMMARY")
    print("=" * 70)
    print(f"\nTotal files/folders archived: {removed_count}")
    print(f"Archive location: {archive_dir}")
    print(f"\nAll files safely moved to archive (not deleted).")
    print(f"You can delete the archive folder once you confirm everything works.\n")

    # List what's left
    print("=" * 70)
    print("REMAINING FILES IN PROJECT ROOT")
    print("=" * 70)

    remaining_files = []
    for item in sorted(os.listdir(".")):
        if item == str(archive_dir) or item.startswith("_") or item.startswith("."):
            continue
        if os.path.isfile(item):
            remaining_files.append(item)

    print(f"\nPython files:")
    for f in remaining_files:
        if f.endswith(".py"):
            print(f"  [OK] {f}")

    print(f"\nData files (CSV/Excel):")
    for f in remaining_files:
        if f.endswith((".csv", ".xlsx", ".xls")):
            print(f"  [OK] {f}")

    print(f"\nConfiguration files:")
    for f in remaining_files:
        if f.endswith((".json", ".txt", ".toml", ".env")):
            print(f"  [OK] {f}")

    print(f"\nDocumentation files:")
    for f in remaining_files:
        if f.endswith(".md"):
            print(f"  [OK] {f}")

    print(f"\nTotal remaining files: {len(remaining_files)}")

    return removed_count

if __name__ == "__main__":
    print("\n" + "#" * 70)
    print("PROJECT FOLDER CLEANUP")
    print("#" * 70 + "\n")

    print("This script will:")
    print("- Archive (not delete) old backups, test scripts, logs, etc.")
    print("- Keep: Latest backup, all CSV/TXT/Excel files, active configs")
    print("- Move everything to _cleanup_archive_20251008/ folder\n")

    print("Starting cleanup...\n")
    removed = cleanup_project()

    print("\n" + "#" * 70)
    print(f"CLEANUP COMPLETE - {removed} items archived")
    print("#" * 70 + "\n")
