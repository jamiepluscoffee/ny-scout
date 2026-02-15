# NYC Concierge Scout

A personal daily digest app that surfaces high-signal NYC event recommendations — jazz, concerts, theatre, exhibitions — tailored to your taste.

## Quick Start

```bash
# Clone & install
git clone https://github.com/jamiepluscoffee/ny-scout.git
cd ny-scout
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys and SMTP credentials

# Initialize database
python -c "from db.models import init_db; init_db()"

# Run ingestion (fetch events from all sources)
python scripts/run_ingest.py

# Generate and send digest
python scripts/run_digest.py

# Or preview without sending
python scripts/run_digest.py --dry-run
```

## Sources

| Source | Method | Reliability |
|--------|--------|-------------|
| Ticketmaster | JSON API | High |
| Jazz Gallery | ICS calendar | High |
| JazzNearYou | JSON-LD extraction | High |
| Village Vanguard | HTML scrape | Medium |
| Smalls Jazz Club | HTML scrape | Medium |
| Poster House | HTML scrape | Medium |

## Adding a New Source

1. Add entry to `config/sources.yaml`
2. Create adapter in `ingestion/sources/your_source.py`
3. Implement `Adapter` class extending `BaseAdapter`, `ScrapeAdapter`, or `ICSAdapter`
4. Add venue to `config/venues.yaml` if applicable

## Configuration

- `config/sources.yaml` — source definitions (URL, method, cadence)
- `config/preferences.yaml` — taste weights, vibe preferences, scoring parameters
- `config/venues.yaml` — venue metadata (neighborhood, coordinates, vibe tags)

## Scheduling

### GitHub Actions (recommended)

The included workflow (`.github/workflows/daily.yml`) runs daily:
- Ingestion at ~8:30 AM ET
- Digest generation + email + web update at ~9:00 AM ET

Add your secrets in GitHub repo Settings → Secrets:
- `TICKETMASTER_API_KEY`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- `DIGEST_RECIPIENT`
- `ANTHROPIC_API_KEY` / `LLM_PROVIDER` (optional)

### Local cron

```bash
30 8 * * * cd /path/to/ny-scout && python scripts/run_ingest.py
0  9 * * * cd /path/to/ny-scout && python scripts/run_digest.py
```

## Web Dashboard

Enable GitHub Pages (Settings → Pages → Source: main, `/docs` folder) for a live daily dashboard at `jamiepluscoffee.github.io/ny-scout/`.

## Tests

```bash
pip install pytest
pytest tests/
```
