#!/usr/bin/env python3
import os
import re
import yaml
import csv
import json
from datetime import date, timedelta
from pathlib import Path


# Import the separated FSRS algorithm engine
from FSRS_engine import retrievability, compute_new_schedule





# ===== CONFIGURATION =====
def load_config(CONFIG_FILE):
    """Load configuration from config.json. Exit if not found."""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Configuration file not found!\n"
            f"Expected location: {CONFIG_FILE}\n"
            f"Please copy 'config.example.json' to 'config.json' and edit it with your local paths."
        )
    
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def to_date(value):
    """Convert a string or date object to a date."""
    if isinstance(value, date):
        return value
    elif isinstance(value, str):
        return date.fromisoformat(value)
    else:
        raise TypeError(f"Cannot convert {type(value)} to date")


def parse_frontmatter(content):
    """Extract YAML frontmatter and the rest of the content."""
    # Locate the YAML frontmatter content and the note content
    frontmatch = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)

    # if we do not have any information to be extracted, it will finish the function
    if not frontmatch:
        return {}, content

    # Get the YAML frontmatter and note contents
    yaml_text, rest = frontmatch.group(1), frontmatch.group(2)


    # Attempt to parse — don't crash if something goes wrong
    try:
        # Convert YAML text into a Python dict
        """{tag: tagContent,
        'topic': FileTopicName,
        'next_review': date,
        ...}
        """
        front = yaml.safe_load(yaml_text)
        # Return parsed content if it exists, otherwise return empty dict as fallback
        return front if front else {}, rest

    # If it is not possible to parse the YAML frontmatter content, it will finish the function
    except yaml.YAMLError:
        return {}, content





# ===== LOGGING FUNCTIONS =====

def log_review_event(filepath_name, grade, elapsed, r_label,
                     stability, difficulty, review_time, configuration):
    """Append one review event to review_log.csv."""
    # Append to review log — csv.writer quotes any field containing commas
    log_path = Path(configuration["log_path"])
    
    # Create the log file if not exists
    if not log_path.exists():
        with open(log_path, "w", newline="", encoding="utf-8") as log:
            csv.writer(log).writerow([
                "date", "note", "grade", "elapsed",
                "R_at_review", "new_stability", "new_difficulty",
                "review_time",
            ])
            
    # Update the already existing log file
    with open(log_path, "a", newline="", encoding="utf-8") as log:
        csv.writer(log).writerow([
            date.today(),
            filepath_name,
            grade,
            elapsed,
            r_label,
            stability,
            difficulty,
            review_time if review_time is not None else "",
        ])


def log_note_edit(filepath_name, configuration):
    """Prompt the user for edit details and append to note_edits.csv."""
    edits_path = Path(configuration["edits_path"])
    
    # Create the log file if not exists
    if not edits_path.exists():
        edits_path.parent.mkdir(parents=True, exist_ok=True)

        with open(edits_path, "w", newline="", encoding="utf-8") as log:
            csv.writer(log).writerow([
                "date", "note", "edit_type", "description"
            ])
            
    print(f"\n{'=' * 70}")
    print("📝 Log a note edit/rewrite")
    print("Edit types:")
    print("  1: minor_tweak (fixed typos, small clarifications)")
    print("  2: major_rewrite (restructured, added/removed significant content)")
    print("  3: complete_overhaul (started from scratch, completely new concept)")
    
    while True:
        type_input = input("Edit type? (1/2/3): ").strip()
        type_map = {'1': 'minor_tweak', '2': 'major_rewrite', '3': 'complete_overhaul'}

        if type_input in type_map:
            edit_type = type_map[type_input]
            break

        print("Invalid choice. Please enter 1, 2, or 3.")
        
    desc = input("Brief description of changes: ").strip()
    
    date_input = input("Date of edit (YYYY-MM-DD, or Enter for today): ").strip()

    if not date_input:
        edit_date = date.today().isoformat()
    else:
        try:
            edit_date = date.fromisoformat(date_input).isoformat()
        except ValueError:
            print("Invalid date format. Defaulting to today.")
            edit_date = date.today().isoformat()
            
    with open(edits_path, "a", newline="", encoding="utf-8") as log:
        csv.writer(log).writerow([
            edit_date,
            filepath_name,
            edit_type,
            desc
        ])

    print(f"✅ Edit logged to {edits_path.name}")






# ===== NOTE UPDATE =====

def update_note(filepath, grade, configuration, review_time):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    front, body = parse_frontmatter(content)
    if not front:
        print(f"No frontmatter in {filepath}, skipping.")
        return

    today = date.today()

    # Calculate elapsed days since last review
    if 'last_reviewed' in front:
        last = to_date(front['last_reviewed'])
        elapsed = (today - last).days
    else:
        elapsed = 0

    # Compute R here so it is available for logging
    if 'stability' in front:
        R = retrievability(elapsed, float(front['stability']))
        r_label = round(R, 3)
    else:
        R = None
        r_label = 'new'

    # Compute new schedule
    updates = compute_new_schedule(front, grade, elapsed)

    # Apply updates to frontmatter
    front.update(updates)
    front['last_reviewed'] = today.isoformat()
    front['next_review']   = (today + timedelta(days=updates['interval'])).isoformat()
    front['review_time']  = review_time   # minutes spent in this review session

    new_content = f"---\n{yaml.dump(front, allow_unicode=True, sort_keys=False)}---\n{body}"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"\n{'=' * 70}")
    print(f"Updated {filepath.name}")
    print(f"Stability: {updates['stability']:.1f}d  | "
          f"Difficulty: {updates['difficulty']:.1f} | "
          f"Next review: {front['next_review']}     |")


    # Delegate CSV logging to its own function, append to review log — csv.writer quotes any field containing commas
    log_review_event(
        filepath_name = filepath.name,
        grade         = grade,
        elapsed       = elapsed,
        r_label       = r_label,
        stability     = updates["stability"],
        difficulty    = updates["difficulty"],
        review_time   = review_time,
        configuration = configuration,
    )























# ===== MAIN =====

def main():
    # Load the config once when the script starts
    config_path = Path(r"..\data\config.json")
    config = load_config(config_path)
    
    # Get the specific file path (ensuring it's a Path object for easy manipulation)
    VAULT_PATH = Path(config["obsidian_vault_path"])
    print(f"Successfully loaded the obsidian vault path: {VAULT_PATH}\n")

    # Get the specific notes file extension
    NOTES_EXT = config["notes_extension"]
    print(f"Searching files with '{NOTES_EXT}' extension\n")

    
    due_files = {}

    
    for md_file in VAULT_PATH.rglob(f"*{NOTES_EXT}"):
        """Extract the .md file contents."""
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        """Extract YAML frontmatter and the rest of the content."""
        front, _ = parse_frontmatter(content)
     
        # Ignore the templates folder, when searching for our .md notes files
        if "template" in str(md_file).lower():
            continue

        # I
        if 'next_review' in front:
            try:
                """Convert a string or date object to a date."""
                next_date, topic = to_date(front['next_review']), front['topic']

                #if next_date <= date.today():  # <=
                if (next_date <= date.today()) and (next_date >= (date.today() - timedelta(days=5))):
                    due_files.setdefault(md_file, topic)
                    
            except Exception as e:
                print(f"\n>>> Warning: Could not parse date in {md_file}:\n{e} <<<")

    if not due_files:
        print("No notes due today. You can still review any note.")
        # Optionally allow manual entry as before
        return

    print(f"\n\nFound {len(due_files)} notes due today:")    
    for i, f in enumerate(due_files.keys()):
        rel = f.relative_to(VAULT_PATH)
        print(f"{i+1}. {rel}")

    for filepath, topic in due_files.items():
        output_message = f"""\n
--- {filepath.relative_to(VAULT_PATH)} ---

{'_' * 70}

<__> Topic of the note:
{topic}

a: for again / white (failed)
h: for hard / red
g: for good / yellow
e: for easy / green
"""
        print(output_message)
        
        grade = input("Grade? (a/h/g/e or skip with Enter): ").strip().lower()

        if not grade:
            print("Skipped.")
            continue         # ← jumps to next note, NEVER reaches edit prompt

        grade_map = {'a':'again', 'h':'hard', 'g':'good', 'e':'easy'}

        if grade not in grade_map:
            print("Invalid grade, skipping.")
            continue         # ← jumps to next note, NEVER reaches edit prompt
        
        
        """Record the time spent on the review session."""
        print("\nReview time? <=======> minutes:seconds.centiseconds --> m:s.cs")
        
        while True:

            time_input = input("m:s.cs, or Enter to skip: ").strip()

            if not time_input:
                review_time = None
                break  # Skip recording

            # Regex to match m:s, allowing integer or float values for each component
            pattern = r'^(?:(\d+)[^\d.]+)?(\d+(?:\.\d+)?)$'
            match = re.match(pattern, time_input)
            
            if not match:
                print("Invalid format. Use numbers separated by the same non‑digit character (e.g., 1:30:45, 2-15-30.5, 0/5/0.75).")
                continue  # Ask again

            try:    
                # Extract groups
                m = int(match.group(1) or 0)    # integer minutes, defaults to 0
                s = float(match.group(2))       # seconds with centiseconds as float
    
                total_minutes = m + s / 60
                review_time = round(total_minutes, 2)
                
                break  # Success, exit loop
    
            except ValueError:
                print("Invalid numeric values. Please enter valid numbers.")
                continue  # Ask again


        """Update all the files regarding to the review."""
        update_note(filepath, grade_map[grade], config, review_time)

        # === Prompt for Note Edits ===
        # Only reached after a valid grade + time. Skipped/invalid reviews
        # never arrive here because of the 'continue' statements above.
        # Default action is Enter (skip) so it adds zero friction on normal days.
        edit_ans = input("\nNote edited? (Enter to skip, 'y' to log): ").strip().lower()
        
        if edit_ans == 'y':
            log_note_edit(filepath.name, config)  # ▼▼▼ ONLY reached if grade was valid ▼▼▼











if __name__ == "__main__":
    main()



