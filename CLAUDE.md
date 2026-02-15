# NY-Scout — Project Instructions

## Workflow
- **BACKLOG.md** is the source of truth for what to work on
- Work on one theme at a time; within a theme, one task at a time
- When starting a task: mark it `[~]` in BACKLOG.md
- While working: add `>` notes under the task explaining decisions, problems, or deviations
- When finishing a task: mark it `[x]` in BACKLOG.md (keep the notes)
- When a theme is complete: move it to "Completed Themes" and pick the next one

## Project Conventions
- Python 3.12, Peewee ORM, SQLite at data/scout.db
- Config lives in config/*.yaml
- Tests: `python3 -m pytest tests/`
- Digest dry run: `python3 scripts/run_digest.py --dry-run -v`
- Ingest: `python3 scripts/run_ingest.py -v`
- Static site output: docs/ (served via GitHub Pages)
- Don't commit .env or data/scout.db
