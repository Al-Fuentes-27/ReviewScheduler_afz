#!/usr/bin/env python3
import os
import re
import yaml
import math
import json
from datetime import date, timedelta
from pathlib import Path



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




# ===== FSRS-INSPIRED PARAMETERS =====
""" DESIRED_RETENTION :
This is the single most impactful parameter because it scales all intervals directly. 

With DESIRED_RETENTION = 0.90, interval equals S exactly. With 0.95, 
intervals shrink to 49% of S — nearly double the review 
frequency. With 0.85, intervals grow to 151% of S.

For Concept Notes and Debug Notes from technical books, 0.90 is the right starting point. Push to 0.85 only if your review load is unsustainable. The cost of dropping below 0.85 is that you are forgetting one in six notes at every review — which undermines the system's purpose.
"""
DESIRED_RETENTION = 0.90   # target 90% recall at review time


# Initial stability (days) assigned on very first review of a note
"""
easy :
The easy case at 10 days is conservative — real FSRS uses longer first intervals for easy ratings. But for code-heavy Concept Notes, even material that feels easy during reading often has gaps that only surface when you try to explain it cold. 10 days keeps you honest.
good :
Tune good upward to 7 if your notes tend to be well-developed before first review — meaning you wrote thorough analogies and tested examples, not just definitions.
"""
INITIAL_STABILITY = {
    'again': 1.0,    # review tomorrow
    'hard':  2.0,    # review in 2 days
    'good':  7.0,    # review in 7 days
    'easy':  10.0,   # review in 10 days
}


# Initial difficulty assigned on very first review
"""
The difficulty scale runs 1–10 with 5.5 as neutral. 
These values mean: 
- if you fail a note on first encounter, it starts life labeled as hard material. 

This is appropriate — a note you could not recall on the first review is empirically more difficult than one you found easy.

Difficulty compounds with DIFFICULTY_DELTA over subsequent reviews, so these initial values are quickly superseded by your actual performance pattern. The exact starting values matter less than the delta values below.
"""
INITIAL_DIFFICULTY = {
    'again': 8.0,
    'hard': 6.5,
    'good': 5.0,
    'easy': 3.0,
}


# How much difficulty shifts per grade
"""This controls how fast the system updates its assessment of a note's inherent difficulty."""
"""
The asymmetry is intentional — forgetting (again) penalizes harder than success rewards. This matches how memory actually works: one failure is stronger evidence of a genuine difficulty than one success is evidence of genuine ease.
The easy delta of -0.3 is deliberately smaller than the again delta of +0.8. If you make it symmetric, the system over-responds to streaks of easy reviews and starts scheduling mature notes at intervals that are too long, which produces surprise failures.

If you find difficulty converging too slowly — notes staying at initial values for many reviews — increase the deltas proportionally. If difficulty is oscillating (a note keeps swinging between hard and easy), reduce them.
"""
DIFFICULTY_DELTA = {
    'again': +0.8,
    'hard':  +0.2,
    'good':   0.0,
    'easy':  -0.3,
}


# Stability growth weights
"""
1. BASE_GROWTH:
Increase it toward 3.5 if your notes are consolidating too slowly (mature notes keep coming back too soon).
Decrease toward 2.0 if intervals are growing so fast that you regularly fail mature notes.
W_RECALL_TIMING:
2. W_RECALL_TIMING:
Controls how much you are rewarded for recalling something you nearly forgot. 
At 0.5, a note recalled at R=0.3 (very overdue) gets 73% more stability growth than one reviewed at R=0.9. 
- Increase toward 0.8 if you want to strongly incentivize spacing reviews out to the edge. 
- Decrease toward 0.2 if you find overdue notes producing unrealistically long next intervals.
"""
BASE_GROWTH       = 2.9    # S roughly triples per review at ideal timing/difficulty
W_RECALL_TIMING   = 0.5    # Reward exponent for recalling near forgetting threshold
W_DIFF_SCALE      = 0.08   # Difficulty effect on growth (centered at D=5.5)
W_DECAY           = 0.1    # Maturity dampening exponent


# Stability after forgetting weights  
"""
W_FORGET_S :
- Increase toward 0.7 to give more recovery credit for prior learning. 
- Decrease toward 0.3 if you want forgetting to be more punishing — closer to a full reset.
"""
W_FORGET_BASE = 0.5
W_FORGET_S    = 0.5    # Prior stability recovery bonus
W_FORGET_D    = 0.3    # Difficulty recovery penalty  
W_FORGET_R    = 1.0    # Low retrievability at failure → less recovery




# Grade multipliers applied on top of recall stability formula
"""
These apply after the main growth calculation. 
hard at 0.75 means you still gain stability — you did recall the note — but 25% less than a clean recall. 

Do not set hard below 0.6 or you will find yourself stuck with notes that oscillate between hard and again without ever maturing.
"""
GRADE_STABILITY_MULTIPLIER = {
    'hard': 0.75,
    'good': 1.00,
    'easy': 1.35,
}






MIN_STABILITY = 0.1
MAX_STABILITY = 365.0
MIN_DIFFICULTY = 1.0
MAX_DIFFICULTY = 10.0
# =====================================




def retrievability(elapsed_days: float, stability: float) -> float:
    """Probability of recall given elapsed time and current stability."""
    """R = 0.9 when elapsed == S. Intuitive: S is the interval."""
    if stability <= 0:
        return 0.0

    return 0.9 ** (elapsed_days / stability)


def stability_after_recall(S: float, D: float, R: float, grade: str) -> float:
    """
    Stability growth after successful recall.
    Growth is larger when:
      - R is low (you recalled near the forgetting threshold)
      - D is low (material is easier to consolidate)
      - S is low (early-stage memories benefit more from each review)
    """
    # Reward reviewing near the forgetting threshold
    # R=0.9 (ideal) → 1.0, R=0.5 (late but recalled) → 1.34, R=0.99 (early) → 0.95
    timing_factor = (0.9 / max(R, 0.05)) ** W_RECALL_TIMING

    # Easier material consolidates faster
    # D=1 → 1.36, D=5 → 1.04, D=10 → 0.64
    diff_factor = max(0.5, 1.0 + W_DIFF_SCALE * (5.5 - D))

    # Diminishing returns for already-mature notes
    maturity_factor = S ** (-W_DECAY)

    new_S = (S * BASE_GROWTH
             * timing_factor
             * diff_factor
             * maturity_factor
             * GRADE_STABILITY_MULTIPLIER[grade])

    return max(MIN_STABILITY, min(MAX_STABILITY, new_S))


def stability_after_forget(S: float, D: float, R: float) -> float:
    """
    Stability after forgetting. Does NOT reset to a fixed value.
    Prior stability partially survives — a well-learned note recovers faster.
    """
    # Well-learned notes recover faster
    prior_credit = W_FORGET_BASE * (S ** W_FORGET_S)
    # Harder material recovers less
    diff_penalty = (10.0 / D) ** W_FORGET_D
    # If very overdue when forgotten, less recovery than if forgotten right on time
    R_factor = math.exp(W_FORGET_R * R)

    return max(MIN_STABILITY, min(MAX_STABILITY,
                                  prior_credit * diff_penalty * R_factor))


def update_difficulty(D: float, grade: str) -> float:
    new_D = D + DIFFICULTY_DELTA[grade]
    return max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, new_D))


def interval_from_stability(S: float) -> int:
    """Days until R drops to DESIRED_RETENTION."""
    days = S * math.log(DESIRED_RETENTION) / math.log(0.9)

    return max(1, int(days))


def compute_new_schedule(front: dict, grade: str, elapsed_days: float) -> dict:
    """
    Core scheduling function. Returns updated scheduling fields.
    Handles both new notes (no stability yet) and reviewed notes.
    """
    is_new = 'stability' not in front

    if is_new:
        S = INITIAL_STABILITY[grade]
        D = INITIAL_DIFFICULTY[grade]
        lapses = 1 if grade == 'again' else 0

    else:
        S = float(front['stability'])
        D = float(front.get('difficulty', 5.0))
        R = retrievability(elapsed_days, S)
        lapses = int(front.get('lapses', 0))

        if grade == 'again':
            S = stability_after_forget(S, D, R)
            lapses += 1
        else:
            S = stability_after_recall(S, D, R, grade)

        D = update_difficulty(D, grade)

    interval = interval_from_stability(S)

    return {
        'stability':  round(S, 4),
        'difficulty': round(D, 4),
        'interval':   interval,
        'lapses':     lapses,
    }






















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



def update_note(filepath, grade, configuration):
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

    new_content = f"---\n{yaml.dump(front, allow_unicode=True, sort_keys=False)}---\n{body}"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"Updated {filepath.name}")
    print(f"Stability: {updates['stability']:.1f}d  | "
          f"Difficulty: {updates['difficulty']:.1f} | "
          f"Next review: {front['next_review']}     |")

    # Append to review log
    log_path = Path(configuration["log_path"])
    if not log_path.exists():
        log_path.write_text("date,note,grade,elapsed,R_at_review,new_stability,new_difficulty\n")

    with open(log_path, "a") as log:
        log.write(f"{today},{filepath.name},{grade},"
                  f"{elapsed},{r_label},"
                  f"{updates['stability']},{updates['difficulty']}\n")






def main():
    # Load the config once when the script starts
    config_path = Path(r"..\data\config.json")
    config = load_config(config_path)
    
    # Get the specific file path (ensuring it's a Path object for easy manipulation)
    VAULT_PATH = Path(config["obsidian_vault_path"])
    print(f"Successfully loaded the obsidian vault path: {VAULT_PATH}")

    # Get the specific notes file extension
    NOTES_EXT = config["notes_extension"]
    print(f"Searching files with '{NOTES_EXT}' extension")

    
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
        rel = f.relative_to(VAULT_PATH)
        print(f"{i+1}. {rel}")

    for filepath, topic in due_files.items():
        print(f"\n--- {filepath.relative_to(VAULT_PATH)} ---")
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

        update_note(filepath, grade_map[grade], config)













if __name__ == "__main__":
    main()



