"""
MusicBrainz Metadata Enricher — offline by default.

Network enrichment is ONLY performed when explicitly requested via --enrich flag.
Never called during normal run, inspect, or full-sync without the flag.

Rate-limits to 1 request/second per MusicBrainz API policy.
Maintains a local JSON cache at ~/.cache/music-agent/mb_cache.json.
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any

# requests is imported lazily inside methods to preserve offline-first behaviour:
# importing requests at module level would not cause network traffic, but this
# pattern makes the optional-network design explicit.


MUSICBRAINZ_API_BASE = "https://musicbrainz.org/ws/2"
COVERART_API_BASE = "https://coverartarchive.org"
USER_AGENT = "MusicLibraryAgent/4.0 ( https://github.com/aruntito/MUSIC )"
RATE_LIMIT_SECONDS = 1.1  # slightly above 1/s to stay safely within MusicBrainz policy


@dataclass
class EnrichedTrackInfo:
    """Enriched metadata returned by MusicBrainz lookup."""
    artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    year: Optional[str] = None
    genre: Optional[str] = None
    mbid_recording: Optional[str] = None   # recording MBID
    mbid_release: Optional[str] = None     # release (album) MBID — needed for Cover Art Archive
    artwork_url: Optional[str] = None      # resolved front cover URL if available
    source: str = "musicbrainz"
    confidence: float = 0.0               # 0.0–1.0 match confidence from MB score


class MusicBrainzEnricher:
    """
    Queries MusicBrainz to fill in missing track metadata (album, year, genre, MBID).
    All network I/O is gated behind explicit calls; no requests are made on import.
    """

    def __init__(self, cache_path: Optional[Path] = None):
        if cache_path is None:
            cache_path = Path.home() / ".cache" / "music-agent" / "mb_cache.json"
        self.cache_path = Path(cache_path)
        self._cache: Dict[str, Any] = {}
        self._last_request_time: float = 0.0
        self._load_cache()

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _load_cache(self) -> None:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._cache = {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except IOError:
            pass  # Cache save failure is non-fatal

    def _cache_key(self, artist: str, title: str) -> str:
        return f"{artist.lower().strip()}|{title.lower().strip()}"

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = time.time()

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _get(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make a GET request respecting rate limits and MusicBrainz User-Agent policy."""
        try:
            import requests  # noqa: PLC0415 — lazy import, network only when called
        except ImportError:
            return None

        self._rate_limit()
        try:
            resp = requests.get(
                url,
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code == 503:
                # MusicBrainz throttling — wait and retry once
                time.sleep(5)
                self._rate_limit()
                resp = requests.get(
                    url,
                    params=params,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                    timeout=10,
                )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # MusicBrainz recording lookup
    # ------------------------------------------------------------------

    def lookup(self, artist: str, title: str) -> Optional[EnrichedTrackInfo]:
        """
        Look up a track on MusicBrainz. Returns EnrichedTrackInfo or None.
        Checks local cache first; only makes a network request on cache miss.
        """
        if not artist or not title:
            return None

        key = self._cache_key(artist, title)
        if key in self._cache:
            cached = self._cache[key]
            if cached is None:
                return None  # Negative cache entry — known miss
            return EnrichedTrackInfo(**cached)

        # Network lookup
        query = f'artist:"{artist}" AND recording:"{title}"'
        data = self._get(
            f"{MUSICBRAINZ_API_BASE}/recording",
            params={"query": query, "fmt": "json", "limit": 5, "inc": "releases+tags"},
        )

        result = self._parse_recording_response(data, artist, title)

        # Cache the result (None → negative cache)
        if result is not None:
            self._cache[key] = {
                "artist": result.artist,
                "title": result.title,
                "album": result.album,
                "year": result.year,
                "genre": result.genre,
                "mbid_recording": result.mbid_recording,
                "mbid_release": result.mbid_release,
                "artwork_url": result.artwork_url,
                "source": result.source,
                "confidence": result.confidence,
            }
        else:
            self._cache[key] = None

        self._save_cache()
        return result

    def _parse_recording_response(
        self, data: Optional[dict], query_artist: str, query_title: str
    ) -> Optional[EnrichedTrackInfo]:
        if not data or "recordings" not in data:
            return None
        recordings = data.get("recordings", [])
        if not recordings:
            return None

        # Take the highest-scoring result
        best = recordings[0]
        score = int(best.get("score", 0))
        confidence = score / 100.0

        mb_title = best.get("title", "")
        mb_artist = ""
        artist_credits = best.get("artist-credit", [])
        if artist_credits and isinstance(artist_credits, list):
            mb_artist = artist_credits[0].get("name", "") if isinstance(artist_credits[0], dict) else ""

        # Extract album + year from the first release
        album = None
        year = None
        mbid_release = None
        releases = best.get("releases", [])
        if releases:
            rel = releases[0]
            album = rel.get("title")
            mbid_release = rel.get("id")
            date_str = rel.get("date", "")
            if date_str:
                year = str(date_str)[:4]

        # Extract tags/genres
        genre = None
        tags = best.get("tags", [])
        if tags and isinstance(tags, list):
            # MusicBrainz tags sorted by vote count — take highest
            tags_sorted = sorted(tags, key=lambda t: t.get("count", 0), reverse=True)
            genre = tags_sorted[0].get("name") if tags_sorted else None

        return EnrichedTrackInfo(
            artist=mb_artist or query_artist,
            title=mb_title or query_title,
            album=album,
            year=year,
            genre=genre,
            mbid_recording=best.get("id"),
            mbid_release=mbid_release,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Cover Art Archive artwork URL
    # ------------------------------------------------------------------

    def get_artwork_url(self, mbid_release: str) -> Optional[str]:
        """
        Return the front cover URL for a release MBID from Cover Art Archive.
        Returns the resolved direct image URL, or None if no artwork is found.
        """
        if not mbid_release:
            return None

        art_key = f"artwork:{mbid_release}"
        if art_key in self._cache:
            return self._cache[art_key]  # May be None (negative cache)

        data = self._get(f"{COVERART_API_BASE}/release/{mbid_release}/front-250")
        # CAA returns a redirect to the actual image; requests follows it automatically.
        # If we reached here and got a 200 with image bytes, the URL is the final URL.
        # Instead just build the direct thumbnail URL and verify it exists.
        try:
            import requests  # noqa: PLC0415
            self._rate_limit()
            url = f"{COVERART_API_BASE}/release/{mbid_release}/front-500"
            resp = requests.head(
                url,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
                timeout=8,
            )
            final_url = resp.url if resp.status_code == 200 else None
        except Exception:
            final_url = None

        self._cache[art_key] = final_url
        self._save_cache()
        return final_url
