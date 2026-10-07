<div align="center">

# 🧠 FSRS-Inspired Obsidian Review Scheduler & Analytics Suite

[![📊 VIEW LOCAL DASHBOARD](https://img.shields.io/badge/📊_OPEN_DASHBOARD-Review_Metrics-1D9E75?style=for-the-badge&logo=obsidian&logoColor=white)](./dashboard example/review_metrics.html)

*Click the button above to explore the global analytics dashboard (Dark/Light mode, dynamic charts, and study insights).*

</div>

![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-Data_Processing-150458?logo=pandas&logoColor=white)
![Chart.js](https://img.shields.io/badge/Chart.js-Interactive-FF6384?logo=chart.js&logoColor=white)
![Algorithm](https://img.shields.io/badge/Algorithm-FSRS_Inspired-purple)
![Status](https://img.shields.io/badge/Status-Production_Ready-success)

An advanced, locally-hosted Spaced Repetition System (SRS) engine and analytics suite designed specifically for **Obsidian** knowledge vaults. Inspired by the **FSRS (Free Spaced Repetition Scheduler)** algorithm, this project moves beyond legacy SM-2 scheduling to dynamically model memory *Stability* and *Difficulty*, translating raw review logs into actionable study insights and identifying "leaky" concept notes before they cause exam failure.

> 📊 **[View the Global Dashboard](./dashboard example/review_metrics.html)** | 🔍 **[View Single-Note Reports](./dashboard example/r.w.a.,_t.s._&_s._rolling_window_aggregation_in_time_series_&_statistics_concept.html)**

---

## 💡 Key Insights & System Features

- 🎯 **Precision Scheduling (FSRS-Inspired)**: Calculates exact review intervals based on a target **Desired Retention (e.g., 90%)**. Notes that are nearly forgotten (low Retrievability) but successfully recalled receive massive stability boosts, optimizing the spacing effect.
- ⚠️ **Divergence Detection (The "Rewrite" Trigger)**: Automatically flags notes that are both **Hard (Difficulty ≥ 9.5)** and **Slow (> 16 min review time)**. These are empirically proven to be poorly structured and are flagged for immediate rewriting.
- ✏️ **Edit Effectiveness Analytics**: Uniquely joins `note_edits.csv` with `review_log.csv` to measure the *actual ROI* of rewriting a note. Did your edit reduce review time? Did it stop the lapses? The dashboard proves it.
- 🔄 **Lapse → Edit → Recovery Pipeline**: Tracks the lifecycle of forgotten notes. Visualizes whether a lapsed note was successfully recovered after an edit, or if it remains a "failed fix" requiring deeper intervention.

---

## 🔄 The Daily Review Workflow (`FSRS_update.py`)

The heart of the system is `FSRS_update.py`, a CLI tool designed for seamless daily studying:

1. **Auto-Discovery**: Scans your Obsidian vault for notes with a `next_review` date in the past (up to 5 days overdue).
2. **Interactive Grading**: Presents the note's topic and prompts for a grade (`a`gain, `h`ard, `g`ood, `e`asy).
3. **Time Tracking**: Prompts for the time spent reviewing (accepts `m:s.cs` format, e.g., `2:15.50` for 2 mins 15.5 secs).
4. **Smart Frontmatter Injection**: Automatically recalculates Stability, Difficulty, and Retrievability, then writes the new `next_review` date directly into the note's YAML frontmatter.
5. **Edit & Backup Pipeline**: Asks if you rewrote the note. If yes, logs the edit type/description to `note_edits.csv` and safely appends the note's current state to a timestamped `.txt` backup file.
6. **Auto-Analytics**: Once the session ends, it automatically triggers the single-note and global dashboard generators, opening your updated HTML reports in your browser.

---

## 📊 Interactive HTML Dashboards

The system generates two tiers of fully interactive, dark-mode-aware HTML dashboards powered by **Chart.js**:

### 1. Global Vault Analytics (`review_metrics.html`)
A 4-tab command center for your entire study corpus:
* **Tab A (Review Time)**: Horizontal bar charts of slowest notes, scatter plots of time vs. grade, and weekly efficiency trends.
* **Tab B (Note Edits)**: Pre/Post edit performance comparisons and an edit effectiveness scorecard.
* **Tab C (Cross-Cutting)**: The Lapse→Edit→Recovery pipeline, a Note×Week review time heatmap, and a Difficulty vs. Time divergence scatter plot.
* **Tab D (Detail Breakdown)**: Granular time distribution and median review speeds.

### 2. Single-Note Deep Dives (`note_reports/*.html`)
Automatically generates an individual dashboard for every tracked concept note, featuring:
* **Stability & Difficulty Trajectories**: Line charts colored by grade (Again/Hard/Good/Easy) with vertical magenta dividers marking exact dates you rewrote the note.
* **Retrievability Histogram**: Ensures you are reviewing notes in the optimal 0.8–1.0 R-window.
* **Full Audit Timeline**: A row-by-row history of every review, elapsed time, and stability shift.

---

## 🧪 The Science: FSRS Core Mechanics

This engine ditches fixed multipliers in favor of continuous mathematical modeling:
1. **Retrievability (R)**: The probability of recalling a note at any given moment. $R = 0.9^{\frac{t}{S}}$.
2. **Stability (S)**: The time (in days) it takes for R to drop to 90%. Successful recalls increase S; lapses decrease it (but retain "prior credit" based on past maturity).
3. **Difficulty (D)**: A 1-10 scale that evolves with every grade. Asymmetric deltas ensure that forgetting (Again) penalizes harder than success rewards, preventing mature notes from being scheduled too far into the future.

---

## 🚀 Quickstart Guide

### Prerequisites
- Python 3.9+
- `PyYAML` and `pandas` (`pip install pyyaml pandas`)
- An **Obsidian** vault containing your `.md` concept notes with YAML frontmatter.

### 1. Clone and Configure
```bash
git clone <your-repo-url>
cd FSRS_ReviewScheduler
```

Create and edit `data/path_config.json` to point to your local Obsidian vault and output directories:

```bash
{
  "obsidian_vault_path": "YOUR OBSIDIAN VAULT PATH",
  "notes_extension": ".md",
  "log_path": "..\\outputs\\review_log.csv",
  "edits_path": "..\\outputs\\note_edits.csv",
  "metrics_path": "..\\outputs\\review_metrics.html",
  "backup_path": "..\\outputs\\note_backup",
  "testing_FSRS_metrics": {
    "log_path": "..\\tests\\review_log.csv",
    "edits_path": "..\\tests\\note_edits.csv",
    "metrics_path": "..\\tests\\review_metrics.html",
    "backup_path": "..\\tests\\note_backup"
  }
}
```


## 2. Run Your Daily Review

Simply execute the main update script. It handles the review loop, logging, and dashboard generation automatically.

```bash
python FSRS_update.py
```

*The script will scan your vault, guide you through the CLI prompts, and automatically open your updated HTML dashboards when finished.*

## 3. Maintain Your Log (CLI Tool)

Use the built-in CLI manager to clean up your data, fix typos in note names, or re-grade a note you accidentally clicked wrong.

```bash
# View a summary of all tracked notes and their lapse counts
python manage_review_log.py --summary

# Delete the last review of a note (to re-grade it)
python manage_review_log.py --delete-last "💡 gro.a. — Grouped Aggregation — Concept.md"

# Rename a note across both review and edit logs (fuzzy matching enabled)
python manage_review_log.py --rename "old_note.md" "new_note.md"
```

## 📂 Project Structure

```
FSRS_ReviewScheduler/
│
├── code_of_conduct.md
├── CONTRIBUTING.rst
├── LICENSE
├── tox.ini
├── 📄 README.md                     ← You are here
│
├── 📁 data/
│   └── path_config.json             ← Centralized path routing (Prod vs Test modes)
│
├── 📁 outputs/                      ← (Generated) Dashboards and CSV logs
│   ├── review_metrics.html          ← The Global Dashboard
│   ├── review_log.csv               ← The raw review history
│   ├── note_edits.csv               ← History of note rewrites
│   ├── 📁 note_reports/             ← Folder containing individual note HTMLs
│   │     └── ...                    ← (Generated) Dashboards for each note
│   └── 📁 note_backup/
│         └── ...                    ← (Generated) Backups for each note type after edition
├── 📁 src/
│   ├── ⚙️ FSRS_engine.py                ← Core scheduling math (Stability, Difficulty, R)
│   ├── 📊 FSRS_metrics.py               ← Global HTML dashboard generator
│   ├── 🔍 FSRS_single_note_metrics.py   ← Per-note HTML dashboard generator
│   ├── 🚀 FSRS_update.py                ← Main CLI entry point (Review loop, logging, backups)
│   ├── 🛠️ manage_review_log.py          ← CLI tool for CSV maintenance
│   └── 📁 other algorithms/
│         └── SM-2_update.py
│
└── 📁 tests/                        ← (Optional) Test datasets for pipeline validation
```

## 🛠️ Tech Stack

| Category | Technologies |
| --- | --- |
| **Language** | Python 3.9+ |
| **Data Processing** | Pandas, Native `csv` & `json` modules |
| **Obsidian Integration** | PyYAML (Frontmatter parsing & injection) |
| **Algorithm** | FSRS-Inspired Math (Custom Python Implementation) |
| **Data Visualization** | Chart.js 4.x, Chart.js Annotation Plugin |
| **Web Dashboard** | HTML5, CSS3 (CSS Variables for Dark/Light Mode), Vanilla JS |
| **Knowledge Base** | Obsidian (Markdown) |

---

## 📚 Core Parameters (Tuning Your Brain)

The system is highly tunable via `FSRS_engine.py`.

1. **DESIRED_RETENTION = 0.90**: The target recall probability. Pushing this to `0.95` will nearly double your review frequency. Dropping to 0.85 reduces load but increases forgetting.
2. **BASE_GROWTH = 2.6**: How fast stability multiplies on a perfect recall.
3. **W_RECALL_TIMING = 0.5**: The "Desirable Difficulty" reward. Recalling a note right before you forget it (low R) yields a larger stability boost than reviewing it too early.

---

## 👨‍🔬 Author & License

**Aldo Fuentes Zaldivar**
*Specializing in Knowledge Management, Cognitive Load Theory, and Python Tooling.*

*This project is open-source and built for the lifelong learning community.*

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-blue?logo=linkedin)](http://www.linkedin.com/in/aldo-fuentes-3816a9424)

[![GitHub](https://img.shields.io/badge/GitHub-Al--Fuentes--27-black?logo=github)](https://github.com/Al-Fuentes-27)

---

## 📚 References & Inspirations:

- *Jaroslawski, P. (2022). FSRS (Free Spaced Repetition Scheduler).*
- *Piotr Wozniak (1990). SM-2 Algorithm (SuperMemo).*
- *Bjork, R. A. (1994). Memory and Metamemory Considerations for the Training of Human Beings (Desirable Difficulties).*
