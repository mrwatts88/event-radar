from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup


LOGGER = logging.getLogger(__name__)
USER_AGENT = "event-radar/0.1"


class FetchError(RuntimeError):
    """Raised when fetching a source fails after retry."""


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_html(session: requests.Session, url: str, timeout_seconds: int) -> str:
    last_error: Exception | None = None
    for attempt in range(1, 3):
        try:
            response = session.get(url, timeout=timeout_seconds)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 2:
                break
            LOGGER.warning("Retrying fetch for %s after error: %s", url, exc)
    raise FetchError(f"failed to fetch {url}: {last_error}")


def extract_visible_text(html: str, max_chars: int) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in ("script", "style", "noscript"):
        for tag in soup.find_all(tag_name):
            tag.decompose()

    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip()
    return text
