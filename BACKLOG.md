# NY-Scout Backlog

## How this works
- `[ ]` = todo, `[~]` = in progress, `[x]` = done
- Add notes under tasks as you go — especially when something doesn't go to plan
- Notes start with `>` and explain *why* a decision was made or what went wrong

---

## Current Theme: Data Quality & Coverage
> Goal: More events, better data, fewer junk results

- [ ] Expand Ticketmaster date range beyond 14 days (for Coming Up section)
- [ ] Filter out junk events (e.g. "COMING SOON!" placeholder from Vanguard scraper)
- [ ] Fix Jazz Gallery DNS / find alternative calendar source
- [x] Playwright adapter for JS-rendered sites (Smalls, LPR, future sources)
  > New base adapter that renders pages with headless browser before parsing. Unblocks Smalls, LPR, and any discovered source that needs JS.
  > `fetch_with_playwright()` standalone function + `PlaywrightAdapter` base class in `ingestion/playwright_adapter.py`.
  > Generic adapter now supports `method: playwright` in sources.yaml — uses Playwright for fetching, then any extraction strategy (json_ld, follow_links, etc.).
  > Also added ItemList JSON-LD support and millisecond datetime parsing.
  > LPR registered via KYD Labs listing page (kydlabs.com/p/lpr/bio) — 67 events with ticket URLs. SSL issue with Python 3.9's LibreSSL bypassed by Playwright's bundled Chromium.
  > Smalls still needs investigation — their /tickets/ page doesn't show event listings even with JS rendering.
- [ ] Add price data where missing
- [ ] Detect and group long-running events (Broadway shows, museum exhibitions)
  > Same event appearing daily at one venue should show once, with a date range. Possibly a dedicated "Long Running" section.

## Up Next
> Themes to pick from when the current one is done

- **Art Taste Intelligence** — Build an art/exhibition taste profile parallel to music. Need sources for gallery/museum exhibitions, a way to express art preferences (artists, movements, mediums, galleries), and a scoring signal that ranks exhibitions by personal interest. Different category from music — can't use Last.fm for this.
- **New Event Alerts** — Detect newly announced events and surface them early so Jamie can buy tickets before they sell out. Regular scans for "what's new since last check" rather than just "what's happening this week."
- **Personal Event Index** — Transform the app from a weekly digest into a comprehensive, always-up-to-date index of everything happening in NYC, scored by personal relevance. Sortable by relevance or date. Current "picks" become a separate tab/page. This is the big vision shift.
- **Digest Polish** — Improve email formatting, add unsubscribe, mobile styling
- **More Sources** — Add Dizzy's Club, Birdland, Carnegie Hall, Le Poisson Rouge scrapers

## Icebox
> Ideas for later — not prioritized yet

- SMS digest option
- Calendar (.ics) export per event
- "Friends going" social signal

## Completed Themes

### Theme: Music Taste Intelligence ✓
- [x] Last.fm API integration (`scripts/sync_lastfm.py`)
  > Pulls all-time top artists (200+ plays) and recent listening (6 months). API key in .env, username: dustpunk.
- [x] Artist affinity scoring (log-scaled plays + recency boost)
  > Log scale prevents the long tail from being flat. Recent artists get up to +0.3 boost. 199 artists synced.
- [x] Manual overrides preserved in taste_profile.yaml
  > Entries that existed before first sync (e.g. Theo Croker: 0.9) are flagged as manual and never overwritten.
- [x] `listening_history_signal` wired up in scorer (was stubbed at 0)
  > Fuzzy-matches event performers against artist_affinities. Best match × 10 = score (0-10 points).
- [x] Smoke Jazz Club scraper + venue metadata
  > Dedicated adapter for tickets.smokejazz.com. Parses .show-card HTML, extracts dates/prices/artists.
- [x] International Anthem registered via follow_links discovery
  > 32 events from /shows page. Mix of NYC/Chicago/LA — scoring handles geo-filtering.

### Theme: Source Discovery ✓
- [x] `discovered_links.yaml` intake format
  > YAML file in config/ where Jamie adds URLs. Each entry gets a status after processing.
- [x] Link classification (event vs calendar vs unknown)
  > Cascade: JSON-LD detection → ICS feed detection → URL pattern matching. Unknown links marked "unclear" for Jamie to clarify.
- [x] JSON-LD event extraction
  > Handles MusicEvent, TheaterEvent, ExhibitionEvent, etc. Extracts title, date, venue, performers, price, ticket URL.
- [x] OpenGraph fallback extraction for single event pages
- [x] Generic config-driven adapter (`ingestion/sources/generic.py`)
  > Supports json_ld, ics, and css_selectors strategies — no custom Python needed per discovered source.
- [x] Automatic source registration in `sources.yaml`
  > Discovered sources tagged with `origin: discovered`. Calendar pages registered directly; single event pages trigger calendar URL discovery.
- [x] Taste signal updates from shared links
  > New venues get default boost (5) in preferences.yaml. New artists get default affinity (0.6) in taste_profile.yaml.
- [x] CLI integration (`--add-link URL`, `--discover`)
- [x] 29 tests covering classification, extraction, registration, and taste updates

### Theme: MVP Launch ✓
- [x] Core ingestion pipeline (6 sources)
- [x] Scoring engine (taste + convenience + social + novelty)
- [x] Email digest renderer
- [x] Web dashboard + GitHub Pages deployment
- [x] GitHub Actions daily automation
- [x] "Coming Up" section (1-6 weeks out)
  > Events 8-42 days out, top 5, no venue cap. Shows "in X weeks" lead time.
- [x] Pluggable taste scoring (signal-based architecture)
  > Refactored score_taste() into TASTE_SIGNALS list. listening_history_signal is a placeholder returning 0 for now.
- [x] Fix GitHub Pages (web/ → docs/)
  > Pages only serves from / or /docs. Renamed web/ → docs/ and updated all refs.
- [x] Fix Ticketmaster geo-filter (NYC-only via lat/long radius)
  > dmaId=324 was unreliable — returned LA events. Switched to latlong=40.7128,-74.0060 with 15mi radius.
