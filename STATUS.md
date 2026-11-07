# STATUS — event-signup-page-template

**Date:** 2026-11-07 · **Owner:** Asdale Dynamics, LLC

## What was built

A copy-ready, data-driven **static event signup page template** for book
launches, workshops, and club nights. Zero backend, zero dependencies,
GitHub Pages ready.

- **`build.py`** — the single Python build script (stdlib only, Python 3.10+).
  Reads `data/event.json`, validates it with plain-English errors, and
  renders `index.html` + a fallback calendar `.ics` file + `.nojekyll` +
  copies `assets/`. Flags: `--data`, `--out`, `--check`.
- **`data/event.json`** — fully-documented sample event ("The Massive AI
  Manual: Launch Night", book-launch flavor) with workshop/club-night notes
  in the README; swappable for any event of the same shape.
- **`template/index.html`** — semantic template (skip link, ARIA labels,
  focus-visible, reduced-motion) with `{{TOKENS}}` filled by the build.
- **`assets/`** — `style.css` (warm, contrast-checked, no external fonts/CDNs),
  `app.js` (copy-RSVP-to-clipboard with legacy fallback, no network calls),
  `favicon.svg`, `placeholder.svg`.
- **`gallery/README.txt`** — where real past-event photos go (placeholder
  slots render until filled).
- Every required feature is present and wired: **RSVP copy button + email
  link, date/time/location cards (+ optional cost card), accessibility notes
  block with access-needs mailto, waiting-list note + button (toggleable),
  past-event gallery slots, fallback ICS download link, no-JS paths for
  every action.**

## How to run it

```bash
python3 build.py                        # build into this folder (updates committed output)
python3 build.py --check                # validate data/event.json only
python3 build.py --out dist/            # build anywhere else
python3 -m unittest discover tests      # full test suite (verbose: add -v)
python3 -m http.server 8000             # preview at localhost:8000
```

GitHub Pages: commit, then Settings → Pages → "Deploy from a branch"
(`main`, `/root`). Built output is committed, so this works immediately.

## Verification results (2026-11-07)

- `python3 build.py --check` → `OK: event.json looks good.`
- `python3 build.py` → built `index.html` +
  `the-massive-ai-manual-launch-night.ics` (no errors, no leftover
  `{{TOKENS}}`).
- `python3 -m unittest discover tests` → **19 tests, all passing.** Coverage
  includes: build writes expected files; `--check` fails on invalid data
  (missing email/title); rendered structure assertions for RSVP copy button
  (`#copy-rsvp`), mailto RSVP + waiting-list links, Date/Time/Location cards,
  accessibility block, 3 gallery slots with alt text, waiting-list section,
  `.ics` link on the page; ICS envelope mastery (VCALENDAR/VEVENT pairs,
  UTC `DTSTART`/`DTEND`, SUMMARY/LOCATION/UID/DESCRIPTION, VALARM); no
  secrets/personal data in output; no external CDN requests; no `<form>`.
- Smoke test: `python3 -m http.server` — index, .ics, CSS, JS all served
  HTTP 200.
- Generalization smoke: a workshop-flavored variant JSON (waiting list
  disabled, different title) built cleanly with slugged ICS name.
- Test-first catches that were fixed during development: the .ics file was
  initially built but never linked (tests caught it; "Download calendar
  event" button added to the RSVP row).

## Known gaps

- No screenshots/visual snapshots in tests — structure-validated via
  HTMLParser, not pixel-tested.
- Multi-day events are supported for ICS/date logic with a coarse
  "Sat–Sun" display; suspicious edge cases (DST transitions, times spanning
  midnight) aren't specially tested.
- Gallery images are placeholders by default; automated checks confirm
  alt text but cannot confirm the photos themselves.
- Waiting-list handling is by email only (no form, by design — zero
  backend).
- Timezone abbreviations come from `zoneinfo` (`tzname()`), which shows
  standard abbreviations like "EST"; ambiguous POSIX-style zones are not
  handled specially.
- Sample contact uses the reserved `asdale.example.com` domain — swap in a
  real RSVP inbox before publishing (the build's `--check` accepts example
  domains, so forgetting will not error; it is on the publisher).
