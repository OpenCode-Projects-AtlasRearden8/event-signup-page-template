"""Tests for the Event Signup Page Template.

These run the real build script (as a subprocess) against the sample data
and validate the rendered signup structure: RSVP copy button, email link,
date/time/location cards, accessibility block, gallery slots, waiting-list
note, and the fallback ICS download.

Run with:
    python3 -m unittest discover tests -v
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build.py"
SAMPLE_DATA = ROOT / "data" / "event.json"


def run_build(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILD), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# HTML inspection helpers
# ---------------------------------------------------------------------------

class PageInspector(HTMLParser):
    """Collects enough structure from the rendered page to assert against."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict]] = []
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.button_ids: set[str] = set()
        self.section_ids: set[str] = set()
        self.link_rels: set[str] = set()
        self._section_depth = 0
        self.events: list[str] = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        self.tags.append((tag, attr))
        self.hrefs.append(attr.get("href") or "")
        if attr.get("rel") and "link" == tag:
            self.link_rels.update(attr["rel"].split())
        element_id = attr.get("id")
        if element_id:
            self.ids.add(element_id)
            if tag == "button":
                self.button_ids.add(element_id)
            if tag == "section":
                self.section_ids.add(element_id)

    def tag_exists(self, tag: str, **match: str) -> bool:
        for seen_tag, attrs in self.tags:
            if seen_tag != tag:
                continue
            ok = True
            for key, expected in match.items():
                attr_name = "class" if key == "class_" else key
                actual = attrs.get(attr_name, "")
                if attr_name == "class":
                    ok = ok and expected in actual.split()
                else:
                    ok = ok and expected == actual
                if not ok:
                    break
            if ok:
                return True
        return False


def parse_page(html_text: str) -> PageInspector:
    parser = PageInspector()
    parser.feed(html_text)
    parser.close()
    return parser


class OutputBuild:
    """Build once into a temp dir and reuse it across several cases."""

    def __init__(self) -> None:
        result = run_build("--out", tempfile.mkdtemp(prefix="signup-out-"))
        self.result = result
        if result.returncode == 0:
            built_line = next(
                line for line in result.stdout.splitlines() if line.startswith("Built: ")
            )
            self.out_dir = Path(built_line.split(": ", 1)[1]).resolve().parent
        else:
            self.out_dir = None

    @property
    def index(self) -> str:
        return (self.out_dir / "index.html").read_text(encoding="utf-8")

    @property
    def parsed(self) -> PageInspector:
        return parse_page(self.index)


OUTPUT = OutputBuild()


# ---------------------------------------------------------------------------
# Build behavior
# ---------------------------------------------------------------------------

class BuildBehaviorTests(unittest.TestCase):
    def test_build_succeeds_and_writes_files(self):
        self.assertEqual(0, OUTPUT.result.returncode, OUTPUT.result.stderr)
        self.assertTrue((OUTPUT.out_dir / "index.html").is_file())
        self.assertTrue((OUTPUT.out_dir / ".nojekyll").is_file())
        ics = list(OUTPUT.out_dir.glob("*.ics"))
        self.assertEqual(1, len(ics), "one fallback ICS file should be built")

    def test_check_mode_passes_on_sample_data(self):
        result = run_build("--check")
        self.assertEqual(0, result.returncode)
        self.assertIn("looks good", result.stdout)

    def test_check_mode_fails_on_invalid_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({"title": "No contact info"}), encoding="utf-8")
            result = run_build("--check", "--data", str(bad))
            self.assertNotEqual(0, result.returncode)
            self.assertIn("contact.email", result.stderr)

    def test_missing_title_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({"contact": {"email": "hi@example.com"}}), encoding="utf-8")
            result = run_build("--check", "--data", str(bad))
            self.assertNotEqual(0, result.returncode)
            self.assertIn("title", result.stderr)

    def test_unfilled_template_tokens_rejected(self):
        self.assertNotIn("{{", OUTPUT.index.split("</script>")[1])

    def test_no_secrets_or_personal_data_in_output(self):
        text = OUTPUT.index.lower()
        for forbidden in ("api_key", "apikey", "secret", "token", "gsk_", "sk-"):
            self.assertNotIn(forbidden, text)


# ---------------------------------------------------------------------------
# Rendered signup structure
# ---------------------------------------------------------------------------

class SignupStructureTests(unittest.TestCase):
    def test_header_and_aria_labels(self):
        page = OUTPUT.parsed
        self.assertTrue(page.tag_exists("html", lang="en"))
        self.assertTrue(page.tag_exists("a", class_="skip-link", href="#main"))
        self.assertTrue(page.tag_exists("main", id="main"))
        self.assertTrue(page.tag_exists("h1", class_="event-title"))

    def test_when_where_cards_render(self):
        page = OUTPUT.parsed
        self.assertTrue(page.tag_exists("section", id="event-cards"))
        self.assertTrue(page.tag_exists("ul", class_="card-list"))
        for heading in ("Date", "Time", "Location"):
            self.assertIn(f">{heading}<", OUTPUT.index, f"{heading} card missing")

    def test_rsvp_copy_button_present_and_wired(self):
        page = OUTPUT.parsed
        self.assertTrue(page.tag_exists("button", id="copy-rsvp"))
        self.assertTrue(page.tag_exists("button", class_="copy-btn"))
        self.assertIn('id="event-data"', OUTPUT.index)
        blob = json.loads(
            OUTPUT.index.split('<script type="application/json" id="event-data">')[1]
            .split("</script>")[0]
        )
        self.assertIn("Name:", blob["rsvp_text"])
        self.assertIn("Access needs", blob["rsvp_text"])

    def test_rsvp_email_link_only_uses_sample_placeholder_domain(self):
        page = OUTPUT.parsed
        mailtos = [href for href in page.hrefs if href.startswith("mailto:")]
        self.assertGreaterEqual(len(mailtos), 2, "RSVP + waiting-list email links expected")
        for href in mailtos:
            decoded = urllib.parse.unquote(href)
            self.assertIn("@asdale.example.com", decoded)
        self.assertIn("subject=RSVP", urllib.parse.unquote(mailtos[0]))

    def test_accessibility_notes_block(self):
        page = OUTPUT.parsed
        self.assertTrue(page.tag_exists("section", id="accessibility"))
        self.assertIn("accessibility-title", OUTPUT.index)
        self.assertIn('class="notes-list"', OUTPUT.index)

    def test_gallery_slots_render(self):
        page = OUTPUT.parsed
        self.assertTrue(page.tag_exists("section", id="gallery"))
        self.assertEqual(OUTPUT.index.count('<figure class="gallery-slot">'), 3)
        self.assertTrue(page.tag_exists("img", src="assets/placeholder.svg", alt="Placeholder gallery slot 1 — a photo of a full room at a past event goes here."))
        alts = [attrs.get("alt", "") for tag, attrs in page.tags if tag == "img"]
        self.assertEqual(len(alts), 3)
        self.assertTrue(all(alt.strip() for alt in alts), "every image needs alt text")

    def test_waiting_list_note(self):
        page = OUTPUT.parsed
        self.assertTrue(page.tag_exists("section", id="waiting-list"))
        self.assertIn("waiting list", OUTPUT.index.lower())

    def test_fallback_ics_download_link(self):
        page = OUTPUT.parsed
        ics_links = [h for h in page.hrefs if h.endswith(".ics")]
        self.assertTrue(ics_links, "a link to the .ics file must be on the page")

    def test_no_backend_no_external_requests(self):
        index = OUTPUT.index
        self.assertNotIn("googleapis.com", index)
        self.assertNotIn("cdn.", index.lower())
        self.assertNotIn("<form", index.lower())

    def test_styles_and_script_linked_from_assets(self):
        page = OUTPUT.parsed
        self.assertTrue(page.tag_exists("link", rel="stylesheet", href="assets/style.css"))
        for tag, attrs in page.tags:
            if tag == "script" and attrs.get("src"):
                self.assertEqual("assets/app.js", attrs["src"])


# ---------------------------------------------------------------------------
# ICS fallback file
# ---------------------------------------------------------------------------

class IcsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = OUTPUT.out_dir / "the-massive-ai-manual-launch-night.ics"
        cls.text = path.read_text(encoding="utf-8")
        cls.lines = cls.text.replace("\r\n", "\n").strip().split("\n")

    def test_valid_calendar_envelope(self):
        self.assertEqual("BEGIN:VCALENDAR", self.lines[0])
        self.assertEqual("END:VCALENDAR", self.lines[-1])
        self.assertIn("BEGIN:VEVENT", self.lines)
        self.assertIn("END:VEVENT", self.lines)
        self.assertIn("VERSION:2.0", self.lines)
        self.assertIn("PRODID:-//Asdale Dynamics, LLC//Event Signup Page Template//EN", self.lines)

    def test_event_fields(self):
        self.assertIn("DTSTART:20261205T230000Z", self.lines)
        self.assertIn("DTEND:20261206T010000Z", self.lines)
        self.assertIn("SUMMARY:The Massive AI Manual: Launch Night", self.lines)
        self.assertIn("STATUS:CONFIRMED", self.lines)
        self.assertTrue(any(line.startswith("UID:") for line in self.lines))
        self.assertTrue(any(line.startswith("LOCATION:") for line in self.lines))
        self.assertTrue(any(line.startswith("DESCRIPTION:") for line in self.lines))

    def test_ids_are_inline_pairs(self):
        begins = sum(1 for line in self.lines if line.startswith("BEGIN:"))
        ends = sum(1 for line in self.lines if line.startswith("END:"))
        self.assertEqual(begins, ends)


if __name__ == "__main__":
    unittest.main()
