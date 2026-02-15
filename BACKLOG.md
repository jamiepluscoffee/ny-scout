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
- [ ] Fix Smalls scraper (needs JavaScript rendering)
- [ ] Add price data where missing

## Up Next
> Themes to pick from when the current one is done

- **Taste Intelligence** — Wire up Last.fm/Spotify listening history to taste scoring via `config/taste_profile.yaml` and `listening_history_signal`
- **Digest Polish** — Improve email formatting, add unsubscribe, mobile styling
- **More Sources** — Add Dizzy's Club, Birdland, Carnegie Hall, Le Poisson Rouge scrapers

## Icebox
> Ideas for later — not prioritized yet

- Interactive web dashboard (filters, search, save events)
- SMS digest option
- Calendar (.ics) export per event
- "Friends going" social signal

## Completed Themes

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
