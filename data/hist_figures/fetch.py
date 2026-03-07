import os
import re
import csv
import requests
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

TEXT_OUTPUT_DIR = "text_summaries"
FIGURES_CSV = "hist_figures_titles.csv"
API_URL = "https://en.wikipedia.org/w/api.php"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "SummaryGameBot/1.0 (historical figures fetcher; educational project)"
})

# Sections to skip (not useful for biographical summaries)
SKIP_SECTIONS = {
    "see also", "references", "external links", "notes", "further reading",
    "bibliography", "citations", "sources", "footnotes",
}


def log(message: str):
    print(message)


def slugify_filename(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def title_from_url(url: str) -> str:
    """Extract the Wikipedia page title from a URL."""
    path = urlparse(url).path
    title = path.rsplit("/", 1)[-1]
    return unquote(title).replace("_", " ")


def _strip_citation_html(html: str) -> str:
    """Remove citation/reference markup from HTML before text extraction."""
    html = re.sub(r"<sup[^>]*>.*?</sup>", "", html, flags=re.DOTALL)
    html = re.sub(r'<ol\b[^>]*class="[^"]*references[^"]*"[^>]*>.*?</ol>', "", html, flags=re.DOTALL)
    html = re.sub(r'<div\b[^>]*class="[^"]*reflist[^"]*"[^>]*>.*?</div>', "", html, flags=re.DOTALL)
    html = re.sub(r'<div\b[^>]*class="[^"]*refbegin[^"]*"[^>]*>.*?</div>', "", html, flags=re.DOTALL)
    html = re.sub(r'<div\b[^>]*class="[^"]*mw-references[^"]*"[^>]*>.*?</div>', "", html, flags=re.DOTALL)
    html = re.sub(r"<cite[^>]*>.*?</cite>", "", html, flags=re.DOTALL)
    html = re.sub(r"<table[^>]*>.*?</table>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r'<div\b[^>]*class="[^"]*navbox[^"]*"[^>]*>.*?</div>', "", html, flags=re.DOTALL)
    return html


class _HTMLStripper(HTMLParser):
    """Simple HTML-to-text converter (feed pre-cleaned HTML)."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "li", "h3", "h4"):
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "p":
            self._parts.append("\n")

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self) -> str:
        text = "".join(self._parts)
        text = re.sub(r"\[\d+\]", "", text)
        text = re.sub(r"\[citation needed\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[edit\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[note \d+\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r" {2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(html: str) -> str:
    cleaned = _strip_citation_html(html)
    stripper = _HTMLStripper()
    stripper.feed(cleaned)
    return stripper.get_text()


def get_sections(title: str) -> list[dict]:
    """Get all sections for a page."""
    resp = SESSION.get(API_URL, params={
        "action": "parse",
        "page": title,
        "prop": "sections",
        "format": "json",
    }, timeout=30)
    resp.raise_for_status()
    return resp.json().get("parse", {}).get("sections", [])


def fetch_section_html(title: str, section_index: str) -> str | None:
    """Fetch the HTML of a specific section."""
    resp = SESSION.get(API_URL, params={
        "action": "parse",
        "page": title,
        "section": section_index,
        "prop": "text",
        "disabletoc": True,
        "format": "json",
    }, timeout=30)
    resp.raise_for_status()
    return resp.json().get("parse", {}).get("text", {}).get("*")


def fetch_figure_bio(person: str, wiki_url: str, wiki_person: str) -> str | None:
    """Fetch the full biographical text for a historical figure."""
    titles_to_try = []

    if wiki_url:
        titles_to_try.append(title_from_url(wiki_url))
    if wiki_person and wiki_person not in titles_to_try:
        titles_to_try.append(wiki_person.strip())
    if person.strip() and person.strip() not in titles_to_try:
        titles_to_try.append(person.strip())

    for title in titles_to_try:
        if not title:
            continue
        log(f"  -> Trying: {title}")
        try:
            # Fetch the lead section (index 0)
            lead_html = fetch_section_html(title, "0")
            parts = []
            if lead_html:
                lead_text = html_to_text(lead_html)
                if lead_text:
                    parts.append(lead_text)

            # Fetch all non-skipped top-level sections
            sections = get_sections(title)
            for section in sections:
                heading = section.get("line", "").strip().lower()
                if heading in SKIP_SECTIONS:
                    continue
                # Only include top-level (level 2) sections and their content
                if section.get("level") != "2":
                    continue
                sec_html = fetch_section_html(title, section["index"])
                if sec_html:
                    sec_text = html_to_text(sec_html)
                    if sec_text:
                        parts.append(sec_text)

            if parts:
                full_text = "\n\n".join(parts)
                log(f"  OK Bio from '{title}' ({len(full_text)} chars)")
                return full_text
        except requests.RequestException as e:
            log(f"  ! Request failed for '{title}': {e}")
            continue

    log("  X Could not extract biography")
    return None


def read_figures(csv_path: str) -> list[dict[str, str]]:
    figures = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            figures.append(row)
    return figures


def write_figure_bios():
    os.makedirs(TEXT_OUTPUT_DIR, exist_ok=True)
    log(f"Writing biographies to: {TEXT_OUTPUT_DIR}")

    figures = read_figures(FIGURES_CSV)
    for index, row in enumerate(figures, start=1):
        person = str(row.get("person", "")).strip()
        wiki_url = str(row.get("url", "")).strip()
        wiki_person = str(row.get("wiki_person", "")).strip()
        label = person or wiki_person or f"row {index}"

        output_name = f"{slugify_filename(wiki_person or person)}.txt"
        output_path = os.path.join(TEXT_OUTPUT_DIR, output_name)

        if os.path.exists(output_path):
            log(f"[{index}] Skipping {label} (already exists)")
            continue

        log(f"\n[{index}] Processing {label}")
        bio_text = fetch_figure_bio(person, wiki_url, wiki_person)
        if not bio_text:
            log(f"X {index}: {label} (no content)")
            continue

        # Remove citation lines (start with ^)
        bio_text = "\n".join(
            line for line in bio_text.splitlines() if not line.startswith("^")
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(bio_text)

        log(f"OK {index}: wrote {output_name} ({len(bio_text)} chars)")


if __name__ == "__main__":
    write_figure_bios()
