# PRD: Source Discovery

## Problem

Adding new event sources to NY-Scout currently requires manually writing a scraper, adding config, and deploying. This is slow and doesn't scale. Meanwhile, Jamie regularly encounters interesting events via links (Instagram, newsletters, friend recommendations) that represent exactly the kind of thing the app should surface more of.

There's no way to say "I like this — find me more like it."

## Goal

Let Jamie share a URL to an event (or venue, or artist page) and have the system:
1. Extract structured event data from the link
2. Learn from it — discover the venue's calendar, the artist's tour dates, or similar events
3. Persist what it learned as new sources that run automatically going forward

This turns every interesting link into a seed that grows the event index.

## How it fits the architecture

The existing system is already built for this:
- **Pluggable adapters** (`BaseAdapter` subclasses) with dynamic loading via `parser_module`
- **`sources.yaml`** as the registry — new sources just need a config entry + adapter
- **`EventDict`** as the universal event format all adapters produce
- **Deduplication** handles overlap when a new source covers events already ingested
- **Taste signals** can weight events from user-submitted links higher (implicit preference)

Source Discovery adds a layer *above* the existing pipeline — it generates the config and adapter code that the pipeline already knows how to run.

---

## User Flow

```
Jamie finds an interesting event
  → Shares the URL (via CLI, config file, or future chat interface)
    → System fetches the page, extracts event data
      → System identifies the venue/org behind it
        → System finds & registers a calendar source for that venue/org
          → Source runs automatically on future ingests
```

### Example scenarios

**Scenario A: Venue link**
Jamie shares `https://www.barbesconcerts.com/calendar`
→ System scrapes the page, finds it's a venue calendar
→ Registers a new scraper for Barbès
→ Future ingests pull all Barbès events automatically

**Scenario B: Single event link**
Jamie shares `https://www.eventbrite.com/e/some-jazz-event-123`
→ System extracts the event (artist, venue, date, price)
→ Stores it as a one-off event
→ Also discovers the venue → checks if it has a scrapeable calendar
→ If yes, registers the venue as a new source

**Scenario C: Artist page**
Jamie shares `https://www.songkick.com/artists/brad-mehldau`
→ System extracts upcoming tour dates in NYC
→ Registers Songkick artist tracking as a source
→ Also updates `taste_profile.yaml` with artist affinity boost

---

## Design

### 1. Link intake: `config/discovered_links.yaml`

A simple list Jamie can append to. Each entry is a URL plus optional context:

```yaml
links:
  - url: "https://www.barbesconcerts.com/calendar"
    note: "Great bar in Park Slope with eclectic live music"
    added: 2026-02-15

  - url: "https://www.eventbrite.com/e/some-jazz-event-123"
    note: "Friend recommended this"
    added: 2026-02-15
```

**Why a YAML file**: Keeps the pattern consistent (all config is YAML). No new infrastructure. Easy to edit manually or programmatically. Later we can add a CLI command or web form that appends to this file.

### 2. Link processor: `ingestion/discovery.py`

New module that processes links from `discovered_links.yaml`. Responsibilities:

1. **Fetch & classify** the URL:
   - Is it a single event page? → Extract event, look for venue calendar
   - Is it a venue/calendar page? → Register as a recurring source
   - Is it an artist page? → Extract tour dates, register artist tracking
   - Unknown? → Log it, ask Jamie to clarify what the link is for and retry

2. **Extract event data** using a general-purpose strategy:
   - Try JSON-LD (`@type: Event/MusicEvent`) first — many sites embed this
   - Try OpenGraph / meta tags as fallback
   - Try HTML heuristics (date patterns, venue names, price patterns)
   - For known platforms (Eventbrite, Dice, Songkick), use platform-specific extraction

3. **Discover the parent source**:
   - From a single event URL, derive the venue/org calendar URL
   - Check if we already have this source in `sources.yaml`
   - If not, attempt to generate an adapter config

4. **Register new sources**:
   - Append to `sources.yaml` with `method: discovered` and `enabled: true`
   - For simple cases (JSON-LD, ICS feeds), use existing adapter base classes
   - For HTML scraping, generate a config-driven generic scraper (see below)
   - Mark the link as `processed: true` in `discovered_links.yaml`

### 3. Generic scraper: `ingestion/sources/generic.py`

A config-driven adapter that handles the common case without custom code. Takes CSS selectors or extraction rules from the source config:

```yaml
# Auto-generated entry in sources.yaml
- name: barbes
  url: "https://www.barbesconcerts.com/calendar"
  category: music
  method: scrape
  parser_module: ingestion.sources.generic
  cadence: daily
  enabled: true
  origin: discovered  # Marks this as auto-discovered
  discovered_from: "https://www.barbesconcerts.com/calendar"
  extraction:
    strategy: json_ld        # or: css_selectors, ics, platform_api
    event_type: MusicEvent
    # For css_selectors strategy:
    # container: ".event-listing"
    # title: "h3"
    # date: ".event-date"
    # venue: ".venue-name"
```

The generic adapter tries strategies in order:
1. **json_ld**: Look for Schema.org Event markup (highest confidence)
2. **ics**: Look for `.ics` feed link on the page
3. **css_selectors**: Use configured selectors (populated during discovery)
4. **heuristic**: Fall back to date/time/title pattern extraction

This avoids generating Python code for every new source. Most venue calendars can be handled by config alone.

### 4. Taste signal from shared links

When Jamie shares a link, that's an implicit taste signal. The discovery processor should:

- Extract artist names → boost in `taste_profile.yaml`
- Extract venue → add/boost in `preferences.yaml` `venue_boost`
- Extract category/genre → note for future category weight tuning

This is lightweight: just append to existing config files. The scoring engine already reads them.

### 5. CLI integration

Extend `scripts/run_ingest.py` with a discovery step:

```bash
# Process all pending discovered links
python3 scripts/run_ingest.py --discover

# Add a link and process it immediately
python3 scripts/run_ingest.py --add-link "https://www.barbesconcerts.com/calendar"

# Normal ingest (includes discovered sources automatically since they're in sources.yaml)
python3 scripts/run_ingest.py
```

### 6. Processing pipeline

```
run_ingest.py --discover
  │
  ├─ Load discovered_links.yaml
  ├─ Filter to unprocessed links
  │
  ├─ For each link:
  │   ├─ Fetch page
  │   ├─ Classify (event / calendar / artist / unknown)
  │   ├─ Extract event data → store as Event (source: "discovered")
  │   ├─ Discover parent source (venue calendar URL)
  │   ├─ If new source found:
  │   │   ├─ Probe it (can we scrape it? JSON-LD? ICS?)
  │   │   ├─ Pick best extraction strategy
  │   │   ├─ Add to sources.yaml with extraction config
  │   │   └─ Run initial ingest of the new source
  │   ├─ Update taste signals (artist boost, venue boost)
  │   └─ Mark link as processed
  │
  └─ Summary: N links processed, M new sources registered, K events found
```

---

## Scope for v1

Keep it focused. v1 handles the most common case well, and we iterate from there.

### In scope
- `discovered_links.yaml` intake format
- Link fetching and classification (event vs calendar vs unknown)
- JSON-LD extraction (covers Eventbrite, many venue sites, Songkick)
- ICS feed detection and registration
- Generic adapter that reads extraction config from `sources.yaml`
- Registering new sources in `sources.yaml` (with `origin: discovered` flag)
- CLI: `--add-link` and `--discover` flags
- Taste signal updates from shared links (venue boost, artist affinity)
- Basic logging and error handling

### Out of scope (v2+)
- Artist page parsing / tour date tracking
- Platform-specific extractors (Dice, DICE, Resident Advisor, etc.)
- CSS selector auto-detection (manual config for HTML-only sites)
- Web UI for submitting links
- Automatic periodic re-probing of discovered sources
- LLM-assisted page understanding (using Claude to parse unstructured pages)

---

## Files to create/modify

| File | Action | Purpose |
|------|--------|---------|
| `config/discovered_links.yaml` | Create | Link intake file |
| `ingestion/discovery.py` | Create | Link processor: fetch, classify, extract, register |
| `ingestion/sources/generic.py` | Create | Config-driven generic adapter |
| `ingestion/runner.py` | Modify | Add `run_discovery()` entry point |
| `scripts/run_ingest.py` | Modify | Add `--discover` and `--add-link` flags |
| `config/sources.yaml` | Modified at runtime | New sources appended by discovery |
| `config/taste_profile.yaml` | Modified at runtime | Artist affinities from shared links |
| `config/preferences.yaml` | Modified at runtime | Venue boosts from shared links |
| `tests/test_discovery.py` | Create | Tests for link classification and extraction |

---

## Open questions

1. **Should discovered sources auto-enable?** Probably yes for v1 — if Jamie shared the link, they want the events. Could add a `--dry-run` discovery mode that shows what *would* be registered.

2. **How to handle sites that need JavaScript?** For v1, skip them and log a warning (same as current Smalls behavior). v2 could add Playwright support via the existing `method: playwright` config option.

3. **Should we validate new sources before registering?** Yes — probe the calendar URL, confirm we can extract at least 1 event. If not, store the link but don't register a source. Log the failure.

4. **Rate limiting on discovery?** Add a 2-second delay between fetches during discovery to be polite. The normal ingest already has retry/backoff.
