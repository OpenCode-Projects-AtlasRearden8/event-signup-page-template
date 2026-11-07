#!/usr/bin/env python3
"""Build script for the Event Signup Page Template.

Read a small JSON file that describes one event (book launch, workshop, or
club night) and render a static, zero-backend signup page plus a fallback
calendar (.ics) file:

    python3 build.py                     # build into the repo root
    python3 build.py --out dist/         # build somewhere else
    python3 build.py --data other.json   # use a different event file
    python3 build.py --check             # validate the event file only

Everything here is plain Python standard library: no dependencies, no
backend, no network calls, no secrets. The output folder can be dropped
straight onto GitHub Pages.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "template" / "index.html"
DEFAULT_DATA = ROOT / "data" / "event.json"
ASSETS_DIR = ROOT / "assets"

PRODID = "-//Asdale Dynamics, LLC//Event Signup Page Template//EN"
PLACEHOLDER_IMG = "assets/placeholder.svg"
DEFAULT_ICS_HOURS = 2

MONTHS = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]
WEEKDAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?$")


class BuildError(Exception):
    """Raised for anything wrong with the event data or template."""


# --------------------------------------------------------------------------
# Loading + validation
# --------------------------------------------------------------------------

def load_event(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError as exc:
        raise BuildError(f"event file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BuildError(
            f"{path.name} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}"
        ) from exc
    if not isinstance(data, dict):
        raise BuildError(f"{path.name} must contain a JSON object at the top level")
    # Convenience: fields may live at the top level or inside an "event" block.
    nested = data.pop("event", None)
    if isinstance(nested, dict):
        for key, value in nested.items():
            data.setdefault(key, value)
    return data


def _need(event: dict, key: str, errors: list[str]) -> str:
    value = event.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"event.{key} is required")
        return ""
    return value.strip()


def validate_event(event: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(event, dict):
        return ["top-level JSON must be an object, not a list"]

    _need(event, "kind", errors)
    _need(event, "title", errors)
    if not isinstance(event.get("description"), str) or not event.get("description", "").strip():
        errors.append("event.description is required")

    contact = event.get("contact", {})
    if not isinstance(contact, dict):
        errors.append("contact must be an object")
        contact = {}
    email = str(contact.get("email", ""))
    if not email:
        errors.append("contact.email is required (use a placeholder like hello@example.com)")
    elif not EMAIL_RE.match(email):
        errors.append(f"contact.email does not look like an email address: {email!r}")

    when = event.get("when", {})
    if not isinstance(when, dict):
        errors.append("when must be an object")
        when = {}
    start_raw = when.get("starts")
    if not start_raw:
        errors.append("when.starts is required (ISO 8601, e.g. 2026-12-05T18:00:00)")
    elif not (isinstance(start_raw, str) and ISO_RE.match(start_raw)):
        errors.append(f"when.starts must look like 2026-12-05T18:00:00, got {start_raw!r}")
    end_raw = when.get("ends")
    if end_raw and not re.search(r"\d{2}:\d{2}", str(end_raw)):
        errors.append(f"when.ends must look like 2026-12-05T20:00:00, got {end_raw!r}")
    if not when.get("timezone"):
        errors.append("when.timezone is required (IANA name, e.g. America/Indiana/Indianapolis)")

    where = event.get("where", {})
    if not isinstance(where, dict) or not str(where.get("venue", "")).strip():
        errors.append("where.venue is required")

    if errors:
        raise BuildError("event file has problems:\n  - " + "\n  - ".join(errors))
    return []


# --------------------------------------------------------------------------
# Date/time helpers
# --------------------------------------------------------------------------

@dataclass
class When:
    start: datetime
    end: datetime
    date_display: str
    time_display: str
    ics_start: str
    ics_end: str


def _fmt_ampm(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d} {'PM' if dt.hour >= 12 else 'AM'}"


def _long_date(dt: datetime) -> str:
    return f"{WEEKDAYS[dt.weekday()]}, {MONTHS[dt.month - 1]} {dt.day}, {dt.year}"


def _short_date(dt: datetime) -> str:
    return f"{WEEKDAYS[dt.weekday()][:3]}, {MONTHS[dt.month - 1][:3]} {dt.day}"


def _ics_stamp(dt: datetime) -> str:
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ")


def resolve_when(event: dict) -> When:
    when = event.get("when", {})
    tz = ZoneInfo(str(when.get("timezone")))
    start = datetime.fromisoformat(str(when["starts"])).replace(tzinfo=tz)
    if when.get("ends"):
        end = datetime.fromisoformat(str(when["ends"])).replace(tzinfo=tz)
        if end <= start:
            raise BuildError("when.ends must be after when.starts")
    else:
        end = start + timedelta(hours=DEFAULT_ICS_HOURS)

    tz_name = start.tzname() or when["timezone"]
    if end.date() == start.date():
        date_display = _long_date(start)
        time_display = f"{_fmt_ampm(start)} \u2013 {_fmt_ampm(end)} ({tz_name})"
    else:
        date_display = f"{_short_date(start)} \u2013 {_short_date(end)}, {end.year}"
        time_display = f"{_fmt_ampm(start)} \u2013 {_fmt_ampm(end)} ({tz_name})"
    return When(start, end, date_display, time_display, _ics_stamp(start), _ics_stamp(end))


# --------------------------------------------------------------------------
# Content builders
# --------------------------------------------------------------------------

def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug or "event"


def venue_lines(event: dict) -> list[tuple[str, str]]:
    where = event.get("where", {})
    lines: list[tuple[str, str]] = [("venue", str(where.get("venue", "")).strip())]
    address = where.get("address_lines")
    if isinstance(address, str) and address.strip():
        lines.append(("address", address.strip().replace("\n", ", ")))
    elif isinstance(address, list):
        joined = ", ".join(str(part).strip() for part in address if str(part).strip())
        if joined:
            lines.append(("address", joined))
    if str(where.get("getting_there", "")).strip():
        lines.append(("getting-there", str(where["getting_there"]).strip()))
    return lines


def build_cards(event: dict) -> str:
    when = resolve_when(event)
    where = event.get("where", {})
    cards: list[str] = []

    cards.append(
        f'<li class="card"><h2>Date</h2><p class="card-value">{html_escape_text(when.date_display)}</p></li>'
    )
    cards.append(
        f'<li class="card"><h2>Time</h2><p class="card-value">{html_escape_text(when.time_display)}</p></li>'
    )

    loc_html = "<br>".join(
        html_escape_text(text) for _, text in venue_lines(event)
    )
    map_url = str(where.get("map_url", "")).strip()
    if map_url.startswith("http://") or map_url.startswith("https://"):
        loc_html += (
            f'<br><a class="card-link" href="{html_escape_attr(map_url)}">'
            f"Open map<span class=\"visually-hidden\"> (opens a map in a new tab)</span></a>"
        )
    cards.append(f'<li class="card"><h2>Location</h2><p class="card-value">{loc_html}</p></li>')

    if event.get("cost"):
        cards.append(
            f'<li class="card"><h2>Cost</h2><p class="card-value">{html_escape_text(str(event["cost"]))}</p></li>'
        )

    cards_html = "\n      ".join(cards)
    return f'    <ul class="card-list">\n      {cards_html}\n    </ul>'


def build_rsvp_text(event: dict) -> str:
    when = resolve_when(event)
    lines = [f"RSVP \u2013 {str(event['title']).strip()}"]
    lines.append(f"When: {when.date_display}, {when.time_display}")
    where_line = " \u2014 ".join(text for _, text in venue_lines(event))
    lines.append(f"Where: {where_line}")
    lines.append("")
    lines.append("Name: ")
    lines.append("Email: ")
    lines.append("Number of guests: ")
    lines.append("Access needs (optional): ")
    return "\n".join(lines)


def build_mailto(event: dict, subject_prefix: str, body: str | None = None) -> str:
    contact = event.get("contact", {})
    email = str(contact.get("email", "")).strip()
    subject = f"{subject_prefix} {str(event['title']).strip()}"[0:78]
    if body is None:
        body = build_rsvp_text(event)
    query = urllib.parse.urlencode({"subject": subject, "body": body}, quote_via=urllib.parse.quote)
    return f"mailto:{urllib.parse.quote(email)}?{query}"


def html_escape_text(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def html_escape_attr(text: str) -> str:
    return html_escape_text(text).replace('"', "&quot;")


def render_description(event: dict) -> str:
    return "<br>".join(
        html_escape_text(line) for line in str(event.get("description", "")).split("\n") if line.strip()
    )


def build_rsvp_section(event: dict) -> str:
    when = resolve_when(event)
    seats = str(event.get("capacity_note", "")).strip()
    seats_html = ""
    if seats:
        seats_html = f'<p class="rsvp-seats">{html_escape_text(seats)}</p>'
    mailto = build_mailto(event, "RSVP \u2013")
    ics_href = f"{slugify(event['title'])}.ics"
    return (
        '  <section id="rsvp" class="section rsvp" aria-labelledby="rsvp-title">\n'
        '    <h2 id="rsvp-title">Save your seat</h2>\n'
        f'    <p>Running a little late or want to bring a friend? Just let us know by '
        f'<strong>{html_escape_text(when.date_display)}</strong> if you can.</p>\n'
        f'{seats_html}\n'
        '    <div class="rsvp-actions">\n'
        f'      <a class="btn btn-primary" href="{html_escape_attr(mailto)}">RSVP by email</a>\n'
        f'      <a class="btn btn-ghost calendar-btn" id="ics-download" href="{html_escape_attr(ics_href)}" download>Download calendar event (.ics)</a>\n'
        '      <button class="btn btn-ghost copy-btn" id="copy-rsvp" type="button">Copy RSVP text</button>\n'
        '      <p class="copy-status" id="copy-status" role="status"></p>\n'
        f'    </div>\n'
        '    <p class="rsvp-note">The email button opens your own mail app \u2014 nothing is tracked here. '
        'No account needed. The calendar button adds the event to any calendar app, '
        'and the <strong>Copy RSVP text</strong> button copies a short form you can '
        'paste into any email, text, or note.</p>\n'
        '  </section>'
    )


def build_waiting_list(event: dict) -> str:
    waiting = event.get("waiting_list", {})
    if not isinstance(waiting, dict) or not waiting.get("enabled"):
        return ""
    note = str(waiting.get("note", "")).strip() or (
        "The event might be full when you read this. Email us anyway: no-shows are rare, "
        "but they happen, and we open seats in the order the emails arrive."
    )
    mailto = build_mailto(event, "Waiting list \u2013")
    return (
        '  <section id="waiting-list" class="section notice" aria-labelledby="waiting-list-title">\n'
        '    <h2 id="waiting-list-title">Waiting list</h2>\n'
        f'    <p>{html_escape_text(note)}</p>\n'
        f'    <p><a class="btn btn-ghost" href="{html_escape_attr(mailto)}">Join the waiting list</a></p>\n'
        '  </section>'
    )


def build_accessibility(event: dict) -> str:
    items_raw = event.get("accessibility_notes", [])
    if not isinstance(items_raw, list):
        items_raw = []
    items = [str(x).strip() for x in items_raw if str(x).strip()]
    if not items:
        items = ["Tell us what you need and we will do our best to make it work."]
    list_html = "\n".join(f"      <li>{html_escape_text(item)}</li>" for item in items)
    mailto = build_mailto(
        event,
        "Accessibility \u2013",
        body=(
            "Hello!\n\n"
            f"Event: {str(event['title']).strip()}\n"
            "My name: \n"
            "My access needs (optional): \n\n"
            "Thank you!"
        ),
    )
    return (
        '  <section id="accessibility" class="section" aria-labelledby="accessibility-title">\n'
        '    <h2 id="accessibility-title">Accessibility notes</h2>\n'
        f'    <p>We would rather help early than scramble later \u2014 '
        f'<a href="{html_escape_attr(mailto)}">email us your access needs</a> '
        f'any time before the event. Nothing is too small to ask.</p>\n'
        f'    <ul class="notes-list">\n{list_html}\n    </ul>\n'
        '  </section>'
    )


def build_gallery(event: dict) -> str:
    slots = event.get("gallery_slots", [])
    if not isinstance(slots, list):
        slots = []
    slots = slots[:6]
    figures: list[str] = []
    for index, slot in enumerate(slots, start=1):
        if isinstance(slot, dict):
            src = str(slot.get("src", "")).strip() or PLACEHOLDER_IMG
            alt = str(slot.get("alt", "")).strip() or f"Placeholder photo slot {index} \u2014 add your own event photo."
            caption = str(slot.get("caption", "")).strip() or f"Photo {index} \u2014 replace this placeholder."
        else:
            src, alt, caption = PLACEHOLDER_IMG, f"Placeholder photo slot {index}.", f"Photo {index}"
        figures.append(
            '    <figure class="gallery-slot">\n'
            f'      <img src="{html_escape_attr(src)}" alt="{html_escape_attr(alt)}" width="480" height="320" loading="lazy">\n'
            f'      <figcaption>{html_escape_text(caption)}</figcaption>\n'
            '    </figure>'
        )
    if not figures:
        figures.append(
            '    <figure class="gallery-slot">\n'
            f'      <img src="{PLACEHOLDER_IMG}" alt="Empty gallery slot ready for an event photo." width="480" height="320" loading="lazy">\n'
            '      <figcaption>Add up to three photos in data/event.json \u2192 gallery_slots.</figcaption>\n'
            '    </figure>'
        )
    figures_html = "\n".join(figures)
    return (
        '  <section id="gallery" class="section" aria-labelledby="gallery-title">\n'
        '    <h2 id="gallery-title">What the last one looked like</h2>\n'
        '    <p>\n'
        '      No photos here yet. Drop real (candid, friendly) photos from your past events\n'
        '      into the <a href="gallery/">gallery folder</a> and point to them in\n'
        '      <code>data/event.json</code> under <code>gallery_slots</code>.\n'
        '    </p>\n'
        f'    <div class="gallery-grid">\n{figures_html}\n    </div>\n'
        '  </section>'
    )


def build_tagline(event: dict) -> str:
    tagline = str(event.get("tagline", "")).strip()
    if not tagline:
        return ""
    return f'<p class="tagline">{html_escape_text(tagline)}</p>'


def build_footer(event: dict) -> str:
    organizer = str(event.get("contact", {}).get("organizer", "")).strip()
    organizer_html = ""
    if organizer:
        organizer_html = f"Run by {html_escape_text(organizer)}. "
    return (
        f'    <p>{organizer_html}This page is static: no cookies, no logins, no trackers.</p>\n'
        '    <p>\n'
        '      Made with the event-signup-page-template \u00b7 MIT License \u00b7 \u00a9 2026 '
        '<span class="footer-org">Asdale Dynamics, LLC</span>\n'
        '    </p>'
    )


def event_payload(event: dict) -> dict:
    when = resolve_when(event)
    return {
        "title": str(event.get("title", "")),
        "rsvp_text": build_rsvp_text(event),
        "needs_js": True,
        "when": {
            "starts": when.ics_start,
            "ends": when.ics_end,
        },
    }


def build_ics(event: dict) -> str:
    when = resolve_when(event)
    slug = slugify(event["title"])
    summary = str(event["title"]).strip().replace("\n", " ")
    loc_text = ", ".join(text for _, text in venue_lines(event))
    desc = build_rsvp_text(event).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{slug}-2026@asdale-dynamics",
        f"DTSTAMP:{_ics_stamp(datetime.now(timezone.utc))}",
        f"DTSTART:{when.ics_start}",
        f"DTEND:{when.ics_end}",
        f"SUMMARY:{summary}",
        f"LOCATION:{loc_text}".replace("\n", " "),
        f"DESCRIPTION:{desc}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "TRIGGER:-PT60M",
        f"DESCRIPTION:{summary} starts in one hour",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render_page(event: dict) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    when = resolve_when(event)
    payload = event_payload(event)
    json_blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    ics_slug = slugify(event["title"])

    replacements = {
        "{{PAGE_TITLE}}": f"RSVP \u2014 {str(event['title']).strip()}",
        "{{META_DESCRIPTION}}": html_escape_text(
            f"RSVP for {str(event['title']).strip()} \u2014 {when.date_display}, "
            f"{when.time_display}. Save a seat in one click."
        ),
        "{{KICKER}}": html_escape_text(str(event["kind"]).strip() + " \u00b7 RSVP page"),
        "{{TITLE}}": html_escape_text(str(event["title"]).strip()),
        "{{TAGLINE_HTML}}": build_tagline(event),
        "{{DESCRIPTION_HTML}}": render_description(event),
        "{{CARDS_HTML}}": build_cards(event),
        "{{RSVP_SECTION_HTML}}": build_rsvp_section(event),
        "{{WAITING_LIST_HTML}}": build_waiting_list(event),
        "{{ACCESSIBILITY_HTML}}": build_accessibility(event),
        "{{GALLERY_HTML}}": build_gallery(event),
        "{{FOOTER_HTML}}": build_footer(event),
        "{{EVENT_JSON}}": json_blob,
        "{{ICS_HREF}}": f"{ics_slug}.ics",
        "{{ORGANIZER}}": html_escape_text(str(event.get("contact", {}).get("organizer", ""))),
    }

    page_text = template
    for key, value in replacements.items():
        page_text = page_text.replace(key, value)

    leftovers = re.findall(r"\{\{[A-Z_]+\}\}", page_text)
    if leftovers:
        raise BuildError(f"template still has unfilled tokens: {', '.join(sorted(set(leftovers)))}")
    return page_text


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="event JSON file (default: data/event.json)")
    parser.add_argument("--out", type=Path, default=Path("."), help="output directory (default: repo root)")
    parser.add_argument("--check", action="store_true", help="validate the event file and exit without writing files")
    args = parser.parse_args(argv)

    try:
        event = load_event(args.data)
        validate_event(event)
        resolve_when(event)
        if args.check:
            print(f"OK: {args.data.name} looks good.")
            return 0

        out_dir = args.out.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = out_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        (out_dir / "index.html").write_text(render_page(event), encoding="utf-8")
        ics_name = f"{slugify(event['title'])}.ics"
        (out_dir / ics_name).write_text(build_ics(event), encoding="utf-8")
        (out_dir / ".nojekyll").write_text("", encoding="utf-8")

        for src in ASSETS_DIR.iterdir():
            if src.is_file():
                (assets_dir / src.name).write_bytes(src.read_bytes())
        print(f"Built: {out_dir / 'index.html'}")
        print(f"Built: {out_dir / ics_name}")
        print("Next: add photos to gallery/ and edit data/event.json.")
        return 0
    except (BuildError, OSError, KeyError) as exc:
        if isinstance(exc, KeyError):
            print(f"Build failed: missing required field {exc}", file=sys.stderr)
        else:
            print(f"Build failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
