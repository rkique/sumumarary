import os
import re
import csv
import requests
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

TEXT_OUTPUT_DIR = "text_summaries"
CITIES_CSV = "city_titles.csv"
API_URL = "https://en.wikipedia.org/w/api.php"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "SummaryGameBot/1.0 (city history fetcher; educational project)"
})


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


def find_history_section_index(title: str) -> str | None:
    """Find the section index of the == History == heading."""
    resp = SESSION.get(API_URL, params={
        "action": "parse",
        "page": title,
        "prop": "sections",
        "format": "json",
    }, timeout=30)
    resp.raise_for_status()
    sections = resp.json().get("parse", {}).get("sections", [])
    for section in sections:
        if section.get("line", "").strip().lower() == "history" and section.get("level") == "2":
            return section["index"]
    return None


def fetch_history_html(title: str, section_index: str) -> str | None:
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


def fetch_city_history(city: str, wiki_url: str, wiki_city: str) -> str | None:
    """Try to fetch the History section for a city, with fallbacks."""
    titles_to_try = []

    if wiki_url:
        titles_to_try.append(title_from_url(wiki_url))
    if wiki_city and wiki_city not in titles_to_try:
        titles_to_try.append(wiki_city.strip())
    if city.strip() and city.strip() not in titles_to_try:
        titles_to_try.append(city.strip())

    for title in titles_to_try:
        if not title:
            continue
        log(f"  -> Trying: {title}")
        try:
            idx = find_history_section_index(title)
            if idx is None:
                log(f"  ! No History section in '{title}'")
                continue
            html = fetch_history_html(title, idx)
            if not html:
                log(f"  ! Empty History section in '{title}'")
                continue
            text = html_to_text(html)
            if text:
                log(f"  OK History from '{title}' ({len(text)} chars)")
                return text
        except requests.RequestException as e:
            log(f"  ! Request failed for '{title}': {e}")
            continue

    log("  X Could not extract History section")
    return None


def read_cities(csv_path: str) -> list[dict[str, str]]:
    cities = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cities.append(row)
    return cities


def write_city_histories():
    os.makedirs(TEXT_OUTPUT_DIR, exist_ok=True)
    log(f"Writing histories to: {TEXT_OUTPUT_DIR}")

    cities = read_cities(CITIES_CSV)
    for index, row in enumerate(cities, start=1):
        city = str(row.get("city", "")).strip()
        wiki_url = str(row.get("url", "")).strip()
        wiki_city = str(row.get("wiki_city", "")).strip()
        label = city or wiki_city or f"row {index}"

        output_name = f"{slugify_filename(wiki_city or city)}.txt"
        output_path = os.path.join(TEXT_OUTPUT_DIR, output_name)

        if os.path.exists(output_path):
            log(f"[{index}] Skipping {label} (already exists)")
            continue

        log(f"\n[{index}] Processing {label}")
        history_text = fetch_city_history(city, wiki_url, wiki_city)
        if not history_text:
            log(f"X {index}: {label} (no content)")
            continue

        # Remove citation lines (start with ^)
        history_text = "\n".join(
            line for line in history_text.splitlines() if not line.startswith("^")
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(history_text)

        log(f"OK {index}: wrote {output_name} ({len(history_text)} chars)")


if __name__ == "__main__":
    write_city_histories()
