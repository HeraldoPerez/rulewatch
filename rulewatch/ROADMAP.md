# Roadmap

Rough plan. Estimates are my guesses and will change.

## v0.1.0: first usable version
- [x] Fetch documents for a watch from the Federal Register API, following every result page
- [x] watches.yml config + validation that lists every problem at once
- [x] Save each watch's results as JSON, with comment deadlines and regulations.gov links
- [ ] Check agency slugs against the Federal Register agency list, and suggest the closest match for a typo (~2h)
- [ ] Retry once when the API times out or returns a 5xx (~1h)
- [ ] RSS feed per watch (~3h)
- [ ] React (Vite) results page: one section per watch, newest first, open comment periods highlighted (~5h)
- [ ] Daily run on GitHub Actions + deploy to GitHub Pages, then tag v0.1.0 (~3h)

## v0.2.0
- [ ] Comment-deadline calendar export (.ics): one event per open comment period, linking to regulations.gov (~5h)
- [ ] Upcoming deadlines on the results page (~2h)
- [ ] Weekly digest page (~5h)
- [ ] Keep documents older than the fetch window, so feeds don't drop items between runs (~2h)

## Later
- [ ] Show what changed between a proposed rule and the final rule, matched by RIN (~8h)
- [ ] Docs: how to add your own watch, with ready-made watches for common agencies (~2h)
- [ ] Tests for the feed builder and calendar export, and CI on every push (~3h)
