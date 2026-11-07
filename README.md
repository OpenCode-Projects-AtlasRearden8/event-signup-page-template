# Event Signup Page Template

A copy-ready **static template for event signup pages** — book launches,
workshops, and club nights. One JSON file, one build script, and the output
drops straight onto GitHub Pages. **Zero backend:** no accounts, no forms, no
trackers, no database, nothing to host beyond a free Pages site.

Built and maintained by **Asdale Dynamics, LLC** (Dylan Asdale's
beginner-friendly AI company). This template follows the same plain-English
style as everything else we publish: warm, clear, step by step, never
condescending.

## What's in the page

| Feature | Where it lives | Works without JavaScript? |
| --- | --- | --- |
| RSVP email link (pre-filled subject + copy-paste form) | button in the "Save your seat" section | Yes |
| RSVP copy button (copies the RSVP text to the clipboard) | hidden until JS loads, then shown | N/A (email button replaces it) |
| Date / Time / Location cards (plus an optional Cost card) | cards grid | Yes |
| Accessibility notes block (with its own access-needs email link) | "Accessibility notes" section | Yes |
| Waiting-list note + button (toggle it in the data file) | notices section | Yes |
| Past-event gallery slots (3 by default, up to 6) | "What the last one looked like" | Yes |
| Fallback ICS download (works in any calendar app) | button next to RSVP | Yes |
| Skip link, alt text, focus styles, reduced-motion support | page-wide | Yes |

## Quick start

```bash
python3 build.py                 # builds index.html + .ics + assets into this folder
python3 build.py --check         # validate data/event.json without writing files
python3 build.py --out dist/     # build somewhere else (e.g. into a Pages repo)
python3 -m unittest discover tests
```

Requires only Python 3.10+ (standard library only — no pip installs).

## Customize your event

Edit `data/event.json` — every field has a friendly example already filled in
from the sample event ("The Massive AI Manual: Launch Night"):

- `kind`, `title`, `tagline`, `description` — the page header
- `when` — ISO start/end times plus an IANA timezone (e.g.
  `America/Indiana/Indianapolis`); human-readable date/time text is generated
  for you and used in the cards and the .ics file
- `where` — venue, address lines, optional map link and transit note
- `contact` — organizer name and the RSVP email (the only address visitors
  will see; use a domain you control, never a personal inbox)
- `capacity_note` — the "seats are limited to…" line
- `cost` — adds a fourth card if present
- `accessibility_notes` — bullet items in the accessibility block
- `waiting_list.enabled` — turn the waiting-list section on or off
- `gallery_slots` \u2013 up to 6 entries with `src`, `alt`, `caption`; drop real
  photos into the `gallery/` folder

Rebuild and done. If a required field is missing or malformed, the build
fails with a plain-English error list instead of a stack trace.

## Put it on GitHub Pages (3 steps)

1. Create a public repository, copy these files in, commit.
2. In **Settings → Pages**, choose "Deploy from a branch" and pick `main` /
   `/ (root)`.
3. Visit `https://<your-username>.github.io/<repo-name>/`.

There is nothing else to configure: the built output is bog-standard static
files (`.nojekyll` is included). Set `contact.email` in your data file so
RSVPs land somewhere you actually monitor.

## How this differs from our other templates

- **book-launch-countdown-page-template** is about the *drive-up to launch* —
  a countdown clock, not RSVP collection.
- **printable-flyer-starter-template** is a *pre-event print piece* — a
  flyer, not a page.
- **This template** is the *signup destination itself*: the QR code or post
  link can point here, and it handles the RSVP, accessibility, waiting list,
  and calendar questions in one place.

## Accessibility first

This is a template for real humans, including folks running on low energy:
semantic headings, a skip link, focus-visible outlines, alt text on every
image, `prefers-reduced-motion` support, and no-JS paths for every action
(email link, .ics download, printable page). Contrast-checked palette.

## Privacy & safety

No cookies, no analytics, no forms, no personal data collected by the page.
The sample data intentionally uses `asdale.example.com` (a reserved example
domain) and a fictional venue — swap in your own details before publishing.
Never commit real attendee information, secrets, or API keys.

## License

MIT \u00b7 Copyright (c) 2026 Asdale Dynamics, LLC. See `LICENSE`. You are
welcome to adapt it for your own events and projects.
