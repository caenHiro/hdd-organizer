# hdd-organizer

> CLI to organize a full HDD in 8 deterministic steps — no AI, no cloud, no data loss.

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-574%20passing-brightgreen?style=flat)](tests/)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat)](LICENSE)
[![CLI](https://img.shields.io/badge/CLI-Click%20%2B%20Rich-00B4D8?style=flat)](src/organizador_hdd/cli.py)

---

## What it does

Takes a chaotic HDD (tested on **890K files / 2.7 TB**) and organizes it into a clean, predictable structure:

```
HDD_organized/
├── 01_photos/       YYYY/MM_name/ — sorted by EXIF or filename date
├── 01b_images/      wallpapers/ superheroes/ art/ cars/ memes/
├── 02_videos/       series/<Name>/Season N/ | movies/ | courses/ | fitness/
├── 03_music/        by_artist/<Artist>/<Album>/
├── 04_books/        ebooks/ audiobooks/ courses/ technical/
├── 07_school/       Semester N/<Subject>/
├── 08_documents/    personal/ health/ work/
├── 09_code/         complete projects moved as atomic units
├── 10_software/     windows/ linux/ mac/
└── _pending/        review/ unclassified/ duplicates/
```

**Core principle: every destructive operation requires `--confirmar`. Default is always dry-run.**

---

## Pipeline (8 steps)

| Step | What it does |
|---|---|
| `paso1` | Remove technical artifacts: `.class`, `.pyc`, `node_modules`, `.DS_Store`, LaTeX output |
| `paso2` | Detect complete code projects by `package.json`, `pom.xml`, `.git` — move as atomic units |
| `paso3` | SHA-256 exact duplicate detection |
| `paso4` | Photos vs downloaded images: EXIF score + folder heuristics → `01_photos/` or `01b_images/` |
| `paso5` | Music by artist/album using ID3/Vorbis/MP4 tags via `mutagen` |
| `paso6` | Classify everything else: videos, PDFs, documents, software, books |
| `paso7` | Smart deduplicator: SHA-256 groups → scoring (path + metadata + name + size + mtime) |
| `paso8` | Detect school material: `Semester N/Subject/` → structured academic folders |

---

## Install

```bash
git clone https://github.com/caenHiro/sistema-archivos-hdd
cd sistema-archivos-hdd
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# With multimedia metadata support (EXIF photos, ID3 music, PDF page count):
pip install -e ".[metadata]"
```

---

## Usage

```bash
# Always dry-run first — shows what WOULD happen
hdd-organizar paso1 /media/HDD --dry-run
hdd-organizar paso6 /media/HDD --dry-run

# Confirm when you're ready
hdd-organizar paso1 /media/HDD --confirmar
hdd-organizar paso6 /media/HDD --confirmar

# Scan and generate an Obsidian map note
hdd-organizar mapa /media/HDD ~/vault

# Generate _README.md guides in each organized folder
hdd-organizar generar-readme /media/HDD/HDD_organized
```

---

## Image subcategories (no AI)

Images that aren't personal photos go to `01b_images/` with automatic subcategories detected from filename/path heuristics:

| Folder | Detection signal |
|---|---|
| `wallpapers/` | Screen resolution (1080p, 4K…) or "wallpaper/background" in path |
| `superheroes/` | Marvel, DC, Batman, Dragon Ball, Naruto… |
| `art/` | anime, manga, illustration, fanart, Pokémon |
| `cars/` | Ferrari, BMW, supercar, automobile… |
| `memes/` | meme, funny, lol, dank… |
| `_unclassified/` | Default |

---

## Obsidian integration

Generates structured Markdown notes in your vault:
- `Personal/HDD/HDD_Index.md` — master index with stats per category
- `_README.md` in each HDD folder — rules, subcategories, current file counts

---

## Tests

```bash
python3 -m pytest tests/ -q
# 574 passed in 1.6s
```

All tests run without a physical HDD using `tmp_path` fixtures. Covers all 8 steps, classifiers, deduplicator, README generator and Obsidian writer.

---

## Tech

- **Python 3.12+** · Click · Rich · SQLite · mutagen · Pillow · pypdf
- Architecture: functional pipeline — `detect → build_plan → execute_plan`
- Idempotent: SHA-256 (64KB) + size check before every move
- Full reversal log in JSON before each real write
