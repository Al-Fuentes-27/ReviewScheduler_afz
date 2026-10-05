"""
manage_review_log.py — CLI tool for managing the FSRS review log.

Part of the GB_PersonalStudyNotes Obsidian vault toolkit.
Reads the path to review_log.csv from config.json, then allows
the user to delete all review records for a given concept note,
delete only the LAST review of a note (to re-grade it),
rename a concept note across all its records,
or display a summary table of all tracked notes.

Usage:
    python manage_review_log.py --summary
        - display a summary table of all tracked notes
    python manage_review_log.py --delete "💡 a — Aggregation in Data Analysis (Family) — Concept.md"
        - delete all review records for a given concept note
    python manage_review_log.py --delete-last "💡 gro.a. — Grouped Aggregation — Concept.md"
        - delete only the LAST review of a note (to re-grade it)
    python manage_review_log.py --rename "old note name.extension file" "new note name.extension file"
        - rename a concept note across all its records (note_edits.csv and review_log.csv)
        
    python manage_review_log.py --delete "..." --dry-run
    python manage_review_log.py --config path/to/config.json --summary

Requirements:
    - pandas
    - Python 3.9+
"""

import pandas as pd
import json
import os
import argparse
import sys
import shutil
import datetime
from pathlib import Path
import re
import yaml



# Resolve paths relative to THIS script's location, not the working directory.
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / ".." / "data" / "path_config.json"




class ReviewLogManager:
    """Manages read/delete/rename operations on the review_log.csv file.

    This class loads a spaced-repetition review log (CSV) whose path is
    defined in a JSON configuration file. It supports deleting all records
    for a specific concept note, deleting only the last review of a note
    (useful for re-grading), renaming a concept note across all its records
    (with smart fuzzy matching for dash/encoding variations), and printing
    a summary of all tracked notes.

    Attributes:
        config_path (Path): Resolved path to the JSON configuration file.
        log_path (str):     Path to the CSV review log, extracted from config.
        df (pd.DataFrame):  In-memory representation of the CSV data.
    """

    def __init__(self, config_path: str = str(DEFAULT_CONFIG_PATH)) -> None:
        """Initialize the manager: load config, resolve CSV path, load data.

        Args:
            config_path: Path to the JSON configuration file.
                         Defaults to '../data/path_config.json' relative to this script.

        Raises:
            FileNotFoundError: If the config file or the CSV file does not exist.
            KeyError:          If 'log_path' is missing from the config.
        """
        self.config_path = Path(config_path)
        
        # Cache the cleaned configuration dictionary
        self.cleaned_config = self._load_and_clean_config()
        
        # Extract log_path directly from the cached config
        self.log_path = self.cleaned_config.get("log_path")
        if not self.log_path:
            raise KeyError("'log_path' not found in the configuration file.")
            
        self.edits_path: str = self._get_edits_path_from_config()   # NEW
        self.backup_path: str = self._get_backup_path_from_config()   # ← NEW LINE
        self.df: pd.DataFrame = self._load_csv(self.log_path)       # signature changed
        self.df_edits: pd.DataFrame | None = self._load_edits_csv() # NEW


    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_and_clean_config(self) -> dict:
        """Load config.json once and strip whitespace from keys/values."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found at: {self.config_path.resolve()}"
            )

        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)

        return {
            k.strip(): v.strip() if isinstance(v, str) else v
            for k, v in raw_config.items()
        }

    def _get_edits_path_from_config(self) -> str:
        """Read config and extract 'edits_path', with fallback."""
        edits_path = self.cleaned_config.get("edits_path")
        if edits_path:
            return edits_path
    
        # Fallback: look for note_edits.csv in the same directory as review_log.
        log_dir = os.path.dirname(os.path.abspath(self.log_path))
        return os.path.join(log_dir, "note_edits.csv")
    
    def _get_backup_path_from_config(self) -> str:
        """Read config and extract 'backup_path', with fallback."""
        backup_path = self.cleaned_config.get("backup_path")
        if backup_path:
            return backup_path
        
        # Fallback: look for 'note_backup' next to the review log.
        log_dir = os.path.dirname(os.path.abspath(self.log_path))
        return os.path.join(log_dir, "note_backup")

    def _get_vault_path_from_config(self) -> str:
        """Read config and extract 'obsidian_vault_path'."""
        vault_path = self.cleaned_config.get("obsidian_vault_path")
        if not vault_path:
            raise KeyError("'obsidian_vault_path' not found in the configuration file.")
        return vault_path

    def _get_notes_ext_from_config(self) -> str:
        """Read config and extract 'notes_extension'."""
        notes_ext = self.cleaned_config.get("notes_extension")
        if not notes_ext:
            raise KeyError("'notes_extension' not found in the configuration file.")
        return notes_ext
    
    def _find_note_file(self, note_name: str) -> Path | None:
        """Locate the physical markdown file in the Obsidian vault by its filename.

        Args:
            note_name: The exact filename of the note (e.g., "Concept.md").

        Returns:
            A Path object to the file if found, otherwise None.
        """
        try:
            vault_path = Path(self._get_vault_path_from_config())
        except (FileNotFoundError, KeyError):
            return None

        if not vault_path.exists():
            return None

        # Search the vault recursively for the exact filename
        for md_file in vault_path.rglob(note_name):
            if md_file.is_file():
                return md_file
                
        return None

    def _read_frontmatter(self, file_path: Path) -> tuple[dict, str]:
        """Extract YAML frontmatter and the rest of the markdown body.

        Args:
            file_path: The Path object to the .md file.

        Returns:
            A tuple containing the parsed frontmatter dictionary and the note body string.
        """
        content = file_path.read_text(encoding="utf-8")
        frontmatch = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
        
        if not frontmatch:
            return {}, content
            
        yaml_text, body = frontmatch.group(1), frontmatch.group(2)
        try:
            front = yaml.safe_load(yaml_text) or {}
        except yaml.YAMLError:
            front = {}
            
        return front, body

    def _write_frontmatter(self, file_path: Path, front: dict, body: str) -> None:
        """Write the updated YAML frontmatter and body back to the markdown file.

        Args:
            file_path: The Path object to the .md file.
            front: The dictionary of frontmatter data.
            body: The string content of the note body.
        """
        yaml_str = yaml.dump(front, allow_unicode=True, sort_keys=False, default_flow_style=False)
        new_content = f"---\n{yaml_str}---\n{body}"
        file_path.write_text(new_content, encoding="utf-8")

    def _update_note_frontmatter(self, note_name: str, new_metrics: dict | None, dry_run: bool = False) -> None:
        """Safely update the frontmatter of a note with error handling.

        Args:
            note_name: The filename of the note.
            new_metrics: A dictionary of metrics to update, or None to purge all FSRS metrics.
            dry_run: If True, only print what would be changed without modifying the file.
        """
        file_path = self._find_note_file(note_name)
        
        if not file_path:
            print(f"  ⚠️  Physical file '{note_name}' not found in vault. Skipping frontmatter update.")
            return

        try:
            front, body = self._read_frontmatter(file_path)
        except Exception as e:
            print(f"  ⚠️  Error reading frontmatter for '{note_name}': {e}. Skipping update.")
            return

        if not front:
            print(f"  ⚠️  Empty or malformed frontmatter in '{note_name}'. Skipping update.")
            return

        if new_metrics is None:
            action_msg = f"Reset '{note_name}' to 'new' state in frontmatter (purging metrics)."
            if not dry_run:
                for key in ['stability', 'difficulty', 'last_reviewed', 'next_review']:
                    front.pop(key, None)
        else:
            action_msg = f"Reverted frontmatter for '{note_name}'."
            if not dry_run:
                front.update(new_metrics)

        if dry_run:
            print(f"  🔍 [DRY RUN] Would {action_msg[0].lower() + action_msg[1:]}")
        else:
            print(f"  ♻️  {action_msg}")
            try:
                self._write_frontmatter(file_path, front, body)
            except Exception as e:
                print(f"  ❌  Error writing frontmatter to '{note_name}': {e}")
     
    def _load_csv(self, path: str) -> pd.DataFrame:
        """Load the review log CSV into a pandas DataFrame.

        Returns:
            A DataFrame with all rows from the CSV.

        Raises:
            FileNotFoundError: If the CSV file does not exist at the provided path.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Review log file not found at: {path}"
            )

        return pd.read_csv(path, encoding="utf-8")

    def _load_edits_csv(self) -> pd.DataFrame | None:
        """Load the note_edits CSV into a pandas DataFrame.
    
        Returns None if the file does not exist (non-fatal).
        """
        if not os.path.exists(self.edits_path):
            return None

        return pd.read_csv(self.edits_path, encoding="utf-8")

    def _save_csv(self, path: str, df: pd.DataFrame, backup: bool = True) -> None:
        """Save the current DataFrame back to the CSV file.

        Args:
            backup: If True (default), create a timestamped .bak copy of the
                    CSV before overwriting it.
        """

        if backup:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{path}.bak_{timestamp}"
            shutil.copy2(path, backup_path)
            print(f"  💾 Backup saved to: {backup_path}")
    
        df.to_csv(path, index=False, encoding="utf-8")

    def _rename_backup_file(self, old_name: str, new_name: str,
                            dry_run: bool = False) -> bool:
        """Rename the backup .txt file for a note inside the backup folder.

        Backup naming convention:
            note  "💡 s.m.a — ... — Concept.md"
            →     "💡 s.m.a — ... — Concept_backup.txt"

        Returns True if a backup file was found and renamed (or would be),
        False otherwise.
        """
        if not os.path.isdir(self.backup_path):
            print(f"  ⚠️  Backup folder not found: {self.backup_path}")
            return False

        # Derive backup filenames: strip note extension, append "_backup.txt"
        old_stem = os.path.splitext(old_name)[0]
        new_stem = os.path.splitext(new_name)[0]
        old_backup_file = f"{old_stem}_backup.txt"
        new_backup_file = f"{new_stem}_backup.txt"

        old_backup_full = os.path.join(self.backup_path, old_backup_file)
        new_backup_full = os.path.join(self.backup_path, new_backup_file)

        # Try exact match first
        if not os.path.isfile(old_backup_full):
            # Fallback: search with normalized names (dash/case-insensitive)
            norm_target = self._normalize_text(old_stem)
            found = None
            for fname in os.listdir(self.backup_path):
                if fname.endswith("_backup.txt"):
                    candidate_stem = fname[: -len("_backup.txt")]
                    if self._normalize_text(candidate_stem) == norm_target:
                        found = fname
                        break
            if found is None:
                print(f"  ℹ️  No backup file found for: '{old_name}'")
                return False
            old_backup_file = found
            old_backup_full = os.path.join(self.backup_path, old_backup_file)

        if dry_run:
            print(f"  🔍 [DRY RUN] Would rename backup file:")
            print(f"     FROM: {old_backup_file}")
            print(f"     TO:   {new_backup_file}")
            return True

        # Guard against overwriting an existing target
        if os.path.isfile(new_backup_full):
            print(f"  ⚠️  Target backup already exists: '{new_backup_file}'. Skipping.")
            return False

        os.rename(old_backup_full, new_backup_full)
        print(f"  ✅ Backup renamed:")
        print(f"     FROM: {old_backup_file}")
        print(f"     TO:   {new_backup_file}")
        return True

    def _find_note_mask(self, df: pd.DataFrame, note_name: str, silent: bool = False) -> pd.Series:
        """Find all rows matching a note name using exact then normalized match.

        This is a shared helper used by delete, delete-last, and rename.

        Args:
            note_name: The (already mojibake-fixed) note string to search for.
            silent:    If True, suppress the print message when smart-normalization
                       is triggered (useful for secondary lookups like in rename_note).

        Returns:
            A boolean Series (mask) where True = row matches the note.

        Raises:
            ValueError: If the DataFrame has no 'note' column.
        """

        if "note" not in df.columns:
            raise ValueError("The 'note' column does not exist in the CSV file.")
    
        mask = df["note"] == note_name
    
        if mask.sum() == 0:
            norm_target = self._normalize_text(note_name)
            mask = df["note"].apply(self._normalize_text) == norm_target
            if mask.sum() > 0 and not silent:
                print(
                    "  ℹ️  Exact match failed; matched via smart-normalization "
                    "(ignored dash/space/case differences)."
                )

        return mask



    # ------------------------------------------------------------------
    # Static / utility methods
    # ------------------------------------------------------------------

    @staticmethod
    def fix_terminal_mojibake(text: str) -> str:
        """Attempt to fix Windows terminal encoding issues.

        When a UTF-8 string (e.g. '💡') is displayed through a cp1252 terminal,
        it appears as 'ðŸ'¡'. This method reverses that specific corruption.

        Note: This is a best-effort fix. If the text is already valid UTF-8,
        the encode('cp1252') step will raise UnicodeEncodeError and we return
        the original text unchanged.

        Args:
            text: The potentially garbled input string.

        Returns:
            The corrected string, or the original if no fix was applicable.
        """
        if not text:
            return text
        try:
            return text.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for forgiving comparisons.

        Handles:
            - Em-dash (—), en-dash (–), and minus sign (−) → standard hyphen (-)
            - Collapsed whitespace
            - Lowercasing

        Args:
            text: The raw note-name string.

        Returns:
            A normalized string suitable for comparison.
        """
        if not text:
            return ""
        text = text.replace("\u2014", "-").replace("\u2013", "-").replace("\u2212", "-")
        return " ".join(text.split()).lower()



    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    def delete_records_by_note(self, note_name: str, dry_run: bool = False) -> int:
        """Delete ALL rows matching the given note name.

        Matching strategy:
            1. Exact string equality on the 'note' column.
            2. If no exact match is found, fall back to a normalized comparison
               (case-insensitive, dash-agnostic, whitespace-collapsed).

        Args:
            note_name: The note filename to match, e.g.
                       "💡 a — Aggregation in Data Analysis (Family) — Concept.md"
            dry_run:   If True, report what WOULD be deleted without saving.

        Returns:
            The number of rows deleted (or that would be deleted in dry-run mode).

        Raises:
            ValueError: If the DataFrame has no 'note' column.
        """
        clean_note = self.fix_terminal_mojibake(note_name)
        mask = self._find_note_mask(self.df, clean_note)
        deleted_count = int(mask.sum())

        if deleted_count == 0:
            print(f"⚠️  No records found matching note:\n   '{clean_note}'")
            print("ℹ️  Tip: Run with --summary to see all available notes.")
            return 0

        actual_note_name = self.df.loc[mask, "note"].iloc[0]

        if dry_run:
            print(f"🔍 [DRY RUN] Would delete {deleted_count} record(s) for note:")
            print(f"   '{actual_note_name}'")
            print("   📄 [DRY RUN] Would reset markdown frontmatter to 'new' state (purge all FSRS metrics).")
            print("   (No changes were saved.)")
            return deleted_count

        # Confirm before destructive operation.
        print(f"⚠️  About to delete {deleted_count} record(s) for note:")
        print(f"   '{actual_note_name}'")
        confirm = input("   Proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("   Aborted. No changes made.")
            return 0

        self.df = self.df[~mask]
        self._save_csv(self.log_path, self.df, backup=True)
        print(f"✅ Deleted {deleted_count} record(s) for note:\n   '{actual_note_name}'")

        # --- Revert Frontmatter ---
        # Pass None to purge all FSRS metrics and reset the note to a "new" state
        self._update_note_frontmatter(actual_note_name, None, dry_run=dry_run)
        # --------------------------

        return deleted_count

    def delete_last_review(self, note_name: str, dry_run: bool = False) -> int:
        """Delete ONLY the last (most recent) review record for a given note.

        Use case: you graded a note but are unsure about the grade and want
        to remove the last entry so you can review and grade it again.

        The "last" record is determined by row position in the CSV (the CSV
        is chronologically ordered, so the last row = most recent review).

        Args:
            note_name: The note filename to match, e.g.
                       "💡 gro.a. — Grouped Aggregation — Concept.md"
            dry_run:   If True, report what WOULD be deleted without saving.

        Returns:
            1 if a record was deleted (or would be in dry-run), 0 otherwise.

        Raises:
            ValueError: If the DataFrame has no 'note' column.
        """
        clean_note = self.fix_terminal_mojibake(note_name)
        mask = self._find_note_mask(self.df, clean_note)
        match_count = int(mask.sum())

        if match_count == 0:
            print(f"⚠️  No records found matching note:\n   '{clean_note}'")
            print("ℹ️  Tip: Run with --summary to see all available notes.")
            return 0

        # Identify the LAST matching row (highest index = most recent in CSV).
        last_idx = self.df.index[mask][-1]
        last_row = self.df.loc[last_idx]

        actual_note_name = last_row["note"]
        last_date = last_row.get("date", "N/A")
        last_grade = last_row.get("grade", "N/A")

        if dry_run:
            print(f"🔍 [DRY RUN] Would delete the LAST review for note:")
            print(f"   Note:  '{actual_note_name}'")
            print(f"   Date:  {last_date}")
            print(f"   Grade: {last_grade}")
            print(f"   (Row {last_idx + 2} in CSV, including header)")
            
            # --- Simulate Frontmatter Revert ---
            remaining_reviews = self.df[self.df['note'] == actual_note_name].drop(index=last_idx)
            if remaining_reviews.empty:
                print("   📄 [DRY RUN] Would reset markdown frontmatter to 'new' state (purge metrics).")
            else:
                new_last_row = remaining_reviews.iloc[-1]
                print(f"   📄 [DRY RUN] Would revert markdown frontmatter to:")
                print(f"      Stability: {new_last_row['new_stability']}, Difficulty: {new_last_row['new_difficulty']}")
                print(f"      Next Review: {datetime.date.today().isoformat()} (forced due today)")
            # -------------------------------------
            
            print("   (No changes were saved.)")
            return 1

        # Confirm before deletion.
        print(f"⚠️  About to delete the LAST review for note:")
        print(f"   Note:  '{actual_note_name}'")
        print(f"   Date:  {last_date}")
        print(f"   Grade: {last_grade}")
        print(f"   (Row {last_idx + 2} in CSV, including header)")
        print(f"   ℹ️  This note has {match_count} total record(s); "
              f"only the last one will be removed.")
        confirm = input("   Proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("   Aborted. No changes made.")
            return 0

        # Delete the single row and save.
        self.df = self.df.drop(index=last_idx)
        self._save_csv(self.log_path, self.df, backup=False)
        print(
            f"✅ Deleted last review for note:\n"
            f"   '{actual_note_name}' (date: {last_date}, grade: {last_grade})\n"
            f"   You can now re-grade this note."
        )

        # --- Revert Frontmatter ---
        remaining_reviews = self.df[self.df['note'] == actual_note_name]
        if remaining_reviews.empty:
            # No more reviews left, reset to new state
            new_metrics = None
        else:
            # Revert to the new last row's state
            new_last_row = remaining_reviews.iloc[-1]
            new_metrics = {
                'stability': float(new_last_row['new_stability']),
                'difficulty': float(new_last_row['new_difficulty']),
                'last_reviewed': str(new_last_row['date']),
                'next_review': datetime.date.today().isoformat()  # Force it to be due today for re-grading
            }
        
        self._update_note_frontmatter(actual_note_name, new_metrics, dry_run=dry_run)
        # --------------------------

        return 1

    def rename_note(self, old_name: str, new_name: str, dry_run: bool = False) -> int:
        """Rename a concept note across ALL its records in the CSV.

        Finds every row whose 'note' column matches *old_name* and replaces
        it with *new_name*. Uses the same two-pass matching strategy as
        delete_records_by_note (exact first, then normalized fallback).

        Args:
            old_name: The current note filename to search for, e.g.
                      "💡 gro.a. — Grouped Aggregation — Concept.md"
            new_name: The new note filename to replace it with, e.g.
                      "💡 gro.a. — Grouped Aggregation (Family) — Concept.md"
            dry_run:  If True, report what WOULD be renamed without saving.

        Returns:
            The number of rows renamed (or that would be renamed in dry-run).

        Raises:
            ValueError: If the DataFrame has no 'note' column.
            ValueError: If old_name and new_name resolve to the same string.
        """
        clean_old = self.fix_terminal_mojibake(old_name)
        clean_new = self.fix_terminal_mojibake(new_name)
    
        if clean_old.strip() == clean_new.strip():
            raise ValueError("Old name and new name are identical. Nothing to rename.")
    
        # --- review_log.csv ---
        mask_reviews = self._find_note_mask(self.df, clean_old)
        renamed_reviews = int(mask_reviews.sum())
        
        # --- note_edits.csv ---
        mask_edits = pd.Series(dtype=bool)
        renamed_edits = 0
        if self.df_edits is not None and not self.df_edits.empty:
            # Pass silent=True to prevent duplicate normalization messages
            mask_edits = self._find_note_mask(self.df_edits, clean_old, silent=True)
            renamed_edits = int(mask_edits.sum())
    
        total_matches = renamed_reviews + renamed_edits
    
        if total_matches == 0:
            print(f"⚠️  No records found matching note:\n   '{clean_old}'")
            print("ℹ️  Tip: Run with --summary to see all available notes.")
            return 0
    
        # Determine the actual stored name for display.
        actual_old_name = clean_old
        if renamed_reviews > 0:
            actual_old_name = self.df.loc[mask_reviews, "note"].iloc[0]
        elif renamed_edits > 0:
            actual_old_name = self.df_edits.loc[mask_edits, "note"].iloc[0]
    
        if dry_run:
            print(f"🔍 [DRY RUN] Would rename across files:")
            print(f"   FROM: '{actual_old_name}'")
            print(f"   TO:   '{clean_new}'")
            print(f"   📄 review_log.csv:  {renamed_reviews} record(s)")
            print(f"   📝 note_edits.csv:  {renamed_edits} record(s)")
            print("   (No changes were saved.)")
            return renamed_reviews
    
        print(f"⚠️  About to rename across files:")
        print(f"   FROM: '{actual_old_name}'")
        print(f"   TO:   '{clean_new}'")
        print(f"   📄 review_log.csv:  {renamed_reviews} record(s)")
        print(f"   📝 note_edits.csv:  {renamed_edits} record(s)")
        confirm = input("   Proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("   Aborted. No changes made.")

            return 0
    
        # Apply rename to review_log.csv
        if renamed_reviews > 0:
            self.df.loc[mask_reviews, "note"] = clean_new
            self._save_csv(self.log_path, self.df, backup=False)
            print(f"  ✅ review_log.csv: renamed {renamed_reviews} record(s).")
    
        # Apply rename to note_edits.csv
        if renamed_edits > 0:
            self.df_edits.loc[mask_edits, "note"] = clean_new
            self._save_csv(self.edits_path, self.df_edits, backup=False)
            print(f"  ✅ note_edits.csv: renamed {renamed_edits} record(s).")
    
        # Apply rename to backup file                          # ← NEW
        self._rename_backup_file(clean_old, clean_new, dry_run=dry_run)  # ← NEW
    
        # --- Rename physical .md file and update topic ---
        old_file_path = self._find_note_file(clean_old)
        if old_file_path:
            new_file_path = old_file_path.parent / clean_new
            
            if dry_run:
                print(f"  🔍 [DRY RUN] Would rename physical file:")
                print(f"     FROM: {old_file_path.name}")
                print(f"     TO:   {new_file_path.name}")
                print(f"  🔍 [DRY RUN] Would update 'topic' in frontmatter to: '{Path(clean_new).stem}'")
            else:
                if new_file_path.exists():
                    print(f"  ⚠️  Target file '{clean_new}' already exists. Skipping physical rename.")
                else:
                    try:
                        old_file_path.rename(new_file_path)
                        print(f"  ✅ Physical file renamed:")
                        print(f"     FROM: {old_file_path.name}")
                        print(f"     TO:   {new_file_path.name}")
                        
                        # Update topic in frontmatter
                        front, body = self._read_frontmatter(new_file_path)
                        if front and 'topic' in front:
                            old_topic = front['topic']
                            # Update topic to the new filename stem (without extension)
                            front['topic'] = Path(clean_new).stem
                            self._write_frontmatter(new_file_path, front, body)
                            print(f"  ✅ Frontmatter 'topic' updated: '{old_topic}' -> '{front['topic']}'")
                    except Exception as e:
                        print(f"  ❌ Error renaming physical file: {e}")
        else:
            if not dry_run:
                print(f"  ⚠️  Physical file '{clean_old}' not found in vault. Skipping physical rename.")
        # -------------------------------------------------
    
        print(
            f"✅ Rename complete:\n"
            f"   FROM: '{actual_old_name}'\n"
            f"   TO:   '{clean_new}'"
        )

        return renamed_reviews
    
    def show_notes_summary(self) -> None:
        """Display all unique notes and the number of review records for each.

        Prints a formatted table to stdout with note names, record counts,
        and totals.
        """
        if self.df.empty:
            print("The review log is empty.")
            return
    
        # --- Review counts ---
        review_counts = self.df["note"].value_counts().reset_index()
        review_counts.columns = ["Note", "Reviews"]
    
        # --- Edit counts (from note_edits.csv if available) ---
        if (
            self.df_edits is not None
            and not self.df_edits.empty
            and "note" in self.df_edits.columns
        ):
            edit_counts = self.df_edits["note"].value_counts().reset_index()
            edit_counts.columns = ["Note", "Edits"]
        else:
            edit_counts = pd.DataFrame(columns=["Note", "Edits"])
    
        # Merge: left join so every reviewed note appears even with 0 edits.
        summary = review_counts.merge(edit_counts, on="Note", how="left")
        summary["Edits"] = summary["Edits"].fillna(0).astype(int)
    
        # Sort by review count descending.
        summary = summary.sort_values("Reviews", ascending=False).reset_index(drop=True)
    
        # --- Print table ---
        col_note_w = 85
        col_rev_w = 8
        col_edit_w = 6
    
        header = (
            f"{'NOTE NAME':<{col_note_w}} | "
            f"{'REVIEWS':>{col_rev_w}} | "
            f"{'EDITS':>{col_edit_w}}"
        )
        separator = "-" * (col_note_w + col_rev_w + col_edit_w + 6)
    
        print(f"\n{header}")
        print(separator)
    
        for _, row in summary.iterrows():
            print(
                f"{row['Note']:<{col_note_w}} | "
                f"{row['Reviews']:>{col_rev_w}} | "
                f"{row['Edits']:>{col_edit_w}}"
            )
    
        print(separator)
        print(
            f"Total Unique Notes: {len(summary):<{col_note_w - 20}} | "
            f"{'Total Reviews: ' + str(summary['Reviews'].sum()):>{col_rev_w + 12}} | "
            f"{'Total Edits: ' + str(summary['Edits'].sum()):>{col_edit_w + 13}}"
        )
        print()



# ======================================================================
# CLI entry point
# ======================================================================


def main() -> None:
    """Parse command-line arguments and dispatch to ReviewLogManager."""

    parser = argparse.ArgumentParser(
        description="Manage review_log.csv records (delete, delete-last, rename, summary).",
        epilog="""\
Examples:
  python manage_review_log.py --summary
  python manage_review_log.py --delete "💡 a — Aggregation in Data Analysis (Family) — Concept.md"
  python manage_review_log.py --delete-last "💡 gro.a. — Grouped Aggregation — Concept.md"
  python manage_review_log.py --delete-last "💡 gro.a. — Grouped Aggregation — Concept.md" --dry-run
  python manage_review_log.py --rename "old name" "new name"
  python manage_review_log.py --rename "old name" "new name" --dry-run
  python manage_review_log.py --config path/to/config.json --summary
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--delete",
        type=str,
        default=None,
        help="Delete ALL records for a specific note string.",
    )
    parser.add_argument(
        "--delete-last",
        type=str,
        default=None,
        dest="delete_last",
        help="Delete only the LAST (most recent) review record for a note "
             "(useful when you want to re-grade).",
    )
    parser.add_argument(
        "--rename",
        nargs=2,
        metavar=("OLD_NAME", "NEW_NAME"),
        default=None,
        help="Rename a note across all its records in review_log.csv AND note_edits.csv.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show all notes, their review counts, and edit counts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what WOULD be changed without saving any changes.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config.json (default: ../data/config.json relative to script).",
    )

    args = parser.parse_args()

    # Require at least one action.
    if not args.summary and not args.delete and not args.delete_last and not args.rename:
        parser.print_help()
        sys.exit(1)

    # Validate --delete input.
    if args.delete is not None and not args.delete.strip():
        parser.error("--delete requires a non-empty note name.")

    # Validate --delete-last input.
    if args.delete_last is not None and not args.delete_last.strip():
        parser.error("--delete-last requires a non-empty note name.")

    # Validate --rename input.
    if args.rename is not None:
        if not args.rename[0].strip() or not args.rename[1].strip():
            parser.error("--rename requires two non-empty note names.")

    try:
        manager = ReviewLogManager(config_path=args.config)

        if args.summary:
            manager.show_notes_summary()

        if args.delete:
            manager.delete_records_by_note(args.delete, dry_run=args.dry_run)

        if args.delete_last:
            manager.delete_last_review(args.delete_last, dry_run=args.dry_run)

        if args.rename:
            old_name, new_name = args.rename
            manager.rename_note(old_name, new_name, dry_run=args.dry_run)

    except FileNotFoundError as e:
        print(f"❌ File not found: {e}")
        sys.exit(1)
    except KeyError as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"❌ Value error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)




if __name__ == "__main__":
    main()
    
    
    
    
    