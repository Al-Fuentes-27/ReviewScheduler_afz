#!/usr/bin/env python3
import os
import re
import yaml
from datetime import date, timedelta
from pathlib import Path







# ===== CONFIGURATION =====
VAULT_PATH = os.getcwd() + r"\GB_PersonalStudyNotes"
NOTES_EXT = ".md"




# FSRS‑like parameters (you can tune these)
EASE_FACTORS = {
    "again": 0.1,   # interval becomes 10% of current
    "hard": 1.2,
    "good": 2.5,    # this is the base ease if not overridden
    "easy": 5.0
}
MIN_INTERVAL = 1      # at least 1 day
MAX_EASE = 5.0
MIN_EASE = 1.3
# =========================





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



def update_note(filepath, grade):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()


    front, body = parse_frontmatter(content)
    if not front:
        print(f"No frontmatter in {filepath}, skipping.")
        return


    # Ensure required fields exist
    if 'last_reviewed' not in front:
        front['last_reviewed'] = date.today().isoformat()

    if 'interval' not in front:
        front['interval'] = 1

    if 'ease' not in front:
        front['ease'] = 2.5

    if 'lapses' not in front:
        front['lapses'] = 0

    # Convert dates
    today = date.today()


    # Calculate new interval based on grade
    if grade == "again":
        front['lapses'] += 1
        front['ease'] = max(MIN_EASE, front['ease'] - 0.2)
        new_interval = 1   # review tomorrow

    elif grade == "hard":
        front['ease'] = max(MIN_EASE, front['ease'] - 0.15)
        new_interval = int(front['interval'] * 1.2)

    elif grade == "good":
        new_interval = int(front['interval'] * front['ease'])
        front['ease'] = min(MAX_EASE, front['ease'] + 0.05)

    elif grade == "easy":
        new_interval = int(front['interval'] * front['ease'] * 1.3)
        front['ease'] = min(MAX_EASE, front['ease'] + 0.1)

    else:
        print(f"Unknown grade {grade}, skipping.")
        return

    # Enforce minimum interval
    new_interval = max(MIN_INTERVAL, new_interval)

    # Update dates
    front['last_reviewed'] = today.isoformat()
    front['next_review'] = (today + timedelta(days=new_interval)).isoformat()
    front['interval'] = new_interval


    # Write back
    new_content = f"---\n{yaml.dump(front, allow_unicode=True, sort_keys=False)}---\n{body}"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"Updated {filepath.name} – next review {front['next_review']}")






def main():
    due_files = {}

    
    for md_file in Path(VAULT_PATH).rglob(f"*{NOTES_EXT}"):
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

                if next_date == date.today():  # <=
                    #due_files.append(md_file)
                    due_files.setdefault(md_file, topic)
                    
            except Exception as e:
                print(f"Warning: Could not parse date in {md_file}: {e}")

    if not due_files:
        print("No notes due today. You can still review any note.")
        # Optionally allow manual entry as before
        return

    print(f"Found {len(due_files)} notes due today:\n")    
    for i, f in enumerate(due_files.keys()):
        rel = f.relative_to(Path(VAULT_PATH))
        print(f"{i+1}. {rel}")

    for filepath, topic in due_files.items():
        print(f"\n--- {filepath.relative_to(Path(VAULT_PATH))} ---")
        print(f"<__> Topic of the note: {topic}")
        print("""\na: for again / white (failed)
              h: for hard / red
              g: for good / yellow
              e: for easy / green
              """)

        grade = input("Grade? (a/h/g/e or skip with Enter): ").strip().lower()

        if not grade:
            print("Skipped.")
            continue

        grade_map = {'a':'again', 'h':'hard', 'g':'good', 'e':'easy'}

        if grade not in grade_map:
            print("Invalid grade, skipping.")
            continue

        update_note(filepath, grade_map[grade])













if __name__ == "__main__":
    main()



