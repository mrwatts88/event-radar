from __future__ import annotations

import requests

from event_radar.fetch import FetchError, extract_visible_text, fetch_html


class DummyResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")


class DummySession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def get(self, url: str, timeout: int):
        self.calls += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_fetch_html_retries_once_on_failure():
    session = DummySession(
        [requests.Timeout("boom"), DummyResponse("<html><body>ok</body></html>")]
    )

    html = fetch_html(session, "https://example.com", timeout_seconds=10)

    assert html == "<html><body>ok</body></html>"
    assert session.calls == 2


def test_fetch_html_raises_after_second_failure():
    session = DummySession([requests.Timeout("boom"), requests.Timeout("boom again")])

    try:
        fetch_html(session, "https://example.com", timeout_seconds=10)
    except FetchError as exc:
        assert "failed to fetch" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected fetch failure")


def test_extract_visible_text_strips_non_visible_content_and_truncates():
    html = """
<html>
  <head>
    <style>.hidden { display: none; }</style>
    <script>console.log("noise")</script>
  </head>
  <body>
    <noscript>fallback</noscript>
    <p>Visible text</p>
    <p>More visible text</p>
  </body>
</html>
"""
    text = extract_visible_text(html, max_chars=12)
    assert text == "Visible text"
