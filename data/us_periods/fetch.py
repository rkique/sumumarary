import os
import re
import csv
import time
import requests
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

TEXT_OUTPUT_DIR = "text_summaries"
PERIODS_CSV = "us_periods.csv"
API_URL = "https://en.wikipedia.org/w/api.php"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "SummaryGameBot/1.0 (US periods fetcher; educational project)"
})

# Sections to skip (not useful for period summaries)
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


REQUEST_DELAY = 0.5          # seconds between API calls
MAX_RETRIES = 5
INITIAL_BACKOFF = 5          # seconds for first 429 retry

def api_get(params: dict) -> dict:
    """Rate-limited API call with retry/backoff for 429s."""
    time.sleep(REQUEST_DELAY)
    for attempt in range(MAX_RETRIES):
        resp = SESSION.get(API_URL, params=params, timeout=30)
        if resp.status_code == 429:
            wait = INITIAL_BACKOFF * (2 ** attempt)
            log(f"  ~ Rate limited, waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()  # raise on final failure
    return {}


def get_sections(title: str) -> list[dict]:
    """Get all sections for a page."""
    data = api_get({
        "action": "parse",
        "page": title,
        "prop": "sections",
        "format": "json",
    })
    return data.get("parse", {}).get("sections", [])


def fetch_section_html(title: str, section_index: str) -> str | None:
    """Fetch the HTML of a specific section."""
    data = api_get({
        "action": "parse",
        "page": title,
        "section": section_index,
        "prop": "text",
        "disabletoc": True,
        "format": "json",
    })
    return data.get("parse", {}).get("text", {}).get("*")


def fetch_period_text(period: str, wiki_url: str, wiki_period: str) -> str | None:
    """Fetch the full article text for a US historical period."""
    titles_to_try = []

    if wiki_url:
        titles_to_try.append(title_from_url(wiki_url))
    if wiki_period and wiki_period not in titles_to_try:
        titles_to_try.append(wiki_period.strip())
    if period.strip() and period.strip() not in titles_to_try:
        titles_to_try.append(period.strip())

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
                if section.get("level") != "2":
                    continue
                sec_html = fetch_section_html(title, section["index"])
                if sec_html:
                    sec_text = html_to_text(sec_html)
                    if sec_text:
                        parts.append(sec_text)

            if parts:
                full_text = "\n\n".join(parts)
                log(f"  OK Text from '{title}' ({len(full_text)} chars)")
                return full_text
        except requests.RequestException as e:
            log(f"  ! Request failed for '{title}': {e}")
            continue

    log("  X Could not extract article text")
    return None


def read_periods(csv_path: str) -> list[dict[str, str]]:
    periods = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            periods.append(row)
    return periods


def write_period_texts():
    os.makedirs(TEXT_OUTPUT_DIR, exist_ok=True)
    log(f"Writing period texts to: {TEXT_OUTPUT_DIR}")

    periods = read_periods(PERIODS_CSV)
    for index, row in enumerate(periods, start=1):
        period = str(row.get("period", "")).strip()
        wiki_url = str(row.get("url", "")).strip()
        wiki_period = str(row.get("wiki_period", "")).strip()
        label = period or wiki_period or f"row {index}"

        output_name = f"{slugify_filename(wiki_period or period)}.txt"
        output_path = os.path.join(TEXT_OUTPUT_DIR, output_name)

        if os.path.exists(output_path):
            log(f"[{index}] Skipping {label} (already exists)")
            continue

        log(f"\n[{index}] Processing {label}")
        period_text = fetch_period_text(period, wiki_url, wiki_period)
        if not period_text:
            log(f"X {index}: {label} (no content)")
            continue

        # Remove citation lines (start with ^)
        period_text = "\n".join(
            line for line in period_text.splitlines() if not line.startswith("^")
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(period_text)

        log(f"OK {index}: wrote {output_name} ({len(period_text)} chars)")


if __name__ == "__main__":
    write_period_texts()
