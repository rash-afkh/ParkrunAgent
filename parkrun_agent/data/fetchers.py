"""Network fetchers — the ONLY code allowed to touch the parkrun network.

Kept behind small functions so tests inject fakes and never hit the network.
Polite by design: a realistic User-Agent, a timeout, and a couple of retries
with backoff. This tool is personal-use only (see DESIGN.md §3).
"""

from __future__ import annotations

import time

import requests

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 ParkrunAgent/0.1 (personal use)"
)
EVENTS_JSON_URL = "https://images.parkrun.com/events.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# The full-history page. Note: the older /results/athleteresultshistory/ endpoint
# now returns only a 10-row summary; /parkrunner/<id>/all/ returns every result
# and works from any country domain regardless of the athlete's home country.
PARKRUN_DEFAULT_DOMAIN = "www.parkrun.org.uk"
ATHLETE_HISTORY_URL_TEMPLATE = "https://{domain}/parkrunner/{athlete_number}/all/"

DEFAULT_TIMEOUT = 20


def _get(url: str, *, params: dict | None = None, headers: dict | None = None,
         retries: int = 3, backoff: float = 2.0) -> requests.Response:
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=DEFAULT_TIMEOUT)
            if resp.status_code in (429, 500, 502, 503, 504):
                resp.raise_for_status()
            return resp
        except requests.RequestException as exc:  # noqa: PERF203
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def fetch_events_json(etag: str | None = None) -> tuple[dict | None, str | None, bool]:
    """Return (data, new_etag, not_modified).

    Sends If-None-Match so an unchanged catalogue costs a cheap 304.
    """
    headers = {"If-None-Match": etag} if etag else None
    resp = _get(EVENTS_JSON_URL, headers=headers)
    if resp.status_code == 304:
        return None, etag, True
    resp.raise_for_status()
    return resp.json(), resp.headers.get("ETag"), False


def fetch_athlete_history_html(athlete_number: int, domain: str = PARKRUN_DEFAULT_DOMAIN) -> str:
    url = ATHLETE_HISTORY_URL_TEMPLATE.format(domain=domain, athlete_number=athlete_number)
    resp = _get(url)
    resp.raise_for_status()
    return resp.text


def fetch_geocode(query: str) -> dict | None:
    """Geocode a place name via OpenStreetMap Nominatim. Returns the top hit as
    {lat, lon, display_name}, or None. Free, no API key; low-volume personal use."""
    resp = _get(NOMINATIM_URL, params={"q": query, "format": "json", "limit": 1})
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return None
    top = data[0]
    return {"lat": float(top["lat"]), "lon": float(top["lon"]), "display_name": top.get("display_name")}
