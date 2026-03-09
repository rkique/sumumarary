import os
import re
import csv
import time
import requests
from urllib.parse import unquote, urlparse

PHOTOS_DIR = "photos"
STATES_CSV = "us_states.csv"
API_URL = "https://en.wikipedia.org/w/api.php"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "SummaryGameBot/1.0 (US state flag fetcher; educational project)"
})


def log(message: str):
    print(message)


def slugify_filename(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def title_from_url(url: str) -> str:
    path = urlparse(url).path
    title = path.rsplit("/", 1)[-1]
    return unquote(title).replace("_", " ")


def fetch_flag_image_filename(page_title: str) -> str | None:
    """Use the Wikipedia API to find the flag image from a state's infobox."""
    resp = SESSION.get(API_URL, params={
        "action": "parse",
        "page": page_title,
        "prop": "images",
        "format": "json",
    }, timeout=30)
    resp.raise_for_status()
    images = resp.json().get("parse", {}).get("images", [])

    # Look for an image with "flag" in its name
    for img in images:
        if "flag" in img.lower() and img.lower().endswith((".svg", ".png")):
            return img

    return None


def get_image_url(filename: str) -> str | None:
    """Get the actual file URL from a Wikipedia/Commons filename."""
    resp = SESSION.get(API_URL, params={
        "action": "query",
        "titles": f"File:{filename}",
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
    }, timeout=30)
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    for page in pages.values():
        info = page.get("imageinfo", [])
        if info:
            return info[0].get("url")
    return None


def download_image(url: str, output_path: str):
    resp = SESSION.get(url, timeout=200)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(resp.content)


def read_states(csv_path: str) -> list[dict[str, str]]:
    states = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            states.append(row)
    return states


def fetch_all_flags():
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    log(f"Saving flags to: {PHOTOS_DIR}")

    states = read_states(STATES_CSV)
    for index, row in enumerate(states, start=1):
        state = str(row.get("state", "")).strip()
        wiki_url = str(row.get("url", "")).strip()
        wiki_state = str(row.get("wiki_state", "")).strip()
        label = state or wiki_state or f"row {index}"

        page_title = title_from_url(wiki_url) if wiki_url else (wiki_state or state)

        # Check if we already have a flag for this state
        slug = slugify_filename(wiki_state or state)
        existing = [f for f in os.listdir(PHOTOS_DIR) if f.startswith(slug + ".")]
        if existing:
            log(f"[{index}] Skipping {label} (already exists)")
            continue

        log(f"[{index}] Fetching flag for {label}")

        try:
            flag_filename = fetch_flag_image_filename(page_title)
            if not flag_filename:
                log(f"  X No flag image found for {label}")
                continue

            image_url = get_image_url(flag_filename)
            if not image_url:
                log(f"  X Could not resolve URL for {flag_filename}")
                continue

            ext = os.path.splitext(flag_filename)[1].lower()
            output_path = os.path.join(PHOTOS_DIR, f"{slug}{ext}")

            download_image(image_url, output_path)
            log(f"  OK saved {slug}{ext}")

        except requests.RequestException as e:
            log(f"  X Request failed for {label}: {e}")

        time.sleep(3)


if __name__ == "__main__":
    fetch_all_flags()
